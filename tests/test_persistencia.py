"""Testes do achatamento em linhas e da gravação de um CSV por quadra."""

import os
from datetime import datetime

import pandas as pd
import pytest

import persistencia

AGORA = datetime(2026, 8, 7, 8, 0, 0)
DIA = "2026-08-07"


def quadra(nome, horarios, coberta="true", tipo="Vôlei de praia", periodo="Noite", data=DIA):
    """Monta o dicionário de uma quadra no formato que _extrair_quadras devolve, para
    os testes descreverem só o que importa em cada caso."""
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


def test_coluna_quadra_coberta_vem_logo_apos_tipo_quadra():
    """A coluna nova entra ao lado de tipo_quadra, não no fim do CSV."""
    colunas = persistencia.COLUNAS_CSV
    assert colunas.index("quadra_coberta") == colunas.index("tipo_quadra") + 1


def test_colunas_de_clima_ficam_em_bloco_contiguo():
    """As cinco colunas que o clima preenche ficam lado a lado, antes dos marcadores de
    contexto: quem abre o CSV lê o ambiente da reserva de uma vez, sem caçar coluna
    perdida no meio das outras."""
    colunas = persistencia.COLUNAS_CSV
    inicio = colunas.index("clima")
    assert colunas[inicio:inicio + 5] == [
        "clima", "temperatura", "umidade", "precipitacao", "velocidade_vento"
    ]
    assert colunas.index("feriado") == inicio + 15


def test_os_tres_blocos_de_clima_espelham_as_mesmas_variaveis():
    """Observado no jogo, observado na hora da reserva e previsto trazem exatamente as
    mesmas cinco variáveis, com prefixo, e ficam nessa ordem: é o que permite comparar
    ponta a ponta o tempo que a pessoa viu ao reservar, o que se esperava para o jogo e
    o que de fato fez, sem procurar equivalência entre nomes diferentes."""
    colunas = persistencia.COLUNAS_CSV
    inicio = colunas.index("clima")

    assert persistencia.COLUNAS_DO_CLIMA_NA_RESERVA == [
        f"reserva_{coluna}" for coluna in persistencia.COLUNAS_DE_CLIMA
    ]
    assert persistencia.COLUNAS_DA_PREVISAO == [
        f"previsao_{coluna}" for coluna in persistencia.COLUNAS_DE_CLIMA
    ]
    assert colunas[inicio + 5:inicio + 15] == (
        persistencia.COLUNAS_DO_CLIMA_NA_RESERVA + persistencia.COLUNAS_DA_PREVISAO
    )


def test_colunas_da_reserva_ficam_juntas_do_carimbo_da_coleta():
    """Quando a reserva foi feita, em que período do dia e com quanta antecedência ficam
    ao lado de primeira_coleta e ultima_atualizacao: as cinco contam a mesma história —
    o que o coletor viu, e quando."""
    colunas = persistencia.COLUNAS_CSV
    inicio = colunas.index("primeira_coleta")

    assert colunas[inicio:inicio + 5] == [
        "primeira_coleta", "ultima_atualizacao",
        "reservado_em", "periodo_da_reserva", "antecedencia_horas",
    ]


def test_mesmo_horario_em_quadras_diferentes_vira_duas_linhas():
    """Regressão da colisão: a chave de colapso inclui a quadra, então o 17:00 da Areia
    1 e o da Areia 2 são dois registros distintos, não um sobrescrevendo o outro."""
    resultados = [
        quadra("Areia 1 - Interna", [{"hora": "17:00", "status": "Livre", "valor": 100.0}]),
        quadra("Areia 2 - Interna", [{"hora": "17:00", "status": "Indisponível"}]),
    ]
    linhas = persistencia._achatar_linhas(resultados, AGORA)

    assert len(linhas) == 2
    assert {l["quadra"] for l in linhas} == {"Areia 1 - Interna", "Areia 2 - Interna"}


def test_linha_carrega_tipo_e_cobertura():
    """As duas colunas novas descem da quadra para a linha do CSV."""
    resultados = [quadra("Areia 4 - EXTERNA", [{"hora": "17:30", "status": "Livre"}], coberta="false")]
    linha = persistencia._achatar_linhas(resultados, AGORA)[0]

    assert linha["tipo_quadra"] == "Vôlei de praia"
    assert linha["quadra_coberta"] == "false"
    assert linha["data"] == "2026-08-07"
    assert linha["valor_horario"] == ""


def test_horario_fim_vira_uma_hora_depois():
    """A duração padrão do slot é uma hora, e a virada do dia não quebra o cálculo."""
    resultados = [quadra("Areia 1 - Interna", [
        {"hora": "17:00", "status": "Livre"},
        {"hora": "23:30", "status": "Livre"},
    ])]
    fins = {l["horario_inicio"]: l["horario_fim"] for l in persistencia._achatar_linhas(resultados, AGORA)}

    assert fins == {"17:00": "18:00", "23:30": "00:30"}


