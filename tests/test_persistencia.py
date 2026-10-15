"""Testes do achatamento em linhas e da gravação de um CSV por quadra."""

import os
from datetime import datetime

import pandas as pd
import pytest

from extrator import persistencia

AGORA = datetime(2026, 8, 7, 8, 0, 0)
DIA = "2026-08-07"


def quadra(nome, horarios, coberta="true", tipo="Vôlei de praia", periodo="Noite", data=DIA):
    return {
        "coletado_em": AGORA.isoformat(timespec="seconds"),
        "data": data,
        "esporte": "Vôlei de praia",
        "periodo": periodo,
        "quadra": nome,
        "tipo_quadra": tipo,
        "quadra_coberta": coberta,
        "aviso": None,
        "horarios": horarios,
    }


def test_arena_e_cidade_abrem_o_csv():
    assert persistencia.COLUNAS_CSV[:2] == ["arena", "cidade"]


def test_linha_carrega_a_arena_e_a_cidade():
    resultados = [quadra("Areia 1 - Interna", [{"hora": "17:00", "status": "Livre"}])]
    linha = persistencia._achatar_linhas(resultados, AGORA, "SP Sports", "Canoas")[0]

    assert linha["arena"] == "SP Sports"
    assert linha["cidade"] == "Canoas"


def test_cidade_descoberta_depois_preenche_a_linha_ja_gravada(tmp_path):
    horarios = [quadra("Areia 1 - Interna", [{"hora": "20:00", "status": "Livre"}])]
    persistencia.salvar_extracao(horarios, str(tmp_path), AGORA, arena="SP Sports")
    caminho = persistencia.salvar_extracao(
        horarios, str(tmp_path), datetime(2026, 8, 7, 9, 0), arena="SP Sports", cidade="Canoas"
    )[0]
    df = pd.read_csv(caminho, dtype=str, keep_default_na=False)

    assert df.loc[0, "cidade"] == "Canoas"


def test_rodada_sem_cidade_nao_apaga_a_que_ja_estava(tmp_path):
    horarios = [quadra("Areia 1 - Interna", [{"hora": "20:00", "status": "Livre"}])]
    persistencia.salvar_extracao(
        horarios, str(tmp_path), AGORA, arena="SP Sports", cidade="Canoas"
    )
    caminho = persistencia.salvar_extracao(
        horarios, str(tmp_path), datetime(2026, 8, 7, 9, 0), arena="SP Sports"
    )[0]
    df = pd.read_csv(caminho, dtype=str, keep_default_na=False)

    assert df.loc[0, "cidade"] == "Canoas"


def test_coluna_quadra_coberta_vem_logo_apos_tipo_quadra():
    colunas = persistencia.COLUNAS_CSV
    assert colunas.index("quadra_coberta") == colunas.index("tipo_quadra") + 1


def test_colunas_de_clima_ficam_em_bloco_contiguo():
    colunas = persistencia.COLUNAS_CSV
    inicio = colunas.index("antes_do_jogo_clima")
    assert colunas[inicio:inicio + 5] == [
        "antes_do_jogo_clima", "antes_do_jogo_temperatura", "antes_do_jogo_umidade",
        "antes_do_jogo_precipitacao", "antes_do_jogo_velocidade_vento",
    ]
    assert colunas.index("feriado") == inicio + 15


def test_os_tres_blocos_de_clima_espelham_as_mesmas_variaveis():
    colunas = persistencia.COLUNAS_CSV
    inicio = colunas.index("antes_do_jogo_clima")

    assert persistencia.COLUNAS_DO_CLIMA_ANTES_DO_JOGO == [
        f"antes_do_jogo_{coluna}" for coluna in persistencia.COLUNAS_DE_CLIMA
    ]
    assert persistencia.COLUNAS_DO_CLIMA_NA_RESERVA == [
        f"na_hora_da_reserva_{coluna}" for coluna in persistencia.COLUNAS_DE_CLIMA
    ]
    assert persistencia.COLUNAS_DA_PREVISAO == [
        f"previsao_para_o_jogo_no_momento_da_reserva_{coluna}"
        for coluna in persistencia.COLUNAS_DE_CLIMA
    ]
    assert colunas[inicio + 5:inicio + 15] == (
        persistencia.COLUNAS_DO_CLIMA_NA_RESERVA + persistencia.COLUNAS_DA_PREVISAO
    )


