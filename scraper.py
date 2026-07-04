"""
Aplicação base de extração — SP Sports (webarena.app)
=====================================================

Objetivo didático: demonstrar o fluxo mínimo de "web scraping" em um site
DINÂMICO (feito no Bubble.io), onde os dados NÃO vêm no HTML inicial e não há
uma API JSON limpa para chamar. Nesses casos, dirigimos um navegador real.

Fluxo reproduzido:
  1. Abre https://webarena.app/arena/sp-sports
  2. Clica no esporte "Futebol de salão"
  3. Seleciona o dia ATUAL no calendário (classe picker__day--today)
  4. Seleciona o período "Noite"
  5. Extrai e imprime os horários disponíveis

Ferramenta: Playwright (controla um Chromium de verdade, que executa o
JavaScript da página — sem isso, os dados nem apareceriam).
"""

import re
import sys
from datetime import datetime
from playwright.sync_api import sync_playwright, TimeoutError as PWTimeout

URL = "https://webarena.app/arena/sp-sports"
ESPORTE = "Futebol de salão"
PERIODO = "Noite"  # opções na página: Manhã | Tarde | Noite

# Cada horário aparece como uma linha de texto tipo "20:00 - Livre".
# As classes CSS do Bubble são aleatórias, então extraímos por TEXTO (regra
# estável) usando esta expressão regular.
PADRAO_HORARIO = re.compile(r"(\d{1,2}:\d{2})\s*-\s*(Livre|Indispon\w+)", re.IGNORECASE)


def extrair(headless: bool = True) -> dict:
    """Executa o fluxo no navegador e devolve os dados extraídos."""
    with sync_playwright() as p:
        # headless=True roda sem abrir janela (ideal pra servidor/cron).
        # Passe headless=False para ASSISTIR o navegador fazendo o passo a passo.
        navegador = p.chromium.launch(headless=headless)
        pagina = navegador.new_page()

        print(f"[1/5] Abrindo {URL} ...")
        pagina.goto(URL, wait_until="networkidle", timeout=60_000)

        print(f"[2/5] Clicando no esporte: {ESPORTE}")
        pagina.get_by_text(ESPORTE, exact=True).first.click()

        print("[3/5] Selecionando o dia de hoje no calendário ...")
        # A classe .picker__day--today marca o dia atual no pickadate.js.
        hoje = pagina.locator(".picker__day--today").first
        hoje.wait_for(state="visible", timeout=15_000)
        hoje.click()

        print(f"[4/5] Selecionando o período: {PERIODO}")
        # Espera a seção de horários aparecer e clica na aba do período.
        pagina.get_by_text("Horários disponíveis").first.wait_for(timeout=15_000)
        pagina.get_by_text(PERIODO, exact=True).first.click()

        # ESPERA INTELIGENTE: em vez de um tempo fixo (frágil), aguardamos até
        # que uma linha de horário (ex.: "20:00 - Livre") realmente exista na
        # página. O cabeçalho da quadra renderiza antes das linhas, então
        # esperar pelo dado em si evita ler a tela cedo demais.
        pagina.wait_for_function(
            r"() => /\d{1,2}:\d{2}\s*-\s*(Livre|Indispon)/i.test(document.body.innerText)",
            timeout=15_000,
        )

        print("[5/5] Extraindo horários ...")
        texto = pagina.locator("body").inner_text()
        navegador.close()

    # Título da quadra/categoria (ex.: "FUTSAL - Interna"), se existir.
    categoria = None
    m = re.search(r"^(FUTSAL.*)$", texto, re.MULTILINE)
    if m:
        categoria = m.group(1).strip()

    horarios = [
        {"hora": h, "status": s.capitalize()}
        for h, s in PADRAO_HORARIO.findall(texto)
    ]

    return {
        "coletado_em": datetime.now().isoformat(timespec="seconds"),
        "esporte": ESPORTE,
        "periodo": PERIODO,
        "categoria": categoria,
        "horarios": horarios,
    }


def imprimir(dados: dict) -> None:
    print("\n" + "=" * 44)
    print(f"  {dados['esporte']}  |  Período: {dados['periodo']}")
    if dados["categoria"]:
        print(f"  {dados['categoria']}")
    print(f"  Coletado em: {dados['coletado_em']}")
    print("=" * 44)
    if not dados["horarios"]:
        print("  Nenhum horário encontrado.")
    for h in dados["horarios"]:
        marca = "🟢" if h["status"].lower() == "livre" else "🔴"
        print(f"  {marca} {h['hora']}  -  {h['status']}")
    print("=" * 44)
    livres = [h["hora"] for h in dados["horarios"] if h["status"].lower() == "livre"]
    print(f"  Livres: {len(livres)}  ->  {', '.join(livres) or '(nenhum)'}\n")


if __name__ == "__main__":
    # Use  `python scraper.py --ver`  para assistir o navegador em ação.
    modo_visivel = "--ver" in sys.argv
    try:
        dados = extrair(headless=not modo_visivel)
        imprimir(dados)
    except PWTimeout as e:
        print(f"\n[ERRO] Tempo esgotado esperando um elemento: {e}", file=sys.stderr)
        sys.exit(1)
