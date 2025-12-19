import time
import random
import os
import urllib.parse
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from webdriver_manager.chrome import ChromeDriverManager
from selenium.webdriver.chrome.service import Service

class WhatsAppDriver:
    def __init__(self):
        self.driver = None
        self.wait = None
    
    def resolver_spintax(self, texto):
        import re
        import random
        # Regex para encontrar conteúdo dentro de {}
        padrao = r'\{([^{}]+)\}'
        
        def substituir(match):
            conteudo = match.group(1)
            # CORREÇÃO: Aceita tanto pipe "|" quanto barra "/" como separador
            if '|' in conteudo:
                opcoes = conteudo.split('|')
            elif '/' in conteudo:
                opcoes = conteudo.split('/')
            else:
                opcoes = [conteudo] # Caso não tenha separador, retorna o próprio texto
            
            return random.choice(opcoes).strip()
        
        return re.sub(padrao, substituir, texto)

    def iniciar_driver(self):
        options = Options()
        dir_path = os.getcwd()
        profile_path = os.path.join(dir_path, "chrome_profile")
        options.add_argument(f"user-data-dir={profile_path}")
        
        # --- NOVAS FLAGS ANTI-BLOQUEIO ---
        # Esconde que é automação
        options.add_argument("--disable-blink-features=AutomationControlled") 
        options.add_experimental_option("excludeSwitches", ["enable-automation"])
        options.add_experimental_option('useAutomationExtension', False)
        
        # User-Agent de navegador real (simula um Chrome normal de usuário)
        options.add_argument("user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36")
        
        options.add_argument("--start-maximized")
        options.add_argument("--disable-infobars")
        options.add_argument("--disable-extensions")
        
        service = Service(ChromeDriverManager().install())
        self.driver = webdriver.Chrome(service=service, options=options)
        
        # Truque extra para remover a propriedade 'webdriver' do navegador via JavaScript
        self.driver.execute_script("Object.defineProperty(navigator, 'webdriver', {get: () => undefined})")
        
        self.wait = WebDriverWait(self.driver, 20)
        
        self.driver.get("https://web.whatsapp.com")
        return self.driver

    def formatar_numero(self, numero_raw):
        """
        Limpa o número e garante o formato 55 + DDD + Numero.
        Não insere o dígito 9, apenas o DDD 62 se estiver faltando.
        """
        # Remove caracteres não numéricos
        nums = "".join([n for n in str(numero_raw) if n.isdigit()])
        
        # Lógica de Auto-completar DDD (Assume 62 se vier sem)
        
        # Caso 1: Tem 8 dígitos (Fixo ou Celular antigo sem DDD) -> Vira 62 + 8 dígitos
        if len(nums) == 8:
            nums = f"62{nums}"
            
        # Caso 2: Tem 9 dígitos (Celular sem DDD) -> Vira 62 + 9 dígitos
        elif len(nums) == 9:
            nums = f"62{nums}"
            
        # Adiciona o DDI do Brasil (55) se o número tiver 10 (Fixo+DDD) ou 11 (Cel+DDD) dígitos
        if len(nums) in [10, 11]: 
            nums = f"55{nums}"
            
        return nums

    def digitar_como_humano(self, elemento, texto):
        """
        Digita caractere por caractere com delay aleatório
        """
        for char in texto:
            elemento.send_keys(char)
            # Delay aleatório entre 0.05 e 0.2 segundos por letra
            time.sleep(random.uniform(0.05, 0.2))

    def enviar_mensagem(self, numero, nome, mensagem_base, primeiro_envio=False):
        try:
            numero_formatado = self.formatar_numero(numero)
            
            # Prepara a mensagem
            msg_com_nome = mensagem_base.replace("{nome}", nome if nome else "")
            mensagem_final = self.resolver_spintax(msg_com_nome)
            
            # --- MUDANÇA CRUCIAL: NÃO ENVIAR TEXTO PELA URL ---
            # Removemos o &text=... para obrigar o robô a digitar
            link = f"https://web.whatsapp.com/send?phone={numero_formatado}"
            
            self.driver.get(link)
            
            tempo_limite = 60 if primeiro_envio else 20
            wait_local = WebDriverWait(self.driver, tempo_limite)

            try:
                # Espera a caixa de texto aparecer e ser clicável
                caixa_texto = wait_local.until(EC.element_to_be_clickable(
                    (By.XPATH, '//*[@id="main"]/footer//div[@contenteditable="true"]')
                ))
            except:
                time.sleep(2)
                # Verifica erro de número inválido
                if "número de telefone compartilhado através de url é inválido" in self.driver.page_source.lower():
                    return False, "Número inválido/não tem WhatsApp"
                # Tenta um seletor alternativo (às vezes o WhatsApp muda o DOM)
                try:
                    caixa_texto = self.driver.find_element(By.CSS_SELECTOR, "div[role='textbox']")
                except:
                    return False, "Timeout: Caixa de texto não encontrada"

            # Delay humano antes de começar a digitar ("Lendo a conversa anterior")
            time.sleep(random.uniform(1.5, 3))
            
            # Clica para focar
            caixa_texto.click()
            
            # --- DIGITAÇÃO HUMANIZADA ---
            # Usa sua função existente para digitar caractere por caractere
            # Isso simula o evento de teclado real (keydown/keyup)
            self.digitar_como_humano(caixa_texto, mensagem_final)
            
            # Delay "conferindo o que escreveu" antes de enviar
            time.sleep(random.uniform(0.5, 1.5))
            
            # Envio
            caixa_texto.send_keys(Keys.ENTER)
            
            # Tempo pós envio
            tempo_pos_envio = 10 if primeiro_envio else random.uniform(3, 6)
            time.sleep(tempo_pos_envio)
            
            return True, "Enviado com sucesso (Digitado)"

        except Exception as e:
            print(f"Erro detalhado: {e}") # Ajuda no debug
            return False, f"Erro crítico: {str(e)}"
        
    def fechar(self):
        if self.driver:
            self.driver.quit()