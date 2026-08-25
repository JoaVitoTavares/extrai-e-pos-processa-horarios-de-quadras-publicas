"""Parâmetros ajustáveis da coleta."""

ARENAS = [
    {"nome": "SP Sports", "url": "https://webarena.app/arena/sp-sports"},
    {
        "nome": "Arena Sabino Futebol Society",
        "url": "https://webarena.app/arena/arena-sabino-futebol-society",
        "tipos": ["Futebol society"],
    },
    {
        "nome": "Arena Grenal",
        "url": "https://webarena.app/arena/arena-grenal",
        "tipos": ["Futebol society"],
    },
    {
        "nome": "Arena Darc Sports",
        "url": "https://webarena.app/arena/arena-darc-sports",
        "tipos": ["Futebol society"],
    },
]

CAMINHO_API_INIT = "/api/1.1/init/data"
API_CLIMA = "https://api.open-meteo.com/v1/forecast"
API_GEOCODIFICACAO = "https://nominatim.openstreetmap.org/search"
IDENTIFICACAO_GEOCODIFICACAO = "extrator-quadras-tcc/1.0"
PAIS_DAS_ARENAS = "br"
FUSO_HORARIO = "America/Sao_Paulo"

TIPOS_QUADRA = ["Vôlei de praia", "Futebol de salão", "Grama 7", "Grama 5"]
PERIODOS_PADRAO = ["Manhã", "Tarde", "Noite"]
TIMEOUT_NAVEGACAO_MS = 30_000
DIAS_A_FRENTE = 5

DIRETORIO_EXTRACOES = ".extracoes"

HORAS_ANTES_DA_RESERVA = 4
HORAS_ATE_A_RESERVA = 1
TOLERANCIA_LEITURA_CLIMA_MIN = 60
