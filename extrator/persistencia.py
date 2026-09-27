"""Gravação das extrações em um CSV por quadra."""

import os
import re
import unicodedata
import pandas as pd
from datetime import date, datetime, timedelta

from extrator.config import ARQUIVO_DE_VERIFICACOES, DIRETORIO_EXTRACOES, DIRETORIO_LOGS

SUFIXO_CSV = "-extracoes.csv"
COLUNAS_DO_LOG = ["arena", "ultima_verificacao", "quadras_verificadas", "quadras"]
COLUNAS_DE_CLIMA = ["clima", "temperatura", "umidade", "precipitacao", "velocidade_vento"]
COLUNAS_DO_CLIMA_NA_RESERVA = [f"reserva_{coluna}" for coluna in COLUNAS_DE_CLIMA]
COLUNAS_DA_PREVISAO = [
    f"previsao_para_o_jogo_no_momento_da_reserva_{coluna}" for coluna in COLUNAS_DE_CLIMA
]
COLUNAS_CONGELADAS_NA_VIRADA = COLUNAS_DO_CLIMA_NA_RESERVA + COLUNAS_DA_PREVISAO
COLUNAS_DA_RESERVA = ["reservado_em", "periodo_da_reserva", "antecedencia_horas"]
COLUNAS_DA_VIRADA = COLUNAS_DA_RESERVA + COLUNAS_CONGELADAS_NA_VIRADA
COLUNAS_DA_COLETA = ["periodo", "horario_fim", "status", "valor_horario", "ultima_atualizacao"]
COLUNAS_DA_ARENA = ["arena", "cidade"]
COLUNAS_CSV = [
    *COLUNAS_DA_ARENA,
    "data", "esporte", "periodo", "horario_inicio", "horario_fim", "status",
    "valor_horario", "primeira_coleta", "ultima_atualizacao",
    *COLUNAS_DA_RESERVA, "tipo_quadra", "quadra_coberta",
    *COLUNAS_DE_CLIMA, *COLUNAS_DO_CLIMA_NA_RESERVA, *COLUNAS_DA_PREVISAO,
    "feriado", "evento_grande", "jogo_em_porto_alegre",
]
FAIXAS_DO_DIA = ((6, "Manhã"), (12, "Tarde"), (18, "Noite"))
STATUS_LIVRE = "livre"


def sem_acento(texto: str) -> str:
    decomposto = unicodedata.normalize("NFKD", texto)
    return "".join(c for c in decomposto if not unicodedata.combining(c))


