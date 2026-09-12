"""Testes do gerenciador: ordem das etapas, tolerância a falha e código de saída."""

import threading
from datetime import date

import pandas as pd
import pytest
import requests
from playwright.sync_api import TimeoutError as PWTimeout

import main
from extrator import arena_extractor
from extrator.config import ARENAS, DIRETORIO_EXTRACOES, DIRETORIO_LOGS, ARENAS_EM_PARALELO
from extrator.localizacao import resolver_local
from extrator.persistencia import salvar_extracao
from extrator.weather_collector import coletar_clima, coletar_previsao

ARENA = {"nome": "SP Sports", "url": "https://webarena.app/arena/sp-sports"}
OUTRA_ARENA = {"nome": "Arena Parobé", "url": "https://webarena.app/arena/parobe"}
LOCAL = {
    "endereco": "Boqueirão 2710, Canoas",
    "latitude": -29.9048885,
    "longitude": -51.1612496,
    "cidade": "Canoas",
    "origem": "Boqueirão 2710, Canoas",
}


def _que_falha(erro):
    def falhar(*args, **kwargs):
        raise erro
    return falhar


def quadra(nome="Areia 1 - Interna", horarios=None, aviso=None, data="2026-08-07"):
    return {
        "coletado_em": "2026-08-07T08:00:00",
        "data": data,
        "esporte": "Vôlei de praia",
        "periodo": "Noite",
        "quadra": nome,
        "tipo_quadra": "Vôlei de praia",
        "quadra_coberta": "true",
        "endereco": "Boqueirão 2710, Canoas",
        "aviso": aviso,
        "horarios": horarios if horarios is not None else [],
    }


@pytest.fixture(autouse=True)
def arena_unica(monkeypatch, tmp_path):
    monkeypatch.setattr(main, "ARENAS", [ARENA])
    monkeypatch.setattr(main, "DIRETORIO_EXTRACOES", str(tmp_path))
    monkeypatch.setattr(main, "DIRETORIO_LOGS", str(tmp_path))
    monkeypatch.setattr(main, "ARENAS_EM_PARALELO", 1)


@pytest.fixture(autouse=True)
def tratamento_dublado(monkeypatch):
    chamadas = []

    class TratamentoFalso:
        def __init__(self, *args, **kwargs):
            pass

        def aplicar(self, agora=None):
            chamadas.append("trata")
            return ["um.csv"]

    monkeypatch.setattr(arena_extractor, "TratamentoDeDados", TratamentoFalso)
    return chamadas


@pytest.fixture(autouse=True)
def clima_dublado(monkeypatch):
    monkeypatch.setattr(arena_extractor, "coletar_clima", lambda lat, lon, diretorio: "clima.csv")
    monkeypatch.setattr(arena_extractor, "coletar_previsao", lambda lat, lon, diretorio: "previsao.csv")
    monkeypatch.setattr(arena_extractor, "resolver_local", lambda endereco, diretorio, coordenadas: LOCAL)


@pytest.fixture
def etapas(monkeypatch, tratamento_dublado):
    ordem = tratamento_dublado
    monkeypatch.setattr(
        arena_extractor, "collect_courts",
        lambda arena, visible_browser=False, output=None: ordem.append("quadras") or [quadra()],
    )
    monkeypatch.setattr(
        arena_extractor, "resolver_local",
        lambda endereco, diretorio, coordenadas: ordem.append("local") or LOCAL,
    )
    monkeypatch.setattr(
        arena_extractor, "salvar_extracao",
        lambda r, diretorio, arena="", cidade="": ordem.append("grava") or ["um.csv"],
    )
    monkeypatch.setattr(
        arena_extractor, "coletar_clima", lambda lat, lon, diretorio: ordem.append("clima") or "clima.csv"
    )
    monkeypatch.setattr(
        arena_extractor, "coletar_previsao",
        lambda lat, lon, diretorio: ordem.append("previsao") or "previsao.csv",
    )
    return ordem


def test_etapas_rodam_na_ordem(etapas):
    main.main()

    assert etapas == ["quadras", "local", "grava", "clima", "previsao", "trata"]


def test_preparar_arena_tira_o_diretorio_da_url():
    arena = main.normalize_arena_info({"nome": "SP Sports", "url": "https://webarena.app/arena/sp-sports/"})

    assert arena["diretorio"].endswith("sp-sports")
    assert arena["nome"] == "SP Sports"


