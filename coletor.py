"""
Coletor SP Sports — as DUAS técnicas juntas
============================================

Este módulo demonstra a "escada" do scraping usando cada degrau onde ele é
mais eficiente:

  TÉCNICA 1 (leve)  -> API JSON direta, com requests, para LISTAR OS ESPORTES.
                       Não abre navegador. É a chamada /api/1.1/init/data que
                       descobrimos farejando a rede (ver sniffer.py).

  TÉCNICA 2 (pesada) -> Playwright (navegador real) para os HORÁRIOS, que vêm
                        de uma busca criptografada e só a página sabe montar.

Regra de ouro: use JSON quando puder, navegador só quando precisar.
"""

import re
import sys
import requests
from datetime import datetime
from playwright.sync_api import sync_playwright, TimeoutError as PWTimeout

URL_ARENA = "https://webarena.app/arena/sp-sports"
API_INIT = "https://webarena.app/api/1.1/init/data"

PADRAO_HORARIO = re.compile(r"(\d{1,2}:\d{2})\s*-\s*(Livre|Indispon\w+)", re.IGNORECASE)


# ---------------------------------------------------------------------------
# TÉCNICA 1 — API JSON direta (sem navegador)
# ---------------------------------------------------------------------------
def listar_esportes() -> list[str]:
    """Pega a lista de esportes chamando a API JSON diretamente."""
    resposta = requests.get(
        API_INIT,
        params={"location": URL_ARENA},
        headers={"User-Agent": "Mozilla/5.0"},
        timeout=30,
    )
    resposta.raise_for_status()
    dados = resposta.json()
    return dados[0]["data"]["esportes_list_text"]


# ---------------------------------------------------------------------------
# TÉCNICA 2 — navegador real (Playwright) para os horários
# ---------------------------------------------------------------------------
def coletar_horarios(esporte: str, periodo: str, headless: bool = True) -> dict:
    """Dirige o navegador para extrair os horários de um esporte/período."""
    with sync_playwright() as p:
        navegador = p.chromium.launch(headless=headless)
        pagina = navegador.new_page()

        pagina.goto(URL_ARENA, wait_until="networkidle", timeout=60_000)
        pagina.get_by_text(esporte, exact=True).first.click()

        hoje = pagina.locator(".picker__day--today").first
        hoje.wait_for(state="visible", timeout=15_000)
        hoje.click()

        pagina.get_by_text("Horários disponíveis").first.wait_for(timeout=15_000)
        pagina.get_by_text(periodo, exact=True).first.click()

        # espera inteligente: aguarda um horário de fato aparecer
        pagina.wait_for_function(
            r"() => /\d{1,2}:\d{2}\s*-\s*(Livre|Indispon)/i.test(document.body.innerText)",
            timeout=15_000,
        )
        texto = pagina.locator("body").inner_text()
        navegador.close()

    m = re.search(r"^(FUTSAL.*)$", texto, re.MULTILINE)
    categoria = m.group(1).strip() if m else None
    horarios = [
        {"hora": h, "status": s.capitalize()}
        for h, s in PADRAO_HORARIO.findall(texto)
    ]
    return {
        "coletado_em": datetime.now().isoformat(timespec="seconds"),
        "esporte": esporte,
        "periodo": periodo,
        "categoria": categoria,
        "horarios": horarios,
    }


# ---------------------------------------------------------------------------
# Programa principal — junta as duas técnicas
# ---------------------------------------------------------------------------
def main() -> None:
    modo_visivel = "--ver" in sys.argv

    print(">> TÉCNICA 1 (API JSON, sem navegador): listando esportes...\n")
    esportes = listar_esportes()
    for i, e in enumerate(esportes, 1):
        print(f"   {i}. {e}")

    esporte = "Futebol de salão"
    periodo = "Noite"
    print(f"\n>> TÉCNICA 2 (Playwright): horários de '{esporte}' / '{periodo}'...")
    dados = coletar_horarios(esporte, periodo, headless=not modo_visivel)

    print("\n" + "=" * 46)
    print(f"  {dados['esporte']}  |  Período: {dados['periodo']}")
    if dados["categoria"]:
        print(f"  {dados['categoria']}")
    print(f"  Coletado em: {dados['coletado_em']}")
    print("=" * 46)
    for h in dados["horarios"]:
        marca = "🟢" if h["status"].lower() == "livre" else "🔴"
        print(f"  {marca} {h['hora']}  -  {h['status']}")
    livres = [h["hora"] for h in dados["horarios"] if h["status"].lower() == "livre"]
    print("=" * 46)
    print(f"  Livres: {len(livres)}  ->  {', '.join(livres) or '(nenhum)'}\n")


if __name__ == "__main__":
    try:
        main()
    except PWTimeout as e:
        print(f"\n[ERRO] Tempo esgotado: {e}", file=sys.stderr)
        sys.exit(1)
    except requests.RequestException as e:
        print(f"\n[ERRO] Falha na API JSON: {e}", file=sys.stderr)
        sys.exit(1)
