"""Testes do intervalo aleatório entre requisições, sem acessar o site real."""

import random

import pytest

from extrator import config
from extrator import courts_collector
from extrator import timing
import main
from extrator import arena_extractor
from extrator import weather_collector
from conftest import RespostaFalsa
from test_main import ARENA, LOCAL, quadra

ARENA_URL = "https://webarena.app/arena/sp-sports"
ESPORTES = ["Grama 7", "Grama 5"]


def test_intervalo_fica_entre_alguns_segundos_e_tres_minutos():
    rand_num_gen = random.Random(0)
    amostras = [timing.random_access_interval_s(rand_num_gen) for _ in range(500)]

    assert config.ACCESS_INTERVAL_MIN_S >= 3
    assert config.ACCESS_INTERVAL_MAX_S == 3 * 60
    assert min(amostras) >= config.ACCESS_INTERVAL_MIN_S
    assert max(amostras) <= config.ACCESS_INTERVAL_MAX_S
    assert min(amostras) < max(amostras)


def test_espera_dorme_o_intervalo_sorteado(monkeypatch):
    observados = []
    monkeypatch.setattr(timing.time, "sleep", observados.append)
    rand_num_gen = random.Random(1)

    segundos = timing.wait_between_accesses(rand_num_gen=rand_num_gen)

    assert observados == [segundos]
    assert config.ACCESS_INTERVAL_MIN_S <= segundos <= config.ACCESS_INTERVAL_MAX_S


def test_listagem_de_esportes_espera_antes_da_requisicao(monkeypatch, respostas):
    ordem = []
    chamadas, get_falso = respostas
    get_falso.resposta = RespostaFalsa([{"data": {"esportes_list_text": ESPORTES}}])

    def get_falso_com_ordem(url, **kwargs):
        ordem.append("requisicao")
        return get_falso(url, **kwargs)

    monkeypatch.setattr(courts_collector.requests, "get", get_falso_com_ordem)
    monkeypatch.setattr(
        courts_collector, "wait_between_accesses", lambda: ordem.append("espera")
    )

    courts_collector.list_sports(ARENA_URL)

    assert ordem == ["espera", "requisicao"]


def test_duas_listagens_em_sequencia_esperam_entre_si(monkeypatch, respostas):
    esperas = []
    chamadas, get_falso = respostas
    get_falso.resposta = RespostaFalsa([{"data": {"esportes_list_text": ESPORTES}}])
    monkeypatch.setattr(
        courts_collector, "wait_between_accesses", lambda: esperas.append("espera")
    )

    courts_collector.list_sports(ARENA_URL)
    courts_collector.list_sports(ARENA_URL)

    assert esperas == ["espera", "espera"]


def test_coleta_espera_antes_de_abrir_o_navegador(monkeypatch):
    ordem = []
    monkeypatch.setattr(
        courts_collector, "wait_between_accesses", lambda: ordem.append("espera")
    )

    def playwright_falso():
        ordem.append("navegador")
        raise RuntimeError("nao abre o site")

    monkeypatch.setattr(courts_collector, "sync_playwright", playwright_falso)

    with pytest.raises(RuntimeError, match="nao abre o site"):
        courts_collector.collect_schedules("Grama 5", ARENA_URL)

    assert ordem == ["espera", "navegador"]


def test_rodada_espera_antes_de_acessar_as_arenas(monkeypatch, tmp_path):
    ordem = []
    monkeypatch.setattr(main, "ARENAS", [ARENA])
    monkeypatch.setattr(main, "DIRETORIO_EXTRACOES", str(tmp_path))
    monkeypatch.setattr(main, "DIRETORIO_LOGS", str(tmp_path))
    monkeypatch.setattr(main, "ARENAS_EM_PARALELO", 1)
    monkeypatch.setattr(arena_extractor, "resolver_local", lambda *args, **kwargs: LOCAL)
    monkeypatch.setattr(arena_extractor, "salvar_extracao", lambda *args, **kwargs: ["um.csv"])
    monkeypatch.setattr(weather_collector, "collect_weather", lambda *args, **kwargs: "clima.csv")
    monkeypatch.setattr(weather_collector, "collect_forecast", lambda *args, **kwargs: "previsao.csv")

    class TratamentoFalso:
        def __init__(self, *args, **kwargs):
            pass

        def aplicar(self, agora=None):
            return ["um.csv"]

    monkeypatch.setattr(arena_extractor, "TratamentoDeDados", TratamentoFalso)
    monkeypatch.setattr(
        main, "wait_between_accesses", lambda: ordem.append("espera-cron")
    )
    monkeypatch.setattr(
        arena_extractor.ArenaExtractor,
        "_collect_courts",
        lambda self: ordem.append("quadras") or [quadra()],
    )

    main.main()

    assert ordem[0] == "espera-cron"
    assert ordem.index("espera-cron") < ordem.index("quadras")


def test_click_pause_reuses_the_access_interval(monkeypatch):
    observed = []
    monkeypatch.setattr(timing.time, "sleep", observed.append)
    rand_num_gen = random.Random(3)

    seconds = timing.wait_between_clicks(rand_num_gen=rand_num_gen)

    assert observed == [seconds]
    assert config.ACCESS_INTERVAL_MIN_S <= seconds <= config.ACCESS_INTERVAL_MAX_S


def test_human_click_waits_before_clicking(monkeypatch):
    order = []
    monkeypatch.setattr(
        courts_collector, "wait_between_accesses", lambda: order.append("wait")
    )

    class Target:
        def click(self, **kwargs):
            order.append(("click", kwargs))

    courts_collector.click_with_pause(Target(), timeout=1000)

    assert order == ["wait", ("click", {"timeout": 1000})]


def test_disabled_click_pauses_do_not_sleep(monkeypatch):
    observed = []
    monkeypatch.setattr(timing.time, "sleep", observed.append)

    timing.disable_click_pauses()
    seconds = timing.wait_between_clicks()

    assert seconds == 0.0
    assert observed == []


def test_disabled_click_pauses_click_without_waiting(monkeypatch):
    order = []
    monkeypatch.setattr(
        courts_collector, "wait_between_accesses", lambda: order.append("wait")
    )

    class Target:
        def click(self, **kwargs):
            order.append(("click", kwargs))

    timing.disable_click_pauses()
    courts_collector.click_with_pause(Target(), timeout=1000)

    assert order == [("click", {"timeout": 1000})]
