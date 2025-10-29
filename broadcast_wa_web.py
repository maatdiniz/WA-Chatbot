# broadcast_wa_web.py
# Execução:
#   python broadcast_wa_web.py --csv contatos.csv --message "Olá {nome}, teste"
#   python broadcast_wa_web.py --csv contatos.csv --message "Teste local via WhatsApp Web ?"
#
# Requisitos:
#   pip install selenium pyperclip webdriver-manager
#
# Aviso:
#   Automação do WhatsApp Web pode violar os Termos de Serviço. Use por sua conta e risco.

import argparse
import csv
import platform
import random
import sys
import time

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
# Configurações padrão
# ---------------------------
DEFAULT_TIMEOUT = 25
DEFAULT_MIN_DELAY = 2.0
DEFAULT_MAX_DELAY = 6.0
DEFAULT_MIN_WAIT_CHAT_LOAD = 1.2
DEFAULT_MAX_WAIT_CHAT_LOAD = 3.5
DEFAULT_RETRIES = 2
DEFAULT_MIN_WAIT_CHAT = 6.8
DEFAULT_MAX_WAIT_CHAT = 12.5

# Seletores (o WhatsApp muda DOM com frequência; ajuste se preciso)
MAIN_UI_READY_SELECTORS = [
    "[data-testid='chat-list-search']",
    "div[role='grid']",
]
SEARCH_INPUT_SELECTOR = "[data-testid='chat-list-search']"  # barra de busca
SEARCH_RESULT_ITEMS = [
    "div[role='listitem']",
    "[data-testid='cell-frame-container']",
]
MESSAGE_BOX_SELECTORS = [
    "div[contenteditable='true'][data-tab='10']",
    "div[contenteditable='true'][data-tab='6']",
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

# ---------------------------
# Utilidades
# ---------------------------
def log(msg: str):
    print(msg, flush=True)

def e164_br(telefone_br: str) -> str:
    digits = "".join([c for c in telefone_br if c.isdigit()])
    if not digits:
        return ""
    if digits.startswith("55"):
        return digits
    return "55" + digits

def random_delay(min_s, max_s):
    time.sleep(random.uniform(min_s, max_s))

def build_driver(profile_dir: str | None, chrome_binary: str | None):
    opts = ChromeOptions()
    if chrome_binary:
        opts.binary_location = chrome_binary
    if profile_dir:
        opts.add_argument(f"--user-data-dir={profile_dir}")
    opts.add_argument("--disable-blink-features=AutomationControlled")
    opts.add_argument("--start-maximized")
    # NÃO usar headless p/ WhatsApp Web
    service = ChromeService(ChromeDriverManager().install())
    driver = webdriver.Chrome(service=service, options=opts)
    return driver

def wait_main_ui_ready(driver, timeout=60):
    last_err = None
    for sel in MAIN_UI_READY_SELECTORS:
        try:
            WebDriverWait(driver, timeout).until(
                EC.presence_of_element_located((By.CSS_SELECTOR, sel))
            )
            return
        except Exception as e:
            last_err = e
    if last_err:
        raise last_err

def find_message_box(driver, timeout: int):
    for sel in MESSAGE_BOX_SELECTORS:
        try:
            el = WebDriverWait(driver, timeout).until(
                EC.presence_of_element_located((By.CSS_SELECTOR, sel))
            )
            if el.is_displayed() and el.is_enabled():
                return el
        except TimeoutException:
            pass
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
    src = driver.page_source.lower()
    return any(s in src for s in INVALID_SNIPPETS)

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

def try_send(driver, message_box, texto: str) -> tuple[bool, str]:
    # 1) ENTER
    try:
        message_box.send_keys(Keys.ENTER)
        return True, "enter_ok"
    except Exception:
        pass
    # 2) botão enviar
    btn = find_send_button(driver)
    if btn:
        try:
            btn.click()
            return True, "click_send_ok"
        except Exception:
            pass
    # 3) CTRL+ENTER
    try:
        if platform.system() == "Darwin":
            message_box.send_keys(Keys.COMMAND, Keys.ENTER)
        else:
            message_box.send_keys(Keys.CONTROL, Keys.ENTER)
        return True, "ctrl_enter_ok"
    except Exception:
        pass
    return False, "nao_enviado"

def was_message_sent(driver, texto: str) -> bool:
    # Heurística: confere se último balão de saída contém parte do texto
    try:
        time.sleep(0.9)
        candidates = driver.find_elements(By.CSS_SELECTOR, "div.message-out, div[data-testid='msg-balloon']")
        if not candidates:
            candidates = driver.find_elements(By.CSS_SELECTOR, "div[data-testid='msg-container']")
        if not candidates:
            return False
        last = candidates[-1].text or ""
        probe = texto.strip()[:12]
        return bool(probe) and (probe in last)
    except Exception:
        return False

def read_contacts_from_csv(path: str) -> list[dict]:
    contacts = []
    with open(path, "r", encoding="utf-8", newline="") as f:
        raw = f.read()
        # tenta detectar delimitador
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

# ---------------------------
# Abrir chat SEM navegar por link (via busca interna)
# ---------------------------
def open_chat_via_search(driver, phone_e164: str, timeout: int) -> bool:
    """
    Tenta abrir conversa via barra de busca interna, para evitar reload.
    Retorna True se conseguiu abrir um chat; False se não encontrou resultado.
    Observação: se o número não estiver salvo/sem histórico, a busca pode não achar.
    """
    # Foco na busca
    try:
        search = WebDriverWait(driver, 10).until(
            EC.presence_of_element_located((By.CSS_SELECTOR, SEARCH_INPUT_SELECTOR))
        )
    except TimeoutException:
        return False

    # Limpa e cola
    try:
        search.click()
        # CTRL+A + DEL para limpar
        if platform.system() == "Darwin":
            search.send_keys(Keys.COMMAND, "a")
        else:
            search.send_keys(Keys.CONTROL, "a")
        search.send_keys(Keys.DELETE)
    except Exception:
        pass

    # Tentar com diferentes formatos (alguns usuários salvam com +55/55/sem DDI)
    variants = [
        phone_e164,                 # 5562...
        "+" + phone_e164,           # +5562...
        phone_e164[2:],             # 62...
    ]

    for query in variants:
        pyperclip.copy(query)
        if platform.system() == "Darwin":
            search.send_keys(Keys.COMMAND, "v")
        else:
            search.send_keys(Keys.CONTROL, "v")

        # aguarda resultados
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
            time.sleep(0.25)

        if found_item:
            try:
                found_item.click()
                # espera a caixa da msg aparecer
                mb = find_message_box(driver, timeout=10)
                if mb:
                    return True
            except Exception:
                pass

        # se não deu, limpa e tenta próxima variante
        try:
            if platform.system() == "Darwin":
                search.send_keys(Keys.COMMAND, "a")
            else:
                search.send_keys(Keys.CONTROL, "a")
            search.send_keys(Keys.DELETE)
        except Exception:
            pass

    return False

# ---------------------------
# Fallback: abrir chat por link (só quando necessário)
# ---------------------------
def open_chat_via_link(driver, phone_e164: str, timeout: int) -> bool:
    url = f"https://web.whatsapp.com/send?phone={phone_e164}&app_absent=0"
    driver.get(url)
    # aguarda carregamento ou modal de inválido
    t0 = time.time()
    while time.time() - t0 < timeout:
        if page_has_invalid_number(driver):
            return False
        mb = find_message_box(driver, timeout=1)
        if mb:
            return True
        time.sleep(0.3)
    return False

# ---------------------------
# Fluxo principal
# ---------------------------
def run(
    csv_path: str,
    msg_template: str,
    profile_dir: str | None,
    chrome_binary: str | None,
    timeout: int,
    min_delay: float,
    max_delay: float,
    min_wait_chat: float,
    max_wait_chat: float,
    retries: int,
):
    contacts = read_contacts_from_csv(csv_path)
    log(f"Lidos {len(contacts)} contatos de {csv_path}")
    if not contacts:
        log("Nenhum contato válido encontrado (verifique cabeçalho 'telefone,nome').")
        sys.exit(1)

    driver = build_driver(profile_dir=profile_dir, chrome_binary=chrome_binary)

    try:
        # Abre WhatsApp Web 1x (sessão precisa estar autenticada)
        driver.get("https://web.whatsapp.com")
        wait_main_ui_ready(driver, timeout=60)
        log("WhatsApp Web carregado (sessão ativa).")

        results = []

        for c in contacts:
            phone_e164 = e164_br(c["telefone"])
            if not phone_e164 or len(phone_e164) < 10:
                log(f"[{c['telefone']}] inválido (formato). Pulando.")
                results.append((c["telefone"], False, "formato_invalido"))
                continue

            texto = msg_template.format(nome=c.get("nome", ""))

            # 1) Tenta via busca interna (sem reload).
            opened = open_chat_via_search(driver, phone_e164, timeout=10)

            # 2) Se não achou (número não salvo/sem histórico), usa fallback por link só nesse caso
            if not opened:
                opened = open_chat_via_link(driver, phone_e164, timeout=timeout)
                if not opened:
                    log(f"[{phone_e164}] número inválido/sem WhatsApp ou falha ao abrir chat.")
                    results.append((phone_e164, False, "nao_abriu_chat"))
                    continue

            # atraso natural antes de colar
            time.sleep(random.uniform(min_wait_chat, max_wait_chat))

            # pega a caixa de mensagem
            message_box = find_message_box(driver, timeout=timeout)
            if not message_box:
                log(f"[{phone_e164}] caixa de mensagem não encontrada.")
                results.append((phone_e164, False, "sem_caixa"))
                continue

            # tenta enviar com retries
            ok_send = False
            reason = "nao_enviado"
            for _ in range(retries + 1):
                paste_text(message_box, texto)
                time.sleep(random.uniform(0.25, 0.7))  # simula “digitação”

                success, motivo = try_send(driver, message_box, texto)
                if success:
                    ok_send = was_message_sent(driver, texto)
                    reason = motivo if ok_send else "nao_detectado_apos_envio"
                else:
                    ok_send = False
                    reason = motivo

                if ok_send:
                    break
                # pequena pausa antes do retry
                time.sleep(random.uniform(0.6, 1.2))

            results.append((phone_e164, ok_send, reason))
            log(f"[{phone_e164}] enviado? {ok_send} | motivo: {reason}")

            # pausa anti-spam entre contatos
            random_delay(min_delay, max_delay)

        # Resumo
        log("\nResumo final:")
        enviados = sum(1 for _, ok, _ in results if ok)
        falhas = len(results) - enviados
        log(f"Total: {len(results)} | Enviados: {enviados} | Falhas: {falhas}")
        for r in results:
            log(str(r))

    finally:
        # deixe aberto p/ auditoria; se quiser, troque por driver.quit()
        pass

def parse_args():
    p = argparse.ArgumentParser(
        description="Broadcast via WhatsApp Web — abre chat via busca (sem reload); fallback por link só se necessário."
    )
    p.add_argument("--csv", required=True, help="Arquivo CSV com colunas: telefone,nome")
    p.add_argument("--message", required=True, help="Mensagem; use {nome} como placeholder opcional.")
    p.add_argument("--profile", default=None, help="Pasta de perfil do Chrome p/ manter sessão (ex.: C:\\Users\\Você\\wa-profile)")
    p.add_argument("--chrome-binary", default=None, help="Caminho do executável do Chrome (opcional).")
    p.add_argument("--timeout", type=int, default=DEFAULT_TIMEOUT, help="Timeout por chat (s).")
    p.add_argument("--min-delay", type=float, default=DEFAULT_MIN_DELAY, help="Pausa mínima entre contatos (s).")
    p.add_argument("--max-delay", type=float, default=DEFAULT_MAX_DELAY, help="Pausa máxima entre contatos (s).")
    p.add_argument("--min-wait-chat", type=float, default=DEFAULT_MIN_WAIT_CHAT, help="Espera mínima antes de colar (s).")
    p.add_argument("--max-wait-chat", type=float, default=DEFAULT_MAX_WAIT_CHAT, help="Espera máxima antes de colar (s).")
    p.add_argument("--retries", type=int, default=DEFAULT_RETRIES, help="Tentativas extras de envio por contato.")
    return p.parse_args()

if __name__ == "__main__":
    args = parse_args()
    try:
        run(
            csv_path=args.csv,
            msg_template=args.message,
            profile_dir=args.profile,
            chrome_binary=args.chrome_binary,
            timeout=args.timeout,
            min_delay=args.min_delay,
            max_delay=args.max_delay,
            min_wait_chat=args.min_wait_chat,
            max_wait_chat=args.max_wait_chat,
            retries=args.retries,
        )
    except KeyboardInterrupt:
        log("\nInterrompido pelo usuário.")