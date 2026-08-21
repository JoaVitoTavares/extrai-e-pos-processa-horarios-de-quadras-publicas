"""Testes do gerenciador: ordem das etapas, tolerância a falha e código de saída."""

import pytest
import requests
from playwright.sync_api import TimeoutError as PWTimeout

import main

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
    """Devolve uma função que levanta `erro` ao ser chamada, para os testes descreverem
    a falha de uma etapa sem precisar de uma função nomeada por caso."""
    def falhar(*args, **kwargs):
        raise erro
    return falhar


def quadra(nome="Areia 1 - Interna", horarios=None, aviso=None, data="2026-08-07"):
    """Monta o dicionário de uma quadra no formato que o coletor devolve, para os testes
    do gerenciador descreverem só o que importa em cada caso."""
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
    """Deixa o config com uma arena só, gravando em tmp_path. É autouse porque main()
    percorre a lista de arenas de verdade: sem isso um teste distraído abriria navegador
    e escreveria no diretório de extrações da máquina."""
    monkeypatch.setattr(main, "ARENAS", [ARENA])
    monkeypatch.setattr(main, "DIRETORIO_EXTRACOES", str(tmp_path))


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
    """Dubla as duas coletas de clima e a geocodificação em todo teste deste arquivo,
    pelo mesmo motivo do tratamento: as de verdade chamam a Open-Meteo e o Nominatim e
    gravam no disco, e a suíte padrão roda offline. Quem precisa da ordem ou da falha
    redubla."""
    monkeypatch.setattr(main, "coletar_clima", lambda lat, lon, diretorio: "clima.csv")
    monkeypatch.setattr(main, "coletar_previsao", lambda lat, lon, diretorio: "previsao.csv")
    monkeypatch.setattr(main, "resolver_local", lambda endereco, diretorio, coordenadas: LOCAL)


@pytest.fixture
def etapas(monkeypatch, tratamento_dublado):
    """Substitui as etapas do gerenciador por dublês que registram a ordem das chamadas,
    para os testes afirmarem o encadeamento sem abrir navegador nem tocar na rede."""
    ordem = tratamento_dublado
    monkeypatch.setattr(
        main, "coletar_quadras",
        lambda arena, modo_visivel=False: ordem.append("quadras") or [quadra()],
    )
    monkeypatch.setattr(
        main, "resolver_local",
        lambda endereco, diretorio, coordenadas: ordem.append("local") or LOCAL,
    )
    monkeypatch.setattr(
        main, "salvar_extracao",
        lambda r, diretorio, arena="", cidade="": ordem.append("grava") or ["um.csv"],
    )
    monkeypatch.setattr(
        main, "coletar_clima", lambda lat, lon, diretorio: ordem.append("clima") or "clima.csv"
    )
    monkeypatch.setattr(
        main, "coletar_previsao",
        lambda lat, lon, diretorio: ordem.append("previsao") or "previsao.csv",
    )
    return ordem


def test_etapas_rodam_na_ordem(etapas):
    """O local vem antes da gravação porque a cidade que ele resolve entra na linha do
    CSV, e o tratamento é o último porque depende de todas as coletas: precisa das
    reservas já gravadas — é a gravação que detecta a virada de status — e das duas
    tabelas de clima para casar uma coisa com a outra."""
    main.main()

    assert etapas == ["quadras", "local", "grava", "clima", "previsao", "trata"]


def test_preparar_arena_tira_o_diretorio_da_url():
    """O diretório de uma arena sai do último trecho da URL, e não do nome: é a URL que
    identifica o site, então renomear a arena no config não desgarra o histórico que ela
    já coletou."""
    arena = main.preparar_arena({"nome": "SP Sports", "url": "https://webarena.app/arena/sp-sports/"})

    assert arena["diretorio"].endswith("sp-sports")
    assert arena["nome"] == "SP Sports"


def test_arena_sem_nome_se_identifica_pela_url():
    """Declarar só a URL basta para acrescentar um site: o nome que falta vira o
    identificador tirado dela, em vez de a coluna `arena` nascer vazia."""
    arena = main.preparar_arena({"url": "https://webarena.app/arena/quadra-nova"})

    assert arena["nome"] == "quadra-nova"


def test_cada_arena_grava_no_seu_diretorio(monkeypatch, etapas):
    """Duas arenas não podem disputar arquivo: quadras de mesmo nome em cidades
    diferentes gerariam o mesmo slug, e uma sobrescreveria o histórico da outra."""
    monkeypatch.setattr(main, "ARENAS", [ARENA, OUTRA_ARENA])
    diretorios = []
    monkeypatch.setattr(
        main, "salvar_extracao",
        lambda r, diretorio, arena="", cidade="": diretorios.append(diretorio) or ["um.csv"],
    )

    main.main()

    assert len(set(diretorios)) == 2
    assert diretorios[0].endswith("sp-sports")
    assert diretorios[1].endswith("parobe")


