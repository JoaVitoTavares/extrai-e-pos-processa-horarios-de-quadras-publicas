"""Testes do gerenciador: ordem das etapas, tolerância a falha e código de saída."""

import pytest
import requests
from playwright.sync_api import TimeoutError as PWTimeout

import main


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
        "aviso": aviso,
        "horarios": horarios if horarios is not None else [],
    }


@pytest.fixture(autouse=True)
def tratamento_dublado(monkeypatch):
    """Dubla o tratamento em todo teste deste arquivo e devolve a lista onde as chamadas
    ficam registradas. É autouse de propósito: o tratamento de verdade varre o diretório
    de extrações real, e um teste distraído reescreveria os CSVs da máquina."""
    chamadas = []

    class TratamentoFalso:
        def __init__(self, *args, **kwargs):
            pass

        def aplicar(self, agora=None):
            chamadas.append("trata")
            return ["um.csv"]

    monkeypatch.setattr(main, "TratamentoDeDados", TratamentoFalso)
    return chamadas


@pytest.fixture(autouse=True)
def clima_dublado(monkeypatch):
    """Dubla as duas coletas de clima em todo teste deste arquivo, pelo mesmo motivo do
    tratamento: as de verdade chamam a Open-Meteo e gravam no diretório de extrações da
    máquina, e a suíte padrão roda offline. Quem precisa da ordem ou da falha redubla."""
    monkeypatch.setattr(main, "coletar_clima", lambda: "clima.csv")
    monkeypatch.setattr(main, "coletar_previsao", lambda: "previsao.csv")


@pytest.fixture
def etapas(monkeypatch, tratamento_dublado):
    ordem = tratamento_dublado
    monkeypatch.setattr(
        main, "coletar_quadras",
        lambda modo_visivel=False: ordem.append("quadras") or [quadra()],
    )
    monkeypatch.setattr(
        main, "salvar_extracao", lambda r: ordem.append("grava") or ["um.csv"]
    )
    monkeypatch.setattr(main, "coletar_clima", lambda: ordem.append("clima") or "clima.csv")
    monkeypatch.setattr(
        main, "coletar_previsao", lambda: ordem.append("previsao") or "previsao.csv"
    )
    return ordem


def test_etapas_rodam_na_ordem(etapas):
    """O tratamento é o último porque depende de todas as coletas: precisa das reservas
    já gravadas — é a gravação que detecta a virada de status — e das duas tabelas de
    clima para casar uma coisa com a outra."""
    main.main()

    assert etapas == ["quadras", "grava", "clima", "previsao", "trata"]


def test_grava_o_que_o_coletor_devolveu(monkeypatch):
    coletado = [quadra(horarios=[{"hora": "17:00", "status": "Livre"}])]
    gravado = []
    monkeypatch.setattr(main, "coletar_quadras", lambda modo_visivel=False: coletado)
    monkeypatch.setattr(main, "salvar_extracao", lambda r: gravado.append(r) or ["um.csv"])
    monkeypatch.setattr(main, "coletar_clima", lambda: "clima.csv")

    main.main()

    assert gravado == [coletado]


def test_falha_no_clima_nao_derruba_a_execucao(monkeypatch, capsys):
    monkeypatch.setattr(main, "coletar_quadras", lambda modo_visivel=False: [quadra()])
    monkeypatch.setattr(main, "salvar_extracao", lambda r: ["um.csv"])
    monkeypatch.setattr(main, "coletar_clima", _que_falha(requests.ConnectionError("sem rede")))

    main.main()

    assert "clima não coletado" in capsys.readouterr().err


def test_json_de_clima_invalido_tambem_e_tolerado(monkeypatch, capsys):
    """Uma resposta malformada da API chega como ValueError, e não como erro de rede:
    os dois caminhos precisam ser tolerados, senão a execução morre por um campo que a
    Open-Meteo renomeou."""
    monkeypatch.setattr(main, "coletar_clima", _que_falha(ValueError("sem o bloco 'current'")))

    assert main.registrar_clima() is None
    assert "clima não coletado" in capsys.readouterr().err


def test_sai_com_erro_quando_nao_grava_nada(monkeypatch):
    monkeypatch.setattr(main, "coletar_quadras", lambda modo_visivel=False: [])
    monkeypatch.setattr(main, "salvar_extracao", lambda r: [])
    monkeypatch.setattr(main, "coletar_clima", lambda: "clima.csv")

    with pytest.raises(SystemExit) as saida:
        main.main()

    assert saida.value.code == 1


def test_esporte_que_estoura_o_tempo_nao_derruba_os_outros(monkeypatch, capsys):
    monkeypatch.setattr(main, "listar_esportes", lambda: ["Grama 7", "Grama 5"])
    monkeypatch.setattr(main, "esportes_alvo", lambda esportes: esportes)
    monkeypatch.setattr(main, "tipos_ausentes", lambda alvos: [])

    def coletar(esporte, periodo=None, headless=True):
        if esporte == "Grama 7":
            raise PWTimeout("tempo esgotado")
        return [quadra(nome="Grama 5 - Interna")]

    monkeypatch.setattr(main, "coletar_horarios", coletar)
    resultados = main.coletar_quadras()

    assert [q["quadra"] for q in resultados] == ["Grama 5 - Interna"]
    assert "Grama 7" in capsys.readouterr().err


def test_modo_visivel_desliga_o_headless(monkeypatch):
    recebido = {}
    monkeypatch.setattr(main, "listar_esportes", lambda: ["Grama 5"])
    monkeypatch.setattr(main, "esportes_alvo", lambda esportes: esportes)
    monkeypatch.setattr(main, "tipos_ausentes", lambda alvos: [])
    monkeypatch.setattr(
        main, "coletar_horarios",
        lambda esporte, periodo=None, headless=True: recebido.update(headless=headless) or [],
    )

    main.coletar_quadras(modo_visivel=True)

    assert recebido["headless"] is False


def test_imprime_livre_e_indisponivel_com_marcas_diferentes(capsys):
    dados = quadra(horarios=[
        {"hora": "17:00", "status": "Livre", "valor": 150.0},
        {"hora": "18:00", "status": "Indisponível"},
    ])
    main._imprimir_extracao(dados)
    saida = capsys.readouterr().out

    assert "🟢 17:00  -  Livre  R$ 150.00" in saida
    assert "🔴 18:00  -  Indisponível" in saida
    assert "Livres: 1  ->  17:00" in saida


def test_periodo_com_aviso_imprime_so_o_aviso(capsys):
    dados = quadra(aviso="Não foi possível coletar os horários deste período.")
    main._imprimir_extracao(dados)
    saida = capsys.readouterr().out

    assert "Não foi possível coletar" in saida
    assert "Livres:" not in saida
