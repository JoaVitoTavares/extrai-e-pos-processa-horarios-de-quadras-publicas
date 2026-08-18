"""Testes da janela em que o clima é aplicado nas reservas de cada quadra."""

from datetime import datetime

import pandas as pd
import pytest

import persistencia
import weather_collector
from tratamento import TratamentoDeDados

DIA = "2026-08-07"
RESERVA = datetime(2026, 8, 7, 20, 0, 0)
ATUAL = {
    "time": "2026-08-07T16:00",
    "temperature_2m": 24.4,
    "apparent_temperature": 26.3,
    "relative_humidity_2m": 76,
    "precipitation": 0.0,
    "weather_code": 3,
    "wind_speed_10m": 13.1,
    "wind_direction_10m": 99,
}


def quadra(nome, horarios):
    """Monta o dicionário de uma quadra no formato que o coletor devolve, para os testes
    montarem o CSV de reservas pelo mesmo caminho que a coleta real usa."""
    return {
        "coletado_em": f"{DIA}T08:00:00",
        "esporte": "Vôlei de praia",
        "periodo": "Noite",
        "quadra": nome,
        "tipo_quadra": "Vôlei de praia",
        "quadra_coberta": "true",
        "aviso": None,
        "horarios": horarios,
    }


@pytest.fixture
def extracoes(tmp_path):
    """Monta em tmp_path uma quadra com reserva às 20:00 e uma leitura de clima às 16:00,
    gravadas pelos módulos de verdade — o tratamento é testado contra os arquivos que a
    coleta produz, não contra um CSV escrito à mão."""
    persistencia.salvar_extracao(
        [quadra("Areia 1 - Interna", [{"hora": "20:00", "status": "Livre", "valor": 100.0}])],
        str(tmp_path),
        datetime(2026, 8, 7, 8, 0, 0),
    )
    weather_collector.salvar_leitura(ATUAL, str(tmp_path), datetime(2026, 8, 7, 16, 1, 0))
    return tmp_path


def reservas(diretorio):
    """Relê o CSV da quadra do teste, para as asserções olharem o arquivo gravado e não
    um DataFrame em memória."""
    return pd.read_csv(
        diretorio / "areia-1-interna-extracoes.csv", dtype=str, keep_default_na=False
    )


@pytest.mark.parametrize(
    "agora, escreve",
    [
        (datetime(2026, 8, 7, 15, 0), False),
        (datetime(2026, 8, 7, 15, 59), False),
        (datetime(2026, 8, 7, 16, 0), True),
        (datetime(2026, 8, 7, 17, 30), True),
        (datetime(2026, 8, 7, 19, 0), True),
        (datetime(2026, 8, 7, 19, 1), False),
        (datetime(2026, 8, 7, 19, 30), False),
        (datetime(2026, 8, 7, 20, 0), False),
        (datetime(2026, 8, 7, 21, 0), False),
    ],
)
def test_janela_de_quatro_horas_ate_uma_hora_antes(extracoes, agora, escreve):
    """A reserva das 20:00 só recebe clima entre 16:00 e 19:00, com as duas pontas
    incluídas: antes disso a observação envelheceria até o jogo, depois o registro já
    entrou na janela morta. A leitura usada é sempre a mais recente disponível."""
    weather_collector.salvar_leitura(dict(ATUAL, time=agora.strftime("%Y-%m-%dT%H:%M")),
                                     str(extracoes), agora)
    TratamentoDeDados(str(extracoes)).aplicar(agora)

    assert (reservas(extracoes).loc[0, "clima"] == "Encoberto") is escreve


def test_rodada_mais_recente_sobrescreve(extracoes):
    """Cada rodada dentro da janela vale mais que a anterior, então o que fica gravado é
    a observação de uma hora antes da reserva — a mais próxima do jogo."""
    tratamento = TratamentoDeDados(str(extracoes))
    tratamento.aplicar(datetime(2026, 8, 7, 16, 0))
    weather_collector.salvar_leitura(
        dict(ATUAL, time="2026-08-07T19:00", weather_code=65, temperature_2m=15.2),
        str(extracoes), datetime(2026, 8, 7, 19, 0),
    )
    tratamento.aplicar(datetime(2026, 8, 7, 19, 0))

    linha = reservas(extracoes).loc[0]
    assert linha["clima"] == "Chuva forte"
    assert linha["temperatura"] == "15.2"


def test_grava_as_cinco_colunas_com_os_valores_da_leitura(extracoes):
    """As cinco colunas ambientais saem da leitura campo a campo; a direção do vento e a
    sensação térmica ficam só no histórico de clima, sem coluna na reserva."""
    TratamentoDeDados(str(extracoes)).aplicar(datetime(2026, 8, 7, 17, 0))
    linha = reservas(extracoes).loc[0]

    assert linha["clima"] == "Encoberto"
    assert linha["temperatura"] == "24.4"
    assert linha["umidade"] == "76"
    assert linha["precipitacao"] == "0.0"
    assert linha["velocidade_vento"] == "13.1"