def test_arena_sem_nome_se_identifica_pela_url():
    arena = main.normalize_arena_info({"url": "https://webarena.app/arena/quadra-nova"})

    assert arena["nome"] == "quadra-nova"


def test_cada_arena_grava_no_seu_diretorio(monkeypatch, etapas):
    monkeypatch.setattr(main, "ARENAS", [ARENA, OUTRA_ARENA])
    diretorios = []
    monkeypatch.setattr(
        arena_extractor, "salvar_extracao",
        lambda r, diretorio, arena="", cidade="": diretorios.append(diretorio) or ["um.csv"],
    )

    main.main()

    assert len(set(diretorios)) == 2
    assert diretorios[0].endswith("sp-sports")
    assert diretorios[1].endswith("parobe")


def test_arena_carimba_nome_e_cidade_na_gravacao(monkeypatch):
    recebido = {}
    monkeypatch.setattr(
        arena_extractor, "collect_courts", lambda arena, visible_browser=False, output=None: [quadra()]
    )
    monkeypatch.setattr(
        arena_extractor, "salvar_extracao",
        lambda r, diretorio, arena="", cidade="": recebido.update(arena=arena, cidade=cidade)
        or ["um.csv"],
    )

    main.main()

    assert recebido == {"arena": "SP Sports", "cidade": "Canoas"}


def test_grava_o_que_o_coletor_devolveu(monkeypatch):
    coletado = [quadra(horarios=[{"hora": "17:00", "status": "Livre"}])]
    gravado = []
    monkeypatch.setattr(
        arena_extractor, "collect_courts", lambda arena, visible_browser=False, output=None: coletado
    )
    monkeypatch.setattr(
        arena_extractor, "salvar_extracao",
        lambda r, diretorio, arena="", cidade="": gravado.append(r) or ["um.csv"],
    )

    main.main()

    assert gravado == [coletado]


def test_clima_e_consultado_nas_coordenadas_da_arena(monkeypatch):
    consultado = {}
    monkeypatch.setattr(
        arena_extractor, "collect_courts", lambda arena, visible_browser=False, output=None: [quadra()]
    )
    monkeypatch.setattr(arena_extractor, "salvar_extracao", lambda r, diretorio, **kwargs: ["um.csv"])
    monkeypatch.setattr(
        arena_extractor, "coletar_clima",
        lambda lat, lon, diretorio: consultado.update(lat=lat, lon=lon, diretorio=diretorio)
        or "clima.csv",
    )

    main.main()

    assert (consultado["lat"], consultado["lon"]) == (LOCAL["latitude"], LOCAL["longitude"])
    assert consultado["diretorio"].endswith("sp-sports")


def test_arena_sem_local_nao_consulta_clima(monkeypatch):
    chamou = []
    monkeypatch.setattr(
        arena_extractor, "collect_courts", lambda arena, visible_browser=False, output=None: [quadra()]
    )
    monkeypatch.setattr(arena_extractor, "salvar_extracao", lambda r, diretorio, **kwargs: ["um.csv"])
    monkeypatch.setattr(arena_extractor, "resolver_local", lambda endereco, diretorio, coordenadas: None)
    monkeypatch.setattr(arena_extractor, "coletar_clima", lambda *a: chamou.append("clima") or "clima.csv")

    main.main()

    assert chamou == []


def test_falha_do_geocodificador_nao_derruba_a_execucao(monkeypatch, capsys):
    monkeypatch.setattr(
        arena_extractor, "collect_courts", lambda arena, visible_browser=False, output=None: [quadra()]
    )
    monkeypatch.setattr(arena_extractor, "salvar_extracao", lambda r, diretorio, **kwargs: ["um.csv"])
    monkeypatch.setattr(arena_extractor, "resolver_local", _que_falha(requests.ConnectionError("sem rede")))

    main.main()

    assert "endereço não geocodificado" in capsys.readouterr().err


def test_falha_no_clima_nao_derruba_a_execucao(monkeypatch, capsys):
    monkeypatch.setattr(
        arena_extractor, "collect_courts", lambda arena, visible_browser=False, output=None: [quadra()]
    )
    monkeypatch.setattr(arena_extractor, "salvar_extracao", lambda r, diretorio, **kwargs: ["um.csv"])
    monkeypatch.setattr(arena_extractor, "coletar_clima", _que_falha(requests.ConnectionError("sem rede")))

    main.main()

    assert "clima não coletado" in capsys.readouterr().err


