import flet as ft
import threading
import csv
import random
import time
from datetime import datetime
from backend import WhatsAppDriver 

# --- FUNÇÃO AUXILIAR DE FORMATAÇÃO (Para Preview) ---
def formatar_numero_preview(numero_raw):
    nums = "".join([n for n in str(numero_raw) if n.isdigit()])
    
    # Se tiver 8 dígitos (Fixo), adiciona só o DDD 62
    if len(nums) == 8:
        nums = f"62{nums}"
    
    # Se tiver 9 dígitos (Celular), adiciona só o DDD 62
    elif len(nums) == 9:
        nums = f"62{nums}"
        
    # Adiciona o DDI 55
    if len(nums) in [10, 11]: 
        nums = f"55{nums}"
        
    return nums

# --- THREAD DO ROBÔ ---
class WhatsappBotThread(threading.Thread):
    def __init__(self, csv_path, message_template, log_callback, progress_callback, on_finish_callback):
        super().__init__()
        self.csv_path = csv_path
        self.message_template = message_template
        self.log_callback = log_callback
        self.progress_callback = progress_callback 
        self.on_finish_callback = on_finish_callback
        self.is_running = False
        self.is_paused = False
        self.stop_signal = False
        self.driver_manager = WhatsAppDriver()

    def run(self):
        self.is_running = True
        self.log_callback("🚀 Inicializando navegador...")
        
        try:
            self.driver_manager.iniciar_driver()
            self.log_callback("✅ Navegador aberto. Aguardando 30s (QR Code/Carregamento)...")
            time.sleep(30)
            
            timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
            nome_relatorio = f"relatorio_envios_{timestamp}.csv"
            
            with open(self.csv_path, 'r', encoding='utf-8') as f_in, \
                 open(nome_relatorio, 'w', encoding='utf-8', newline='') as f_out:
                
                leitor = csv.reader(f_in, delimiter=';')
                escritor = csv.writer(f_out, delimiter=';')
                escritor.writerow(["Telefone", "Nome", "Status", "Detalhes", "DataHora"])
                
                contatos = list(leitor)
                total = len(contatos)
                self.log_callback(f"📂 Lista carregada: {total} contatos.")

                for i, linha in enumerate(contatos):
                    if self.stop_signal:
                        self.log_callback("🛑 Processo abortado.")
                        break
                    
                    while self.is_paused:
                        if self.stop_signal: break
                        time.sleep(1)

                    if not linha: continue
                    
                    numero = linha[0].strip()
                    nome = linha[1].strip() if len(linha) > 1 else ""
                    
                    self.log_callback(f"🔄 ({i+1}/{total}) Enviando para: {numero}...")

                    # Pausa longa a cada 50
                    if (i + 1) % 50 == 0 and i < total - 1:
                        tempo_pausa = random.randint(300, 600)
                        minutos = tempo_pausa // 60
                        self.log_callback(f"☕ Pausa de segurança: descansando por {minutos} min...")
                        self.progress_callback(i, total, status=f"Em pausa ({minutos} min)...")
                        for _ in range(tempo_pausa):
                            if self.stop_signal: break
                            time.sleep(1)

                    # Envio
                    eh_o_primeiro = (i == 0)
                    sucesso, msg_status = self.driver_manager.enviar_mensagem(
                        numero=numero,
                        nome=nome,
                        mensagem_base=self.message_template,
                        primeiro_envio=eh_o_primeiro
                    )
                    
                    hora_atual = datetime.now().strftime("%H:%M:%S")
                    status_str = "SUCESSO" if sucesso else "FALHA"
                    icon = "✅" if sucesso else "❌"
                    
                    self.log_callback(f"{icon} {numero}: {msg_status}")
                    escritor.writerow([numero, nome, status_str, msg_status, hora_atual])
                    f_out.flush()

                    self.progress_callback(i + 1, total, status="Aguardando delay...")

                    if i < total - 1:
                        tempo_espera = random.uniform(15, 25)
                        self.log_callback(f"⏳ Aguardando {tempo_espera:.1f}s...")
                        time.sleep(tempo_espera)

        except Exception as e:
            self.log_callback(f"💀 Erro Crítico: {str(e)}")
        finally:
            self.log_callback("🏁 Processo finalizado.")
            self.driver_manager.fechar()
            self.is_running = False
            self.on_finish_callback()

    def pause(self):
        self.is_paused = True
        self.log_callback("⏸️ Pausado.")
    def resume(self):
        self.is_paused = False
        self.log_callback("▶️ Retomado.")
    def stop(self):
        self.stop_signal = True
        self.log_callback("⚠️ Parando...")