def test_nao_mexe_nas_colunas_da_reserva(extracoes):
    """O tratamento escreve só o ambiente: status, preço e carimbo da coleta são do
    coletor de quadras e não podem ser reescritos por ele."""
    antes = reservas(extracoes).loc[0]
    TratamentoDeDados(str(extracoes)).aplicar(datetime(2026, 8, 7, 17, 0))
    depois = reservas(extracoes).loc[0]

    for coluna in ["status", "valor_horario", "ultima_atualizacao", "periodo", "horario_fim"]:
        assert depois[coluna] == antes[coluna]


def test_linha_fora_da_janela_fica_intacta(extracoes):
    """Numa mesma quadra, só as reservas da janela recebem clima: a das 23:00 continua
    vazia enquanto a das 20:00 é preenchida."""
    persistencia.salvar_extracao(
        [quadra("Areia 1 - Interna", [{"hora": "23:00", "status": "Livre"}])],
        str(extracoes),
        datetime(2026, 8, 7, 8, 0, 0),
    )
    TratamentoDeDados(str(extracoes)).aplicar(datetime(2026, 8, 7, 17, 0))
    df = reservas(extracoes).set_index("horario_inicio")

    assert df.loc["20:00", "clima"] == "Encoberto"
    assert df.loc["23:00", "clima"] == ""


def test_reserva_de_outro_dia_nao_entra_na_janela(extracoes):
    """A conta usa a data junto com a hora: 20:00 de amanhã não está a três horas de
    distância só porque o relógio marca 17:00 hoje."""
    persistencia.salvar_extracao(
        [quadra("Areia 2 - Interna", [{"hora": "20:00", "status": "Livre"}])],
        str(extracoes),
        datetime(2026, 8, 8, 8, 0, 0),
    )
    TratamentoDeDados(str(extracoes)).aplicar(datetime(2026, 8, 7, 17, 0))
    outra = pd.read_csv(
        extracoes / "areia-2-interna-extracoes.csv", dtype=str, keep_default_na=False
    )

    assert outra.loc[0, "clima"] == ""


def test_sem_leitura_de_clima_nada_e_tocado(tmp_path):
    """Sem histórico de clima nenhum arquivo é reescrito, nem para acrescentar coluna
    vazia: uma execução inócua não pode aparecer como alteração."""
    persistencia.salvar_extracao(
        [quadra("Areia 1 - Interna", [{"hora": "20:00", "status": "Livre"}])],
        str(tmp_path),
        datetime(2026, 8, 7, 8, 0, 0),
    )
    antes = (tmp_path / "areia-1-interna-extracoes.csv").read_text(encoding="utf-8")
    alterados = TratamentoDeDados(str(tmp_path)).aplicar(datetime(2026, 8, 7, 17, 0))

    assert alterados == []
    assert (tmp_path / "areia-1-interna-extracoes.csv").read_text(encoding="utf-8") == antes


def test_leitura_velha_demais_e_ignorada(extracoes):
    """Clima de três horas atrás não vale como observação da reserva: carimbá-lo seria
    pior do que deixar a lacuna, então a janela passa em branco."""
    TratamentoDeDados(str(extracoes)).aplicar(datetime(2026, 8, 7, 19, 0))

    assert reservas(extracoes).loc[0, "clima"] == ""


def test_leitura_futura_e_ignorada(extracoes):
    """Uma leitura à frente do relógio indica desalinhamento de máquina, não previsão:
    o tratamento usa a última leitura que já aconteceu."""
    weather_collector.salvar_leitura(
        dict(ATUAL, time="2026-08-07T23:00", weather_code=95),
        str(extracoes), datetime(2026, 8, 7, 16, 30),
    )
    TratamentoDeDados(str(extracoes)).aplicar(datetime(2026, 8, 7, 16, 30))

    assert reservas(extracoes).loc[0, "clima"] == "Encoberto"


def test_arquivo_de_clima_nao_e_tratado_como_quadra(extracoes):
    """A tabela de clima está no mesmo diretório e não pode ser varrida junto com as
    quadras: depois do tratamento ela continua com o seu próprio cabeçalho."""
    TratamentoDeDados(str(extracoes)).aplicar(datetime(2026, 8, 7, 17, 0))
    df = pd.read_csv(extracoes / weather_collector.ARQUIVO_CLIMA, dtype=str, keep_default_na=False)

    assert list(df.columns) == weather_collector.COLUNAS_CLIMA


def test_devolve_so_os_arquivos_alterados(extracoes):
    """O gerenciador relata o que mudou, então um arquivo sem linha na janela não pode
    entrar na lista."""
    persistencia.salvar_extracao(
        [quadra("Areia 3 - Interna", [{"hora": "23:00", "status": "Livre"}])],
        str(extracoes),
        datetime(2026, 8, 7, 8, 0, 0),
    )
    alterados = TratamentoDeDados(str(extracoes)).aplicar(datetime(2026, 8, 7, 17, 0))

    assert [caminho.split("/")[-1] for caminho in alterados] == [
        "areia-1-interna-extracoes.csv"
    ]
