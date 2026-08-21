"""Testes da resolução do endereço da arena em coordenadas, com o Nominatim dublado."""

import fnmatch
import json

import pytest
import requests

import config
import localizacao
import persistencia
from conftest import RespostaFalsa

ENDERECO = "20 de Junho 54, Parobé"
ACHADO = {
    "lat": "-29.6509717",
    "lon": "-50.8169235",
    "category": "highway",
    "display_name": "Rua 20 de Junho, Parobé, Rio Grande do Sul, Brasil",
    "address": {"road": "Rua 20 de Junho", "town": "Parobé", "state": "Rio Grande do Sul"},
}


@pytest.fixture(autouse=True)
def sem_espera(monkeypatch):
    """Zera a pausa entre as tentativas de consulta. A pausa existe para respeitar o
    limite de uma chamada por segundo do serviço público, e num teste com o requests
    dublado ela só faria a suíte esperar por nada."""
    monkeypatch.setattr(localizacao.time, "sleep", lambda segundos: None)


def quadra(endereco):
    """Monta o mínimo de uma quadra coletada para os testes de endereço observado: só o
    campo que o coletor traz da tela."""
    return {"quadra": "Areia 1", "endereco": endereco}


def test_endereco_observado_fica_com_o_mais_repetido():
    """O site mostra o endereço uma vez por esporte, então a rodada traz várias cópias
    do mesmo texto. A leitura que falhou vem vazia e não pode votar."""
    resultados = [quadra(ENDERECO), quadra(""), quadra(ENDERECO), quadra("Outro 1, Canoas")]

    assert localizacao.endereco_observado(resultados) == ENDERECO


def test_endereco_observado_sem_nenhuma_leitura():
    """Nenhuma quadra com endereço devolve vazio, que é como a rodada diz que não sabe
    onde a arena fica — e não que ela mudou de lugar."""
    assert localizacao.endereco_observado([quadra(""), {"quadra": "Areia 2"}]) == ""


@pytest.mark.parametrize(
    "endereco, esperado",
    [
        ("20 de Junho 54, Parobé", ["20 de Junho 54, Parobé", "20 de Junho, Parobé", "Parobé"]),
        ("Boqueirão 2710, Canoas", ["Boqueirão 2710, Canoas", "Boqueirão, Canoas", "Canoas"]),
        ("Av. Brasil, 1200, Canoas", ["Av. Brasil, 1200, Canoas", "Av. Brasil, Canoas", "Canoas"]),
        ("Parobé", ["Parobé"]),
    ],
)
def test_variacoes_descem_do_especifico_para_o_generico(endereco, esperado):
    """As formas de perguntar vão da mais específica à mais genérica: como veio, sem o
    número do prédio e só a cidade. Para o clima a cidade já basta — a grade da Open-Meteo
    tem quilômetros de lado —, então descer um degrau vale mais do que devolver nada
    porque o número não está no mapa."""
    assert localizacao.variacoes_da_consulta(endereco) == esperado


def test_consulta_identifica_a_aplicacao_e_filtra_o_pais(respostas):
    """O User-Agent é exigência do Nominatim, que recusa chamada anônima; o país entra
    como filtro porque o site escreve rua e cidade, sem nada que situe o endereço no
    mundo. E a chamada não fica pendurada sem timeout."""
    chamadas, get_falso = respostas
    get_falso.resposta = RespostaFalsa([ACHADO])
    localizacao.consultar_geocodificacao(ENDERECO)

    url, kwargs = chamadas[0]
    assert url == config.API_GEOCODIFICACAO
    assert kwargs["params"]["q"] == ENDERECO
    assert kwargs["params"]["countrycodes"] == config.PAIS_DAS_ARENAS
    assert kwargs["headers"]["User-Agent"] == config.IDENTIFICACAO_GEOCODIFICACAO
    assert kwargs["timeout"] > 0


def test_geocodifica_endereco_em_coordenadas_e_cidade(respostas):
    """O endereço vira latitude, longitude e cidade. A cidade sai do endereço estruturado
    que o serviço devolve — `town` para Parobé —, e não de um pedaço do texto livre."""
    chamadas, get_falso = respostas
    get_falso.resposta = RespostaFalsa([ACHADO])
    local = localizacao.geocodificar(ENDERECO)

    assert (local["latitude"], local["longitude"]) == (-29.6509717, -50.8169235)
    assert local["cidade"] == "Parobé"
    assert local["endereco"] == ENDERECO


def test_desce_para_a_consulta_seguinte_quando_nao_ha_resultado(monkeypatch):
    """Endereço que o mapa não conhece com o número do prédio é perguntado de novo sem
    ele, e depois só pela cidade. É a diferença entre a arena ter clima e não ter."""
    consultas = []

    def get_falso(url, **kwargs):
        consultas.append(kwargs["params"]["q"])
        return RespostaFalsa([ACHADO] if consultas[-1] == "Parobé" else [])

    monkeypatch.setattr(requests, "get", get_falso)
    local = localizacao.geocodificar(ENDERECO)

    assert consultas == ["20 de Junho 54, Parobé", "20 de Junho, Parobé", "Parobé"]
    assert local["origem"] == "Parobé"


def test_endereco_que_nenhuma_consulta_resolve_devolve_none(respostas):
    """Esgotadas as variações, o resultado é None: sem coordenada confiável é melhor a
    arena passar a rodada sem clima do que consultar a Open-Meteo no lugar errado."""
    chamadas, get_falso = respostas
    get_falso.resposta = RespostaFalsa([])

    assert localizacao.geocodificar(ENDERECO) is None


