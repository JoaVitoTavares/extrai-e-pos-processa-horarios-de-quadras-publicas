"""Gerenciador das extrações: roda os coletores em sequência e grava o resultado."""

import os
import sys
import requests
from playwright.sync_api import TimeoutError as PWTimeout

from config import ARENAS, DIRETORIO_EXTRACOES
from courts_collector import coletar_horarios, esportes_alvo, listar_esportes, tipos_ausentes
from localizacao import endereco_observado, resolver_local
from persistencia import salvar_extracao, slug
from tratamento import TratamentoDeDados
from weather_collector import coletar_clima, coletar_previsao


def preparar_arena(arena: dict) -> dict:
    """Completa o que o config deixou implícito numa arena: o nome, que vai à coluna
    `arena` do CSV, e o diretório onde ela grava, tirado do último trecho da URL. É a URL
    que identifica o site, então renomear a arena no config não desgarra o histórico já
    coletado. Coordenadas fixadas à mão passam adiante como estão, para o endereço que o
    mapa não reconhece não custar o clima daquela arena."""
    identificador = slug(arena["url"].rstrip("/").rsplit("/", 1)[-1])
    return {
        "nome": arena.get("nome") or identificador,
        "url": arena["url"],
        "diretorio": os.path.join(DIRETORIO_EXTRACOES, identificador),
        "coordenadas": arena.get("coordenadas"),
    }


def coletar_quadras(arena: dict, modo_visivel: bool = False) -> list[dict]:
    """Roda as duas técnicas do coletor de quadras numa arena e devolve tudo o que foi
    extraído, relatando o progresso no terminal. Um esporte que estoure o tempo é
    reportado e pulado, para a lentidão do site em um não derrubar a coleta dos outros."""
    print(">> TÉCNICA 1 (API JSON, sem navegador): listando esportes...\n")
    esportes = listar_esportes(arena["url"])
    for i, e in enumerate(esportes, 1):
        print(f"   {i}. {e}")

    alvos = esportes_alvo(esportes)
    ausentes = tipos_ausentes(alvos)
    if ausentes:
        print(f"\n[AVISO] tipos de quadra não encontrados no site: {', '.join(ausentes)}")

    resultados = []
    for esporte in alvos:
        print(f"\n>> TÉCNICA 2 (Playwright): horários de '{esporte}' (todos os períodos)...")
        try:
            resultados.extend(
                coletar_horarios(esporte, arena["url"], periodo=None, headless=not modo_visivel)
            )
        except PWTimeout as erro:
            print(f"[AVISO] '{esporte}' pulado por tempo esgotado: {erro}", file=sys.stderr)
    return resultados


def registrar_local(arena: dict, resultados: list[dict]) -> dict | None:
    """Descobre em que ponto do mapa a arena fica, a partir do endereço que as quadras
    trouxeram, e devolve o local ou None quando não há como saber. A falha do
    geocodificador é tratada como a da Open-Meteo: as quadras já estão coletadas, e o que
    se perde é o clima desta arena até a próxima rodada."""
    print(f"\n>> LOCAL (Nominatim): onde fica a {arena['nome']}...")
    try:
        local = resolver_local(
            endereco_observado(resultados), arena["diretorio"], arena["coordenadas"]
        )
    except (requests.RequestException, ValueError) as erro:
        print(f"[AVISO] endereço não geocodificado: {erro}", file=sys.stderr)
        return None

    if local is None:
        print("[AVISO] arena sem endereço reconhecido: rodada sem clima.", file=sys.stderr)
        return None
    print(f"   {local['endereco']} -> {local['latitude']}, {local['longitude']}")
    return local


def registrar_clima(local: dict, diretorio: str) -> str | None:
    """Coleta a leitura de clima nas coordenadas da arena e devolve o caminho gravado, ou
    None se a API falhar. Uma queda da Open-Meteo não pode derrubar a execução: as quadras
    já foram gravadas, e o tratamento sabe trabalhar com a última leitura que houver no
    histórico."""
    print("\n>> CLIMA (API Open-Meteo): condições atuais na arena...")
    try:
        caminho = coletar_clima(local["latitude"], local["longitude"], diretorio)
    except (requests.RequestException, ValueError) as erro:
        print(f"[AVISO] clima não coletado: {erro}", file=sys.stderr)
        return None
    print(f"   registrado em {caminho}")
    return caminho