def test_colunas_da_reserva_ficam_juntas_do_carimbo_da_coleta():
    colunas = persistencia.COLUNAS_CSV
    inicio = colunas.index("primeira_coleta")

    assert colunas[inicio:inicio + 5] == [
        "primeira_coleta", "ultima_atualizacao",
        "reservado_em", "periodo_da_reserva", "antecedencia_horas",
    ]


def test_mesmo_horario_em_quadras_diferentes_vira_duas_linhas():
    resultados = [
        quadra("Areia 1 - Interna", [{"hora": "17:00", "status": "Livre", "valor": 100.0}]),
        quadra("Areia 2 - Interna", [{"hora": "17:00", "status": "Indisponível"}]),
    ]
    linhas = persistencia._achatar_linhas(resultados, AGORA)

    assert len(linhas) == 2
    assert {l["quadra"] for l in linhas} == {"Areia 1 - Interna", "Areia 2 - Interna"}


def test_linha_carrega_tipo_e_cobertura():
    resultados = [quadra("Areia 4 - EXTERNA", [{"hora": "17:30", "status": "Livre"}], coberta="false")]
    linha = persistencia._achatar_linhas(resultados, AGORA)[0]

    assert linha["tipo_quadra"] == "Vôlei de praia"
    assert linha["quadra_coberta"] == "false"
    assert linha["data"] == "2026-08-07"
    assert linha["valor_horario"] == ""


def test_horario_fim_vira_uma_hora_depois():
    resultados = [quadra("Areia 1 - Interna", [
        {"hora": "17:00", "status": "Livre"},
        {"hora": "23:30", "status": "Livre"},
    ])]
    fins = {l["horario_inicio"]: l["horario_fim"] for l in persistencia._achatar_linhas(resultados, AGORA)}

    assert fins == {"17:00": "18:00", "23:30": "00:30"}


def test_periodo_com_aviso_e_pulado():
    sem_dados = quadra(None, [])
    sem_dados["aviso"] = "Não foi possível coletar os horários deste período."

    assert persistencia._achatar_linhas([sem_dados], AGORA) == []


def test_cria_um_arquivo_por_quadra(tmp_path):
    resultados = [
        quadra("Areia 1 - Interna", [{"hora": "17:00", "status": "Livre", "valor": 100.0}]),
        quadra("Areia 4 - EXTERNA", [{"hora": "17:30", "status": "Livre"}], coberta="false"),
    ]
    caminhos = persistencia.salvar_extracao(resultados, str(tmp_path), AGORA)

    assert sorted(os.path.basename(c) for c in caminhos) == [
        "areia-1-interna-extracoes.csv",
        "areia-4-externa-extracoes.csv",
    ]
    assert all(os.path.exists(c) for c in caminhos)


def test_cabecalho_e_conteudo_do_csv(tmp_path):
    resultados = [quadra("Areia 4 - EXTERNA", [{"hora": "17:30", "status": "Livre", "valor": 120.0}], coberta="false")]
    caminho = persistencia.salvar_extracao(resultados, str(tmp_path), AGORA)[0]
    df = pd.read_csv(caminho, dtype=str, keep_default_na=False)

    assert list(df.columns) == persistencia.COLUNAS_CSV
    assert "quadra" not in df.columns
    assert df.loc[0, "tipo_quadra"] == "Vôlei de praia"
    assert df.loc[0, "quadra_coberta"] == "false"
    assert df.loc[0, "horario_inicio"] == "17:30"


