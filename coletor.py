"""Coletor de horários de quadras do SP Sports (webarena.app)."""

import re
import sys
import requests
from datetime import datetime
from playwright.sync_api import sync_playwright, TimeoutError as PWTimeout

URL_ARENA = "https://webarena.app/arena/sp-sports"
API_INIT = "https://webarena.app/api/1.1/init/data"
PADRAO_HORARIO = re.compile(r"(\d{1,2}:\d{2})\s*-\s*(Livre|Indispon\w+)", re.IGNORECASE)
PERIODOS_PADRAO = ["Manhã", "Tarde", "Noite"]


def listar_esportes() -> list[str]:
    """Lista os esportes chamando a API JSON diretamente, sem abrir navegador."""
    resposta = requests.get(
        API_INIT,
        params={"location": URL_ARENA},
        headers={"User-Agent": "Mozilla/5.0"},
        timeout=30,
    )
    resposta.raise_for_status()
    dados = resposta.json()
    return dados[0]["data"]["esportes_list_text"]


def _selecionar_periodo(pagina, periodo: str, texto_anterior: str) -> str:
    """Clica no período e espera o conteúdo trocar de fato: como a página já
    mostra os horários do período anterior, aguardar "aparecer algum horário"
    não basta, então esperamos o texto mudar em relação ao anterior ao clique."""
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
    """Converte o texto bruto da página no dicionário de saída do período; se
    nenhum horário é encontrado, preenche `aviso` sinalizando que não foi
    possível coletar aquele período, em vez de devolver uma lista vazia ambígua."""
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
    """Abre o navegador uma vez e extrai os horários de um esporte. Com `periodo`
    informado coleta apenas aquele; com None percorre PERIODOS_PADRAO. Retorna
    sempre uma lista, com um item por período coletado."""
    with sync_playwright() as p:
        navegador = p.chromium.launch(headless=headless)
        pagina = navegador.new_page()

        pagina.goto(URL_ARENA, wait_until="networkidle", timeout=60_000)
        pagina.get_by_text(esporte, exact=True).first.click()

        hoje = pagina.locator(".picker__day--today").first
        hoje.wait_for(state="visible", timeout=15_000)
        hoje.click()

        pagina.get_by_text("Horários disponíveis").first.wait_for(timeout=15_000)

        periodos = [periodo] if periodo else PERIODOS_PADRAO

        texto_anterior = pagina.locator("body").inner_text()
        resultados = []
        for periodo_atual in periodos:
            texto = _selecionar_periodo(pagina, periodo_atual, texto_anterior)
            resultados.append(_extrair_dados(texto, esporte, periodo_atual))
            texto_anterior = texto

        navegador.close()

    return resultados


def main() -> None:
    """Executa as duas técnicas em sequência e imprime os horários no terminal."""
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
