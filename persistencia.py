"""Gravação das extrações em um CSV por quadra."""

import os
import re
import unicodedata
import pandas as pd
from datetime import datetime, timedelta

from config import DIRETORIO_EXTRACOES

SUFIXO_CSV = "-extracoes.csv"
COLUNAS_CSV = [
    "data", "esporte", "periodo", "horario_inicio", "horario_fim", "status",
    "valor_horario", "ultima_atualizacao", "tipo_quadra", "quadra_coberta", "clima",
    "temperatura", "umidade", "precipitacao", "velocidade_vento", "feriado",
    "evento_grande", "jogo_em_porto_alegre",
]


def sem_acento(texto: str) -> str:
    """Devolve o texto sem sinais diacríticos, para comparar e montar nomes de arquivo
    sem depender de o site escrever 'Vôlei' ou 'Volei'."""
    decomposto = unicodedata.normalize("NFKD", texto)
    return "".join(c for c in decomposto if not unicodedata.combining(c))


def slug(nome: str) -> str:
    """Converte o nome de uma quadra em identificador de arquivo: minúsculo, sem acento
    e com qualquer sequência de pontuação ou espaço virando um hífen só."""
    return re.sub(r"[^a-z0-9]+", "-", sem_acento(nome).lower()).strip("-")


def caminho_csv_da_quadra(nome: str, diretorio: str = "") -> str:
    """Monta o caminho do CSV daquela quadra, já que cada quadra tem o seu: assim o
    horário de uma nunca disputa linha com o horário de outra."""
    return os.path.join(diretorio, slug(nome) + SUFIXO_CSV)


def anexar_linha(caminho_csv: str, linha: dict, colunas: list[str], chave: str) -> None:
    """Grava uma linha em CSV com upsert pela coluna `chave`: havendo registro com aquele
    valor, ele é atualizado no lugar; senão a linha entra no fim. Serve para série
    temporal em que a própria fonte já arredonda o instante, como a leitura de clima,
    que repete o mesmo horário enquanto o balde de quinze minutos não vira."""
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


def _achatar_linhas(resultados: list[dict], agora: datetime) -> list[dict]:
    """Achata as quadras coletadas em linhas de reserva prontas para o CSV, pulando as
    que vieram com aviso, derivando horario_fim (início + 1h) e colapsando horários
    repetidos na mesma extração — de cada slot fica sempre o último. A chave de colapso
    inclui a quadra, senão o mesmo horário em quadras diferentes viraria uma linha só."""
    data = agora.date().isoformat()
    por_chave = {}
    for quadra in resultados:
        if quadra["aviso"]:
            continue
        for h in quadra["horarios"]:
            inicio = datetime.strptime(h["hora"], "%H:%M")
            fim = (inicio + timedelta(hours=1)).strftime("%H:%M")
            por_chave[(data, quadra["quadra"], h["hora"])] = {
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


def _gravar_csv(caminho_csv: str, linhas: list[dict], agora: datetime) -> None:
    """Grava as linhas de uma quadra no seu CSV com upsert por (data, esporte,
    horario_inicio): um slot novo é sempre inserido; um slot já existente só é
    atualizado enquanto `agora < horario_inicio`, congelando quando o horário chega ou
    passa. A coluna auxiliar `quadra` cai fora no reindex, já que o arquivo é dela."""
    if os.path.exists(caminho_csv):
        df = pd.read_csv(caminho_csv, dtype=str, keep_default_na=False)
    else:
        df = pd.DataFrame(columns=COLUNAS_CSV)

    for linha in linhas:
        inicio = datetime.strptime(linha["horario_inicio"], "%H:%M").time()
        slot_dt = datetime.combine(agora.date(), inicio)
        existente = (
            (df["data"] == linha["data"])
            & (df["esporte"] == linha["esporte"])
            & (df["horario_inicio"] == linha["horario_inicio"])
        )
        if not existente.any():
            nova = pd.DataFrame([linha]).reindex(columns=COLUNAS_CSV, fill_value="")
            df = nova if df.empty else pd.concat([df, nova], ignore_index=True)
        elif agora < slot_dt:
            df.loc[existente, ["periodo", "horario_fim", "status", "valor_horario", "ultima_atualizacao"]] = [
                linha["periodo"],
                linha["horario_fim"],
                linha["status"],
                linha["valor_horario"],
                linha["ultima_atualizacao"],
            ]

    df.reindex(columns=COLUNAS_CSV, fill_value="").to_csv(caminho_csv, index=False)


def salvar_extracao(
    resultados: list[dict], diretorio: str = DIRETORIO_EXTRACOES, agora=None
) -> list[str]:
    """Distribui a extração em um CSV por quadra, dentro de `diretorio`, criado junto com
    o primeiro arquivo. É o que garante a unicidade do horário: o 17:00 de uma quadra
    nunca disputa linha com o 17:00 de outra. Devolve os caminhos gravados."""
    agora = agora or datetime.now()
    por_quadra = {}
    for linha in _achatar_linhas(resultados, agora):
        por_quadra.setdefault(linha["quadra"], []).append(linha)

    if por_quadra and diretorio:
        os.makedirs(diretorio, exist_ok=True)

    caminhos = []
    for nome, linhas in por_quadra.items():
        caminho_csv = caminho_csv_da_quadra(nome, diretorio)
        _gravar_csv(caminho_csv, linhas, agora)
        caminhos.append(caminho_csv)
    return caminhos
