"""Gerenciador das extrações: roda as arenas em paralelo e grava o resultado."""

import os
import sys
import requests
from concurrent.futures import ThreadPoolExecutor, as_completed
from playwright.sync_api import TimeoutError as PWTimeout

from extrator.arena_extractor import ArenaExtractor
from extrator.config import (
    ARENAS, ARENAS_EM_PARALELO, DIRETORIO_EXTRACOES, DIRETORIO_LOGS, COURT_TYPES
)
from extrator.debug import debug
from extrator.persistencia import registrar_verificacao, slug


def normalize_arena_info(arena: dict) -> dict:
    """Completa uma entrada de ARENAS: deriva o identificador da URL, preenche nome e
    tipos ausentes com os padrões e monta o diretório de saída da arena."""
    arena_slug = slug(arena["url"].rstrip("/").rsplit("/", 1)[-1])
    return {
        "nome": arena.get("nome") or arena_slug,
        "url": arena["url"],
        "diretorio": os.path.join(DIRETORIO_EXTRACOES, arena_slug),
        "coordenadas": arena.get("coordenadas"),
        "tipos": arena.get("tipos") or COURT_TYPES,
    }


def main() -> None:
    visible_browser = "--ver" in sys.argv
    arenas = [normalize_arena_info(configured_arena) for configured_arena in ARENAS]

    saved_paths = []
    arenas_with_results = 0
    pending_arenas = len(arenas)
    debug(f"rodada iniciada: {pending_arenas} arena(s), "
          f"{ARENAS_EM_PARALELO} em paralelo, navegador visivel={visible_browser}")
    with ThreadPoolExecutor(max_workers=max(1, min(ARENAS_EM_PARALELO, len(arenas)))) as executor:
        arena_by_future = {}
        for arena in arenas:
            extractor = ArenaExtractor(arena, visible_browser)
            future = executor.submit(extractor.extract_isolating_failures)
            arena_by_future[future] = arena
        for completed_run in as_completed(arena_by_future):
            paths, verified_courts, run_log = completed_run.result()
            print(run_log, end="")
            registrar_verificacao(
                arena_by_future[completed_run]["nome"], verified_courts, DIRETORIO_LOGS
            )
            arenas_with_results += bool(paths)
            saved_paths.extend(paths)
            pending_arenas -= 1
            debug(f"arena '{arena_by_future[completed_run]['nome']}' concluida: "
                  f"{len(paths)} arquivo(s), {len(verified_courts)} quadra(s) verificada(s); "
                  f"faltam {pending_arenas}")

    if not saved_paths:
        print("\n[ERRO] nenhuma quadra coletada em nenhuma arena.", file=sys.stderr)
        sys.exit(1)

    print(f"\n>> Rodada concluída: {len(saved_paths)} arquivo(s) de quadra "
          f"em {arenas_with_results} de {len(ARENAS)} arena(s).")
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
