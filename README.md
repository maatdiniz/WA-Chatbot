# 💬 WA Chatbot — Disparo via WhatsApp Web (Automação local com Selenium + Flet)

Automação de envio de mensagens pelo **WhatsApp Web**, feita em **Python + Selenium**,  
com interface gráfica em **Flet**, controle de tempo, logs, CSV de resultados e suporte a perfil persistente do Chrome.

> ⚠️ Este projeto é apenas para fins educacionais e testes locais.  
> O uso de automação para mensagens comerciais em massa pode violar os **Termos de Serviço do WhatsApp**.

---

## 🚀 Funcionalidades

✅ Abre o WhatsApp Web **uma única vez** (mantém sessão ativa com perfil salvo)  
✅ Envia mensagens digitando de forma humanizada (evita bloco por automação)  
✅ Gera **log completo** e **CSV de resultados** com status e motivos  
✅ Suporta placeholders de mensagem (ex.: `{nome}`) e spintax `{Olá|Oi}`  
✅ Controla tempo mínimo e máximo entre envios (para evitar bloqueios)  
✅ Interface visual para carregar CSV, editar mensagem e acompanhar progresso

---

## 📂 Estrutura


````yaml
WA Chatbot/
│
├── app.py            # Aplicação principal com GUI (Flet)
├── backend.py        # Lógica de envio (Selenium)
├── contatos.csv      # Lista de contatos (CSV com ';')
├── requirements.txt  # Dependências Python
├── setup.sh          # Setup automático do venv e instalação
├── README.md
│
└── chrome_profile/   # Perfil persistente do Chrome (criado automaticamente)
````

---

## ⚙️ Instalação

Pré‑requisitos:
- **Python 3.9+**
- **Google Chrome** instalado (ChromeDriver é baixado automaticamente pelo `webdriver-manager`)

Com Homebrew (opcional):
```bash
brew install --cask google-chrome
```

Usando o script de setup:
```bash
cd /Users/mattdiniz/Dev/WA-Chatbot
bash setup.sh
source .venv/bin/activate
```

Instalação manual (sem Homebrew e sem script):
```bash
cd /Users/mattdiniz/Dev/WA-Chatbot
python3 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
pip install -r requirements.txt
```

`requirements.txt` contém:
````nginx
selenium
pyperclip
webdriver-manager
flet
````

---

## 🧾 CSV de contatos

Formato esperado (delimitado por ponto e vírgula `;`):
````csv
telefone;nome
62999999999;João
62988888888;Maria
````

Os números são convertidos automaticamente para o formato internacional `55 + DDD + número`.
Você pode usar `{nome}` na mensagem para personalizar.

---

## ▶️ Execução

Abrir a interface (GUI) e iniciar os disparos:
````bash
cd /Users/mattdiniz/Dev/WA-Chatbot
source .venv/bin/activate
python app.py
````

Alternativa (CLI do Flet):
````bash
source .venv/bin/activate
python -m flet run app.py
````

Na primeira execução, faça login no WhatsApp Web (QR Code). O perfil é salvo em `chrome_profile/`.

---

## 🧠 Observações de funcionamento
- O envio é feito digitando na caixa de texto do WhatsApp Web (simulação humana).
- O perfil do Chrome é persistido automaticamente em `chrome_profile/`.
- Pausas aleatórias são aplicadas entre envios e a cada lote para reduzir risco de bloqueio.

---

## 📊 Logs e Resultados

Durante a execução, a interface exibe o log. Além disso, é gerado um CSV de relatório, por exemplo `relatorio_envios_YYYYMMDD_HHMMSS.csv`, com as colunas:

````csv
Telefone;Nome;Status;Detalhes;DataHora
5562999999999;João;SUCESSO;Enviado com sucesso (Digitado);15:30:02
5562888888888;Maria;FALHA;Número inválido/não tem WhatsApp;15:30:10
````

---

## 🧩 Recomendado

Criar uma pasta separada (wa-profile/) para manter a sessão logada do WhatsApp Web.

Evitar rodar múltiplas instâncias simultâneas.

Respeitar limites naturais de tempo entre envios.

Fazer testes locais com poucos contatos antes de rodar listas grandes.

---

## ⚖️ Aviso Legal

>Este projeto é destinado a fins de estudo e uso pessoal.
>O uso comercial ou em massa pode violar os Termos de Serviço do WhatsApp / Meta.
>O autor não se responsabiliza por bloqueios ou sanções aplicadas a contas que usem esta automação de forma indevida.

---

## 📄 Licença

MIT License © 2026
Desenvolvido por Matheus Diniz Amorim