def test_json_de_clima_invalido_tambem_e_tolerado(monkeypatch, capsys):
    monkeypatch.setattr(arena_extractor, "coletar_clima", _que_falha(ValueError("sem o bloco 'current'")))

    assert arena_extractor.record_weather(LOCAL, "qualquer") is None
    assert "clima não coletado" in capsys.readouterr().err


def test_arena_que_falha_nao_derruba_as_outras(monkeypatch, capsys):
    monkeypatch.setattr(main, "ARENAS", [ARENA, OUTRA_ARENA])
    monkeypatch.setattr(arena_extractor, "salvar_extracao", lambda r, diretorio, **kwargs: ["um.csv"])

    def coletar(arena, visible_browser=False, output=None):
        if arena["nome"] == "SP Sports":
            raise PWTimeout("tempo esgotado")
        return [quadra()]

    monkeypatch.setattr(arena_extractor, "collect_courts", coletar)
    main.main()

    assert "SP Sports" in capsys.readouterr().err


def test_arenas_rodam_ao_mesmo_tempo(monkeypatch):
    monkeypatch.setattr(main, "ARENAS", [ARENA, OUTRA_ARENA])
    monkeypatch.setattr(main, "ARENAS_EM_PARALELO", 2)
    monkeypatch.setattr(arena_extractor, "salvar_extracao", lambda r, diretorio, **kwargs: ["um.csv"])
    barreira = threading.Barrier(2, timeout=5)

    def coletar(arena, visible_browser=False, output=None):
        barreira.wait()
        return [quadra()]

    monkeypatch.setattr(arena_extractor, "collect_courts", coletar)

    main.main()


def test_saida_de_cada_arena_sai_num_bloco_so(monkeypatch, capsys):
    monkeypatch.setattr(main, "ARENAS", [ARENA, OUTRA_ARENA])
    monkeypatch.setattr(main, "ARENAS_EM_PARALELO", 2)
    monkeypatch.setattr(arena_extractor, "salvar_extracao", lambda r, diretorio, **kwargs: ["um.csv"])
    monkeypatch.setattr(
        arena_extractor, "collect_courts",
        lambda arena, visible_browser=False, output=None:
            print(f"marca de {arena['nome']}", file=output) or [quadra()],
    )

    main.main()
    linhas = [linha for linha in capsys.readouterr().out.splitlines() if linha.strip()]
    cabecalhos = [i for i, linha in enumerate(linhas) if linha.startswith("  ARENA:")]
    marcas = [i for i, linha in enumerate(linhas) if linha.startswith("marca de")]
    seguintes = cabecalhos[1:] + [len(linhas)]

    assert len(cabecalhos) == len(marcas) == 2
    assert all(
        cabecalho < marca < seguinte
        for cabecalho, marca, seguinte in zip(cabecalhos, marcas, seguintes)
    )
    assert all(
        linhas[cabecalho].split("ARENA: ")[1].startswith(linhas[marca].removeprefix("marca de "))
        for cabecalho, marca in zip(cabecalhos, marcas)
    )


def test_log_de_verificacoes_tem_uma_linha_por_arena(monkeypatch, tmp_path):
    monkeypatch.setattr(main, "ARENAS", [ARENA, OUTRA_ARENA])
    monkeypatch.setattr(arena_extractor, "salvar_extracao", lambda r, diretorio, **kwargs: ["um.csv"])
    monkeypatch.setattr(
        arena_extractor, "collect_courts",
        lambda arena, visible_browser=False, output=None: [
            quadra("Areia 2 - Externa"),
            quadra("Areia 1 - Interna"),
            quadra("Areia 1 - Interna", data="2026-08-08"),
        ],
    )

    main.main()
    df = pd.read_csv(tmp_path / "verificacoes.csv", dtype=str, keep_default_na=False)

    assert list(df["arena"]) == ["SP Sports", "Arena Parobé"]
    assert list(df["quadras_verificadas"]) == ["2", "2"]
    assert df.loc[0, "quadras"] == "Areia 1 - Interna; Areia 2 - Externa"
    assert df.loc[0, "ultima_verificacao"].startswith(date.today().isoformat())


def test_arena_que_falhou_aparece_no_log_sem_quadra_nenhuma(monkeypatch, tmp_path):
    monkeypatch.setattr(arena_extractor, "collect_courts", _que_falha(PWTimeout("tempo esgotado")))

    with pytest.raises(SystemExit):
        main.main()
    df = pd.read_csv(tmp_path / "verificacoes.csv", dtype=str, keep_default_na=False)

    assert list(df["arena"]) == ["SP Sports"]
    assert df.loc[0, "quadras_verificadas"] == "0"
    assert df.loc[0, "quadras"] == ""