def slug(nome: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", sem_acento(nome).lower()).strip("-")


def periodo_do_dia(momento: datetime) -> str:
    for hora, nome in reversed(FAIXAS_DO_DIA):
        if momento.hour >= hora:
            return nome
    return "Madrugada"


def caminho_csv_da_quadra(nome: str, diretorio: str = "") -> str:
    return os.path.join(diretorio, slug(nome) + SUFIXO_CSV)


def anexar_linha(caminho_csv: str, linha: dict, colunas: list[str], chave: str) -> None:
    if os.path.exists(caminho_csv):
        df = pd.read_csv(caminho_csv, dtype=str, keep_default_na=False)
    else:
        df = pd.DataFrame(columns=colunas)
    df = df.reindex(columns=colunas, fill_value="")

    existente = df[chave] == str(linha[chave])
    if existente.any():
        df.loc[existente, colunas] = [linha.get(coluna, "") for coluna in colunas]
    else:
        nova = pd.DataFrame([linha]).reindex(columns=colunas, fill_value="")
        df = nova if df.empty else pd.concat([df, nova], ignore_index=True)

    df.to_csv(caminho_csv, index=False)


def _achatar_linhas(
    resultados: list[dict], agora: datetime, arena: str = "", cidade: str = ""
) -> list[dict]:
    por_chave = {}
    for quadra in resultados:
        if quadra["aviso"]:
            continue
        data = quadra["data"]
        for h in quadra["horarios"]:
            inicio = datetime.strptime(h["hora"], "%H:%M")
            fim = (inicio + timedelta(hours=1)).strftime("%H:%M")
            por_chave[(data, quadra["quadra"], h["hora"])] = {
                "arena": arena,
                "cidade": cidade,
                "data": data,
                "esporte": quadra["esporte"],
                "periodo": quadra["periodo"],
                "horario_inicio": h["hora"],
                "horario_fim": fim,
                "status": h["status"],
                "valor_horario": h.get("valor", ""),
                "ultima_atualizacao": agora.isoformat(timespec="seconds"),
                "tipo_quadra": quadra["tipo_quadra"],
                "quadra_coberta": quadra["quadra_coberta"],
                "quadra": quadra["quadra"],
            }
    return list(por_chave.values())


def _momento_do_slot(linha: dict) -> datetime:
    inicio = datetime.strptime(linha["horario_inicio"], "%H:%M").time()
    return datetime.combine(date.fromisoformat(linha["data"]), inicio)


def _marcar_reserva(
    status_anterior: str, status_novo: str, slot_dt: datetime, agora: datetime
) -> list[str] | None:
    era_livre = status_anterior.lower() == STATUS_LIVRE
    esta_livre = status_novo.lower() == STATUS_LIVRE
    limpas = [""] * len(COLUNAS_CONGELADAS_NA_VIRADA)
    if era_livre and not esta_livre:
        horas = (slot_dt - agora).total_seconds() / 3600
        return [
            agora.isoformat(timespec="seconds"), periodo_do_dia(agora), f"{horas:.2f}", *limpas
        ]
    if esta_livre and not era_livre:
        return ["", "", "", *limpas]
    return None


def _gravar_csv(caminho_csv: str, linhas: list[dict], agora: datetime) -> None:
    if os.path.exists(caminho_csv):
        df = pd.read_csv(caminho_csv, dtype=str, keep_default_na=False)
    else:
        df = pd.DataFrame(columns=COLUNAS_CSV)
    df = df.reindex(columns=COLUNAS_CSV, fill_value="")

    for linha in linhas:
        slot_dt = _momento_do_slot(linha)
        existente = (
            (df["data"] == linha["data"])
            & (df["esporte"] == linha["esporte"])
            & (df["horario_inicio"] == linha["horario_inicio"])
        )
        if not existente.any():
            primeira = dict(linha, primeira_coleta=agora.isoformat(timespec="seconds"))
            nova = pd.DataFrame([primeira]).reindex(columns=COLUNAS_CSV, fill_value="")
            df = nova if df.empty else pd.concat([df, nova], ignore_index=True)
        elif agora < slot_dt:
            reserva = _marcar_reserva(
                df.loc[existente, "status"].iloc[0], linha["status"], slot_dt, agora
            )
            df.loc[existente, COLUNAS_DA_COLETA] = [linha[coluna] for coluna in COLUNAS_DA_COLETA]
            conhecidas = [coluna for coluna in COLUNAS_DA_ARENA if linha[coluna]]
            if conhecidas:
                df.loc[existente, conhecidas] = [linha[coluna] for coluna in conhecidas]
            if reserva is not None:
                df.loc[existente, COLUNAS_DA_VIRADA] = reserva

    df.to_csv(caminho_csv, index=False)


def registrar_verificacao(
    arena: str, quadras: list[str], diretorio: str = DIRETORIO_LOGS, agora=None
) -> str:
    agora = agora or datetime.now()
    caminho_csv = os.path.join(diretorio, ARQUIVO_DE_VERIFICACOES)
    if diretorio:
        os.makedirs(diretorio, exist_ok=True)

    linha = {
        "arena": arena,
        "ultima_verificacao": agora.isoformat(timespec="seconds"),
        "quadras_verificadas": len(quadras),
        "quadras": "; ".join(quadras),
    }
    anexar_linha(caminho_csv, linha, COLUNAS_DO_LOG, "arena")
    return caminho_csv


def salvar_extracao(
    resultados: list[dict],
    diretorio: str = DIRETORIO_EXTRACOES,
    agora=None,
    arena: str = "",
    cidade: str = "",
) -> list[str]:
    agora = agora or datetime.now()
    por_quadra = {}
    for linha in _achatar_linhas(resultados, agora, arena, cidade):
        por_quadra.setdefault(linha["quadra"], []).append(linha)

    if por_quadra and diretorio:
        os.makedirs(diretorio, exist_ok=True)

    caminhos = []
    for nome, linhas in por_quadra.items():
        caminho_csv = caminho_csv_da_quadra(nome, diretorio)
        _gravar_csv(caminho_csv, linhas, agora)
        caminhos.append(caminho_csv)
    return caminhos
