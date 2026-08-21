"""Gravação das extrações em um CSV por quadra."""

import os
import re
import unicodedata
import pandas as pd
from datetime import date, datetime, timedelta

from config import DIRETORIO_EXTRACOES

SUFIXO_CSV = "-extracoes.csv"
COLUNAS_DE_CLIMA = ["clima", "temperatura", "umidade", "precipitacao", "velocidade_vento"]
COLUNAS_DA_PREVISAO = [f"previsao_{coluna}" for coluna in COLUNAS_DE_CLIMA]
COLUNAS_DA_RESERVA = ["reservado_em", "periodo_da_reserva", "antecedencia_horas"]
COLUNAS_DA_VIRADA = COLUNAS_DA_RESERVA + COLUNAS_DA_PREVISAO
COLUNAS_DA_COLETA = ["periodo", "horario_fim", "status", "valor_horario", "ultima_atualizacao"]
COLUNAS_CSV = [
    "data", "esporte", "periodo", "horario_inicio", "horario_fim", "status",
    "valor_horario", "primeira_coleta", "ultima_atualizacao",
    *COLUNAS_DA_RESERVA, "tipo_quadra", "quadra_coberta",
    *COLUNAS_DE_CLIMA, *COLUNAS_DA_PREVISAO,
    "feriado", "evento_grande", "jogo_em_porto_alegre",
]
FAIXAS_DO_DIA = ((6, "Manhã"), (12, "Tarde"), (18, "Noite"))
STATUS_LIVRE = "livre"


def sem_acento(texto: str) -> str:
    """Devolve o texto sem sinais diacríticos, para comparar e montar nomes de arquivo
    sem depender de o site escrever 'Vôlei' ou 'Volei'."""
    decomposto = unicodedata.normalize("NFKD", texto)
    return "".join(c for c in decomposto if not unicodedata.combining(c))


def slug(nome: str) -> str:
    """Converte o nome de uma quadra em identificador de arquivo: minúsculo, sem acento
    e com qualquer sequência de pontuação ou espaço virando um hífen só."""
    return re.sub(r"[^a-z0-9]+", "-", sem_acento(nome).lower()).strip("-")


def periodo_do_dia(momento: datetime) -> str:
    """Diz em que período do dia um instante cai, com a madrugada separada da manhã: o
    site só oferece Manhã, Tarde e Noite porque a arena não abre de madrugada, mas a
    reserva pode ser feita às três da manhã, e essa é justamente a informação nova."""
    for hora, nome in reversed(FAIXAS_DO_DIA):
        if momento.hour >= hora:
            return nome
    return "Madrugada"


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
    inclui a data e a quadra: a rodada percorre vários dias, e o mesmo horário em quadras
    ou dias diferentes não pode virar uma linha só."""
    por_chave = {}
    for quadra in resultados:
        if quadra["aviso"]:
            continue
        data = quadra["data"]
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


def _momento_do_slot(linha: dict) -> datetime:
    """Junta a data e o horário de início de uma linha num datetime. A data vem da linha,
    e não do relógio, porque a rodada coleta dias à frente: usar `hoje` daria por passado
    o horário de amanhã que já passou hoje, congelando o registro cedo demais."""
    inicio = datetime.strptime(linha["horario_inicio"], "%H:%M").time()
    return datetime.combine(date.fromisoformat(linha["data"]), inicio)


def _marcar_reserva(
    status_anterior: str, status_novo: str, slot_dt: datetime, agora: datetime
) -> list[str] | None:
    """Devolve os valores de COLUNAS_DA_VIRADA quando o status muda de uma coleta para a
    seguinte, ou None quando não houve virada e nada deve ser tocado. Livre para
    indisponível é a reserva acontecendo: grava quando foi feita e de quanto foi a
    antecedência. O caminho de volta é cancelamento, e apaga o que ficou. Nos dois casos
    a previsão congelada sai junto: ela descrevia a reserva anterior, não a de agora."""
    era_livre = status_anterior.lower() == STATUS_LIVRE
    esta_livre = status_novo.lower() == STATUS_LIVRE
    limpas = [""] * len(COLUNAS_DA_PREVISAO)
    if era_livre and not esta_livre:
        horas = (slot_dt - agora).total_seconds() / 3600
        return [
            agora.isoformat(timespec="seconds"), periodo_do_dia(agora), f"{horas:.2f}", *limpas
        ]
    if esta_livre and not era_livre:
        return ["", "", "", *limpas]
    return None


def _gravar_csv(caminho_csv: str, linhas: list[dict], agora: datetime) -> None:
    """Grava as linhas de uma quadra no seu CSV com upsert por (data, esporte,
    horario_inicio): um slot novo é sempre inserido, carimbando `primeira_coleta`; um
    slot já existente só é atualizado enquanto `agora < horario_inicio`, congelando
    quando o horário chega ou passa. É na atualização que a virada de status é vista, e
    daí saem as colunas da reserva. A coluna auxiliar `quadra` cai fora no reindex."""
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
            if reserva is not None:
                df.loc[existente, COLUNAS_DA_VIRADA] = reserva

    df.to_csv(caminho_csv, index=False)


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
