"""Gerenciador das extrações: roda as arenas em paralelo e grava o resultado."""

import io
import os
import sys
import threading
import requests
from concurrent.futures import ThreadPoolExecutor, as_completed
from playwright.sync_api import TimeoutError as PWTimeout

from config import (
    ARENAS, ARENAS_EM_PARALELO, DIRETORIO_EXTRACOES, DIRETORIO_LOGS, TIPOS_QUADRA
)
from courts_collector import coletar_horarios, esportes_alvo, listar_esportes, tipos_ausentes
from localizacao import endereco_observado, resolver_local
from persistencia import registrar_verificacao, salvar_extracao, slug
from tratamento import TratamentoDeDados
from weather_collector import coletar_clima, coletar_previsao

TRAVA_DA_GEOCODIFICACAO = threading.Lock()


def preparar_arena(arena: dict) -> dict:
    """Completa o que o config deixou implícito numa arena: o nome, que vai à coluna
    `arena` do CSV, e o diretório onde ela grava, tirado do último trecho da URL. É a URL
    que identifica o site, então renomear a arena no config não desgarra o histórico já
    coletado. Coordenadas fixadas à mão passam adiante como estão, para o endereço que o
    mapa não reconhece não custar o clima daquela arena. Sem `tipos` próprios, a arena
    procura os tipos de quadra padrão."""
    identificador = slug(arena["url"].rstrip("/").rsplit("/", 1)[-1])
    return {
        "nome": arena.get("nome") or identificador,
        "url": arena["url"],
        "diretorio": os.path.join(DIRETORIO_EXTRACOES, identificador),
        "coordenadas": arena.get("coordenadas"),
        "tipos": arena.get("tipos") or TIPOS_QUADRA,
    }


def coletar_quadras(arena: dict, modo_visivel: bool = False, saida=None) -> list[dict]:
    """Roda as duas técnicas do coletor de quadras numa arena e devolve tudo o que foi
    extraído, relatando o progresso em `saida`. Um esporte que estoure o tempo é
    reportado e pulado, para a lentidão do site em um não derrubar a coleta dos outros."""
    saida = saida or sys.stdout
    print(">> TÉCNICA 1 (API JSON, sem navegador): listando esportes...\n", file=saida)
    esportes = listar_esportes(arena["url"])
    for i, e in enumerate(esportes, 1):
        print(f"   {i}. {e}", file=saida)

    alvos = esportes_alvo(esportes, arena["tipos"])
    ausentes = tipos_ausentes(alvos, arena["tipos"])
    if ausentes:
        print(f"\n[AVISO] tipos de quadra não encontrados no site: {', '.join(ausentes)}",
              file=saida)

    resultados = []
    for esporte in alvos:
        print(f"\n>> TÉCNICA 2 (Playwright): horários de '{esporte}' (todos os períodos)...",
              file=saida)
        try:
            resultados.extend(
                coletar_horarios(
                    esporte,
                    arena["url"],
                    periodo=None,
                    headless=not modo_visivel,
                    tipos=arena["tipos"],
                )
            )
        except PWTimeout as erro:
            print(f"[AVISO] {arena['nome']}: '{esporte}' pulado por tempo esgotado: {erro}",
                  file=sys.stderr)
    return resultados


def registrar_local(arena: dict, resultados: list[dict], saida=None) -> dict | None:
    """Resolve onde a arena fica, uma arena de cada vez mesmo com a rodada em paralelo: o
    Nominatim é um serviço público que pede no máximo uma consulta por segundo, e a
    primeira rodada de uma lista nova geocodifica todas as arenas de uma vez. Consulta só
    acontece quando o endereço muda, então a trava fica livre nas rodadas seguintes."""
    saida = saida or sys.stdout
    print(f"\n>> LOCAL (Nominatim): onde fica a {arena['nome']}...", file=saida)
    try:
        with TRAVA_DA_GEOCODIFICACAO:
            local = resolver_local(
                endereco_observado(resultados), arena["diretorio"], arena["coordenadas"]
            )
    except (requests.RequestException, ValueError) as erro:
        print(f"[AVISO] {arena['nome']}: endereço não geocodificado: {erro}", file=sys.stderr)
        return None

    if local is None:
        print(f"[AVISO] {arena['nome']}: sem endereço reconhecido, rodada sem clima.",
              file=sys.stderr)
        return None
    print(f"   {local['endereco']} -> {local['latitude']}, {local['longitude']}", file=saida)
    return local