def test_periodo_com_aviso_e_pulado():
    """Período que não carregou não gera linha nenhuma."""
    sem_dados = quadra(None, [])
    sem_dados["aviso"] = "Não foi possível coletar os horários deste período."

    assert persistencia._achatar_linhas([sem_dados], AGORA) == []


def test_cria_um_arquivo_por_quadra(tmp_path):
    """Cada quadra ganha o seu CSV, nomeado pelo slug, criado na primeira vez que a
    quadra aparece."""
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
    """O CSV mantém as colunas de COLUNAS_CSV, com as duas novas preenchidas, e não
    vaza a coluna auxiliar `quadra`, cuja informação já está no nome do arquivo."""
    resultados = [quadra("Areia 4 - EXTERNA", [{"hora": "17:30", "status": "Livre", "valor": 120.0}], coberta="false")]
    caminho = persistencia.salvar_extracao(resultados, str(tmp_path), AGORA)[0]
    df = pd.read_csv(caminho, dtype=str, keep_default_na=False)

    assert list(df.columns) == persistencia.COLUNAS_CSV
    assert "quadra" not in df.columns
    assert df.loc[0, "tipo_quadra"] == "Vôlei de praia"
    assert df.loc[0, "quadra_coberta"] == "false"
    assert df.loc[0, "horario_inicio"] == "17:30"


def test_quadras_diferentes_nao_colidem_no_mesmo_horario(tmp_path):
    """O ganho central do arquivo por quadra: dois 17:00 convivem, cada um no seu CSV,
    com o seu próprio status."""
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
    """Coletando de novo antes de o horário chegar, a linha é atualizada no lugar em vez
    de duplicada."""
    antes = [quadra("Areia 1 - Interna", [{"hora": "17:00", "status": "Indisponível"}])]
    depois = [quadra("Areia 1 - Interna", [{"hora": "17:00", "status": "Livre", "valor": 100.0}])]

    persistencia.salvar_extracao(antes, str(tmp_path), AGORA)
    caminho = persistencia.salvar_extracao(depois, str(tmp_path), AGORA)[0]
    df = pd.read_csv(caminho, dtype=str, keep_default_na=False)

    assert len(df) == 1
    assert df.loc[0, "status"] == "Livre"
    assert df.loc[0, "valor_horario"] == "100.0"


def test_upsert_congela_slot_que_ja_passou(tmp_path):
    """Depois que o horário chega, o registro histórico não é mais reescrito."""
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
    """A madrugada é um período à parte, e não manhã: o site só vende Manhã, Tarde e
    Noite porque a arena não abre de madrugada, mas reservar às três da manhã acontece —
    e é essa a hora que a coluna precisa saber distinguir."""
    assert persistencia.periodo_do_dia(datetime(2026, 8, 7, hora, 30)) == esperado


def test_primeira_coleta_carimbada_uma_vez_so(tmp_path):
    """A primeira vez que um slot é visto fica gravada e não é mais reescrita: é ela que
    diz desde quando aquele horário está sob observação. Sem esse carimbo, um
    `reservado_em` vazio seria ambíguo entre 'nunca reservado' e 'já chegou reservado'."""
    livre = [quadra("Areia 1 - Interna", [{"hora": "20:00", "status": "Livre"}])]
    caminho = persistencia.salvar_extracao(livre, str(tmp_path), AGORA)[0]
    persistencia.salvar_extracao(livre, str(tmp_path), datetime(2026, 8, 7, 12, 0))
    df = pd.read_csv(caminho, dtype=str, keep_default_na=False)

    assert df.loc[0, "primeira_coleta"] == "2026-08-07T08:00:00"
    assert df.loc[0, "ultima_atualizacao"] == "2026-08-07T12:00:00"


def test_reserva_detectada_quando_o_horario_livre_vira_indisponivel(tmp_path):
    """O ganho central da coleta de vários dias: o slot é visto livre numa rodada e
    ocupado na seguinte, e é essa virada que data a reserva. Ficam gravados o instante,
    o período do dia em que a pessoa reservou e a antecedência em relação ao jogo."""
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
    """A antecedência é contada até o início do jogo, não até o fim do dia da coleta:
    reservar na quinta um horário de sábado tem que aparecer como dois dias, que é
    justamente o comportamento que a coleta só do dia atual nunca conseguia ver."""
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
    """Slot que aparece ocupado na primeira coleta foi reservado antes de estar sob
    observação, e a hora dessa reserva não é conhecida: a coluna fica vazia em vez de
    receber a hora da coleta, que seria um dado inventado."""
    caminho = persistencia.salvar_extracao(
        [quadra("Areia 1 - Interna", [{"hora": "20:00", "status": "Indisponível"}])],
        str(tmp_path), AGORA,
    )[0]
    df = pd.read_csv(caminho, dtype=str, keep_default_na=False)

    assert df.loc[0, "reservado_em"] == ""
    assert df.loc[0, "primeira_coleta"] == "2026-08-07T08:00:00"