def test_periodo_com_aviso_nao_entra_nas_quadras_verificadas():
    resultados = [
        quadra("Areia 1 - Interna"),
        quadra("Areia 2 - Externa", aviso="Não foi possível coletar os horários."),
    ]

    assert arena_extractor.ArenaExtractor.verified_court_names(resultados) == ["Areia 1 - Interna"]


def test_sai_com_erro_quando_nao_grava_nada(monkeypatch):
    monkeypatch.setattr(arena_extractor, "collect_courts", lambda arena, visible_browser=False, output=None: [])
    monkeypatch.setattr(arena_extractor, "salvar_extracao", lambda r, diretorio, **kwargs: [])

    with pytest.raises(SystemExit) as saida:
        main.main()

    assert saida.value.code == 1


def test_esporte_que_estoura_o_tempo_nao_derruba_os_outros(monkeypatch, capsys):
    monkeypatch.setattr(arena_extractor, "listar_esportes", lambda url_arena: ["Grama 7", "Grama 5"])
    monkeypatch.setattr(arena_extractor, "esportes_alvo", lambda esportes, tipos: esportes)
    monkeypatch.setattr(arena_extractor, "tipos_ausentes", lambda alvos, tipos: [])

    def coletar(esporte, url_arena, periodo=None, headless=True, tipos=None):
        if esporte == "Grama 7":
            raise PWTimeout("tempo esgotado")
        return [quadra(nome="Grama 5 - Interna")]

    monkeypatch.setattr(arena_extractor, "coletar_horarios", coletar)
    resultados = arena_extractor.collect_courts(main.normalize_arena_info(ARENA))

    assert [q["quadra"] for q in resultados] == ["Grama 5 - Interna"]
    assert "Grama 7" in capsys.readouterr().err


def test_modo_visivel_desliga_o_headless(monkeypatch):
    recebido = {}
    monkeypatch.setattr(arena_extractor, "listar_esportes", lambda url_arena: ["Grama 5"])
    monkeypatch.setattr(arena_extractor, "esportes_alvo", lambda esportes, tipos: esportes)
    monkeypatch.setattr(arena_extractor, "tipos_ausentes", lambda alvos, tipos: [])
    monkeypatch.setattr(
        arena_extractor, "coletar_horarios",
        lambda esporte, url_arena, periodo=None, headless=True, tipos=None:
            recebido.update(headless=headless, url=url_arena) or [],
    )

    arena_extractor.collect_courts(main.normalize_arena_info(ARENA), visible_browser=True)

    assert recebido["headless"] is False
    assert recebido["url"] == ARENA["url"]


def test_arena_procura_os_tipos_de_quadra_que_ela_declara(monkeypatch):
    recebido = {}
    monkeypatch.setattr(arena_extractor, "listar_esportes", lambda url_arena: ["Futebol society"])
    monkeypatch.setattr(
        arena_extractor, "coletar_horarios",
        lambda esporte, url_arena, periodo=None, headless=True, tipos=None:
            recebido.update(esporte=esporte, tipos=tipos) or [],
    )
    arena = dict(OUTRA_ARENA, tipos=["Futebol society"])

    arena_extractor.collect_courts(main.normalize_arena_info(arena))

    assert recebido == {"esporte": "Futebol society", "tipos": ["Futebol society"]}


def test_arena_sem_tipos_proprios_usa_os_padrao():
    assert main.normalize_arena_info(ARENA)["tipos"] == main.TIPOS_QUADRA


def test_imprime_livre_e_indisponivel_com_marcas_diferentes(capsys):
    dados = quadra(horarios=[
        {"hora": "17:00", "status": "Livre", "valor": 150.0},
        {"hora": "18:00", "status": "Indisponível"},
    ])
    arena_extractor.ArenaExtractor(ARENA)._print_extraction(dados)
    saida = capsys.readouterr().out

    assert "🟢 17:00  -  Livre  R$ 150.00" in saida
    assert "🔴 18:00  -  Indisponível" in saida
    assert "Livres: 1  ->  17:00" in saida
    assert "Boqueirão 2710, Canoas" in saida


def test_periodo_com_aviso_imprime_so_o_aviso(capsys):
    dados = quadra(aviso="Não foi possível coletar os horários deste período.")
    arena_extractor.ArenaExtractor(ARENA)._print_extraction(dados)
    saida = capsys.readouterr().out

    assert "Não foi possível coletar" in saida
    assert "Livres:" not in saida
