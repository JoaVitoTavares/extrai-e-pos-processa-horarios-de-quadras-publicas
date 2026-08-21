"""Parâmetros ajustáveis da coleta."""

URL_ARENA = "https://webarena.app/arena/sp-sports"
API_INIT = "https://webarena.app/api/1.1/init/data"
API_CLIMA = "https://api.open-meteo.com/v1/forecast"

LATITUDE = -29.9128
LONGITUDE = -51.1836
FUSO_HORARIO = "America/Sao_Paulo"

TIPOS_QUADRA = ["Vôlei de praia", "Futebol de salão", "Grama 7", "Grama 5"]
PERIODOS_PADRAO = ["Manhã", "Tarde", "Noite"]
TIMEOUT_NAVEGACAO_MS = 30_000
DIAS_A_FRENTE = 14

DIRETORIO_EXTRACOES = ".extracoes"

HORAS_ANTES_DA_RESERVA = 4
HORAS_ATE_A_RESERVA = 1
TOLERANCIA_LEITURA_CLIMA_MIN = 60
