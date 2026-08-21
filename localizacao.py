"""Descobre em que ponto do mapa cada arena fica, a partir do endereço que ela publica."""

import json
import os
import re
import time
import requests
from datetime import datetime

from config import API_GEOCODIFICACAO, IDENTIFICACAO_GEOCODIFICACAO, PAIS_DAS_ARENAS

ARQUIVO_LOCAL = "local.json"
CAMPOS_DE_CIDADE = ("city", "town", "village", "municipality", "county")
PADRAO_NUMERO_NA_RUA = re.compile(r",?\s+\d+\s*(?=,|$)")
ESPERA_ENTRE_CONSULTAS_S = 1.1


def endereco_observado(resultados: list[dict]) -> str:
    """Escolhe o endereço da arena entre os que as quadras trouxeram, ficando com o mais
    repetido: o site mostra o endereço uma vez por esporte, e a leitura que falhou vem
    vazia. Sem nenhum endereço devolve vazio, que é como esta rodada diz que não sabe
    onde a arena fica — e não que ela mudou de lugar."""
    contagem = {}
    for quadra in resultados:
        endereco = (quadra.get("endereco") or "").strip()
        if endereco:
            contagem[endereco] = contagem.get(endereco, 0) + 1
    return max(contagem, key=contagem.get) if contagem else ""


def variacoes_da_consulta(endereco: str) -> list[str]:
    """Monta as formas de perguntar o mesmo endereço ao geocodificador, da mais específica
    para a mais genérica: como veio, sem o número do prédio e só a cidade. Para o clima a
    cidade já basta — a grade da Open-Meteo tem quilômetros de lado —, então descer um
    degrau vale mais do que devolver nada porque o número não está no mapa."""
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
    """Pergunta ao Nominatim, o geocodificador do OpenStreetMap, onde fica um endereço, e
    devolve o primeiro resultado ou None quando não há nenhum. O User-Agent que identifica
    a aplicação é exigência do serviço, que recusa chamada anônima; o país entra como
    filtro porque o site escreve rua e cidade, sem nada que situe o endereço no mundo."""
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
    """Lê a cidade no endereço estruturado que o geocodificador devolve, testando os
    campos na ordem em que o OpenStreetMap costuma preenchê-los — `city` para Canoas,
    `town` para Parobé. Sem nenhum deles devolve vazio, em vez de deduzir a cidade do
    texto livre, que é justamente o que o campo estruturado existe para evitar."""
    endereco = achado.get("address") or {}
    for campo in CAMPOS_DE_CIDADE:
        if endereco.get(campo):
            return endereco[campo]
    return ""


def geocodificar(endereco: str) -> dict | None:
    """Traduz o endereço da arena em latitude, longitude e cidade, tentando as variações
    da consulta até uma responder e respeitando o limite de uma chamada por segundo do
    serviço público. Devolve None quando nenhuma responde: sem coordenada confiável é
    melhor ficar sem clima nesta rodada do que consultar a Open-Meteo no lugar errado."""
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
    """Lê o local que já foi resolvido para a arena, guardado junto das extrações dela. É
    este arquivo que evita repetir a mesma pergunta ao geocodificador a cada quinze
    minutos: o endereço de uma quadra não muda, e o serviço é público, gratuito e limitado
    a uma consulta por segundo. Arquivo ausente ou corrompido conta como cache vazio."""
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
    """Grava em local.json o ponto do mapa que a arena ocupa, com o instante em que foi
    resolvido. O arquivo é a memória do geocodificador e também o registro de onde o clima
    daquela pasta foi medido. Devolve o caminho gravado."""
    agora = agora or datetime.now()
    os.makedirs(diretorio, exist_ok=True)
    caminho = os.path.join(diretorio, ARQUIVO_LOCAL)
    datado = dict(local, resolvido_em=agora.isoformat(timespec="seconds"))
    with open(caminho, "w", encoding="utf-8") as arquivo:
        json.dump(datado, arquivo, ensure_ascii=False, indent=2)
        arquivo.write("\n")
    return caminho


def resolver_local(endereco: str, diretorio: str, coordenadas=None, agora=None) -> dict | None:
    """Devolve onde a arena fica, geocodificando só quando o endereço observado agora é
    diferente do que já está gravado — sem isso a coleta agendada bateria no Nominatim
    quatro vezes por hora para reconfirmar o que não mudou. Rodada sem endereço legível
    fica com o local já conhecido, e endereço novo que o mapa não reconhece devolve None:
    a arena passa a rodada sem clima, em vez de receber o clima do endereço antigo."""
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
