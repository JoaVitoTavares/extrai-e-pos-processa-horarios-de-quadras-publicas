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
    {
        "nome": "AABB Camaquã",
        "url": "https://webarena.app/arena/aabb-camaqua",
        "tipos": ["Handebol"],
    },
    {
        "nome": "Arena Grings",
        "url": "https://webarena.app/arena/arena-grings",
        "tipos": ["Beach Tennis"],
    },
    {
        "nome": "Arena Santi",
        "url": "https://webarena.app/arena/arena-santi",
        "tipos": ["Beach Tennis"],
    },
    {
        "nome": "Arena Total 90",
        "url": "https://webarena.app/arena/arena-total-90",
        "tipos": ["Society 5"],
    },
    {
        "nome": "Arena Trescopark",
        "url": "https://webarena.app/arena/arena-trescopark",
        "tipos": ["Vôlei de praia"],
    },
    {
        "nome": "Arena Yes Play",
        "url": "https://webarena.app/arena/arena-yes-play",
        "tipos": ["Vôlei de praia"],
    },
    {
        "nome": "Na 5 Beach Sport",
        "url": "https://webarena.app/arena/arenacinco",
        "tipos": ["Beach Tennis"],
    },
    {
        "nome": "Beach Brasil",
        "url": "https://webarena.app/arena/beach-brasil",
        "tipos": ["Futevôlei"],
    },
    {
        "nome": "Beach Place Poa",
        "url": "https://webarena.app/arena/beach-place-poa",
        "tipos": ["Beach Tennis"],
    },
    {
        "nome": "Casarão NH Sports",
        "url": "https://webarena.app/arena/casarao-nh-sports",
        "tipos": ["Futebol society"],
    },
    {
        "nome": "Complexo Rams",
        "url": "https://webarena.app/arena/complexo-rams",
        "tipos": ["Futebol society"],
    },
    {
        "nome": "CT Belotto",
        "url": "https://webarena.app/arena/ct-belotto",
        "tipos": ["Beach Tennis"],
    },
    {
        "nome": "CT Kliks",
        "url": "https://webarena.app/arena/ct-kliks",
        "tipos": ["Beach Tennis"],
    },
    {
        "nome": "Esporte e Lazer Fênix",
        "url": "https://webarena.app/arena/esporte-e-lazer-fenix",
        "tipos": ["Futebol society"],
    },
    {
        "nome": "Ginásio Bigornão Futsal",
        "url": "https://webarena.app/arena/ginasio-bigornao-futsal",
        "tipos": ["Futebol de salão"],
    },
    {
        "nome": "Gol de Placa",
        "url": "https://webarena.app/arena/gol-de-placa",
        "tipos": ["Futebol society"],
    },
    {
        "nome": "Home Sports Bar",
        "url": "https://webarena.app/arena/home-sports-bar",
        "tipos": ["Futebol society"],
    },
    {
        "nome": "MB Arena",
        "url": "https://webarena.app/arena/mb-arena",
        "tipos": ["Beach Tennis"],
    },
    {
        "nome": "Mundial Society Club",
        "url": "https://webarena.app/arena/mundial-society-club",
        "tipos": ["Futebol society"],
    },
    {
        "nome": "My Beach Sport",
        "url": "https://webarena.app/arena/my-beach-sport",
        "tipos": ["Beach Tennis"],
    },
    {
        "nome": "Playpadel",
        "url": "https://webarena.app/arena/playpadel",
        "tipos": ["Padel"],
    },
    {
        "nome": "Racket Garden",
        "url": "https://webarena.app/arena/racket-garden",
        "tipos": ["Beach Tennis"],
    },
    {
        "nome": "Ravena Beach",
        "url": "https://webarena.app/arena/ravena-beach",
        "tipos": ["Futevôlei"],
    },
    {
        "nome": "Table Tennis Place",
        "url": "https://webarena.app/arena/table-tennis-place",
        "tipos": ["Tênis de mesa"],
    },
    {
        "nome": "Vila Society",
        "url": "https://webarena.app/arena/vila-society",
        "tipos": ["Beach Tennis"],
    },
]

API_INIT_PATH = "/api/1.1/init/data"
API_CLIMA = "https://api.open-meteo.com/v1/forecast"
API_GEOCODIFICACAO = "https://nominatim.openstreetmap.org/search"
IDENTIFICACAO_GEOCODIFICACAO = "extrator-quadras-tcc/1.0"
PAIS_DAS_ARENAS = "br"
FUSO_HORARIO = "America/Sao_Paulo"

COURT_TYPES = ["Vôlei de praia", "Futebol de salão", "Grama 7", "Grama 5"]
DEFAULT_PERIODS = ["Manhã", "Tarde", "Noite"]
NAVIGATION_TIMEOUT_MS = 30_000
DAYS_AHEAD = 5
ARENAS_EM_PARALELO = 4

DIRETORIO_EXTRACOES = ".extracoes"
DIRETORIO_LOGS = ".logs"
ARQUIVO_DE_VERIFICACOES = "verificacoes.csv"

HORAS_ANTES_DA_RESERVA = 4
HORAS_ATE_A_RESERVA = 1
TOLERANCIA_LEITURA_CLIMA_MIN = 60