def registrar_previsao(local: dict, diretorio: str) -> str | None:
    """Coleta a previsão hora a hora dos dias que a extração percorre e devolve o caminho
    gravado, ou None se a API falhar. Vale a mesma tolerância da leitura atual: sem a
    previsão desta rodada, a reserva detectada agora fica com a coluna vazia e a próxima
    rodada a preenche, o que custa menos do que derrubar a execução."""
    print("\n>> PREVISÃO (API Open-Meteo): horas à frente na arena...")
    try:
        caminho = coletar_previsao(local["latitude"], local["longitude"], diretorio)
    except (requests.RequestException, ValueError) as erro:
        print(f"[AVISO] previsão não coletada: {erro}", file=sys.stderr)
        return None
    print(f"   registrada em {caminho}")
    return caminho


def _imprimir_extracao(dados: dict) -> None:
    """Imprime o bloco de uma quadra num período: cabeçalho com esporte e cobertura,
    um horário por linha com 🟢 para livre e 🔴 para indisponível, e o resumo de vagas.
    Um período que não carregou mostra só o aviso, já que não há horário para listar."""
    print("\n" + "=" * 46)
    print(f"  {dados['esporte']}  |  {dados['data']}  |  Período: {dados['periodo']}")
    if dados["quadra"]:
        cobertura = {"true": "coberta", "false": "descoberta"}.get(dados["quadra_coberta"], "?")
        print(f"  {dados['quadra']}  ({cobertura})")
    if dados.get("endereco"):
        print(f"  {dados['endereco']}")
    print(f"  Coletado em: {dados['coletado_em']}")
    print("=" * 46)
    if dados["aviso"]:
        print(f"  ⚠️  {dados['aviso']}")
        print("=" * 46)
        return
    for h in dados["horarios"]:
        marca = "🟢" if h["status"].lower() == "livre" else "🔴"
        preco = f"  R$ {h['valor']:.2f}" if h.get("valor") is not None else ""
        print(f"  {marca} {h['hora']}  -  {h['status']}{preco}")
    livres = [h["hora"] for h in dados["horarios"] if h["status"].lower() == "livre"]
    print("=" * 46)
    print(f"  Livres: {len(livres)}  ->  {', '.join(livres) or '(nenhum)'}")


def _imprimir_resumo(arena: dict, caminhos: list[str], enriquecidos: list[str]) -> None:
    """Fecha o bloco da arena com os arquivos de quadra gravados e quantos o tratamento
    tocou. Os caminhos saem um por linha porque é por eles que se confere, no log da
    rodada agendada, que uma arena nova está mesmo gravando na pasta dela."""
    print(f"\n>> {arena['nome']}: extração salva/atualizada em {len(caminhos)} arquivo(s):")
    for caminho in caminhos:
        print(f"   {caminho}")
    print(f">> Clima aplicado em {len(enriquecidos)} arquivo(s) de quadra.")


def rodar_arena(arena: dict, modo_visivel: bool = False) -> list[str]:
    """Executa uma arena de ponta a ponta: coleta as quadras de hoje e dos próximos dias,
    imprime o que achou, resolve onde ela fica, grava um CSV por quadra — é na gravação
    que a reserva feita entre duas rodadas é detectada —, registra clima e previsão
    daquelas coordenadas e aplica os dois nas reservas. Tudo dentro do diretório da
    arena, para nada do que se grava aqui disputar arquivo com outra."""
    resultados = coletar_quadras(arena, modo_visivel)
    for dados in resultados:
        _imprimir_extracao(dados)

    local = registrar_local(arena, resultados)
    caminhos = salvar_extracao(
        resultados,
        arena["diretorio"],
        arena=arena["nome"],
        cidade=(local or {}).get("cidade", ""),
    )
    if local:
        registrar_clima(local, arena["diretorio"])
        registrar_previsao(local, arena["diretorio"])

    enriquecidos = TratamentoDeDados(arena["diretorio"]).aplicar()
    _imprimir_resumo(arena, caminhos, enriquecidos)
    return caminhos


def main() -> None:
    """Executa a rodada em cada arena do config, uma de cada vez e independentes: a que
    falhar inteira é reportada e pulada, do mesmo jeito que já acontecia com o esporte
    lento dentro de uma arena. Uma execução que não colete quadra nenhuma em arena nenhuma
    sai com erro em vez de gravar silêncio — o modo de falha mais caro num coletor
    agendado."""
    modo_visivel = "--ver" in sys.argv

    gravados = []
    coletadas = 0
    for configurada in ARENAS:
        arena = preparar_arena(configurada)
        print("\n" + "#" * 46)
        print(f"  ARENA: {arena['nome']}  ({arena['url']})")
        print("#" * 46)
        try:
            caminhos = rodar_arena(arena, modo_visivel)
        except (PWTimeout, requests.RequestException, ValueError) as erro:
            print(f"[AVISO] arena '{arena['nome']}' pulada: {erro}", file=sys.stderr)
            continue
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
