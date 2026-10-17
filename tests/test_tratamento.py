"""Testes da janela em que o clima é aplicado nas reservas de cada quadra."""

from datetime import datetime

import pandas as pd
import pytest

from extrator import persistencia
from extrator import weather_collector
from extrator.tratamento import TratamentoDeDados

DIA = "2026-08-07"
COORDENADAS = (-29.9128, -51.1836)
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
PREVISAO = {
    "time": [f"{DIA}T20:00", f"{DIA}T21:00", f"{DIA}T22:00"],
    "temperature_2m": [18.9, 17.5, 16.8],
    "relative_humidity_2m": [88, 90, 91],
    "precipitation": [2.4, 0.0, 0.0],
    "precipitation_probability": [70, 20, 10],
    "weather_code": [63, 0, 0],
    "wind_speed_10m": [19.4, 12.0, 9.8],
}


def gravar_leitura(atual, diretorio, agora):
    return weather_collector.save_reading(atual, *COORDENADAS, diretorio, agora)


def gravar_previsao(horas, diretorio, agora):
    return weather_collector.save_forecast(horas, *COORDENADAS, diretorio, agora)


def quadra(nome, horarios, data=DIA):
    return {
        "coletado_em": f"{DIA}T08:00:00",
        "data": data,
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
    persistencia.salvar_extracao(
        [quadra("Areia 1 - Interna", [{"hora": "20:00", "status": "Livre", "valor": 100.0}])],
        str(tmp_path),
        datetime(2026, 8, 7, 8, 0, 0),
    )
    gravar_leitura(ATUAL, str(tmp_path), datetime(2026, 8, 7, 16, 1, 0))
    return tmp_path


def reservas(diretorio):
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
    gravar_leitura(dict(ATUAL, time=agora.strftime("%Y-%m-%dT%H:%M")),
                                     str(extracoes), agora)
    TratamentoDeDados(str(extracoes)).aplicar(agora)

    assert (reservas(extracoes).loc[0, "antes_do_jogo_clima"] == "Encoberto") is escreve


def test_rodada_mais_recente_sobrescreve(extracoes):
    tratamento = TratamentoDeDados(str(extracoes))
    tratamento.aplicar(datetime(2026, 8, 7, 16, 0))
    gravar_leitura(
        dict(ATUAL, time="2026-08-07T19:00", weather_code=65, temperature_2m=15.2),
        str(extracoes), datetime(2026, 8, 7, 19, 0),
    )
    tratamento.aplicar(datetime(2026, 8, 7, 19, 0))

    linha = reservas(extracoes).loc[0]
    assert linha["antes_do_jogo_clima"] == "Chuva forte"
    assert linha["antes_do_jogo_temperatura"] == "15.2"


def test_grava_as_cinco_colunas_com_os_valores_da_leitura(extracoes):
    TratamentoDeDados(str(extracoes)).aplicar(datetime(2026, 8, 7, 17, 0))
    linha = reservas(extracoes).loc[0]

    assert linha["antes_do_jogo_clima"] == "Encoberto"
    assert linha["antes_do_jogo_temperatura"] == "24.4"
    assert linha["antes_do_jogo_umidade"] == "76"
    assert linha["antes_do_jogo_precipitacao"] == "0.0"
    assert linha["antes_do_jogo_velocidade_vento"] == "13.1"


def test_nao_mexe_nas_colunas_da_reserva(extracoes):
    antes = reservas(extracoes).loc[0]
    TratamentoDeDados(str(extracoes)).aplicar(datetime(2026, 8, 7, 17, 0))
    depois = reservas(extracoes).loc[0]

    for coluna in ["status", "valor_horario", "ultima_atualizacao", "periodo", "horario_fim"]:
        assert depois[coluna] == antes[coluna]


def test_linha_fora_da_janela_fica_intacta(extracoes):
    persistencia.salvar_extracao(
        [quadra("Areia 1 - Interna", [{"hora": "23:00", "status": "Livre"}])],
        str(extracoes),
        datetime(2026, 8, 7, 8, 0, 0),
    )
    TratamentoDeDados(str(extracoes)).aplicar(datetime(2026, 8, 7, 17, 0))
    df = reservas(extracoes).set_index("horario_inicio")

    assert df.loc["20:00", "antes_do_jogo_clima"] == "Encoberto"
    assert df.loc["23:00", "antes_do_jogo_clima"] == ""


def test_reserva_de_outro_dia_nao_entra_na_janela(extracoes):
    persistencia.salvar_extracao(
        [quadra("Areia 2 - Interna", [{"hora": "20:00", "status": "Livre"}], data="2026-08-08")],
        str(extracoes),
        datetime(2026, 8, 7, 8, 0, 0),
    )
    TratamentoDeDados(str(extracoes)).aplicar(datetime(2026, 8, 7, 17, 0))
    outra = pd.read_csv(
        extracoes / "areia-2-interna-extracoes.csv", dtype=str, keep_default_na=False
    )

    assert outra.loc[0, "antes_do_jogo_clima"] == ""


def test_sem_leitura_de_clima_nada_e_tocado(tmp_path):
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
    TratamentoDeDados(str(extracoes)).aplicar(datetime(2026, 8, 7, 19, 0))

    assert reservas(extracoes).loc[0, "antes_do_jogo_clima"] == ""


def test_leitura_futura_e_ignorada(extracoes):
    gravar_leitura(
        dict(ATUAL, time="2026-08-07T23:00", weather_code=95),
        str(extracoes), datetime(2026, 8, 7, 16, 30),
    )
    TratamentoDeDados(str(extracoes)).aplicar(datetime(2026, 8, 7, 16, 30))

    assert reservas(extracoes).loc[0, "antes_do_jogo_clima"] == "Encoberto"


def test_arquivo_de_clima_nao_e_tratado_como_quadra(extracoes):
    TratamentoDeDados(str(extracoes)).aplicar(datetime(2026, 8, 7, 17, 0))
    df = pd.read_csv(extracoes / weather_collector.WEATHER_FILE, dtype=str, keep_default_na=False)

    assert list(df.columns) == weather_collector.WEATHER_COLUMNS


def reservar(diretorio, hora="20:00", quando=datetime(2026, 8, 7, 10, 0), data=DIA):
    persistencia.salvar_extracao(
        [quadra("Areia 1 - Interna", [{"hora": hora, "status": "Indisponível"}], data=data)],
        str(diretorio),
        quando,
    )


def test_clima_do_instante_da_reserva_e_congelado(extracoes):
    gravar_leitura(
        dict(ATUAL, time="2026-08-07T10:00", weather_code=61, temperature_2m=19.8),
        str(extracoes), datetime(2026, 8, 7, 10, 0),
    )
    reservar(extracoes)
    TratamentoDeDados(str(extracoes)).aplicar(datetime(2026, 8, 7, 10, 0))
    linha = reservas(extracoes).loc[0]

    assert linha["reservado_em"] == "2026-08-07T10:00:00"
    assert linha["na_hora_da_reserva_clima"] == "Chuva fraca"
    assert linha["na_hora_da_reserva_temperatura"] == "19.8"
    assert linha["na_hora_da_reserva_umidade"] == "76"
    assert linha["na_hora_da_reserva_precipitacao"] == "0.0"
    assert linha["na_hora_da_reserva_velocidade_vento"] == "13.1"


def test_clima_da_reserva_nao_e_reescrito_por_rodada_posterior(extracoes):
    gravar_leitura(
        dict(ATUAL, time="2026-08-07T10:00", weather_code=61), str(extracoes),
        datetime(2026, 8, 7, 10, 0),
    )
    reservar(extracoes)
    tratamento = TratamentoDeDados(str(extracoes))
    tratamento.aplicar(datetime(2026, 8, 7, 10, 0))

    gravar_leitura(
        dict(ATUAL, time="2026-08-07T17:00", weather_code=0), str(extracoes),
        datetime(2026, 8, 7, 17, 0),
    )
    tratamento.aplicar(datetime(2026, 8, 7, 17, 0))
    linha = reservas(extracoes).loc[0]

    assert linha["na_hora_da_reserva_clima"] == "Chuva fraca"
    assert linha["antes_do_jogo_clima"] == "Céu limpo"


def test_horario_livre_nao_recebe_o_clima_da_reserva(extracoes):
    TratamentoDeDados(str(extracoes)).aplicar(datetime(2026, 8, 7, 16, 30))

    assert reservas(extracoes).loc[0, "na_hora_da_reserva_clima"] == ""


def test_clima_da_reserva_usa_a_observacao_mais_proxima_da_virada(extracoes):
    for hora, codigo in [("10:30", 3), ("10:45", 95)]:
        gravar_leitura(
            dict(ATUAL, time=f"2026-08-07T{hora}", weather_code=codigo), str(extracoes),
            datetime(2026, 8, 7, 10, 45),
        )
    reservar(extracoes, quando=datetime(2026, 8, 7, 10, 40))
    TratamentoDeDados(str(extracoes)).aplicar(datetime(2026, 8, 7, 10, 45))

    assert reservas(extracoes).loc[0, "na_hora_da_reserva_clima"] == "Trovoada"


def test_reserva_sem_observacao_por_perto_fica_sem_o_bloco(extracoes):
    reservar(extracoes, quando=datetime(2026, 8, 7, 19, 0))
    TratamentoDeDados(str(extracoes)).aplicar(datetime(2026, 8, 7, 19, 0))

    assert reservas(extracoes).loc[0, "na_hora_da_reserva_clima"] == ""


def test_previsao_congelada_na_reserva_recem_detectada(extracoes):
    gravar_previsao(PREVISAO, str(extracoes), datetime(2026, 8, 7, 10, 0))
    reservar(extracoes)
    TratamentoDeDados(str(extracoes)).aplicar(datetime(2026, 8, 7, 10, 0))
    linha = reservas(extracoes).loc[0]

    assert linha["previsao_para_o_jogo_no_momento_da_reserva_clima"] == "Chuva moderada"
    assert linha["previsao_para_o_jogo_no_momento_da_reserva_temperatura"] == "18.9"
    assert linha["previsao_para_o_jogo_no_momento_da_reserva_precipitacao"] == "2.4"
    assert linha["previsao_para_o_jogo_no_momento_da_reserva_umidade"] == "88"
    assert linha["previsao_para_o_jogo_no_momento_da_reserva_velocidade_vento"] == "19.4"


def test_previsao_nao_e_reescrita_por_rodada_posterior(extracoes):
    gravar_previsao(PREVISAO, str(extracoes), datetime(2026, 8, 7, 10, 0))
    reservar(extracoes)
    tratamento = TratamentoDeDados(str(extracoes))
    tratamento.aplicar(datetime(2026, 8, 7, 10, 0))

    revisada = dict(PREVISAO, weather_code=[0, 0, 0], temperature_2m=[30.0, 30.0, 30.0])
    gravar_previsao(revisada, str(extracoes), datetime(2026, 8, 7, 17, 0))
    tratamento.aplicar(datetime(2026, 8, 7, 17, 0))

    assert reservas(extracoes).loc[0, "previsao_para_o_jogo_no_momento_da_reserva_clima"] == "Chuva moderada"


def test_horario_livre_nao_recebe_previsao(extracoes):
    gravar_previsao(PREVISAO, str(extracoes), datetime(2026, 8, 7, 10, 0))
    TratamentoDeDados(str(extracoes)).aplicar(datetime(2026, 8, 7, 10, 0))

    assert reservas(extracoes).loc[0, "previsao_para_o_jogo_no_momento_da_reserva_clima"] == ""


def test_reserva_de_meia_hora_pega_a_previsao_da_hora_cheia(extracoes):
    gravar_previsao(PREVISAO, str(extracoes), datetime(2026, 8, 7, 10, 0))
    persistencia.salvar_extracao(
        [quadra("Areia 1 - Interna", [{"hora": "21:30", "status": "Livre"}])],
        str(extracoes), datetime(2026, 8, 7, 9, 0),
    )
    reservar(extracoes, hora="21:30")
    TratamentoDeDados(str(extracoes)).aplicar(datetime(2026, 8, 7, 10, 0))
    df = reservas(extracoes).set_index("horario_inicio")

    assert df.loc["21:30", "previsao_para_o_jogo_no_momento_da_reserva_clima"] == "Céu limpo"


def test_reserva_fora_do_horizonte_da_previsao_fica_sem_coluna(extracoes):
    gravar_previsao(PREVISAO, str(extracoes), datetime(2026, 8, 7, 10, 0))
    persistencia.salvar_extracao(
        [quadra("Areia 1 - Interna", [{"hora": "20:00", "status": "Livre"}], data="2026-08-09")],
        str(extracoes), datetime(2026, 8, 7, 9, 0),
    )
    reservar(extracoes, data="2026-08-09")
    TratamentoDeDados(str(extracoes)).aplicar(datetime(2026, 8, 7, 10, 0))
    df = reservas(extracoes).set_index("data")

    assert df.loc["2026-08-09", "previsao_para_o_jogo_no_momento_da_reserva_clima"] == ""


def test_sem_previsao_o_clima_observado_continua_sendo_aplicado(extracoes):
    reservar(extracoes)
    TratamentoDeDados(str(extracoes)).aplicar(datetime(2026, 8, 7, 17, 0))
    linha = reservas(extracoes).loc[0]

    assert linha["antes_do_jogo_clima"] == "Encoberto"
    assert linha["previsao_para_o_jogo_no_momento_da_reserva_clima"] == ""


def test_nova_reserva_congela_o_clima_da_segunda_virada(tmp_path):
    diretorio = str(tmp_path)
    livre = [quadra("Areia 1 - Interna", [{"hora": "20:00", "status": "Livre"}])]
    ocupado = [quadra("Areia 1 - Interna", [{"hora": "20:00", "status": "Indisponível"}])]
    persistencia.salvar_extracao(livre, diretorio, datetime(2026, 8, 7, 8, 0))
    gravar_leitura(
        dict(ATUAL, time="2026-08-07T10:00", weather_code=61, temperature_2m=19.8),
        diretorio, datetime(2026, 8, 7, 10, 0),
    )
    gravar_previsao(PREVISAO, diretorio, datetime(2026, 8, 7, 10, 0))
    persistencia.salvar_extracao(ocupado, diretorio, datetime(2026, 8, 7, 10, 0))
    TratamentoDeDados(diretorio).aplicar(datetime(2026, 8, 7, 10, 0))

    persistencia.salvar_extracao(livre, diretorio, datetime(2026, 8, 7, 16, 0))
    gravar_leitura(
        dict(ATUAL, time="2026-08-07T17:45", weather_code=0, temperature_2m=22.0),
        diretorio, datetime(2026, 8, 7, 17, 45),
    )
    revisada = dict(PREVISAO, weather_code=[0, 0, 0], temperature_2m=[30.0, 30.0, 30.0])
    gravar_previsao(revisada, diretorio, datetime(2026, 8, 7, 17, 50))
    persistencia.salvar_extracao(ocupado, diretorio, datetime(2026, 8, 7, 17, 59))
    TratamentoDeDados(diretorio).aplicar(datetime(2026, 8, 7, 17, 59))
    linha = reservas(tmp_path).loc[0]

    assert linha["reservado_em"] == "2026-08-07T17:59:00"
    assert linha["na_hora_da_reserva_clima"] == "Céu limpo"
    assert linha["na_hora_da_reserva_temperatura"] == "22.0"
    assert linha["previsao_para_o_jogo_no_momento_da_reserva_clima"] == "Céu limpo"
    assert linha["previsao_para_o_jogo_no_momento_da_reserva_temperatura"] == "30.0"


def test_devolve_so_os_arquivos_alterados(extracoes):
    persistencia.salvar_extracao(
        [quadra("Areia 3 - Interna", [{"hora": "23:00", "status": "Livre"}])],
        str(extracoes),
        datetime(2026, 8, 7, 8, 0, 0),
    )
    alterados = TratamentoDeDados(str(extracoes)).aplicar(datetime(2026, 8, 7, 17, 0))

    assert [caminho.split("/")[-1] for caminho in alterados] == [
        "areia-1-interna-extracoes.csv"
    ]
