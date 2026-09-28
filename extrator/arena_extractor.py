"""Extração de uma arena: coleta, localiza, grava e casa o clima."""

import io
import sys
import threading
import requests
from playwright.sync_api import TimeoutError as PWTimeout

from extrator.config import DAYS_AHEAD
from extrator.courts_collector import (
    collect_schedules, filter_target_sports, list_sports, missing_court_types
)
from extrator.localizacao import endereco_observado, resolver_local
from extrator.persistencia import salvar_extracao
from extrator.tratamento import TratamentoDeDados
from extrator.weather_collector import record_forecast, record_weather

GEOCODING_LOCK = threading.Lock()


class ArenaExtractor:
    """Executa o pipeline de uma arena: quadras, local, gravação, clima e tratamento.
    Cada chamada de `extract_isolating_failures` acumula o próprio log, então a
    instância pode ser reusada em sequência, mas não em paralelo."""

    def __init__(
        self,
        arena: dict,
        visible_browser: bool = False,
        days_from: int = 0,
        days_ahead: int = DAYS_AHEAD,
        proxy: str | None = None,
    ) -> None:
        self.arena = arena
        self.visible_browser = visible_browser
        self.days_from = days_from
        self.days_ahead = days_ahead
        self.proxy = proxy
        self.output = sys.stdout

    def extract_isolating_failures(self) -> tuple[list[str], list[str], str]:
        self.output = io.StringIO()
        self._print_arena_header()
        try:
            results = self._collect_courts()
            for data in results:
                self._print_extraction(data)

            location = self._record_location(results)
            paths = salvar_extracao(
                results,
                self.arena["diretorio"],
                arena=self.arena["nome"],
                cidade=(location or {}).get("cidade", ""),
            )
            if location:
                record_weather(location, self.arena["diretorio"], self.output, self.arena["nome"])
                record_forecast(location, self.arena["diretorio"], self.output, self.arena["nome"])

            enriched_paths = TratamentoDeDados(self.arena["diretorio"]).aplicar()
            self._print_summary(paths, enriched_paths)
            court_names = self.verified_court_names(results)
        except (PWTimeout, requests.RequestException, ValueError) as error:
            print(f"[AVISO] arena '{self.arena['nome']}' pulada: {error}", file=sys.stderr)
            paths, court_names = [], []
        return paths, court_names, self.output.getvalue()

    @staticmethod
    def verified_court_names(results: list[dict]) -> list[str]:
        return sorted({result["quadra"] for result in results if result["quadra"] and not result["aviso"]})

    def _collect_courts(self) -> list[dict]:
        print(">> TÉCNICA 1 (API JSON, sem navegador): listando esportes...\n", file=self.output)
        sports = list_sports(self.arena["url"])
        for position, sport in enumerate(sports, 1):
            print(f"   {position}. {sport}", file=self.output)

        target_sports = filter_target_sports(sports, self.arena["tipos"])
        missing_types = missing_court_types(target_sports, self.arena["tipos"])
        if missing_types:
            print(f"\n[AVISO] tipos de quadra não encontrados no site: {', '.join(missing_types)}",
                  file=self.output)

        results = []
        for sport in target_sports:
            print(f"\n>> TÉCNICA 2 (Playwright): horários de '{sport}' (todos os períodos)...",
                  file=self.output)
            try:
                sport_results = collect_schedules(
                    sport,
                    self.arena["url"],
                    period=None,
                    headless=not self.visible_browser,
                    days_ahead=self.days_ahead,
                    days_from=self.days_from,
                    types=self.arena["tipos"],
                    proxy=self.proxy,
                )
                results.extend(sport_results)
            except PWTimeout as error:
                print(f"[AVISO] {self.arena['nome']}: '{sport}' pulado por tempo esgotado: {error}",
                      file=sys.stderr)
        return results

    def _record_location(self, results: list[dict]) -> dict | None:
        print(f"\n>> LOCAL (Nominatim): onde fica a {self.arena['nome']}...", file=self.output)
        try:
            with GEOCODING_LOCK:
                location = resolver_local(
                    endereco_observado(results),
                    self.arena["diretorio"],
                    self.arena["coordenadas"],
                )
        except (requests.RequestException, ValueError) as error:
            print(f"[AVISO] {self.arena['nome']}: endereço não geocodificado: {error}",
                  file=sys.stderr)
            return None

        if location is None:
            print(f"[AVISO] {self.arena['nome']}: sem endereço reconhecido, rodada sem clima.",
                  file=sys.stderr)
            return None
        print(f"   {location['endereco']} -> {location['latitude']}, {location['longitude']}",
              file=self.output)
        return location

    def _print_arena_header(self) -> None:
        print("\n" + "#" * 46, file=self.output)
        print(f"  ARENA: {self.arena['nome']}  ({self.arena['url']})", file=self.output)
        print("#" * 46, file=self.output)

    def _print_extraction(self, data: dict) -> None:
        """Imprime o bloco de uma quadra em um período, com os horários e o total de livres."""
        print("\n" + "=" * 46, file=self.output)
        print(f"  {data['esporte']}  |  {data['data']}  |  Período: {data['periodo']}",
              file=self.output)
        if data["quadra"]:
            coverage = {"true": "coberta", "false": "descoberta"}.get(data["quadra_coberta"], "?")
            print(f"  {data['quadra']}  ({coverage})", file=self.output)
        if data.get("endereco"):
            print(f"  {data['endereco']}", file=self.output)
        print(f"  Coletado em: {data['coletado_em']}", file=self.output)
        print("=" * 46, file=self.output)
        if data["aviso"]:
            print(f"  ⚠️  {data['aviso']}", file=self.output)
            print("=" * 46, file=self.output)
            return
        for slot in data["horarios"]:
            marker = "🟢" if slot["status"].lower() == "livre" else "🔴"
            price = f"  R$ {slot['valor']:.2f}" if slot.get("valor") is not None else ""
            print(f"  {marker} {slot['hora']}  -  {slot['status']}{price}", file=self.output)
        free_hours = [slot["hora"] for slot in data["horarios"]
                      if slot["status"].lower() == "livre"]
        print("=" * 46, file=self.output)
        print(f"  Livres: {len(free_hours)}  ->  {', '.join(free_hours) or '(nenhum)'}",
              file=self.output)

    def _print_summary(self, paths: list[str], enriched_paths: list[str]) -> None:
        print(f"\n>> {self.arena['nome']}: extração salva/atualizada em {len(paths)} arquivo(s):",
              file=self.output)
        for path in paths:
            print(f"   {path}", file=self.output)
        print(f">> Clima aplicado em {len(enriched_paths)} arquivo(s) de quadra.",
              file=self.output)
