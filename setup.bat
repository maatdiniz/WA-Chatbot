@echo off
setlocal

REM ===== Caminho do projeto (pasta atual) =====
set PROJECT_DIR=%~dp0

REM ===== Nome do ambiente virtual =====
set VENV_DIR=%PROJECT_DIR%\.venv

echo.
echo [1/4] Criando ambiente virtual em %VENV_DIR% ...
python -m venv "%VENV_DIR%"
if %ERRORLEVEL% NEQ 0 (
  echo Falha ao criar o ambiente virtual. Verifique se o Python esta no PATH.
  pause
  exit /b 1
)

echo.
echo [2/4] Ativando ambiente virtual ...
call "%VENV_DIR%\Scripts\activate.bat"
if %ERRORLEVEL% NEQ 0 (
  echo Falha ao ativar a venv.
  pause
  exit /b 1
)

echo.
echo [3/4] Atualizando pip ...
python -m pip install --upgrade pip

echo.
echo [4/4] Instalando dependencias do requirements.txt ...
pip install -r "%PROJECT_DIR%requirements.txt"
if %ERRORLEVEL% NEQ 0 (
  echo Falha ao instalar dependencias.
  pause
  exit /b 1
)

echo.
echo ==========================================
echo Ambiente pronto!
echo Para rodar:
echo   %VENV_DIR%\Scripts\activate
echo   python broadcast_wa_web.py --csv contatos.csv --message "Oi {nome}"
echo ==========================================
echo.

pause
endlocal
