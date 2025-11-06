# wa_gui.py
# GUI para broadcast via WhatsApp Web (abrir chat, colar e enviar — sem opções de tempo na UI)
# Correções:
# - Atraso de estabilização após abrir o WA Web e no primeiro chat
# - Detecção híbrida de envio: contagem de message-out OU mudança de assinatura do último balão + composer vazio
# - Retry sem duplicar: não repasta se o composer já ficou vazio; limpa/repasta somente quando necessário
# - Um único método de disparo por tentativa (botão -> ENTER -> CTRL+ENTER)
# - Evita reabrir o mesmo chat duas vezes no mesmo ciclo

import csv
import os
import platform
import random
import threading
import time
from datetime import datetime
from typing import Callable
from tkinter import (
    Tk, Label, Entry, Button, StringVar, filedialog, Text, END, DISABLED, NORMAL,
    Frame
)
from tkinter.scrolledtext import ScrolledText

from tkinter import font as tkfont
from html.parser import HTMLParser
import ctypes
from ctypes import wintypes

import pyperclip
from selenium import webdriver
from selenium.common.exceptions import TimeoutException, NoSuchElementException
from selenium.webdriver import ChromeOptions
from selenium.webdriver.chrome.service import Service as ChromeService
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.ui import WebDriverWait
from webdriver_manager.chrome import ChromeDriverManager

# ---------------------------
# CONSTANTES (sem sliders na UI)
# ---------------------------
GLOBAL_INITIAL_STABILIZATION = 6.0  # espera única após carregar WA Web
FIRST_CHAT_STABILIZATION = 2.8      # espera extra ao abrir o primeiro chat
TIMEOUT_CHAT = 25                   # timeout para abrir chat / encontrar composer
WAIT_UI_READY = 60                  # timeout para esperar WhatsApp Web carregar inicialmente
MIN_DELAY_BETWEEN = 2.0             # pausa mínima entre contatos
MAX_DELAY_BETWEEN = 6.0             # pausa máxima entre contatos
MIN_WAIT_BEFORE_PASTE = 1.2         # espera mínima antes de colar (chat já aberto)
MAX_WAIT_BEFORE_PASTE = 3.5         # espera máxima antes de colar
RETRIES_PER_CONTACT = 2             # tentativas extras de envio por contato
POST_SEND_CHECK_TIMEOUT = 9.0       # tempo máximo esperando DOM refletir envio
POST_SEND_POLL_INTERVAL = 0.35

# Seletores (WhatsApp Web muda DOM; se quebrar, ajuste aqui)
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
DEFAULT_PROFILE_DIR = os.path.join(SCRIPT_DIR, "wa_profile")

MAIN_UI_READY_SELECTORS = [
    "[data-testid='chat-list-search']",
    "div[role='grid']",
]
SEARCH_INPUT_SELECTOR = "[data-testid='chat-list-search']"
SEARCH_RESULT_ITEMS = [
    "div[role='listitem']",
    "[data-testid='cell-frame-container']",
]
MESSAGE_BOX_SELECTORS = [
    "footer div[contenteditable='true'][data-tab='10']",
    "footer div[contenteditable='true'][data-tab='6']",
    "footer div[contenteditable='true']",
    "div[contenteditable='true']",
]
SEND_BUTTON_SELECTORS = [
    "[data-testid='compose-btn-send']",
    "button[aria-label='Enviar']",
    "span[data-icon='send']",
]
INVALID_SNIPPETS = [
    "número de telefone compartilhado via url é inválido",
    "phone number shared via url is invalid",
    "número de telefone não é válido",
    "não está no whatsapp",
    "invalid phone",
]
OUTGOING_BUBBLE_SELECTORS = [
    "div.message-out",
    "div[data-testid='msg-container'][data-arg1='out']",
    "div[data-testid='msg-balloon'][class*='message-out']"
]

# ---------------------------
# Utilitários
# ---------------------------
def e164_br(telefone_br: str) -> str:
    digits = "".join([c for c in telefone_br if c.isdigit()])
    if not digits:
        return ""
    return digits if digits.startswith("55") else "55" + digits

def read_contacts_from_csv(path: str) -> list[dict]:
    contacts = []
    with open(path, "r", encoding="utf-8", newline="") as f:
        raw = f.read()
        try:
            sniffer = csv.Sniffer()
            dialect = sniffer.sniff(raw, delimiters=",;\t")
            f.seek(0)
            reader = csv.DictReader(f, dialect=dialect)
        except Exception:
            f.seek(0)
            reader = csv.DictReader(f)
        for row in reader:
            tel = (row.get("telefone") or row.get("numero") or "").strip()
            nome = (row.get("nome") or "").strip()
            if tel:
                contacts.append({"telefone": tel, "nome": nome})
    return contacts

