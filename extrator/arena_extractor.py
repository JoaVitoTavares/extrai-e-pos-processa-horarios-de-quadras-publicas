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

GEOCODING_LOCK = threading.Lock()


def collect_courts(arena: dict, visible_browser: bool = False, output=None) -> list[dict]:
    """Lista os esportes pela API e varre os horários de cada esporte alvo com o
    navegador. Um esporte que estoura o tempo vira aviso e não interrompe os demais."""
    output = output or sys.stdout
    print(">> TÉCNICA 1 (API JSON, sem navegador): listando esportes...\n", file=output)
    sports = listar_esportes(arena["url"])
    for position, sport in enumerate(sports, 1):
        print(f"   {position}. {sport}", file=output)

    target_sports = esportes_alvo(sports, arena["tipos"])
    missing_types = tipos_ausentes(target_sports, arena["tipos"])
    if missing_types:
        print(f"\n[AVISO] tipos de quadra não encontrados no site: {', '.join(missing_types)}",
              file=output)

    results = []
    for sport in target_sports:
        print(f"\n>> TÉCNICA 2 (Playwright): horários de '{sport}' (todos os períodos)...",
              file=output)
        try:
            results.extend(
                coletar_horarios(
                    sport,
                    arena["url"],
                    periodo=None,
                    headless=not visible_browser,
                    tipos=arena["tipos"],
                )
            )
        except PWTimeout as error:
            print(f"[AVISO] {arena['nome']}: '{sport}' pulado por tempo esgotado: {error}",
                  file=sys.stderr)
    return results


def record_location(arena: dict, results: list[dict], output=None) -> dict | None:
    """Geocodifica o endereço mais observado da rodada, uma arena por vez. Devolve None
    quando o endereço não é reconhecido, e nesse caso a rodada segue sem clima."""
    output = output or sys.stdout
    print(f"\n>> LOCAL (Nominatim): onde fica a {arena['nome']}...", file=output)
    try:
        with GEOCODING_LOCK:
            location = resolver_local(
                endereco_observado(results), arena["diretorio"], arena["coordenadas"]
            )
    except (requests.RequestException, ValueError) as error:
        print(f"[AVISO] {arena['nome']}: endereço não geocodificado: {error}", file=sys.stderr)
        return None

    if location is None:
        print(f"[AVISO] {arena['nome']}: sem endereço reconhecido, rodada sem clima.",
              file=sys.stderr)
        return None
    print(f"   {location['endereco']} -> {location['latitude']}, {location['longitude']}",
          file=output)
    return location


def record_weather(
    location: dict, directory: str, output=None, arena_name: str = ""
) -> str | None:
    """Grava as condições atuais do ponto da arena. Falha de rede vira aviso e None."""
    output = output or sys.stdout
    print("\n>> CLIMA (API Open-Meteo): condições atuais na arena...", file=output)
    try:
        path = coletar_clima(location["latitude"], location["longitude"], directory)
    except (requests.RequestException, ValueError) as error:
        print(f"[AVISO] {arena_name}: clima não coletado: {error}", file=sys.stderr)
        return None
    print(f"   registrado em {path}", file=output)
    return path


def record_forecast(
    location: dict, directory: str, output=None, arena_name: str = ""
) -> str | None:
    """Grava a previsão hora a hora do ponto da arena. Falha de rede vira aviso e None."""
    output = output or sys.stdout
    print("\n>> PREVISÃO (API Open-Meteo): horas à frente na arena...", file=output)
    try:
        path = coletar_previsao(location["latitude"], location["longitude"], directory)
    except (requests.RequestException, ValueError) as error:
        print(f"[AVISO] {arena_name}: previsão não coletada: {error}", file=sys.stderr)
        return None
    print(f"   registrada em {path}", file=output)
    return path