def registrar_clima(local: dict, diretorio: str, saida=None, nome: str = "") -> str | None:
    saida = saida or sys.stdout
    print("\n>> CLIMA (API Open-Meteo): condições atuais na arena...", file=saida)
    try:
        caminho = coletar_clima(local["latitude"], local["longitude"], diretorio)
    except (requests.RequestException, ValueError) as erro:
        print(f"[AVISO] {nome}: clima não coletado: {erro}", file=sys.stderr)
        return None
    print(f"   registrado em {caminho}", file=saida)
    return caminho


def registrar_previsao(local: dict, diretorio: str, saida=None, nome: str = "") -> str | None:
    saida = saida or sys.stdout
    print("\n>> PREVISÃO (API Open-Meteo): horas à frente na arena...", file=saida)
    try:
        caminho = coletar_previsao(local["latitude"], local["longitude"], diretorio)
    except (requests.RequestException, ValueError) as erro:
        print(f"[AVISO] {nome}: previsão não coletada: {erro}", file=sys.stderr)
        return None
    print(f"   registrada em {caminho}", file=saida)
    return caminho


def _imprimir_extracao(dados: dict, saida=None) -> None:
    saida = saida or sys.stdout
    print("\n" + "=" * 46, file=saida)
    print(f"  {dados['esporte']}  |  {dados['data']}  |  Período: {dados['periodo']}", file=saida)
    if dados["quadra"]:
        cobertura = {"true": "coberta", "false": "descoberta"}.get(dados["quadra_coberta"], "?")
        print(f"  {dados['quadra']}  ({cobertura})", file=saida)
    if dados.get("endereco"):
        print(f"  {dados['endereco']}", file=saida)
    print(f"  Coletado em: {dados['coletado_em']}", file=saida)
    print("=" * 46, file=saida)
    if dados["aviso"]:
        print(f"  ⚠️  {dados['aviso']}", file=saida)
        print("=" * 46, file=saida)
        return
    for h in dados["horarios"]:
        marca = "🟢" if h["status"].lower() == "livre" else "🔴"
        preco = f"  R$ {h['valor']:.2f}" if h.get("valor") is not None else ""
        print(f"  {marca} {h['hora']}  -  {h['status']}{preco}", file=saida)
    livres = [h["hora"] for h in dados["horarios"] if h["status"].lower() == "livre"]
    print("=" * 46, file=saida)
    print(f"  Livres: {len(livres)}  ->  {', '.join(livres) or '(nenhum)'}", file=saida)


def _imprimir_resumo(
    arena: dict, caminhos: list[str], enriquecidos: list[str], saida=None
) -> None:
    saida = saida or sys.stdout
    print(f"\n>> {arena['nome']}: extração salva/atualizada em {len(caminhos)} arquivo(s):",
          file=saida)
    for caminho in caminhos:
        print(f"   {caminho}", file=saida)
    print(f">> Clima aplicado em {len(enriquecidos)} arquivo(s) de quadra.", file=saida)


def quadras_verificadas(resultados: list[dict]) -> list[str]:
    """Lista, em ordem e sem repetir, o nome das quadras que a coleta chegou a ler na
    arena. A quadra vem repetida nos resultados — uma vez por período e por dia —, e o
    período que voltou com aviso fica de fora: ali o site não respondeu, então dizer no
    log que a quadra foi verificada seria dizer o que não aconteceu."""
    return sorted({d["quadra"] for d in resultados if d["quadra"] and not d["aviso"]})