def build_driver(profile_dir: str | None):
    opts = ChromeOptions()
    if profile_dir:
        persistent_dir = os.path.abspath(profile_dir)
        os.makedirs(persistent_dir, exist_ok=True)
        opts.add_argument(f"--user-data-dir={persistent_dir}")
        opts.add_argument("--profile-directory=Default")  # garante subpasta previsível
    opts.add_argument("--disable-blink-features=AutomationControlled")
    opts.add_argument("--start-maximized")
    service = ChromeService(ChromeDriverManager().install())
    driver = webdriver.Chrome(service=service, options=opts)
    return driver

def wait_main_ui_ready(driver):
    last_err = None
    for sel in MAIN_UI_READY_SELECTORS:
        try:
            WebDriverWait(driver, WAIT_UI_READY).until(
                EC.presence_of_element_located((By.CSS_SELECTOR, sel))
            )
            return
        except Exception as e:
            last_err = e
    if last_err:
        raise last_err

def find_message_box(driver, timeout: int):
    deadline = time.time() + timeout
    while time.time() < deadline:
        for sel in MESSAGE_BOX_SELECTORS:
            try:
                els = driver.find_elements(By.CSS_SELECTOR, sel)
                for el in reversed(els):
                    if el.is_displayed() and el.is_enabled():
                        return el
            except Exception:
                pass
        time.sleep(0.15)
    return None

def find_send_button(driver):
    for sel in SEND_BUTTON_SELECTORS:
        try:
            el = driver.find_element(By.CSS_SELECTOR, sel)
            if el.is_displayed() and el.is_enabled():
                return el
        except NoSuchElementException:
            continue
    return None

def page_has_invalid_number(driver) -> bool:
    try:
        src = driver.page_source.lower()
        return any(s in src for s in INVALID_SNIPPETS)
    except Exception:
        return False

def get_outgoing_count(driver) -> int:
    total = 0
    for sel in OUTGOING_BUBBLE_SELECTORS:
        try:
            total = max(total, len(driver.find_elements(By.CSS_SELECTOR, sel)))
        except Exception:
            pass
    return total

def get_last_outgoing_signature(driver) -> str:
    """
    Retorna uma 'assinatura' (hash simples por texto truncado) do último balão de saída.
    Usado para detectar mudança sem depender apenas da contagem.
    """
    candidates = []
    for sel in OUTGOING_BUBBLE_SELECTORS:
        try:
            elements = driver.find_elements(By.CSS_SELECTOR, sel)
            if elements:
                candidates.extend(elements)
        except Exception:
            pass
    if not candidates:
        return ""
    last = candidates[-1]
    try:
        txt = (last.text or "").strip()
        # Normaliza espaços e limita tamanho
        txt_norm = " ".join(txt.split())
        return txt_norm[:80]  # assinatura curta
    except Exception:
        return ""

def composer_text(el) -> str:
    try:
        return (el.text or "").strip()
    except Exception:
        return ""

def clear_composer(el):
    try:
        if platform.system() == "Darwin":
            el.send_keys(Keys.COMMAND, "a")
        else:
            el.send_keys(Keys.CONTROL, "a")
        el.send_keys(Keys.DELETE)
    except Exception:
        pass

def paste_text(el, texto: str):
    pyperclip.copy(texto)
    try:
        el.click()
    except Exception:
        pass
    if platform.system() == "Darwin":
        el.send_keys(Keys.COMMAND, "v")
    else:
        el.send_keys(Keys.CONTROL, "v")

def try_send_once(driver, message_box) -> tuple[bool, str]:
    # Dispara apenas UM método por tentativa
    btn = find_send_button(driver)
    if btn:
        try:
            btn.click()
            return True, "click_send_ok"
        except Exception:
            pass
    try:
        message_box.send_keys(Keys.ENTER)
        return True, "enter_ok"
    except Exception:
        pass
    try:
        if platform.system() == "Darwin":
            message_box.send_keys(Keys.COMMAND, Keys.ENTER)
        else:
            message_box.send_keys(Keys.CONTROL, Keys.ENTER)
        return True, "ctrl_enter_ok"
    except Exception:
        pass
    return False, "nao_enviado"

