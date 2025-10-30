#!/usr/bin/env bash
set -e

VENV_DIR=".venv"

echo
echo "[1/4] Criando ambiente virtual em $VENV_DIR ..."
python3 -m venv "$VENV_DIR"

echo
echo "[2/4] Ativando ambiente virtual ..."
# shellcheck disable=SC1091
source "$VENV_DIR/bin/activate"

echo
echo "[3/4] Atualizando pip ..."
python -m pip install --upgrade pip

echo
echo "[4/4] Instalando dependencias ..."
pip install -r requirements.txt

echo
echo "=========================================="
echo "Ambiente pronto!"
echo "Para rodar:"
echo "  source $VENV_DIR/bin/activate"
echo '  python broadcast_wa_web.py --csv contatos.csv --message "Oi {nome}"'
echo "=========================================="
