"""Testes do achatamento em linhas e da gravação de um CSV por quadra."""

import os
from datetime import datetime

import pandas as pd
import pytest

import coletor

AGORA = datetime(2026, 8, 7, 8, 0, 0)


def quadra(nome, horarios, coberta="true", tipo="Vôlei de praia", periodo="Noite"):
    """Monta o dicionário de uma quadra no formato que _extrair_quadras devolve, para
    os testes descreverem só o que importa em cada caso."""
    return {
        "coletado_em": AGORA.isoformat(timespec="seconds"),
        "esporte": "Vôlei de praia",
        "periodo": periodo,
        "quadra": nome,
        "tipo_quadra": tipo,
        "quadra_coberta": coberta,
        "aviso": None,
        "horarios": horarios,
    }


def test_mesmo_horario_em_quadras_diferentes_vira_duas_linhas():
    """Regressão da colisão: a chave de colapso inclui a quadra, então o 17:00 da Areia
    1 e o da Areia 2 são dois registros distintos, não um sobrescrevendo o outro."""
    resultados = [
        quadra("Areia 1 - Interna", [{"hora": "17:00", "status": "Livre", "valor": 100.0}]),
        quadra("Areia 2 - Interna", [{"hora": "17:00", "status": "Indisponível"}]),
    ]
    linhas = coletor._achatar_linhas(resultados, AGORA)

    assert len(linhas) == 2
    assert {l["quadra"] for l in linhas} == {"Areia 1 - Interna", "Areia 2 - Interna"}


def test_linha_carrega_tipo_e_cobertura():
    """As duas colunas novas descem da quadra para a linha do CSV."""
    resultados = [quadra("Areia 4 - EXTERNA", [{"hora": "17:30", "status": "Livre"}], coberta="false")]
    linha = coletor._achatar_linhas(resultados, AGORA)[0]

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
    fins = {l["horario_inicio"]: l["horario_fim"] for l in coletor._achatar_linhas(resultados, AGORA)}

    assert fins == {"17:00": "18:00", "23:30": "00:30"}


def test_periodo_com_aviso_e_pulado():
    """Período que não carregou não gera linha nenhuma."""
    sem_dados = quadra(None, [])
    sem_dados["aviso"] = "Não foi possível coletar os horários deste período."

    assert coletor._achatar_linhas([sem_dados], AGORA) == []


def test_cria_um_arquivo_por_quadra(tmp_path):
    """Cada quadra ganha o seu CSV, nomeado pelo slug, criado na primeira vez que a
    quadra aparece."""
    resultados = [
        quadra("Areia 1 - Interna", [{"hora": "17:00", "status": "Livre", "valor": 100.0}]),
        quadra("Areia 4 - EXTERNA", [{"hora": "17:30", "status": "Livre"}], coberta="false"),
    ]
    caminhos = coletor.salvar_extracao(resultados, str(tmp_path), AGORA)

    assert sorted(os.path.basename(c) for c in caminhos) == [
        "areia-1-interna-extracoes.csv",
        "areia-4-externa-extracoes.csv",
    ]
    assert all(os.path.exists(c) for c in caminhos)


def test_cabecalho_e_conteudo_do_csv(tmp_path):
    """O CSV mantém as colunas de COLUNAS_CSV, com as duas novas preenchidas, e não
    vaza a coluna auxiliar `quadra`, cuja informação já está no nome do arquivo."""
    resultados = [quadra("Areia 4 - EXTERNA", [{"hora": "17:30", "status": "Livre", "valor": 120.0}], coberta="false")]
    caminho = coletor.salvar_extracao(resultados, str(tmp_path), AGORA)[0]
    df = pd.read_csv(caminho, dtype=str, keep_default_na=False)

    assert list(df.columns) == coletor.COLUNAS_CSV
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
    coletor.salvar_extracao(resultados, str(tmp_path), AGORA)

    um = pd.read_csv(tmp_path / "areia-1-interna-extracoes.csv", dtype=str, keep_default_na=False)
    dois = pd.read_csv(tmp_path / "areia-2-interna-extracoes.csv", dtype=str, keep_default_na=False)

    assert um.loc[0, "status"] == "Livre"
    assert dois.loc[0, "status"] == "Indisponível"


