"""Descobre em que ponto do mapa cada arena fica, a partir do endereço que ela publica."""

import json
import os
import re
import time
import requests
from datetime import datetime

from extrator.config import API_GEOCODIFICACAO, IDENTIFICACAO_GEOCODIFICACAO, PAIS_DAS_ARENAS

ARQUIVO_LOCAL = "local.json"
CAMPOS_DE_CIDADE = ("city", "town", "village", "municipality", "county")
PADRAO_NUMERO_NA_RUA = re.compile(r",?\s+\d+\s*(?=,|$)")
ESPERA_ENTRE_CONSULTAS_S = 1.1


def endereco_observado(resultados: list[dict]) -> str:
    contagem = {}
    for quadra in resultados:
        endereco = (quadra.get("endereco") or "").strip()
        if endereco:
            contagem[endereco] = contagem.get(endereco, 0) + 1
    return max(contagem, key=contagem.get) if contagem else ""


def variacoes_da_consulta(endereco: str) -> list[str]:
    endereco = endereco.strip()
    consultas = [endereco]
    sem_numero = PADRAO_NUMERO_NA_RUA.sub("", endereco).strip(" ,")
    if sem_numero and sem_numero not in consultas:
        consultas.append(sem_numero)
    cidade = endereco.rsplit(",", 1)[-1].strip()
    if cidade and cidade not in consultas:
        consultas.append(cidade)
    return consultas


def consultar_geocodificacao(consulta: str, timeout: int = 30) -> dict | None:
    resposta = requests.get(
        API_GEOCODIFICACAO,
        params={
            "q": consulta,
            "format": "jsonv2",
            "limit": 1,
            "addressdetails": 1,
            "countrycodes": PAIS_DAS_ARENAS,
            "accept-language": "pt-BR",
        },
        headers={"User-Agent": IDENTIFICACAO_GEOCODIFICACAO},
        timeout=timeout,
    )
    resposta.raise_for_status()
    achados = resposta.json()
    return achados[0] if isinstance(achados, list) and achados else None


def _cidade(achado: dict) -> str:
    endereco = achado.get("address") or {}
    for campo in CAMPOS_DE_CIDADE:
        if endereco.get(campo):
            return endereco[campo]
    return ""


def geocodificar(endereco: str) -> dict | None:
    for indice, consulta in enumerate(variacoes_da_consulta(endereco)):
        if indice:
            time.sleep(ESPERA_ENTRE_CONSULTAS_S)
        achado = consultar_geocodificacao(consulta)
        if achado is None:
            continue
        try:
            return {
                "endereco": endereco,
                "latitude": float(achado["lat"]),
                "longitude": float(achado["lon"]),
                "cidade": _cidade(achado),
                "origem": consulta,
            }
        except (KeyError, TypeError, ValueError) as erro:
            raise ValueError(
                f"{API_GEOCODIFICACAO} devolveu JSON em formato inesperado: {erro}"
            ) from erro
    return None


def local_gravado(diretorio: str) -> dict | None:
    caminho = os.path.join(diretorio, ARQUIVO_LOCAL)
    if not os.path.exists(caminho):
        return None
    try:
        with open(caminho, encoding="utf-8") as arquivo:
            gravado = json.load(arquivo)
    except (OSError, ValueError):
        return None
    return gravado if isinstance(gravado, dict) and gravado.get("latitude") is not None else None


def salvar_local(local: dict, diretorio: str, agora=None) -> str:
    agora = agora or datetime.now()
    os.makedirs(diretorio, exist_ok=True)
    caminho = os.path.join(diretorio, ARQUIVO_LOCAL)
    datado = dict(local, resolvido_em=agora.isoformat(timespec="seconds"))
    with open(caminho, "w", encoding="utf-8") as arquivo:
        json.dump(datado, arquivo, ensure_ascii=False, indent=2)
        arquivo.write("\n")
    return caminho


def resolver_local(endereco: str, diretorio: str, coordenadas=None, agora=None) -> dict | None:
    gravado = local_gravado(diretorio)
    if coordenadas:
        local = {
            "endereco": endereco,
            "latitude": float(coordenadas[0]),
            "longitude": float(coordenadas[1]),
            "cidade": (gravado or {}).get("cidade", ""),
            "origem": "config",
        }
    elif not endereco or (gravado or {}).get("endereco") == endereco:
        return gravado
    else:
        local = geocodificar(endereco)
        if local is None:
            return None
    if gravado and {campo: gravado.get(campo) for campo in local} == local:
        return gravado
    salvar_local(local, diretorio, agora)
    return local