def test_quadras_diferentes_nao_colidem_no_mesmo_horario(tmp_path):
    resultados = [
        quadra("Areia 1 - Interna", [{"hora": "17:00", "status": "Livre", "valor": 100.0}]),
        quadra("Areia 2 - Interna", [{"hora": "17:00", "status": "Indisponível"}]),
    ]
    persistencia.salvar_extracao(resultados, str(tmp_path), AGORA)

    um = pd.read_csv(tmp_path / "areia-1-interna-extracoes.csv", dtype=str, keep_default_na=False)
    dois = pd.read_csv(tmp_path / "areia-2-interna-extracoes.csv", dtype=str, keep_default_na=False)

    assert um.loc[0, "status"] == "Livre"
    assert dois.loc[0, "status"] == "Indisponível"


def test_upsert_atualiza_slot_futuro(tmp_path):
    antes = [quadra("Areia 1 - Interna", [{"hora": "17:00", "status": "Indisponível"}])]
    depois = [quadra("Areia 1 - Interna", [{"hora": "17:00", "status": "Livre", "valor": 100.0}])]

    persistencia.salvar_extracao(antes, str(tmp_path), AGORA)
    caminho = persistencia.salvar_extracao(depois, str(tmp_path), AGORA)[0]
    df = pd.read_csv(caminho, dtype=str, keep_default_na=False)

    assert len(df) == 1
    assert df.loc[0, "status"] == "Livre"
    assert df.loc[0, "valor_horario"] == "100.0"


def test_upsert_congela_slot_que_ja_passou(tmp_path):
    antes = [quadra("Areia 1 - Interna", [{"hora": "17:00", "status": "Livre", "valor": 100.0}])]
    depois = [quadra("Areia 1 - Interna", [{"hora": "17:00", "status": "Indisponível"}])]

    persistencia.salvar_extracao(antes, str(tmp_path), AGORA)
    caminho = persistencia.salvar_extracao(depois, str(tmp_path), datetime(2026, 8, 7, 18, 0, 0))[0]
    df = pd.read_csv(caminho, dtype=str, keep_default_na=False)

    assert len(df) == 1
    assert df.loc[0, "status"] == "Livre"


@pytest.mark.parametrize(
    "hora, esperado",
    [(0, "Madrugada"), (3, "Madrugada"), (5, "Madrugada"), (6, "Manhã"), (11, "Manhã"),
     (12, "Tarde"), (17, "Tarde"), (18, "Noite"), (23, "Noite")],
)
def test_periodo_do_dia(hora, esperado):
    assert persistencia.periodo_do_dia(datetime(2026, 8, 7, hora, 30)) == esperado


def test_primeira_coleta_carimbada_uma_vez_so(tmp_path):
    livre = [quadra("Areia 1 - Interna", [{"hora": "20:00", "status": "Livre"}])]
    caminho = persistencia.salvar_extracao(livre, str(tmp_path), AGORA)[0]
    persistencia.salvar_extracao(livre, str(tmp_path), datetime(2026, 8, 7, 12, 0))
    df = pd.read_csv(caminho, dtype=str, keep_default_na=False)

    assert df.loc[0, "primeira_coleta"] == "2026-08-07T08:00:00"
    assert df.loc[0, "ultima_atualizacao"] == "2026-08-07T12:00:00"


def test_reserva_detectada_quando_o_horario_livre_vira_indisponivel(tmp_path):
    persistencia.salvar_extracao(
        [quadra("Areia 1 - Interna", [{"hora": "20:00", "status": "Livre"}])], str(tmp_path), AGORA
    )
    caminho = persistencia.salvar_extracao(
        [quadra("Areia 1 - Interna", [{"hora": "20:00", "status": "Indisponível"}])],
        str(tmp_path), datetime(2026, 8, 7, 17, 0),
    )[0]
    df = pd.read_csv(caminho, dtype=str, keep_default_na=False)

    assert df.loc[0, "reservado_em"] == "2026-08-07T17:00:00"
    assert df.loc[0, "periodo_da_reserva"] == "Tarde"
    assert df.loc[0, "antecedencia_horas"] == "3.00"