# --- INTERFACE GRÁFICA ---
def main(page: ft.Page):
    page.title = "Bot WhatsApp Marketing - Python"
    page.theme_mode = ft.ThemeMode.LIGHT
    page.window_width = 1200
    page.window_height = 900

    bot_thread = None

    # --- FUNÇÕES DE UPDATE DA UI ---

    def add_log(message):
        timestamp = datetime.now().strftime("%H:%M:%S")
        log_text.value += f"[{timestamp}] {message}\n"
        page.update()

    def update_progress_ui(current, total, status="Rodando"):
        percent = current / total if total > 0 else 0
        progress_bar.value = percent
        restantes = total - current
        progress_text.value = f"Processado: {current}/{total} | Restam: {restantes} | {int(percent*100)}%"
        status_indicator.value = f"Status atual: {status}"
        page.update()

    def on_bot_finish():
        add_log("--- FIM DA EXECUÇÃO ---")
        progress_bar.value = 0
        status_indicator.value = "Status: Parado"
        btn_start.disabled = False
        btn_pause.disabled = True
        btn_stop.disabled = True
        page.update()

    # --- COMPONENTES VISUAIS ---

    # 1. Logs e Status
    log_text = ft.TextField(
        value="Aguardando início...\n",
        multiline=True,
        read_only=True,
        min_lines=10,
        max_lines=10,
        text_size=12,
        bgcolor=ft.Colors.GREY_100,
        expand=True
    )

    progress_bar = ft.ProgressBar(width=400, value=0, color=ft.Colors.GREEN)
    progress_text = ft.Text("0/0 (0%)", size=12, weight="bold")
    status_indicator = ft.Text("Status: Parado", size=12, color=ft.Colors.GREY_700)

    # 2. File Picker e Tabela de Preview
    file_picker = ft.FilePicker(on_result=lambda e: atualizar_arquivo(e))
    page.overlay.append(file_picker)
    selected_file_text = ft.Text("Nenhum CSV selecionado", italic=True, color=ft.Colors.RED)
    
    # Tabela de dados
    data_table = ft.DataTable(
        columns=[
            ft.DataColumn(ft.Text("Original (CSV)")),
            ft.DataColumn(ft.Text("Formatado (Envio)")),
            ft.DataColumn(ft.Text("Nome Detectado")),
        ],
        rows=[],
        border=ft.border.all(1, ft.Colors.GREY_300),
        vertical_lines=ft.border.BorderSide(1, ft.Colors.GREY_200),
        heading_row_color=ft.Colors.BLUE_50,
    )

    def atualizar_arquivo(e: ft.FilePickerResultEvent):
        if e.files:
            path = e.files[0].path
            selected_file_text.value = path
            selected_file_text.color = ft.Colors.BLACK
            add_log(f"📂 Lendo CSV: {e.files[0].name}")
            
            # Lógica de Leitura e Preview
            try:
                with open(path, 'r', encoding='utf-8') as f:
                    leitor = csv.reader(f, delimiter=';')
                    rows_view = []
                    count = 0
                    for row in leitor:
                        if not row: continue
                        count += 1
                        # Dados originais
                        orig_num = row[0]
                        orig_nome = row[1] if len(row) > 1 else "-"
                        
                        # Formatação simulada
                        fmt_num = formatar_numero_preview(orig_num)
                        
                        # Adiciona na tabela visual
                        rows_view.append(ft.DataRow(cells=[
                            ft.DataCell(ft.Text(orig_num)),
                            ft.DataCell(ft.Text(fmt_num, weight="bold", color=ft.Colors.BLUE)),
                            ft.DataCell(ft.Text(orig_nome)),
                        ]))
                    
                    data_table.rows = rows_view
                    add_log(f"✅ Pré-visualização gerada para {count} contatos.")
            except Exception as err:
                add_log(f"❌ Erro ao ler CSV: {err}")
                data_table.rows = []

        else:
            selected_file_text.value = "Nenhum arquivo selecionado"
            data_table.rows = []
        
        page.update()

    # 3. Input Mensagem e Ajuda (RESTAURADA)
    def update_preview(e):
        markdown_preview.value = message_input.value
        page.update()

    message_input = ft.TextField(
        label="Mensagem para envio",
        multiline=True,
        min_lines=6,
        on_change=update_preview,
        hint_text="Olá {nome}, tudo bem?"
    )

    # PAINEL DE AJUDA COMPLETO
    help_panel = ft.Container(
        content=ft.Column([
            ft.Text("ℹ️ Comandos Disponíveis na Mensagem:", weight="bold", size=14),
            ft.Text("• {nome} : Substitui pelo nome do contato (se houver no CSV).", size=12),
            ft.Text("• {texto1|texto2} : Escolhe aleatoriamente uma das opções (Spintax).", size=12),
            ft.Text("  Exemplo: \"{Olá|Oi} {nome}, {tudo bem?|como vai?}\"", size=12, italic=True, color=ft.Colors.BLUE_GREY),
            ft.Text("• *Negrito*, _Itálico_, ~Riscado~ : Formatação padrão do WhatsApp.", size=12),
        ], spacing=2),
        padding=10,
        bgcolor=ft.Colors.BLUE_50,
        border_radius=5,
        border=ft.border.all(1, ft.Colors.BLUE_100)
    )

    markdown_preview = ft.Markdown(
        value="Preview...",
        selectable=True,
        extension_set=ft.MarkdownExtensionSet.GITHUB_WEB
    )

    # 4. Botões
    def start_click(e):
        nonlocal bot_thread
        if "Nenhum" in selected_file_text.value:
            add_log("❌ Selecione um CSV primeiro.")
            return
        if not message_input.value.strip():
            add_log("❌ Digite uma mensagem.")
            return

        btn_start.disabled = True
        btn_pause.disabled = False
        btn_stop.disabled = False
        
        bot_thread = WhatsappBotThread(
            csv_path=selected_file_text.value,
            message_template=message_input.value,
            log_callback=add_log,
            progress_callback=update_progress_ui,
            on_finish_callback=on_bot_finish
        )
        bot_thread.start()
        page.update()

    def pause_click(e):
        if bot_thread and bot_thread.is_running:
            if bot_thread.is_paused:
                bot_thread.resume()
                btn_pause.text = "Pausar"
                btn_pause.icon = ft.Icons.PAUSE
            else:
                bot_thread.pause()
                btn_pause.text = "Continuar"
                btn_pause.icon = ft.Icons.PLAY_ARROW
            page.update()

    def stop_click(e):
        if bot_thread and bot_thread.is_running:
            bot_thread.stop()
            btn_stop.disabled = True
            add_log("⚠️ Parando...")
            page.update()

    btn_file = ft.ElevatedButton("Carregar Lista (CSV)", icon=ft.Icons.UPLOAD_FILE, 
                                 on_click=lambda _: file_picker.pick_files(allow_multiple=False, allowed_extensions=["csv"]))
    btn_start = ft.ElevatedButton("INICIAR DISPAROS", icon=ft.Icons.ROCKET_LAUNCH, 
                                  on_click=start_click, bgcolor=ft.Colors.GREEN, color=ft.Colors.WHITE)
    btn_pause = ft.ElevatedButton("Pausar", icon=ft.Icons.PAUSE, on_click=pause_click, disabled=True)
    btn_stop = ft.ElevatedButton("PARAR", icon=ft.Icons.STOP, on_click=stop_click, disabled=True, bgcolor=ft.Colors.RED_100, color=ft.Colors.RED)

    # --- LAYOUT PRINCIPAL (SEM NUMERAÇÃO) ---
    page.add(
        ft.Row([
            # ESQUERDA: Configuração e Logs (Largura Fixa)
            ft.Container(
                width=450,
                padding=10,
                content=ft.Column([
                    ft.Text("Configurações & Logs", size=18, weight="bold"),
                    btn_file,
                    selected_file_text,
                    ft.Divider(),
                    
                    ft.Text("Controles", size=16),
                    ft.Row([btn_start, btn_pause, btn_stop], alignment=ft.MainAxisAlignment.CENTER),
                    ft.Divider(),

                    status_indicator,
                    progress_text,
                    progress_bar,
                    ft.Divider(),
                    
                    ft.Text("Log de Execução:", weight="bold"),
                    log_text
                ], scroll=ft.ScrollMode.AUTO)
            ),
            ft.VerticalDivider(width=1),
            
            # DIREITA: Editor e Preview de Dados (Expansível)
            ft.Container(
                expand=True,
                padding=10,
                # ALIGNMENT=START força o conteúdo para o topo
                content=ft.Column([
                    # Seção Editor
                    ft.Text("Edição da Mensagem", size=18, weight="bold"),
                    message_input,
                    help_panel,
                    ft.Text("Visualização:", weight="bold", color=ft.Colors.GREEN, size=12),
                    ft.Container(
                        content=markdown_preview,
                        padding=10,
                        bgcolor=ft.Colors.GREEN_50,
                        border_radius=5,
                        border=ft.border.all(1, ft.Colors.GREEN_200)
                    ),
                    ft.Divider(),
                    
                    # Seção Dados (Nova)
                    ft.Text("Pré-visualização da Lista (Dados Formatados)", size=18, weight="bold"),
                    ft.Text("Verifique se os números formatados estão com DDI+DDD+NUMERO (ex: 55629...)", size=12, color=ft.Colors.GREY),
                    
                    # Container com scroll apenas para a tabela
                    ft.Container(
                        content=ft.Column([data_table], scroll=ft.ScrollMode.ALWAYS),
                        height=300, # Altura fixa para a tabela ter scroll próprio
                        border=ft.border.all(1, ft.Colors.GREY_300),
                        border_radius=5,
                    )
                ], 
                alignment=ft.MainAxisAlignment.START, # FIXA NO TOPO
                scroll=ft.ScrollMode.AUTO
                )
            )
        ], expand=True)
    )

if __name__ == "__main__":
    ft.app(target=main)