def wait_sent_hybrid(driver, before_count: int, before_sig: str, message_box) -> bool:
    """
    Sucesso se:
      - contagem de message-out aumentou, OU
      - composer está vazio E assinatura do último balão mudou
    """
    deadline = time.time() + POST_SEND_CHECK_TIMEOUT
    while time.time() < deadline:
        after = get_outgoing_count(driver)
        if after >= before_count + 1:
            return True
        # checa composer vazio
        try:
            txt_now = composer_text(message_box)
        except Exception:
            txt_now = ""
        if txt_now == "":
            sig_now = get_last_outgoing_signature(driver)
            if before_sig != "" and sig_now != "" and sig_now != before_sig:
                return True
        time.sleep(POST_SEND_POLL_INTERVAL)
    return False

def open_chat_via_search(driver, phone_e164: str, timeout: int) -> bool:
    try:
        search = WebDriverWait(driver, 10).until(
            EC.presence_of_element_located((By.CSS_SELECTOR, SEARCH_INPUT_SELECTOR))
        )
    except TimeoutException:
        return False
    try:
        search.click()
        if platform.system() == "Darwin":
            search.send_keys(Keys.COMMAND, "a")
        else:
            search.send_keys(Keys.CONTROL, "a")
        search.send_keys(Keys.DELETE)
    except Exception:
        pass

    variants = [phone_e164, "+" + phone_e164, phone_e164[2:]]

    for query in variants:
        pyperclip.copy(query)
        if platform.system() == "Darwin":
            search.send_keys(Keys.COMMAND, "v")
        else:
            search.send_keys(Keys.CONTROL, "v")

        found_item = None
        t0 = time.time()
        while time.time() - t0 < timeout:
            for sel in SEARCH_RESULT_ITEMS:
                items = driver.find_elements(By.CSS_SELECTOR, sel)
                if items:
                    found_item = items[0]
                    break
            if found_item:
                break
            time.sleep(0.2)

        if found_item:
            try:
                found_item.click()
                mb = find_message_box(driver, timeout=10)
                if mb:
                    return True
            except Exception:
                pass

        try:
            if platform.system() == "Darwin":
                search.send_keys(Keys.COMMAND, "a")
            else:
                search.send_keys(Keys.CONTROL, "a")
            search.send_keys(Keys.DELETE)
        except Exception:
            pass

    return False

def open_chat_via_link(driver, phone_e164: str, timeout: int) -> bool:
    url = f"https://web.whatsapp.com/send?phone={phone_e164}&app_absent=0"
    driver.get(url)
    t0 = time.time()
    while time.time() - t0 < timeout:
        if page_has_invalid_number(driver):
            return False
        mb = find_message_box(driver, timeout=1)
        if mb:
            return True
        time.sleep(0.25)
    return False

