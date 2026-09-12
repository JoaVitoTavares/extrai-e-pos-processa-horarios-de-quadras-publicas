"""Extração de uma arena: coleta, localiza, grava e casa o clima."""

import io
import sys
import threading
import requests
from playwright.sync_api import TimeoutError as PWTimeout

from extrator.courts_collector import (
    coletar_horarios, esportes_alvo, listar_esportes, tipos_ausentes
)
from extrator.localizacao import endereco_observado, resolver_local
from extrator.persistencia import salvar_extracao
from extrator.tratamento import TratamentoDeDados
from extrator.weather_collector import coletar_clima, coletar_previsao

TRAVA_DA_GEOCODIFICACAO = threading.Lock()


def coletar_quadras(arena: dict, modo_visivel: bool = False, saida=None) -> list[dict]:
    """Lista os esportes pela API e varre os horários de cada esporte alvo com o
    navegador. Um esporte que estoura o tempo vira aviso e não interrompe os demais."""
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
    """Geocodifica o endereço mais observado da rodada, uma arena por vez. Devolve None
    quando o endereço não é reconhecido, e nesse caso a rodada segue sem clima."""
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
    """Grava as condições atuais do ponto da arena. Falha de rede vira aviso e None."""
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
    """Grava a previsão hora a hora do ponto da arena. Falha de rede vira aviso e None."""
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
    """Imprime o bloco de uma quadra em um período, com os horários e o total de livres."""
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
    arena: dict, paths: list[str], enriquecidos: list[str], saida=None
) -> None:
    """Imprime quantos arquivos de quadra a arena gravou e quantos receberam clima."""
    saida = saida or sys.stdout
    print(f"\n>> {arena['nome']}: extração salva/atualizada em {len(paths)} arquivo(s):",
          file=saida)
    for path in paths:
        print(f"   {path}", file=saida)
    print(f">> Clima aplicado em {len(enriquecidos)} arquivo(s) de quadra.", file=saida)


def quadras_verificadas(resultados: list[dict]) -> list[str]:
    """Devolve os nomes das quadras que renderam horários, sem repetição e ordenados."""
    return sorted({d["quadra"] for d in resultados if d["quadra"] and not d["aviso"]})


class ArenaExtractor:
    """Executa o pipeline de uma arena: quadras, local, gravação, clima e tratamento.
    Cada chamada de `run` acumula o próprio log, então a instância pode ser reusada."""

    def __init__(self, arena: dict, modo_visivel: bool = False) -> None:
        self.arena = arena
        self.modo_visivel = modo_visivel

    def run(self) -> tuple[list[str], list[str], str]:
        """Roda a arena isolando falhas e devolve os paths gravados, as quadras
        verificadas e o log da rodada, que o chamador imprime quando quiser."""
        saida = io.StringIO()
        print("\n" + "#" * 46, file=saida)
        print(f"  ARENA: {self.arena['nome']}  ({self.arena['url']})", file=saida)
        print("#" * 46, file=saida)
        try:
            paths, quadras = self._executar(saida)
        except (PWTimeout, requests.RequestException, ValueError) as erro:
            print(f"[AVISO] arena '{self.arena['nome']}' pulada: {erro}", file=sys.stderr)
            paths, quadras = [], []
        return paths, quadras, saida.getvalue()

    def _executar(self, saida) -> tuple[list[str], list[str]]:
        """Encadeia as etapas da arena na ordem em que uma depende da anterior."""
        resultados = coletar_quadras(self.arena, self.modo_visivel, saida)
        for dados in resultados:
            _imprimir_extracao(dados, saida)

        local = registrar_local(self.arena, resultados, saida)
        paths = salvar_extracao(
            resultados,
            self.arena["diretorio"],
            arena=self.arena["nome"],
            cidade=(local or {}).get("cidade", ""),
        )
        if local:
            registrar_clima(local, self.arena["diretorio"], saida, self.arena["nome"])
            registrar_previsao(local, self.arena["diretorio"], saida, self.arena["nome"])

        enriquecidos = TratamentoDeDados(self.arena["diretorio"]).aplicar()
        _imprimir_resumo(self.arena, paths, enriquecidos, saida)
        return paths, quadras_verificadas(resultados)
