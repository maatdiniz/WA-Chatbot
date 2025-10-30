param(
  [string]$VenvName = ".venv"
)

Write-Host "`n[1/4] Criando ambiente virtual: $VenvName" -ForegroundColor Cyan
python -m venv $VenvName
if (!$?) { throw "Falha ao criar venv. Verifique se o Python está no PATH." }

Write-Host "`n[2/4] Ativando venv..." -ForegroundColor Cyan
$activate = Join-Path $VenvName "Scripts\Activate.ps1"
. $activate

Write-Host "`n[3/4] Atualizando pip..." -ForegroundColor Cyan
python -m pip install --upgrade pip

Write-Host "`n[4/4] Instalando dependências (requirements.txt)..." -ForegroundColor Cyan
pip install -r requirements.txt
if (!$?) { throw "Falha ao instalar dependências." }

Write-Host "`nAmbiente pronto!" -ForegroundColor Green
Write-Host "Para rodar:" -ForegroundColor Yellow
Write-Host "  .\$VenvName\Scripts\Activate.ps1"
Write-Host '  python broadcast_wa_web.py --csv contatos.csv --message "Oi {nome}"'