def test_reserva_de_dias_antes_mantem_a_antecedencia_grande(tmp_path):
    sabado = "2026-08-09"
    persistencia.salvar_extracao(
        [quadra("Areia 1 - Interna", [{"hora": "20:00", "status": "Livre"}], data=sabado)],
        str(tmp_path), AGORA,
    )
    caminho = persistencia.salvar_extracao(
        [quadra("Areia 1 - Interna", [{"hora": "20:00", "status": "Indisponível"}], data=sabado)],
        str(tmp_path), datetime(2026, 8, 7, 20, 0),
    )[0]
    df = pd.read_csv(caminho, dtype=str, keep_default_na=False)

    assert df.loc[0, "antecedencia_horas"] == "48.00"
    assert df.loc[0, "periodo_da_reserva"] == "Noite"


def test_horario_que_ja_nasce_indisponivel_nao_inventa_reserva(tmp_path):
    caminho = persistencia.salvar_extracao(
        [quadra("Areia 1 - Interna", [{"hora": "20:00", "status": "Indisponível"}])],
        str(tmp_path), AGORA,
    )[0]
    df = pd.read_csv(caminho, dtype=str, keep_default_na=False)

    assert df.loc[0, "reservado_em"] == ""
    assert df.loc[0, "primeira_coleta"] == "2026-08-07T08:00:00"


def test_reserva_detectada_nao_e_reescrita_pelas_rodadas_seguintes(tmp_path):
    persistencia.salvar_extracao(
        [quadra("Areia 1 - Interna", [{"hora": "20:00", "status": "Livre"}])], str(tmp_path), AGORA
    )
    ocupado = [quadra("Areia 1 - Interna", [{"hora": "20:00", "status": "Indisponível"}])]
    persistencia.salvar_extracao(ocupado, str(tmp_path), datetime(2026, 8, 7, 17, 0))
    caminho = persistencia.salvar_extracao(ocupado, str(tmp_path), datetime(2026, 8, 7, 18, 30))[0]
    df = pd.read_csv(caminho, dtype=str, keep_default_na=False)

    assert df.loc[0, "reservado_em"] == "2026-08-07T17:00:00"
    assert df.loc[0, "antecedencia_horas"] == "3.00"


def test_cancelamento_apaga_o_que_a_reserva_tinha_deixado(tmp_path):
    persistencia.salvar_extracao(
        [quadra("Areia 1 - Interna", [{"hora": "20:00", "status": "Livre"}])], str(tmp_path), AGORA
    )
    caminho = persistencia.salvar_extracao(
        [quadra("Areia 1 - Interna", [{"hora": "20:00", "status": "Indisponível"}])],
        str(tmp_path), datetime(2026, 8, 7, 15, 0),
    )[0]
    df = pd.read_csv(caminho, dtype=str, keep_default_na=False)
    df.loc[0, persistencia.COLUNAS_CONGELADAS_NA_VIRADA] = [
        "Encoberto", "24.4", "76", "0.0", "13.1",
        "Chuva forte", "15.2", "80", "4.1", "22.0",
    ]
    df.to_csv(caminho, index=False)

    persistencia.salvar_extracao(
        [quadra("Areia 1 - Interna", [{"hora": "20:00", "status": "Livre"}])],
        str(tmp_path), datetime(2026, 8, 7, 16, 0),
    )
    df = pd.read_csv(caminho, dtype=str, keep_default_na=False)

    assert list(df.loc[0, persistencia.COLUNAS_DA_VIRADA]) == (
        [""] * len(persistencia.COLUNAS_DA_VIRADA)
    )


def test_slot_de_outro_dia_nao_congela_pelo_relogio_de_hoje(tmp_path):
    amanha = "2026-08-08"
    persistencia.salvar_extracao(
        [quadra("Areia 1 - Interna", [{"hora": "07:00", "status": "Livre"}], data=amanha)],
        str(tmp_path), AGORA,
    )
    caminho = persistencia.salvar_extracao(
        [quadra("Areia 1 - Interna", [{"hora": "07:00", "status": "Indisponível"}], data=amanha)],
        str(tmp_path), datetime(2026, 8, 7, 9, 0),
    )[0]
    df = pd.read_csv(caminho, dtype=str, keep_default_na=False)

    assert df.loc[0, "status"] == "Indisponível"
    assert df.loc[0, "reservado_em"] == "2026-08-07T09:00:00"