def test_resposta_sem_coordenada_falha_alto(respostas):
    """JSON fora do formato levanta ValueError, como nos outros coletores: um campo que o
    serviço renomeie precisa aparecer como erro, e não virar arena sem clima em silêncio."""
    chamadas, get_falso = respostas
    get_falso.resposta = RespostaFalsa([{"display_name": "sem lat nem lon"}])

    with pytest.raises(ValueError, match="formato inesperado"):
        localizacao.geocodificar(ENDERECO)


def test_erro_http_sobe(respostas):
    """Um 500 do Nominatim não é engolido aqui: quem chamou decide o que fazer, e o
    gerenciador transforma isso em aviso no stderr."""
    chamadas, get_falso = respostas
    get_falso.resposta = RespostaFalsa([ACHADO], erro=requests.HTTPError("500"))

    with pytest.raises(requests.HTTPError):
        localizacao.geocodificar(ENDERECO)


def test_resolver_grava_o_local_no_diretorio_da_arena(respostas, tmp_path):
    """O local resolvido fica em local.json, ao lado das extrações daquela arena: é a
    memória do geocodificador e o registro de onde o clima daquela pasta foi medido."""
    chamadas, get_falso = respostas
    get_falso.resposta = RespostaFalsa([ACHADO])
    localizacao.resolver_local(ENDERECO, str(tmp_path))
    gravado = json.loads((tmp_path / localizacao.ARQUIVO_LOCAL).read_text(encoding="utf-8"))

    assert gravado["endereco"] == ENDERECO
    assert gravado["cidade"] == "Parobé"
    assert gravado["resolvido_em"]


def test_endereco_ja_conhecido_nao_consulta_de_novo(respostas, tmp_path):
    """Rodada a rodada o endereço é o mesmo, e o serviço é público, gratuito e limitado a
    uma consulta por segundo: reconfirmar o que não mudou quatro vezes por hora seria
    abusar dele por nada."""
    chamadas, get_falso = respostas
    get_falso.resposta = RespostaFalsa([ACHADO])
    localizacao.resolver_local(ENDERECO, str(tmp_path))
    local = localizacao.resolver_local(ENDERECO, str(tmp_path))

    assert len(chamadas) == 1
    assert local["cidade"] == "Parobé"


def test_rodada_sem_endereco_legivel_fica_com_o_local_conhecido(respostas, tmp_path):
    """A leitura do endereço pode falhar numa rodada — o bloco não pintou a tempo —, e
    isso não pode custar o clima: vale o local que já estava gravado, porque a arena não
    mudou de lugar só porque a página não abriu."""
    chamadas, get_falso = respostas
    get_falso.resposta = RespostaFalsa([ACHADO])
    localizacao.resolver_local(ENDERECO, str(tmp_path))
    local = localizacao.resolver_local("", str(tmp_path))

    assert len(chamadas) == 1
    assert local["latitude"] == -29.6509717


def test_endereco_novo_que_o_mapa_recusa_nao_herda_o_antigo(respostas, tmp_path):
    """Endereço diferente do gravado é arena que mudou de lugar. Se o novo não resolve, a
    rodada fica sem clima em vez de usar as coordenadas do endereço velho, que descrevem
    outro ponto do mapa — e a rodada seguinte tenta de novo."""
    chamadas, get_falso = respostas
    get_falso.resposta = RespostaFalsa([ACHADO])
    localizacao.resolver_local(ENDERECO, str(tmp_path))
    get_falso.resposta = RespostaFalsa([])

    assert localizacao.resolver_local("Outro Lugar 9, Canoas", str(tmp_path)) is None


def test_coordenadas_do_config_dispensam_o_geocodificador(respostas, tmp_path):
    """Coordenadas fixadas à mão vencem tudo: são a saída para o endereço que o mapa não
    reconhece, e não faria sentido consultar o serviço para depois descartar a resposta."""
    chamadas, get_falso = respostas
    get_falso.resposta = RespostaFalsa([ACHADO])
    local = localizacao.resolver_local(ENDERECO, str(tmp_path), coordenadas=(-29.65, -50.81))

    assert chamadas == []
    assert (local["latitude"], local["longitude"]) == (-29.65, -50.81)
    assert local["origem"] == "config"


def test_sem_endereco_e_sem_cache_devolve_none(tmp_path):
    """Arena nova cujo endereço não foi lido não tem como ser localizada, e a rodada
    segue sem clima em vez de estourar."""
    assert localizacao.resolver_local("", str(tmp_path)) is None


def test_local_corrompido_conta_como_cache_vazio(respostas, tmp_path):
    """Um local.json truncado por queda de energia não pode derrubar a rodada nem
    devolver coordenada pela metade: vale como se não houvesse cache, e a consulta é
    refeita."""
    chamadas, get_falso = respostas
    get_falso.resposta = RespostaFalsa([ACHADO])
    (tmp_path / localizacao.ARQUIVO_LOCAL).write_text('{"endereco": "20 de J', encoding="utf-8")
    local = localizacao.resolver_local(ENDERECO, str(tmp_path))

    assert len(chamadas) == 1
    assert local["cidade"] == "Parobé"


def test_arquivo_do_local_nao_casa_com_o_glob_das_quadras():
    """local.json divide o diretório com os CSVs de quadra e não pode ser varrido junto
    com eles, pelo mesmo motivo dos arquivos de clima."""
    assert not fnmatch.fnmatch(localizacao.ARQUIVO_LOCAL, "*" + persistencia.SUFIXO_CSV)