def test_arena_carimba_nome_e_cidade_na_gravacao(monkeypatch):
    """O nome da arena e a cidade que a geocodificação resolveu descem para o CSV: sem
    eles, juntar os arquivos de várias arenas num dataset só perderia de que lugar cada
    linha veio."""
    recebido = {}
    monkeypatch.setattr(main, "coletar_quadras", lambda arena, modo_visivel=False: [quadra()])
    monkeypatch.setattr(
        main, "salvar_extracao",
        lambda r, diretorio, arena="", cidade="": recebido.update(arena=arena, cidade=cidade)
        or ["um.csv"],
    )

    main.main()

    assert recebido == {"arena": "SP Sports", "cidade": "Canoas"}


def test_grava_o_que_o_coletor_devolveu(monkeypatch):
    """O gerenciador passa adiante exatamente as quadras coletadas: quem coleta e quem
    grava são módulos diferentes, e é aqui que os dois se encontram."""
    coletado = [quadra(horarios=[{"hora": "17:00", "status": "Livre"}])]
    gravado = []
    monkeypatch.setattr(main, "coletar_quadras", lambda arena, modo_visivel=False: coletado)
    monkeypatch.setattr(
        main, "salvar_extracao",
        lambda r, diretorio, arena="", cidade="": gravado.append(r) or ["um.csv"],
    )

    main.main()

    assert gravado == [coletado]


def test_clima_e_consultado_nas_coordenadas_da_arena(monkeypatch):
    """As coordenadas que saem do endereço da arena são as que vão à Open-Meteo: é isso
    que faz cada quadra receber o tempo do lugar dela, e não o de uma cidade fixa."""
    consultado = {}
    monkeypatch.setattr(main, "coletar_quadras", lambda arena, modo_visivel=False: [quadra()])
    monkeypatch.setattr(main, "salvar_extracao", lambda r, diretorio, **kwargs: ["um.csv"])
    monkeypatch.setattr(
        main, "coletar_clima",
        lambda lat, lon, diretorio: consultado.update(lat=lat, lon=lon, diretorio=diretorio)
        or "clima.csv",
    )

    main.main()

    assert (consultado["lat"], consultado["lon"]) == (LOCAL["latitude"], LOCAL["longitude"])
    assert consultado["diretorio"].endswith("sp-sports")


def test_arena_sem_local_nao_consulta_clima(monkeypatch):
    """Sem saber onde a arena fica, a rodada grava as quadras e para por aí: consultar a
    Open-Meteo num ponto qualquer carimbaria na reserva o clima de outro lugar, que é
    pior do que a lacuna."""
    chamou = []
    monkeypatch.setattr(main, "coletar_quadras", lambda arena, modo_visivel=False: [quadra()])
    monkeypatch.setattr(main, "salvar_extracao", lambda r, diretorio, **kwargs: ["um.csv"])
    monkeypatch.setattr(main, "resolver_local", lambda endereco, diretorio, coordenadas: None)
    monkeypatch.setattr(main, "coletar_clima", lambda *a: chamou.append("clima") or "clima.csv")

    main.main()

    assert chamou == []


def test_falha_do_geocodificador_nao_derruba_a_execucao(monkeypatch, capsys):
    """O Nominatim fora do ar custa o clima daquela arena, não a coleta: o aviso vai para
    o stderr, as quadras seguem gravadas e a rodada seguinte tenta de novo."""
    monkeypatch.setattr(main, "coletar_quadras", lambda arena, modo_visivel=False: [quadra()])
    monkeypatch.setattr(main, "salvar_extracao", lambda r, diretorio, **kwargs: ["um.csv"])
    monkeypatch.setattr(main, "resolver_local", _que_falha(requests.ConnectionError("sem rede")))

    main.main()

    assert "endereço não geocodificado" in capsys.readouterr().err


def test_falha_no_clima_nao_derruba_a_execucao(monkeypatch, capsys):
    """A Open-Meteo fora do ar não pode custar a coleta das quadras, que já está gravada:
    o erro vai para o stderr e a execução termina normalmente."""
    monkeypatch.setattr(main, "coletar_quadras", lambda arena, modo_visivel=False: [quadra()])
    monkeypatch.setattr(main, "salvar_extracao", lambda r, diretorio, **kwargs: ["um.csv"])
    monkeypatch.setattr(main, "coletar_clima", _que_falha(requests.ConnectionError("sem rede")))

    main.main()

    assert "clima não coletado" in capsys.readouterr().err


