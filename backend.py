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
        # Salva o perfil do navegador na pasta do projeto para manter o login
        dir_path = os.getcwd()
        profile_path = os.path.join(dir_path, "chrome_profile")
        options.add_argument(f"user-data-dir={profile_path}")
        
        # Flags para evitar detecção básica de bot
        options.add_argument("--start-maximized")
        options.add_argument("--disable-infobars")
        options.add_argument("--disable-extensions")
        
        service = Service(ChromeDriverManager().install())
        self.driver = webdriver.Chrome(service=service, options=options)
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
            
            # --- CORREÇÃO DE ORDEM (CRUCIAL) ---
            # 1º Passo: Substitui o {nome} ANTES de rodar o spintax
            # Assim garantimos que o {nome} não seja confundido com uma variação
            msg_com_nome = mensagem_base.replace("{nome}", nome if nome else "")
            
            # 2º Passo: Resolve as variações {Opa|Olá}
            mensagem_final = self.resolver_spintax(msg_com_nome)
            
            # Codifica a mensagem para URL
            texto_encoded = urllib.parse.quote(mensagem_final)
            link = f"https://web.whatsapp.com/send?phone={numero_formatado}&text={texto_encoded}"
            
            self.driver.get(link)
            
            # Definição de Timeouts (Lógica que já criamos antes)
            tempo_limite = 60 if primeiro_envio else 20
            wait_local = WebDriverWait(self.driver, tempo_limite)

            try:
                # Espera a caixa de texto aparecer
                caixa_texto = wait_local.until(EC.presence_of_element_located(
                    (By.XPATH, '//*[@id="main"]/footer//div[@contenteditable="true"]')
                ))
            except:
                time.sleep(2)
                if "número de telefone compartilhado através de url é inválido" in self.driver.page_source.lower():
                    return False, "Número inválido/não tem WhatsApp"
                return False, "Timeout ao carregar chat (Interface demorou muito)"

            # Delay de "pensando"
            time.sleep(random.uniform(2, 4))
            
            # Envio
            caixa_texto.click()
            time.sleep(0.5)
            caixa_texto.send_keys(Keys.ENTER)
            
            # Tempo pós envio
            tempo_pos_envio = 10 if primeiro_envio else random.uniform(2, 4)
            time.sleep(tempo_pos_envio)
            
            if caixa_texto.text.strip() == "":
                return True, "Enviado com sucesso"
            else:
                return False, "Falha ao clicar em enviar"

        except Exception as e:
            return False, f"Erro crítico: {str(e)}"
        
    def fechar(self):
        if self.driver:
            self.driver.quit()