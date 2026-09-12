"""Recaptura as fixtures HTML de tests/fixtures a partir do site real."""

import os
import sys
from datetime import date

from playwright.sync_api import sync_playwright

RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, RAIZ)

from extrator import config
from extrator import courts_collector

ARENA = config.ARENAS[0]["url"]
DIRETORIO_FIXTURES = os.path.join(RAIZ, "tests", "fixtures")
SELETOR_CONTAINER = "div.bubble-rg-flex-row"
CAPTURAS = [
    ("quatro_quadras_volei.html", "Vôlei de praia", "Noite"),
    ("quadra_unica_grama7.html", "Grama 7", "Noite"),
]


def capturar(pagina, esporte: str, periodo: str) -> str:
    """Navega até o esporte, o dia de hoje e o período pedidos e devolve o outerHTML do
    RepeatingGroup de quadras, que é o trecho que as fixtures precisam congelar."""
    pagina.goto(ARENA, wait_until="networkidle", timeout=60_000)
    courts_collector._escolher_esporte(pagina, esporte, timeout_ms=15_000)

    hoje = pagina.locator(".picker__day--today").first
    hoje.wait_for(state="visible", timeout=15_000)
    hoje.click()

    pagina.get_by_text("Horários disponíveis").first.wait_for(timeout=15_000)
    courts_collector._selecionar_periodo(pagina, periodo, pagina.locator("body").inner_text())
    container = pagina.locator(SELETOR_CONTAINER).first
    return container.evaluate("elemento => elemento.outerHTML")


def main() -> None:
    with sync_playwright() as playwright:
        navegador = playwright.chromium.launch(headless=True)
        for nome_arquivo, esporte, periodo in CAPTURAS:
            pagina = navegador.new_page()
            html = capturar(pagina, esporte, periodo)
            pagina.close()

            caminho = os.path.join(DIRETORIO_FIXTURES, nome_arquivo)
            cabecalho = (
                f"<!-- capturado de {ARENA} em {date.today().isoformat()} -->\n"
                f"<!-- {esporte}, período {periodo} -->\n"
            )
            with open(caminho, "w", encoding="utf-8") as arquivo:
                arquivo.write(cabecalho + html + "\n")
            print(f"gravado: {caminho}")
        navegador.close()


if __name__ == "__main__":
    main()
