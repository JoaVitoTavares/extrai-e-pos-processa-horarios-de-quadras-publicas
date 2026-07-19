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

# Períodos percorridos quando coletar_horarios recebe periodo=None ("buscar todos").
# Se o site mudar os rótulos, ajuste aqui.
PERIODOS_PADRAO = ["Manhã", "Tarde", "Noite"]


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
def _selecionar_periodo(pagina, periodo: str, texto_anterior: str) -> str:
    """Clica no período e espera o conteúdo TROCAR (não apenas existir).

    Ao alternar entre períodos, a página já contém horários do período anterior;
    por isso não basta esperar "aparecer algum horário" — precisamos esperar o
    texto MUDAR em relação ao que estava na tela antes do clique.
    """
    pagina.get_by_text(periodo, exact=True).first.click()
    pagina.wait_for_function(
        r"""(anterior) => {
            const t = document.body.innerText;
            return t !== anterior && /\d{1,2}:\d{2}\s*-\s*(Livre|Indispon)/i.test(t);
        }""",
        arg=texto_anterior,
        timeout=15_000,
    )
    return pagina.locator("body").inner_text()


def _extrair_dados(texto: str, esporte: str, periodo: str) -> dict:
    """Transforma o texto bruto da página no dicionário de saída de um período.

    Se nenhum horário for encontrado, preenche `aviso` sinalizando que não foi
    possível coletar os dados daquele período (em vez de devolver silenciosamente
    uma lista vazia, que seria ambígua).
    """
    m = re.search(r"^(FUTSAL.*)$", texto, re.MULTILINE)
    categoria = m.group(1).strip() if m else None
    horarios = [
        {"hora": h, "status": s.capitalize()}
        for h, s in PADRAO_HORARIO.findall(texto)
    ]
    aviso = None if horarios else "Não foi possível coletar os horários deste período."
    return {
        "coletado_em": datetime.now().isoformat(timespec="seconds"),
        "esporte": esporte,
        "periodo": periodo,
        "categoria": categoria,
        "aviso": aviso,
        "horarios": horarios,
    }


def coletar_horarios(
    esporte: str, periodo: str | None = None, headless: bool = True
) -> list[dict]:
    """Dirige o navegador para extrair os horários de um esporte.

    Se `periodo` for informado, coleta só aquele período. Se for None, percorre
    todos os períodos de PERIODOS_PADRAO. Retorna SEMPRE uma lista (um item por
    período coletado), mesmo quando há um único período.
    """
    with sync_playwright() as p:
        navegador = p.chromium.launch(headless=headless)
        pagina = navegador.new_page()

        # --- setup comum: feito UMA vez, reaproveitado por todos os períodos ---
        pagina.goto(URL_ARENA, wait_until="networkidle", timeout=60_000)
        pagina.get_by_text(esporte, exact=True).first.click()

        hoje = pagina.locator(".picker__day--today").first
        hoje.wait_for(state="visible", timeout=15_000)
        hoje.click()

        pagina.get_by_text("Horários disponíveis").first.wait_for(timeout=15_000)

        # --- decide o que iterar: um período específico ou todos ---
        periodos = [periodo] if periodo else PERIODOS_PADRAO

        # --- loop: um clique + extração por período, na mesma página ---
        texto_anterior = pagina.locator("body").inner_text()
        resultados = []
        for periodo_atual in periodos:
            texto = _selecionar_periodo(pagina, periodo_atual, texto_anterior)
            resultados.append(_extrair_dados(texto, esporte, periodo_atual))
            texto_anterior = texto

        navegador.close()

    return resultados


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
    print(f"\n>> TÉCNICA 2 (Playwright): horários de '{esporte}' (todos os períodos)...")
    resultados = coletar_horarios(esporte, periodo=None, headless=not modo_visivel)

    for dados in resultados:
        print("\n" + "=" * 46)
        print(f"  {dados['esporte']}  |  Período: {dados['periodo']}")
        if dados["categoria"]:
            print(f"  {dados['categoria']}")
        print(f"  Coletado em: {dados['coletado_em']}")
        print("=" * 46)
        if dados["aviso"]:
            print(f"  ⚠️  {dados['aviso']}")
            print("=" * 46)
            continue
        for h in dados["horarios"]:
            marca = "🟢" if h["status"].lower() == "livre" else "🔴"
            print(f"  {marca} {h['hora']}  -  {h['status']}")
        livres = [h["hora"] for h in dados["horarios"] if h["status"].lower() == "livre"]
        print("=" * 46)
        print(f"  Livres: {len(livres)}  ->  {', '.join(livres) or '(nenhum)'}")
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