def _print_extraction(data: dict, output=None) -> None:
    """Imprime o bloco de uma quadra em um período, com os horários e o total de livres."""
    output = output or sys.stdout
    print("\n" + "=" * 46, file=output)
    print(f"  {data['esporte']}  |  {data['data']}  |  Período: {data['periodo']}", file=output)
    if data["quadra"]:
        coverage = {"true": "coberta", "false": "descoberta"}.get(data["quadra_coberta"], "?")
        print(f"  {data['quadra']}  ({coverage})", file=output)
    if data.get("endereco"):
        print(f"  {data['endereco']}", file=output)
    print(f"  Coletado em: {data['coletado_em']}", file=output)
    print("=" * 46, file=output)
    if data["aviso"]:
        print(f"  ⚠️  {data['aviso']}", file=output)
        print("=" * 46, file=output)
        return
    for slot in data["horarios"]:
        marker = "🟢" if slot["status"].lower() == "livre" else "🔴"
        price = f"  R$ {slot['valor']:.2f}" if slot.get("valor") is not None else ""
        print(f"  {marker} {slot['hora']}  -  {slot['status']}{price}", file=output)
    free_hours = [slot["hora"] for slot in data["horarios"] if slot["status"].lower() == "livre"]
    print("=" * 46, file=output)
    print(f"  Livres: {len(free_hours)}  ->  {', '.join(free_hours) or '(nenhum)'}", file=output)


def _print_summary(
    arena: dict, paths: list[str], enriched_paths: list[str], output=None
) -> None:
    """Imprime quantos arquivos de quadra a arena gravou e quantos receberam clima."""
    output = output or sys.stdout
    print(f"\n>> {arena['nome']}: extração salva/atualizada em {len(paths)} arquivo(s):",
          file=output)
    for path in paths:
        print(f"   {path}", file=output)
    print(f">> Clima aplicado em {len(enriched_paths)} arquivo(s) de quadra.", file=output)


def verified_court_names(results: list[dict]) -> list[str]:
    """Devolve os nomes das quadras que renderam horários, sem repetição e ordenados."""
    return sorted({result["quadra"] for result in results if result["quadra"] and not result["aviso"]})


class ArenaExtractor:
    """Executa o pipeline de uma arena: quadras, local, gravação, clima e tratamento.
    Cada chamada de `run` acumula o próprio log, então a instância pode ser reusada."""

    def __init__(self, arena: dict, visible_browser: bool = False) -> None:
        self.arena = arena
        self.visible_browser = visible_browser

    def run(self) -> tuple[list[str], list[str], str]:
        """Roda a arena isolando falhas e devolve os paths gravados, as quadras
        verificadas e o log da rodada, que o chamador imprime quando quiser."""
        output = io.StringIO()
        print("\n" + "#" * 46, file=output)
        print(f"  ARENA: {self.arena['nome']}  ({self.arena['url']})", file=output)
        print("#" * 46, file=output)
        try:
            paths, court_names = self._execute(output)
        except (PWTimeout, requests.RequestException, ValueError) as error:
            print(f"[AVISO] arena '{self.arena['nome']}' pulada: {error}", file=sys.stderr)
            paths, court_names = [], []
        return paths, court_names, output.getvalue()

    def _execute(self, output) -> tuple[list[str], list[str]]:
        """Encadeia as etapas da arena na ordem em que uma depende da anterior."""
        results = collect_courts(self.arena, self.visible_browser, output)
        for data in results:
            _print_extraction(data, output)

        location = record_location(self.arena, results, output)
        paths = salvar_extracao(
            results,
            self.arena["diretorio"],
            arena=self.arena["nome"],
            cidade=(location or {}).get("cidade", ""),
        )
        if location:
            record_weather(location, self.arena["diretorio"], output, self.arena["nome"])
            record_forecast(location, self.arena["diretorio"], output, self.arena["nome"])

        enriched_paths = TratamentoDeDados(self.arena["diretorio"]).aplicar()
        _print_summary(self.arena, paths, enriched_paths, output)
        return paths, verified_court_names(results)