def test_reserva_detectada_nao_e_reescrita_pelas_rodadas_seguintes(tmp_path):
    """O que interessa é quando a reserva foi feita, não quando foi vista de novo: as
    coletas seguintes continuam achando o slot ocupado e não podem empurrar o carimbo
    para a frente."""
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
    """Voltando a livre, a reserva deixou de existir: as colunas que a descreviam saem
    junto, inclusive os dois blocos de clima congelados na virada. Manter o carimbo antigo
    seria afirmar uma reserva que não está mais lá; se o horário for reservado de novo, a
    próxima virada grava a data nova e o tratamento congela o clima daquele instante."""
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
    """O congelamento compara o relógio com a data da própria linha: às 08:00 de sexta o
    horário das 07:00 de sábado ainda está a um dia de distância. Comparando só a hora,
    todo horário matinal dos dias à frente nasceria congelado e nunca veria a reserva."""
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
    """A rodada percorre vários dias, então a data entra na chave do upsert: o 20:00 de
    hoje e o 20:00 de amanhã são dois registros, e não um sobrescrevendo o outro."""
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
    """Uma quadra que aparece só na segunda coleta cria o seu arquivo sem tocar no da
    primeira."""
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
    """Um horário novo entra no arquivo que já existe, sem apagar o que estava lá."""
    persistencia.salvar_extracao(
        [quadra("Areia 1 - Interna", [{"hora": "17:00", "status": "Livre"}])], str(tmp_path), AGORA
    )
    caminho = persistencia.salvar_extracao(
        [quadra("Areia 1 - Interna", [{"hora": "18:00", "status": "Livre"}])], str(tmp_path), AGORA
    )[0]
    df = pd.read_csv(caminho, dtype=str, keep_default_na=False)

    assert sorted(df["horario_inicio"]) == ["17:00", "18:00"]


def test_coleta_seguinte_preserva_o_clima_ja_gravado(tmp_path):
    """O upsert só reescreve periodo, horario_fim, status, valor_horario e
    ultima_atualizacao, então uma coleta posterior de quadra não apaga as colunas
    ambientais que o tratamento tiver preenchido no mesmo slot."""
    resultados = [quadra("Areia 1 - Interna", [{"hora": "17:00", "status": "Indisponível"}])]
    caminho = persistencia.salvar_extracao(resultados, str(tmp_path), AGORA)[0]
    df = pd.read_csv(caminho, dtype=str, keep_default_na=False)
    df.loc[0, ["clima", "temperatura", "umidade", "precipitacao", "velocidade_vento"]] = [
        "Encoberto", "24.4", "76", "0.0", "13.1"
    ]
    df.to_csv(caminho, index=False)

    depois = [quadra("Areia 1 - Interna", [{"hora": "17:00", "status": "Livre", "valor": 100.0}])]
    persistencia.salvar_extracao(depois, str(tmp_path), AGORA)
    df = pd.read_csv(caminho, dtype=str, keep_default_na=False)

    assert df.loc[0, "status"] == "Livre"
    assert df.loc[0, "clima"] == "Encoberto"
    assert df.loc[0, "umidade"] == "76"
    assert df.loc[0, "velocidade_vento"] == "13.1"


def test_grava_no_diretorio_de_extracoes_por_padrao(tmp_path, monkeypatch):
    """Sem diretório informado, os CSVs vão para .extracoes/ em vez de sujarem a raiz
    do projeto."""
    monkeypatch.chdir(tmp_path)
    resultados = [quadra("Areia 1 - Interna", [{"hora": "17:00", "status": "Livre"}])]
    persistencia.salvar_extracao(resultados, agora=AGORA)

    assert (tmp_path / persistencia.DIRETORIO_EXTRACOES / "areia-1-interna-extracoes.csv").exists()


def test_cria_o_diretorio_se_nao_existir(tmp_path):
    """A primeira coleta numa máquina nova cria o diretório, em vez de estourar."""
    destino = tmp_path / "ainda-nao-existe"
    resultados = [quadra("Areia 1 - Interna", [{"hora": "17:00", "status": "Livre"}])]
    caminhos = persistencia.salvar_extracao(resultados, str(destino), AGORA)

    assert destino.is_dir()
    assert os.path.exists(caminhos[0])


def test_extracao_so_com_aviso_nao_cria_arquivo(tmp_path):
    """Sem linha nenhuma para gravar, nada é criado e a lista de caminhos volta vazia."""
    sem_dados = quadra(None, [])
    sem_dados["aviso"] = "Não foi possível coletar os horários deste período."

    assert persistencia.salvar_extracao([sem_dados], str(tmp_path), AGORA) == []
    assert list(tmp_path.iterdir()) == []