def test_mesmo_horario_em_dias_diferentes_vira_duas_linhas(tmp_path):
    caminho = persistencia.salvar_extracao(
        [
            quadra("Areia 1 - Interna", [{"hora": "20:00", "status": "Livre"}]),
            quadra("Areia 1 - Interna", [{"hora": "20:00", "status": "Indisponível"}],
                   data="2026-08-08"),
        ],
        str(tmp_path), AGORA,
    )[0]
    df = pd.read_csv(caminho, dtype=str, keep_default_na=False).set_index("data")

    assert len(df) == 2
    assert df.loc["2026-08-07", "status"] == "Livre"
    assert df.loc["2026-08-08", "status"] == "Indisponível"


def test_quadra_nova_nao_altera_o_arquivo_existente(tmp_path):
    persistencia.salvar_extracao(
        [quadra("Areia 1 - Interna", [{"hora": "17:00", "status": "Livre"}])], str(tmp_path), AGORA
    )
    antes = (tmp_path / "areia-1-interna-extracoes.csv").read_text(encoding="utf-8")

    persistencia.salvar_extracao(
        [quadra("Areia 9 - Nova", [{"hora": "17:00", "status": "Livre"}])], str(tmp_path), AGORA
    )

    assert (tmp_path / "areia-9-nova-extracoes.csv").exists()
    assert (tmp_path / "areia-1-interna-extracoes.csv").read_text(encoding="utf-8") == antes


def test_arquivo_existente_e_estendido(tmp_path):
    persistencia.salvar_extracao(
        [quadra("Areia 1 - Interna", [{"hora": "17:00", "status": "Livre"}])], str(tmp_path), AGORA
    )
    caminho = persistencia.salvar_extracao(
        [quadra("Areia 1 - Interna", [{"hora": "18:00", "status": "Livre"}])], str(tmp_path), AGORA
    )[0]
    df = pd.read_csv(caminho, dtype=str, keep_default_na=False)

    assert sorted(df["horario_inicio"]) == ["17:00", "18:00"]


def test_coleta_seguinte_preserva_o_clima_ja_gravado(tmp_path):
    resultados = [quadra("Areia 1 - Interna", [{"hora": "17:00", "status": "Indisponível"}])]
    caminho = persistencia.salvar_extracao(resultados, str(tmp_path), AGORA)[0]
    df = pd.read_csv(caminho, dtype=str, keep_default_na=False)
    df.loc[0, persistencia.COLUNAS_DO_CLIMA_ANTES_DO_JOGO] = [
        "Encoberto", "24.4", "76", "0.0", "13.1"
    ]
    df.to_csv(caminho, index=False)

    depois = [quadra("Areia 1 - Interna", [{"hora": "17:00", "status": "Livre", "valor": 100.0}])]
    persistencia.salvar_extracao(depois, str(tmp_path), AGORA)
    df = pd.read_csv(caminho, dtype=str, keep_default_na=False)

    assert df.loc[0, "status"] == "Livre"
    assert df.loc[0, "antes_do_jogo_clima"] == "Encoberto"
    assert df.loc[0, "antes_do_jogo_umidade"] == "76"
    assert df.loc[0, "antes_do_jogo_velocidade_vento"] == "13.1"