# ---------------------------
# GUI
# ---------------------------
class App:
    msg_box: Text
    btn_start: Button
    log_box: ScrolledText

    def __init__(self, master: Tk):
        self.master = master
        master.title("WA Chatbot — Disparo via WhatsApp Web")

        self.csv_path = StringVar()
        self.profile_dir = StringVar(value=DEFAULT_PROFILE_DIR)
        self.first_chat_done = False

        # Linha: CSV
        row = 0
        Label(master, text="Arquivo CSV (telefone,nome):").grid(row=row, column=0, sticky="w", padx=6, pady=4)
        frame_csv = Frame(master)
        frame_csv.grid(row=row, column=1, sticky="we", padx=6, pady=4)
        self.entry_csv = Entry(frame_csv, textvariable=self.csv_path, width=52)
        self.entry_csv.pack(side="left", fill="x", expand=True)
        Button(frame_csv, text="Escolher...", command=self.pick_csv).pack(side="left", padx=4)
        row += 1

        # Linha: Perfil (opcional)
        Label(master, text="Perfil do Chrome (mantém login) - padrão: wa_profile").grid(row=row, column=0, sticky="w", padx=6, pady=4)
        frame_prof = Frame(master)
        frame_prof.grid(row=row, column=1, sticky="we", padx=6, pady=4)
        self.entry_prof = Entry(frame_prof, textvariable=self.profile_dir, width=52)
        self.entry_prof.pack(side="left", fill="x", expand=True)
        Button(frame_prof, text="Pasta...", command=self.pick_profile).pack(side="left", padx=4)
        row += 1

        # Mensagem (editor com formatação visível)
        Label(master, text="Mensagem (suporta *negrito*, _itálico_, ~tachado~, `mono`, emojis):").grid(row=row, column=0, sticky="nw", padx=6, pady=4)
        self._build_rich_editor(master, grid_row=row)
        row += 1

        # Botão iniciar
        self.btn_start = Button(master, text="INICIAR ENVIO", command=self.start_worker)
        self.btn_start.grid(row=row, column=0, columnspan=2, pady=8)
        row += 1

        # Log (MENOR)
        Label(master, text="Log:").grid(row=row, column=0, sticky="w", padx=6)
        row += 1
        self.log_box = ScrolledText(master, width=90, height=8)
        self.log_box.grid(row=row, column=0, columnspan=2, padx=6, pady=6, sticky="nsew")
        master.grid_rowconfigure(row, weight=1)
        master.grid_columnconfigure(1, weight=1)

        self.running = False

    def pick_csv(self):
        path = filedialog.askopenfilename(
            title="Selecione o CSV",
            filetypes=[("CSV", "*.csv"), ("Todos", "*.*")]
        )
        if path:
            self.csv_path.set(path)

    def pick_profile(self):
        path = filedialog.askdirectory(title="Selecione a pasta de perfil do Chrome")
        if path:
            self.profile_dir.set(path)

    def log(self, msg: str):
        ts = datetime.now().strftime("%H:%M:%S")
        self.log_box.config(state=NORMAL)
        self.log_box.insert(END, f"[{ts}] {msg}\n")
        self.log_box.see(END)
        self.log_box.config(state=DISABLED)

    def _build_rich_editor(self, master, grid_row: int):
        editor_frame = Frame(master, borderwidth=1, relief="sunken")
        editor_frame.grid(row=grid_row, column=1, sticky="nsew", padx=6, pady=4)
        master.grid_rowconfigure(grid_row, weight=1)
        master.grid_columnconfigure(1, weight=1)

        toolbar = Frame(editor_frame)
        toolbar.pack(fill="x", padx=6, pady=(6, 2))

        Button(toolbar, text="Negrito", command=self._toggle_bold).pack(side="left", padx=2)
        Button(toolbar, text="Itálico", command=self._toggle_italic).pack(side="left", padx=2)
        Button(toolbar, text="Tachado", command=self._toggle_strike).pack(side="left", padx=2)
        Button(toolbar, text="Mono", command=self._toggle_mono).pack(side="left", padx=2)
        Button(toolbar, text="Limpar", command=self._clear_formatting).pack(side="left", padx=2)

        self.msg_box = Text(editor_frame, height=12, wrap="word", undo=True)
        self.msg_box.pack(fill="both", expand=True, padx=6, pady=(0, 6))

        self._init_text_formats()
        self._bind_rich_paste()

        # atalhos de teclado para aplicar estilos rapidamente
        self.msg_box.bind("<Control-b>", self._shortcut_bold)
        self.msg_box.bind("<Control-B>", self._shortcut_bold)
        self.msg_box.bind("<Control-i>", self._shortcut_italic)
        self.msg_box.bind("<Control-I>", self._shortcut_italic)
        self.msg_box.bind("<Control-t>", self._shortcut_strike)
        self.msg_box.bind("<Control-T>", self._shortcut_strike)
        self.msg_box.bind("<Control-m>", self._shortcut_mono)
        self.msg_box.bind("<Control-M>", self._shortcut_mono)
        self.msg_box.bind("<Control-Shift-l>", self._shortcut_clear)

    def set_running(self, val: bool):
        self.running = val
        if self.btn_start is not None:
            self.btn_start.config(state=DISABLED if val else NORMAL)

    def _shortcut_bold(self, _event):
        self._toggle_bold()
        return "break"

    def _shortcut_italic(self, _event):
        self._toggle_italic()
        return "break"

    def _shortcut_strike(self, _event):
        self._toggle_strike()
        return "break"

    def _shortcut_mono(self, _event):
        self._toggle_mono()
        return "break"

    def _shortcut_clear(self, _event):
        self._clear_formatting()
        return "break"

    def _toggle_bold(self):
        self._transform_selection(base_transform=self._toggle_bold_base)

    def _toggle_italic(self):
        self._transform_selection(base_transform=self._toggle_italic_base)

    def _toggle_strike(self):
        self._transform_selection(strike_transform=lambda strike: not strike)

    def _toggle_mono(self):
        def to_mono(base: str) -> str:
            return "N" if base == "MONO" else "MONO"
        self._transform_selection(base_transform=to_mono)

    def _clear_formatting(self):
        self._transform_selection(
            base_transform=lambda _base: "N",
            strike_transform=lambda _strike: False
        )

    @staticmethod
    def _toggle_bold_base(base: str) -> str:
        if base == "MONO":
            return base
        if base == "B":
            return "N"
        if base == "BI":
            return "I"
        if base == "I":
            return "BI"
        return "B"

    @staticmethod
    def _toggle_italic_base(base: str) -> str:
        if base == "MONO":
            return base
        if base == "I":
            return "N"
        if base == "BI":
            return "B"
        if base == "B":
            return "BI"
        return "I"

    def _transform_selection(
        self,
        base_transform: Callable[[str], str] | None = None,
        strike_transform: Callable[[bool], bool] | None = None
    ):
        if not hasattr(self, "msg_box") or self.msg_box is None:
            return
        try:
            start = self.msg_box.index("sel.first")
            end = self.msg_box.index("sel.last")
        except Exception:
            return

        runs = self._gather_runs(start, end)
        if not runs:
            return

        transformed = []
        for text, base, strike in runs:
            new_base = base_transform(base) if base_transform else base
            new_strike = strike_transform(strike) if strike_transform else strike
            transformed.append((text, new_base, new_strike))

        self.msg_box.delete(start, end)
        self._insert_runs(start, transformed)

    def start_worker(self):
        if self.running:
            return
        csv_path = self.csv_path.get().strip()
        if not csv_path or not os.path.exists(csv_path):
            self.log("❌ Selecione um CSV válido.")
            return
        # Extrai o texto como marcadores WhatsApp a partir das tags visuais
        message = self._export_whatsapp_text()
        if not message.strip():
            self.log("❌ Digite a mensagem.")
            return
        profile = self.profile_dir.get().strip() or DEFAULT_PROFILE_DIR

        self.set_running(True)
        t = threading.Thread(
            target=self.worker,
            args=(csv_path, message, profile),
            daemon=True
        )
        t.start()

    # ---------------------------
    # Formatação visual e colagem rica
    # ---------------------------
    def _init_text_formats(self):
        base = tkfont.nametofont(self.msg_box.cget("font"))
        try:
            size = base.cget("size")
            family = base.cget("family")
        except Exception:
            size = 10
            family = "TkDefaultFont"

        self._font_norm = tkfont.Font(family=family, size=size)
        self._font_b = tkfont.Font(family=family, size=size, weight="bold")
        self._font_i = tkfont.Font(family=family, size=size, slant="italic")
        self._font_bi = tkfont.Font(family=family, size=size, weight="bold", slant="italic")
        self._font_mono = tkfont.Font(family="Courier New", size=size)

        # Tags de fonte (somente uma delas por trecho)
        self.msg_box.tag_configure("FMT_N", font=self._font_norm)
        self.msg_box.tag_configure("FMT_B", font=self._font_b)
        self.msg_box.tag_configure("FMT_I", font=self._font_i)
        self.msg_box.tag_configure("FMT_BI", font=self._font_bi)
        self.msg_box.tag_configure("FMT_MONO", font=self._font_mono)

        # Tag combinável: tachado
        self.msg_box.tag_configure("FMT_S", overstrike=True)

    def _bind_rich_paste(self):
        # Intercepta paste padrão e aplica formatação quando disponível
        self.msg_box.bind("<<Paste>>", self._on_paste)
        self.msg_box.bind("<Control-v>", self._on_paste)
        self.msg_box.bind("<Control-V>", self._on_paste)

    def _on_paste(self, event=None):
        try:
            # Se houver seleção, substitui
            try:
                sel_first = self.msg_box.index("sel.first")
                sel_last = self.msg_box.index("sel.last")
                self.msg_box.delete(sel_first, sel_last)
                insert_index = sel_first
            except Exception:
                insert_index = self.msg_box.index("insert")

            html = self._get_clipboard_html()
            if html:
                runs = self._html_to_runs(html)
                if runs:
                    self._insert_runs(insert_index, runs)
                return "break"
            # Fallback: texto puro
            txt = self.master.clipboard_get()
            self._insert_runs(insert_index, [(txt, "N", False)])
            return "break"
        except Exception:
            # Se algo falhar, deixe o paste padrão acontecer
            return None

    # ---------------------------
    # Exportação p/ marcadores WhatsApp
    # ---------------------------
    def _export_whatsapp_text(self) -> str:
        runs = self._gather_runs_from_widget()
        return self._runs_to_whatsapp(runs)

    def _gather_runs_from_widget(self):
        if not hasattr(self, "msg_box") or self.msg_box is None:
            return []
        return self._gather_runs("1.0", self.msg_box.index("end-1c"))

    def _gather_runs(self, start: str, end: str):
        if not hasattr(self, "msg_box") or self.msg_box is None:
            return []
        if self.msg_box.compare(start, ">=", end):
            return []

        def flags_at(index: str):
            tags = set(self.msg_box.tag_names(index))
            if "FMT_MONO" in tags:
                base = "MONO"
            elif "FMT_BI" in tags:
                base = "BI"
            elif "FMT_B" in tags:
                base = "B"
            elif "FMT_I" in tags:
                base = "I"
            else:
                base = "N"
            strike = "FMT_S" in tags
            return base, strike

        pieces: list[tuple[str, str, bool]] = []
        buf: list[str] = []
        prev_state: tuple[str, bool] | None = None

        i = start
        while self.msg_box.compare(i, "<", end):
            ch = self.msg_box.get(i)
            state = flags_at(i)
            if prev_state is None:
                prev_state = state
            elif state != prev_state:
                pieces.append(("".join(buf), prev_state[0], prev_state[1]))
                buf = []
                prev_state = state
            buf.append(ch)
            i = self.msg_box.index(f"{i} +1c")

        if buf and prev_state is not None:
            pieces.append(("".join(buf), prev_state[0], prev_state[1]))

        return pieces

    def _runs_to_whatsapp(self, runs) -> str:
        out = []
        for text, base, strike in runs:
            if not text:
                continue
            frag = text
            if base == "MONO":
                if "\n" in frag:
                    out.append("```\n" + frag + "\n```")
                else:
                    out.append("```" + frag + "```")
                continue
            prefix = suffix = ""
            if base in ("B", "BI"):
                prefix += "*"; suffix = "*" + suffix
            if base in ("I", "BI"):
                prefix += "_"; suffix = "_" + suffix
            if strike:
                prefix += "~"; suffix = "~" + suffix
            out.append(prefix + frag + suffix)
        return "".join(out)

    def _insert_runs(self, index: str, runs):
        if not hasattr(self, "msg_box") or self.msg_box is None:
            return index
        base_tag = {
            "N": "FMT_N",
            "B": "FMT_B",
            "I": "FMT_I",
            "BI": "FMT_BI",
            "MONO": "FMT_MONO",
        }
        for text, base, strike in runs:
            if not text:
                continue
            tags = [base_tag.get(base, "FMT_N")]
            if strike:
                tags.append("FMT_S")
            self.msg_box.insert(index, text, tuple(tags))
            index = self.msg_box.index(f"{index} + {len(text)}c")
        return index

    # ---------------------------
    # Clipboard (Windows): lê CF_HTML e extrai o fragmento
    # ---------------------------
    def _get_clipboard_html(self) -> str | None:
        try:
            user32 = ctypes.windll.user32
            kernel32 = ctypes.windll.kernel32
        except Exception:
            return None
        CF_HTML = user32.RegisterClipboardFormatW("HTML Format")
        if not user32.OpenClipboard(None):
            return None
        try:
            if not user32.IsClipboardFormatAvailable(CF_HTML):
                return None
            handle = user32.GetClipboardData(CF_HTML)
            if not handle:
                return None
            ptr = kernel32.GlobalLock(handle)
            if not ptr:
                return None
            try:
                data = ctypes.c_char_p(ptr).value
            finally:
                kernel32.GlobalUnlock(handle)
            if not data:
                return None
            raw = None
            for enc in ("utf-8", "windows-1252", "latin-1"):
                try:
                    raw = data.decode(enc, errors="ignore")
                    break
                except Exception:
                    continue
            if not raw:
                return None
            # Parse ponteiros StartFragment/EndFragment
            def _find_int(marker):
                i = raw.find(marker)
                if i == -1:
                    return -1
                j = raw.find("\n", i)
                if j == -1:
                    j = raw.find("\r", i)
                try:
                    return int(raw[i+len(marker):j].strip())
                except Exception:
                    return -1
            s = _find_int("StartFragment:")
            e = _find_int("EndFragment:")
            if s != -1 and e != -1 and e > s:
                return raw[s:e]
            # Fallback: tenta StartHTML/EndHTML
            s = _find_int("StartHTML:")
            e = _find_int("EndHTML:")
            if s != -1 and e != -1 and e > s:
                return raw[s:e]
            return None
        finally:
            user32.CloseClipboard()

    # ---------------------------
    # HTML -> runs básicos (b/i/s/code/pre, br, p/div)
    # ---------------------------
    def _html_to_runs(self, html: str):
        class _HP(HTMLParser):
            def __init__(self):
                super().__init__()
                self.stack = []  # (base, strike)
                self.cur_base = "N"
                self.cur_strike = False
                self.runs = []
                self.buf = []

            @staticmethod
            def _base_flags(base: str) -> tuple[bool, bool, bool]:
                bold = base in ("B", "BI")
                italic = base in ("I", "BI")
                mono = base == "MONO"
                return bold, italic, mono

            @staticmethod
            def _flags_to_base(bold: bool, italic: bool, mono: bool) -> str:
                if mono:
                    return "MONO"
                if bold and italic:
                    return "BI"
                if bold:
                    return "B"
                if italic:
                    return "I"
                return "N"

            def _apply_style(self, base: str, strike: bool, attrs: dict[str, str]) -> tuple[str, bool]:
                style = attrs.get("style", "")
                if not style:
                    return base, strike

                bold, italic, mono = self._base_flags(base)
                decorations = set()

                for chunk in style.split(";"):
                    if ":" not in chunk:
                        continue
                    key, value = chunk.split(":", 1)
                    key = key.strip().lower()
                    value = value.strip().lower()
                    if key == "font-weight":
                        if "bold" in value:
                            bold = True
                        else:
                            try:
                                weight_val = int(value)
                                if weight_val >= 600:
                                    bold = True
                            except ValueError:
                                pass
                    elif key == "font-style":
                        if "italic" in value:
                            italic = True
                    elif key == "font-family":
                        if "mono" in value or "courier" in value:
                            mono = True
                    elif key == "text-decoration":
                        decorations.update(part.strip() for part in value.split())
                    elif key == "text-decoration-line":
                        decorations.update(part.strip() for part in value.split())

                if "line-through" in decorations or "strikethrough" in decorations:
                    strike = True

                return self._flags_to_base(bold, italic, mono), strike

            def _flush(self):
                if self.buf:
                    self.runs.append(("".join(self.buf), self.cur_base, self.cur_strike))
                    self.buf = []

            def handle_starttag(self, tag, attrs):
                tag = tag.lower()
                attrs_dict = {k.lower(): (v or "") for k, v in attrs}
                base = self.cur_base
                strike = self.cur_strike
                if tag in ("b", "strong"):
                    if base == "I":
                        base = "BI"
                    elif base == "N":
                        base = "B"
                    elif base == "MONO":
                        base = "MONO"  # mono tem prioridade visual
                elif tag in ("i", "em"):
                    if base == "B":
                        base = "BI"
                    elif base == "N":
                        base = "I"
                    elif base == "MONO":
                        base = "MONO"
                elif tag in ("s", "strike", "del"):
                    strike = True
                elif tag in ("code", "pre"):
                    base = "MONO"
                elif tag in ("br",):
                    self.buf.append("\n"); return
                elif tag in ("p", "div", "section", "article", "h1", "h2", "h3", "h4", "h5", "h6", "li"):
                    # Nova linha antes de bloco, exceto se início
                    if self.runs or self.buf:
                        self.buf.append("\n")

                new_base, new_strike = self._apply_style(base, strike, attrs_dict)
                if new_base != self.cur_base or new_strike != self.cur_strike:
                    self._flush()
                base, strike = new_base, new_strike
                self.stack.append((self.cur_base, self.cur_strike))
                self.cur_base, self.cur_strike = base, strike

            def handle_endtag(self, tag):
                tag = tag.lower()
                if tag in ("p", "div", "section", "article", "h1", "h2", "h3", "h4", "h5", "h6", "li"):
                    self.buf.append("\n")
                self._flush()
                if self.stack:
                    self.cur_base, self.cur_strike = self.stack.pop()

            def handle_data(self, data):
                if data:
                    self.buf.append(data)

            def close(self):
                super().close()
                self._flush()

        hp = _HP()
        hp.feed(html)
        hp.close()
        return hp.runs

    def worker(self, csv_path, message, profile):
        try:
            contacts = read_contacts_from_csv(csv_path)
            self.log(f"Contatos lidos: {len(contacts)}")
            if not contacts:
                self.log("Nenhum contato válido no CSV (esperado cabeçalho telefone,nome).")
                return

            driver = build_driver(profile_dir=profile)
            try:
                driver.get("https://web.whatsapp.com")
                wait_main_ui_ready(driver)
                self.log("WhatsApp Web carregado (sessão ativa).")

                # estabilização global
                time.sleep(GLOBAL_INITIAL_STABILIZATION)

                total_ok = 0
                total_fail = 0
                self.first_chat_done = False

                for c in contacts:
                    raw_phone = c["telefone"]
                    nome = c.get("nome", "")
                    phone_e164 = e164_br(raw_phone)
                    if not phone_e164 or len(phone_e164) < 10:
                        self.log(f"[{raw_phone}] inválido (formato).")
                        total_fail += 1
                        time.sleep(random.uniform(MIN_DELAY_BETWEEN, MAX_DELAY_BETWEEN))
                        continue

                    texto = message.replace("{nome}", nome)
                    self.log(f"[{phone_e164}] Abrindo chat...")

                    # 1) Tenta via busca interna (sem reload)
                    opened = open_chat_via_search(driver, phone_e164, timeout=10)

                    # 2) Fallback por link só se necessário
                    if not opened:
                        opened = open_chat_via_link(driver, phone_e164, timeout=TIMEOUT_CHAT)

                    if not opened:
                        self.log(f"[{phone_e164}] não abriu chat (inválido/sem WhatsApp?).")
                        total_fail += 1
                        time.sleep(random.uniform(MIN_DELAY_BETWEEN, MAX_DELAY_BETWEEN))
                        continue

                    # estabilização extra no PRIMEIRO chat
                    if not self.first_chat_done:
                        time.sleep(FIRST_CHAT_STABILIZATION)
                        self.first_chat_done = True

                    # Espera "humana" antes de colar
                    time.sleep(random.uniform(MIN_WAIT_BEFORE_PASTE, MAX_WAIT_BEFORE_PASTE))

                    message_box = find_message_box(driver, timeout=TIMEOUT_CHAT)
                    if not message_box:
                        self.log(f"[{phone_e164}] caixa de mensagem não encontrada.")
                        total_fail += 1
                        time.sleep(random.uniform(MIN_DELAY_BETWEEN, MAX_DELAY_BETWEEN))
                        continue

                    # ---- Snapshot antes
                    before_count = get_outgoing_count(driver)
                    before_sig = get_last_outgoing_signature(driver)

                    ok_send = False
                    reason = "nao_enviado"

                    # Se o composer já tiver algo, limpe antes da primeira colagem
                    if composer_text(message_box) != "":
                        clear_composer(message_box)

                    for attempt in range(RETRIES_PER_CONTACT + 1):
                        # Se NÃO é a primeira tentativa e o composer está vazio (provável envio),
                        # não repaste — apenas revalide mais um pouco
                        if attempt > 0 and composer_text(message_box) == "":
                            sent = wait_sent_hybrid(driver, before_count, before_sig, message_box)
                            if sent:
                                ok_send = True
                                reason = "late_detect_ok"
                                break
                            # se ainda não detectou, segue para nova tentativa (vai colar de novo)

                        # Se há texto indesejado, limpe
                        if composer_text(message_box) != "":
                            clear_composer(message_box)

                        # Colar conteúdo
                        paste_text(message_box, texto)
                        time.sleep(random.uniform(0.25, 0.6))  # pequena pausa

                        # Disparar uma única forma
                        success, motivo_local = try_send_once(driver, message_box)
                        if not success:
                            reason = motivo_local
                            time.sleep(0.7)
                            continue

                        # Espera detecção híbrida
                        sent = wait_sent_hybrid(driver, before_count, before_sig, message_box)
                        if sent:
                            ok_send = True
                            reason = motivo_local
                            break
                        else:
                            reason = "nao_detectado_apos_envio"
                            time.sleep(0.9)

                    status_txt = "enviado" if ok_send else "falha"
                    self.log(f"[{phone_e164}] {status_txt} | motivo: {reason}")

                    if ok_send:
                        total_ok += 1
                    else:
                        total_fail += 1

                    # pausa entre contatos
                    time.sleep(random.uniform(MIN_DELAY_BETWEEN, MAX_DELAY_BETWEEN))

                self.log("---- Concluído ----")
                self.log(f"Total: {total_ok + total_fail} | Enviados: {total_ok} | Falhas: {total_fail}")

            finally:
                # mantenha aberto para inspeção; se preferir, use driver.quit()
                pass

        except Exception as e:
            self.log(f"❌ Erro: {e}")

        finally:
            self.set_running(False)

# ---------------------------
# main
# ---------------------------
if __name__ == "__main__":
    root = Tk()
    root.geometry("880x520")
    app = App(root)
    root.mainloop()