def rodar_arena(
    arena: dict, modo_visivel: bool = False, saida=None
) -> tuple[list[str], list[str]]:
    """Executa uma arena de ponta a ponta: coleta as quadras de hoje e dos próximos dias,
    imprime o que achou, resolve onde ela fica, grava um CSV por quadra — é na gravação
    que a reserva feita entre duas rodadas é detectada —, registra clima e previsão
    daquelas coordenadas e aplica os dois nas reservas. Tudo dentro do diretório da
    arena, para nada do que se grava aqui disputar arquivo com outra. Devolve os arquivos
    gravados e as quadras que foram verificadas."""
    saida = saida or sys.stdout
    resultados = coletar_quadras(arena, modo_visivel, saida)
    for dados in resultados:
        _imprimir_extracao(dados, saida)

    local = registrar_local(arena, resultados, saida)
    caminhos = salvar_extracao(
        resultados,
        arena["diretorio"],
        arena=arena["nome"],
        cidade=(local or {}).get("cidade", ""),
    )
    if local:
        registrar_clima(local, arena["diretorio"], saida, arena["nome"])
        registrar_previsao(local, arena["diretorio"], saida, arena["nome"])

    enriquecidos = TratamentoDeDados(arena["diretorio"]).aplicar()
    _imprimir_resumo(arena, caminhos, enriquecidos, saida)
    return caminhos, quadras_verificadas(resultados)


def _rodada_da_arena(
    arena: dict, modo_visivel: bool = False
) -> tuple[list[str], list[str], str]:
    """Roda uma arena guardando num texto só tudo o que ela imprimiria, para a saída
    receber o bloco inteiro de uma vez quando ela terminar: com várias arenas ao mesmo
    tempo, imprimir na hora entrelaçaria as linhas de umas com as das outras. A arena que
    falha inteira é reportada e volta sem arquivo e sem quadra nenhuma, sem levar as
    outras junto."""
    saida = io.StringIO()
    print("\n" + "#" * 46, file=saida)
    print(f"  ARENA: {arena['nome']}  ({arena['url']})", file=saida)
    print("#" * 46, file=saida)
    try:
        caminhos, quadras = rodar_arena(arena, modo_visivel, saida)
    except (PWTimeout, requests.RequestException, ValueError) as erro:
        print(f"[AVISO] arena '{arena['nome']}' pulada: {erro}", file=sys.stderr)
        caminhos, quadras = [], []
    return caminhos, quadras, saida.getvalue()


def main() -> None:
    """Executa a rodada nas arenas do config, ARENAS_EM_PARALELO ao mesmo tempo: cada uma
    tem navegador, diretório e clima próprios, então nenhuma espera nem atrapalha a outra
    e a lista inteira cabe no intervalo do agendamento. Cada arena que termina imprime o
    bloco inteiro de uma vez e deixa no CSV de verificações a hora em que foi vista e as
    quadras que tinha — registrada aqui, e não dentro dela, porque este laço é o único
    ponto onde as rodadas voltam a ser uma de cada vez e o CSV é reescrito inteiro. Uma
    execução que não colete quadra nenhuma sai com erro em vez de gravar silêncio."""
    modo_visivel = "--ver" in sys.argv
    arenas = [preparar_arena(configurada) for configurada in ARENAS]

    gravados = []
    coletadas = 0
    with ThreadPoolExecutor(max_workers=max(1, min(ARENAS_EM_PARALELO, len(arenas)))) as executor:
        rodadas = {
            executor.submit(_rodada_da_arena, arena, modo_visivel): arena for arena in arenas
        }
        for rodada in as_completed(rodadas):
            caminhos, quadras, texto = rodada.result()
            print(texto, end="")
            registrar_verificacao(rodadas[rodada]["nome"], quadras, DIRETORIO_LOGS)
            coletadas += bool(caminhos)
            gravados.extend(caminhos)

    if not gravados:
        print("\n[ERRO] nenhuma quadra coletada em nenhuma arena.", file=sys.stderr)
        sys.exit(1)

    print(f"\n>> Rodada concluída: {len(gravados)} arquivo(s) de quadra "
          f"em {coletadas} de {len(ARENAS)} arena(s).")
    print()


if __name__ == "__main__":
    try:
        main()
    except PWTimeout as e:
        print(f"\n[ERRO] Tempo esgotado: {e}", file=sys.stderr)
        sys.exit(1)
    except requests.RequestException as e:
        print(f"\n[ERRO] Falha na API JSON: {e}", file=sys.stderr)
        sys.exit(1)