def test_grava_no_diretorio_de_extracoes_por_padrao(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    resultados = [quadra("Areia 1 - Interna", [{"hora": "17:00", "status": "Livre"}])]
    persistencia.salvar_extracao(resultados, agora=AGORA)

    assert (tmp_path / persistencia.DIRETORIO_EXTRACOES / "areia-1-interna-extracoes.csv").exists()


def test_cria_o_diretorio_se_nao_existir(tmp_path):
    destino = tmp_path / "ainda-nao-existe"
    resultados = [quadra("Areia 1 - Interna", [{"hora": "17:00", "status": "Livre"}])]
    caminhos = persistencia.salvar_extracao(resultados, str(destino), AGORA)

    assert destino.is_dir()
    assert os.path.exists(caminhos[0])


def test_extracao_so_com_aviso_nao_cria_arquivo(tmp_path):
    sem_dados = quadra(None, [])
    sem_dados["aviso"] = "Não foi possível coletar os horários deste período."

    assert persistencia.salvar_extracao([sem_dados], str(tmp_path), AGORA) == []
    assert list(tmp_path.iterdir()) == []


def test_verificacao_da_arena_e_atualizada_no_lugar(tmp_path):
    persistencia.registrar_verificacao("SP Sports", ["Areia 1"], str(tmp_path), AGORA)
    caminho = persistencia.registrar_verificacao(
        "SP Sports", ["Areia 1", "Areia 2"], str(tmp_path), datetime(2026, 8, 7, 8, 15)
    )
    df = pd.read_csv(caminho, dtype=str, keep_default_na=False)

    assert len(df) == 1
    assert df.loc[0, "ultima_verificacao"] == "2026-08-07T08:15:00"
    assert df.loc[0, "quadras_verificadas"] == "2"
    assert df.loc[0, "quadras"] == "Areia 1; Areia 2"


def test_cada_arena_tem_a_sua_linha_no_log(tmp_path):
    persistencia.registrar_verificacao("SP Sports", ["Areia 1"], str(tmp_path), AGORA)
    caminho = persistencia.registrar_verificacao("Arena Parobé", ["Grama 5"], str(tmp_path), AGORA)
    df = pd.read_csv(caminho, dtype=str, keep_default_na=False)

    assert list(df["arena"]) == ["SP Sports", "Arena Parobé"]
    assert list(df["quadras"]) == ["Areia 1", "Grama 5"]


def test_virada_em_reserva_preserva_o_clima_pre_jogo(tmp_path):
    caminho = persistencia.salvar_extracao(
        [quadra("Areia 1 - Interna", [{"hora": "20:00", "status": "Livre"}])],
        str(tmp_path), AGORA,
    )[0]
    df = pd.read_csv(caminho, dtype=str, keep_default_na=False)
    df.loc[0, persistencia.COLUNAS_DO_CLIMA_ANTES_DO_JOGO] = [
        "Encoberto", "24.4", "76", "0.0", "13.1",
    ]
    df.to_csv(caminho, index=False)

    quando = datetime(2026, 8, 7, 19, 59, 57)
    persistencia.salvar_extracao(
        [quadra("Areia 1 - Interna", [{"hora": "20:00", "status": "Indisponível"}])],
        str(tmp_path), quando,
    )
    df = pd.read_csv(caminho, dtype=str, keep_default_na=False)

    assert df.loc[0, "reservado_em"] == "2026-08-07T19:59:57"
    assert df.loc[0, "antecedencia_horas"] == "0.00"
    assert df.loc[0, "periodo_da_reserva"] == "Noite"
    assert df.loc[0, "antes_do_jogo_clima"] == "Encoberto"
    assert df.loc[0, "antes_do_jogo_temperatura"] == "24.4"
    assert df.loc[0, "antes_do_jogo_umidade"] == "76"


def test_periodo_do_horario_futuro_e_atualizado_sem_duplicar(tmp_path):
    persistencia.salvar_extracao(
        [quadra("Areia 1 - Interna", [{"hora": "17:00", "status": "Livre"}], periodo="Tarde")],
        str(tmp_path), AGORA,
    )
    caminho = persistencia.salvar_extracao(
        [quadra("Areia 1 - Interna", [{"hora": "17:00", "status": "Livre"}], periodo="Noite")],
        str(tmp_path), datetime(2026, 8, 7, 12, 0),
    )[0]
    df = pd.read_csv(caminho, dtype=str, keep_default_na=False)

    assert len(df) == 1
    assert df.loc[0, "periodo"] == "Noite"
    assert df.loc[0, "horario_inicio"] == "17:00"
    assert df.loc[0, "horario_fim"] == "18:00"
    assert df.loc[0, "reservado_em"] == ""


def test_log_cria_o_diretorio_se_nao_existir(tmp_path):
    destino = tmp_path / "ainda-nao-existe"
    caminho = persistencia.registrar_verificacao("SP Sports", ["Areia 1"], str(destino), AGORA)

    assert os.path.exists(caminho)
