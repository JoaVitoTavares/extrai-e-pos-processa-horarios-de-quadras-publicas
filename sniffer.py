"""
Sniffer de API (a "busca JSON") — SP Sports
============================================

DEMONSTRAÇÃO DIDÁTICA: como descobrir se um site dinâmico tem uma API JSON
por baixo dos panos, e como espionar o que ela envia/recebe.

Isto é o equivalente AUTOMATIZADO de:
  DevTools (F12) -> aba Network -> filtro Fetch/XHR -> olhar cada chamada.

O Playwright deixa a gente "grampear" o tráfego de rede com listeners de
eventos `request` e `response`. Rodamos o MESMO fluxo do scraper.py, mas em
vez de ler a tela, ESCUTAMOS as chamadas de API que a página faz.
"""

import json
from playwright.sync_api import sync_playwright

URL = "https://webarena.app/arena/sp-sports"

# Só nos interessam chamadas de dados (XHR/Fetch), não imagens/fontes/css.
# Filtramos por trechos de URL que cheiram a "API".
PISTAS_DE_API = ("/api/", "/elasticsearch/", "/user/", "bubble.io")

capturadas = []


def eh_api(url: str) -> bool:
    return any(p in url for p in PISTAS_DE_API)


def ao_terminar_resposta(resposta):
    req = resposta.request
    if req.method not in ("POST", "GET") or not eh_api(req.url):
        return
    # Tenta ler o corpo enviado (POST) e a resposta como JSON.
    payload = req.post_data
    try:
        corpo = resposta.json()
        corpo_txt = json.dumps(corpo, ensure_ascii=False)
    except Exception:
        corpo_txt = "(resposta não é JSON)"
    capturadas.append({
        "metodo": req.method,
        "url": req.url,
        "status": resposta.status,
        "enviado": payload,
        "recebido_preview": corpo_txt[:400],
        "recebido_tamanho": len(corpo_txt),
    })


with sync_playwright() as p:
    navegador = p.chromium.launch(headless=True)
    pagina = navegador.new_page()
    pagina.on("response", ao_terminar_resposta)  # <- o "grampo"

    print("Executando o fluxo enquanto escutamos a rede...\n")
    pagina.goto(URL, wait_until="networkidle", timeout=60_000)
    pagina.get_by_text("Futebol de salão", exact=True).first.click()
    hoje = pagina.locator(".picker__day--today").first
    hoje.wait_for(state="visible", timeout=15_000)
    hoje.click()
    pagina.get_by_text("Horários disponíveis").first.wait_for(timeout=15_000)
    pagina.get_by_text("Noite", exact=True).first.click()
    pagina.wait_for_timeout(3000)  # deixa as chamadas de API acontecerem
    navegador.close()


print(f"=== {len(capturadas)} chamadas de API capturadas ===\n")
for i, c in enumerate(capturadas, 1):
    # encurta a URL pra caber
    url = c["url"].split("?")[0]
    print(f"[{i}] {c['metodo']} {c['status']}  {url}")
    if c["enviado"]:
        env = c["enviado"]
        print(f"    ENVIOU  : {env[:200]}{'...' if len(env) > 200 else ''}")
    print(f"    RECEBEU ({c['recebido_tamanho']} chars): {c['recebido_preview']}")
    print()
