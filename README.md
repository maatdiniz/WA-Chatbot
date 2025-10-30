# 💬 WA Chatbot — Disparo via WhatsApp Web (Automação local com Selenium)

Automação de envio de mensagens pelo **WhatsApp Web**, feita em **Python + Selenium**,  
com controle de tempo, logs, CSV de resultados e suporte a perfis persistentes do Chrome.

> ⚠️ Este projeto é apenas para fins educacionais e testes locais.  
> O uso de automação para mensagens comerciais em massa pode violar os **Termos de Serviço do WhatsApp**.

---

## 🚀 Funcionalidades

✅ Abre o WhatsApp Web **uma única vez** (mantém sessão ativa com perfil salvo)  
✅ Busca o contato **sem recarregar a página** (via barra de pesquisa interna)  
✅ Faz fallback automático via link apenas se o número não estiver salvo  
✅ Cola e envia mensagens (ENTER / botão / Ctrl+Enter)  
✅ Gera **log completo** e **CSV de resultados** com status e motivos  
✅ Suporta placeholders de mensagem (ex.: `{nome}`)  
✅ Controla tempo mínimo e máximo entre envios (para evitar bloqueios)  

---

## 📂 Estrutura sugerida


````yaml
WA Chatbot/
│
├── broadcast_wa_web.py # Script principal
├── contatos.csv # Lista de contatos
├── requirements.txt # (opcional) Dependências
├── .gitignore
├── README.md
│
├── logs/ # Logs e resultados (gerados automaticamente)
│ ├── broadcast_wa_web.log
│ ├── results_20251029_1530.csv
│
└── wa-profile/ # (opcional) perfil persistente do Chrome
````

---

## ⚙️ Instalação

> Requer **Python 3.10+**

```bash
pip install selenium pyperclip webdriver-manager
```


Se quiser automatizar a instalação:

```bash
pip install -r requirements.txt
```

Conteúdo recomendado de requirements.txt:
````nginx
selenium
pyperclip
webdriver-manager
````

🧾 CSV de contatos

O arquivo contatos.csv deve ter o seguinte formato:
````csv
telefone,nome
62999999999,João
62988888888,Maria
````

O script automaticamente converte para o formato internacional (55DDD...).

O campo {nome} pode ser usado dentro da mensagem para personalização.

▶️ Execução

Comando padrão:
````bash
python broadcast_wa_web.py --csv contatos.csv --message "Olá {nome}, tudo bem?"
````

Exemplos de uso:

✅ Usar perfil persistente do Chrome (mantém login entre execuções):
````bash
python broadcast_wa_web.py --csv contatos.csv --message "Oi {nome}!" --profile "C:\Users\SeuUsuario\wa-profile"
````

✅ Personalizar tempo entre envios:
````bash
python broadcast_wa_web.py --csv contatos.csv --message "Oi {nome}!" --min-delay 3 --max-delay 8
````

✅ Gerar logs e CSVs em pastas específicas:
````bash
python broadcast_wa_web.py --csv contatos.csv --message "Teste {nome}" --log-file "logs\wa.log" --results-csv "logs\resultados.csv"
````

🧠 Parâmetros principais
| Parâmetro                             | Descrição                                            | Padrão                        |
| ------------------------------------- | ---------------------------------------------------- | ----------------------------- |
| `--csv`                               | Caminho do arquivo de contatos (`telefone,nome`)     | —                             |
| `--message`                           | Mensagem com placeholders (ex.: `"Olá {nome}"`)      | —                             |
| `--profile`                           | Caminho da pasta de perfil do Chrome (mantém sessão) | `None`                        |
| `--min-delay` / `--max-delay`         | Intervalo aleatório entre envios (segundos)          | `2.0 / 6.0`                   |
| `--min-wait-chat` / `--max-wait-chat` | Espera antes de colar mensagem                       | `1.2 / 3.5`                   |
| `--retries`                           | Tentativas extras de envio por contato               | `2`                           |
| `--log-file`                          | Caminho do log de execução                           | `broadcast_wa_web.log`        |
| `--results-csv`                       | CSV de resultados (criado se não existir)            | `results_YYYYMMDD_HHMMSS.csv` |

📊 Logs e Resultados

Log: tudo é registrado em tempo real no terminal e no arquivo broadcast_wa_web.log

Resultados: o script gera um CSV com colunas:

````csv
timestamp,telefone,nome,status,motivo
2025-10-29 15:30:02,5562999999999,João,enviado,enter_ok
2025-10-29 15:30:10,5562888888888,Maria,falha,nao_enviado
````

🧩 Recomendado

Criar uma pasta separada (wa-profile/) para manter a sessão logada do WhatsApp Web.

Evitar rodar múltiplas instâncias simultâneas.

Respeitar limites naturais de tempo entre envios.

Fazer testes locais com poucos contatos antes de rodar listas grandes.

🧩 Recomendado

Criar uma pasta separada (wa-profile/) para manter a sessão logada do WhatsApp Web.

Evitar rodar múltiplas instâncias simultâneas.

Respeitar limites naturais de tempo entre envios.

Fazer testes locais com poucos contatos antes de rodar listas grandes.

⚖️ Aviso Legal

>Este projeto é destinado a fins de estudo e uso pessoal.
>O uso comercial ou em massa pode violar os Termos de Serviço do WhatsApp / Meta.
>O autor não se responsabiliza por bloqueios ou sanções aplicadas a contas que usem esta automação de forma indevida.

📄 Licença

MIT License © 2025
Desenvolvido por Matheus Diniz Amorim