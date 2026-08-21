#!/usr/bin/env bash
set -uo pipefail

RAIZ="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
DIRETORIO_LOGS="$RAIZ/.logs"
ARQUIVO_TRAVA="/tmp/extrator-sp-sports.lock"
LIMITE_DE_EXECUCAO="12m"
DIAS_DE_LOG=14

export HOME="${HOME:-/home/tavares}"
export TZ="America/Sao_Paulo"
export LANG="${LANG:-C.UTF-8}"
export PATH="/usr/local/bin:/usr/bin:/bin"
export PYTHONUNBUFFERED=1

mkdir -p "$DIRETORIO_LOGS"
exec >>"$DIRETORIO_LOGS/extracao-$(date +%F).log" 2>&1

exec 9>"$ARQUIVO_TRAVA"
if ! flock -n 9; then
    echo "[$(date +%Y-%m-%dT%H:%M:%S)] pulado: a execução anterior ainda está em andamento"
    exit 0
fi

cd "$RAIZ" || exit 1

LEDGER="$DIRETORIO_LOGS/execucoes.csv"
[ -f "$LEDGER" ] || echo "instante,codigo,duracao_s" >"$LEDGER"

inicio=$(date +%s)
echo "===== início $(date +%Y-%m-%dT%H:%M:%S) ====="
timeout --signal=TERM --kill-after=60 "$LIMITE_DE_EXECUCAO" "$RAIZ/.venv/bin/python" main.py
codigo=$?
duracao=$(( $(date +%s) - inicio ))
echo "===== fim $(date +%Y-%m-%dT%H:%M:%S)  código=$codigo  duração=${duracao}s ====="

echo "$(date +%Y-%m-%dT%H:%M:%S),$codigo,$duracao" >>"$LEDGER"

if [ "$codigo" -ne 0 ]; then
    logger -t extrator-sp-sports -p user.err \
        "extração falhou com código $codigo; veja $DIRETORIO_LOGS/extracao-$(date +%F).log"
fi

find "$DIRETORIO_LOGS" -name 'extracao-*.log' -mtime +$DIAS_DE_LOG -delete

exit "$codigo"