def test_upsert_atualiza_slot_futuro(tmp_path):
    """Coletando de novo antes de o horário chegar, a linha é atualizada no lugar em vez
    de duplicada."""
    antes = [quadra("Areia 1 - Interna", [{"hora": "17:00", "status": "Indisponível"}])]
    depois = [quadra("Areia 1 - Interna", [{"hora": "17:00", "status": "Livre", "valor": 100.0}])]

    coletor.salvar_extracao(antes, str(tmp_path), AGORA)
    caminho = coletor.salvar_extracao(depois, str(tmp_path), AGORA)[0]
    df = pd.read_csv(caminho, dtype=str, keep_default_na=False)

    assert len(df) == 1
    assert df.loc[0, "status"] == "Livre"
    assert df.loc[0, "valor_horario"] == "100.0"


def test_upsert_congela_slot_que_ja_passou(tmp_path):
    """Depois que o horário chega, o registro histórico não é mais reescrito."""
    antes = [quadra("Areia 1 - Interna", [{"hora": "17:00", "status": "Livre", "valor": 100.0}])]
    depois = [quadra("Areia 1 - Interna", [{"hora": "17:00", "status": "Indisponível"}])]

    coletor.salvar_extracao(antes, str(tmp_path), AGORA)
    caminho = coletor.salvar_extracao(depois, str(tmp_path), datetime(2026, 8, 7, 18, 0, 0))[0]
    df = pd.read_csv(caminho, dtype=str, keep_default_na=False)

    assert len(df) == 1
    assert df.loc[0, "status"] == "Livre"


def test_quadra_nova_nao_altera_o_arquivo_existente(tmp_path):
    """Uma quadra que aparece só na segunda coleta cria o seu arquivo sem tocar no da
    primeira."""
    coletor.salvar_extracao(
        [quadra("Areia 1 - Interna", [{"hora": "17:00", "status": "Livre"}])], str(tmp_path), AGORA
    )
    antes = (tmp_path / "areia-1-interna-extracoes.csv").read_text(encoding="utf-8")

    coletor.salvar_extracao(
        [quadra("Areia 9 - Nova", [{"hora": "17:00", "status": "Livre"}])], str(tmp_path), AGORA
    )

    assert (tmp_path / "areia-9-nova-extracoes.csv").exists()
    assert (tmp_path / "areia-1-interna-extracoes.csv").read_text(encoding="utf-8") == antes


def test_arquivo_existente_e_estendido(tmp_path):
    """Um horário novo entra no arquivo que já existe, sem apagar o que estava lá."""
    coletor.salvar_extracao(
        [quadra("Areia 1 - Interna", [{"hora": "17:00", "status": "Livre"}])], str(tmp_path), AGORA
    )
    caminho = coletor.salvar_extracao(
        [quadra("Areia 1 - Interna", [{"hora": "18:00", "status": "Livre"}])], str(tmp_path), AGORA
    )[0]
    df = pd.read_csv(caminho, dtype=str, keep_default_na=False)

    assert sorted(df["horario_inicio"]) == ["17:00", "18:00"]


def test_grava_no_diretorio_de_extracoes_por_padrao(tmp_path, monkeypatch):
    """Sem diretório informado, os CSVs vão para .extracoes/ em vez de sujarem a raiz
    do projeto."""
    monkeypatch.chdir(tmp_path)
    resultados = [quadra("Areia 1 - Interna", [{"hora": "17:00", "status": "Livre"}])]
    coletor.salvar_extracao(resultados, agora=AGORA)

    assert (tmp_path / coletor.DIRETORIO_EXTRACOES / "areia-1-interna-extracoes.csv").exists()


def test_cria_o_diretorio_se_nao_existir(tmp_path):
    """A primeira coleta numa máquina nova cria o diretório, em vez de estourar."""
    destino = tmp_path / "ainda-nao-existe"
    resultados = [quadra("Areia 1 - Interna", [{"hora": "17:00", "status": "Livre"}])]
    caminhos = coletor.salvar_extracao(resultados, str(destino), AGORA)

    assert destino.is_dir()
    assert os.path.exists(caminhos[0])


def test_extracao_so_com_aviso_nao_cria_arquivo(tmp_path):
    """Sem linha nenhuma para gravar, nada é criado e a lista de caminhos volta vazia."""
    sem_dados = quadra(None, [])
    sem_dados["aviso"] = "Não foi possível coletar os horários deste período."

    assert coletor.salvar_extracao([sem_dados], str(tmp_path), AGORA) == []
    assert list(tmp_path.iterdir()) == []
