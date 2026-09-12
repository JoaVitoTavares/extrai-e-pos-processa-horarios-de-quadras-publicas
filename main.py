"""Gerenciador das extrações: roda as arenas em paralelo e grava o resultado."""

import os
import sys
import requests
from concurrent.futures import ThreadPoolExecutor, as_completed
from playwright.sync_api import TimeoutError as PWTimeout

from extrator.arena_extractor import ArenaExtractor
from extrator.config import (
    ARENAS, ARENAS_EM_PARALELO, DIRETORIO_EXTRACOES, DIRETORIO_LOGS, TIPOS_QUADRA
)
from extrator.persistencia import registrar_verificacao, slug


def normalize_arena_info(arena: dict) -> dict:
    """Completa uma entrada de ARENAS: deriva o identificador da URL, preenche nome e
    tipos ausentes com os padrões e monta o diretório de saída da arena."""
    identificador = slug(arena["url"].rstrip("/").rsplit("/", 1)[-1])
    return {
        "nome": arena.get("nome") or identificador,
        "url": arena["url"],
        "diretorio": os.path.join(DIRETORIO_EXTRACOES, identificador),
        "coordenadas": arena.get("coordenadas"),
        "tipos": arena.get("tipos") or TIPOS_QUADRA,
    }


def main() -> None:
    modo_visivel = "--ver" in sys.argv
    arenas = [normalize_arena_info(configurada) for configurada in ARENAS]

    gravados = []
    coletadas = 0
    with ThreadPoolExecutor(max_workers=max(1, min(ARENAS_EM_PARALELO, len(arenas)))) as executor:
        rodadas = {
            executor.submit(ArenaExtractor(arena, modo_visivel).run): arena for arena in arenas
        }
        for rodada in as_completed(rodadas):
            paths, quadras, texto = rodada.result()
            print(texto, end="")
            registrar_verificacao(rodadas[rodada]["nome"], quadras, DIRETORIO_LOGS)
            coletadas += bool(paths)
            gravados.extend(paths)

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