def test_json_de_clima_invalido_tambem_e_tolerado(monkeypatch, capsys):
    """Uma resposta malformada da API chega como ValueError, e não como erro de rede:
    os dois caminhos precisam ser tolerados, senão a execução morre por um campo que a
    Open-Meteo renomeou."""
    monkeypatch.setattr(main, "coletar_clima", _que_falha(ValueError("sem o bloco 'current'")))

    assert main.registrar_clima(LOCAL, "qualquer") is None
    assert "clima não coletado" in capsys.readouterr().err


def test_arena_que_falha_nao_derruba_as_outras(monkeypatch, capsys):
    """Uma arena fora do ar é reportada e pulada, como já acontecia com o esporte lento
    dentro de uma arena: a lista de sites não pode ficar refém do pior deles."""
    monkeypatch.setattr(main, "ARENAS", [ARENA, OUTRA_ARENA])
    monkeypatch.setattr(main, "salvar_extracao", lambda r, diretorio, **kwargs: ["um.csv"])

    def coletar(arena, modo_visivel=False):
        if arena["nome"] == "SP Sports":
            raise PWTimeout("tempo esgotado")
        return [quadra()]

    monkeypatch.setattr(main, "coletar_quadras", coletar)
    main.main()

    assert "SP Sports" in capsys.readouterr().err


def test_sai_com_erro_quando_nao_grava_nada(monkeypatch):
    """Uma execução que não coletou nada sai com código 1 em vez de terminar em silêncio:
    num coletor agendado, a falha muda é a mais cara — ninguém percebe que o histórico
    parou de crescer."""
    monkeypatch.setattr(main, "coletar_quadras", lambda arena, modo_visivel=False: [])
    monkeypatch.setattr(main, "salvar_extracao", lambda r, diretorio, **kwargs: [])

    with pytest.raises(SystemExit) as saida:
        main.main()

    assert saida.value.code == 1


def test_esporte_que_estoura_o_tempo_nao_derruba_os_outros(monkeypatch, capsys):
    """A lentidão do site em um esporte não pode custar a coleta dos demais: o que
    estourou é reportado no stderr e a execução segue com o que deu certo."""
    monkeypatch.setattr(main, "listar_esportes", lambda url_arena: ["Grama 7", "Grama 5"])
    monkeypatch.setattr(main, "esportes_alvo", lambda esportes: esportes)
    monkeypatch.setattr(main, "tipos_ausentes", lambda alvos: [])

    def coletar(esporte, url_arena, periodo=None, headless=True):
        if esporte == "Grama 7":
            raise PWTimeout("tempo esgotado")
        return [quadra(nome="Grama 5 - Interna")]

    monkeypatch.setattr(main, "coletar_horarios", coletar)
    resultados = main.coletar_quadras(main.preparar_arena(ARENA))

    assert [q["quadra"] for q in resultados] == ["Grama 5 - Interna"]
    assert "Grama 7" in capsys.readouterr().err


def test_modo_visivel_desliga_o_headless(monkeypatch):
    """A flag --ver existe para assistir ao passo a passo, então ela precisa chegar ao
    coletor invertida: modo visível é headless desligado."""
    recebido = {}
    monkeypatch.setattr(main, "listar_esportes", lambda url_arena: ["Grama 5"])
    monkeypatch.setattr(main, "esportes_alvo", lambda esportes: esportes)
    monkeypatch.setattr(main, "tipos_ausentes", lambda alvos: [])
    monkeypatch.setattr(
        main, "coletar_horarios",
        lambda esporte, url_arena, periodo=None, headless=True:
            recebido.update(headless=headless, url=url_arena) or [],
    )

    main.coletar_quadras(main.preparar_arena(ARENA), modo_visivel=True)

    assert recebido["headless"] is False
    assert recebido["url"] == ARENA["url"]


def test_imprime_livre_e_indisponivel_com_marcas_diferentes(capsys):
    """O relatório do terminal distingue os dois status de bate-pronto, e o preço só
    aparece no horário que tem preço."""
    dados = quadra(horarios=[
        {"hora": "17:00", "status": "Livre", "valor": 150.0},
        {"hora": "18:00", "status": "Indisponível"},
    ])
    main._imprimir_extracao(dados)
    saida = capsys.readouterr().out

    assert "🟢 17:00  -  Livre  R$ 150.00" in saida
    assert "🔴 18:00  -  Indisponível" in saida
    assert "Livres: 1  ->  17:00" in saida
    assert "Boqueirão 2710, Canoas" in saida


def test_periodo_com_aviso_imprime_so_o_aviso(capsys):
    """Sem horário para listar, o bloco mostra o aviso e para por aí, em vez de exibir
    um resumo de vagas que não foi observado."""
    dados = quadra(aviso="Não foi possível coletar os horários deste período.")
    main._imprimir_extracao(dados)
    saida = capsys.readouterr().out

    assert "Não foi possível coletar" in saida
    assert "Livres:" not in saida
