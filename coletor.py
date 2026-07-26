"""Coletor de horários de quadras do SP Sports (webarena.app)."""

import os
import re
import sys
import requests
import pandas as pd
from datetime import datetime, timedelta
from playwright.sync_api import sync_playwright, TimeoutError as PWTimeout

URL_ARENA = "https://webarena.app/arena/sp-sports"
API_INIT = "https://webarena.app/api/1.1/init/data"
PADRAO_HORARIO = re.compile(r"(\d{1,2}:\d{2})\s*-\s*(Livre|Indispon\w+)", re.IGNORECASE)
PERIODOS_PADRAO = ["Manhã", "Tarde", "Noite"]
CAMINHO_CSV = "extracoes.csv"
COLUNAS_CSV = [
    "data", "esporte", "periodo", "horario_inicio", "horario_fim", "status",
    "valor_horario", "ultima_atualizacao", "tipo_quadra", "clima",
    "temperatura", "umidade", "feriado", "evento_grande", "jogo_em_porto_alegre",
]


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
    não basta, então esperamos o texto mudar em relação ao anterior ao clique.
    Se o conteúdo não trocar em 6s, o período é dado como indisponível (PWTimeout)."""
    pagina.get_by_text(periodo, exact=True).first.click()
    pagina.wait_for_function(
        r"""(anterior) => {
            const t = document.body.innerText;
            return t !== anterior && /\d{1,2}:\d{2}\s*-\s*(Livre|Indispon)/i.test(t);
        }""",
        arg=texto_anterior,
        timeout=6_000,
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
    informado coleta apenas aquele; com None percorre PERIODOS_PADRAO. Um período
    cujo conteúdo não troca em 6s é dado como indisponível e pulado. Retorna sempre
    uma lista, com um item por período coletado."""
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
            try:
                texto = _selecionar_periodo(pagina, periodo_atual, texto_anterior)
                resultados.append(_extrair_dados(texto, esporte, periodo_atual))
            except PWTimeout:
                continue
            texto_anterior = pagina.locator("body").inner_text()

        navegador.close()

    return resultados


def _achatar_linhas(resultados: list[dict], agora: datetime) -> list[dict]:
    """Achata a lista de períodos em linhas de reserva prontas para o CSV, pulando
    períodos sem dados (com aviso), derivando horario_fim (início + 1h) e colapsando
    horários repetidos na mesma extração — de cada slot fica sempre o último."""
    data = agora.date().isoformat()
    por_chave = {}
    for periodo in resultados:
        if periodo["aviso"]:
            continue
        for h in periodo["horarios"]:
            inicio = datetime.strptime(h["hora"], "%H:%M")
            fim = (inicio + timedelta(hours=1)).strftime("%H:%M")
            por_chave[(data, periodo["esporte"], h["hora"])] = {
                "data": data,
                "esporte": periodo["esporte"],
                "periodo": periodo["periodo"],
                "horario_inicio": h["hora"],
                "horario_fim": fim,
                "status": h["status"],
                "ultima_atualizacao": agora.isoformat(timespec="seconds"),
            }
    return list(por_chave.values())


def salvar_extracao(resultados: list[dict], caminho_csv: str = CAMINHO_CSV, agora=None):
    """Grava a extração no CSV com upsert por (data, esporte, horario_inicio): um
    slot novo é sempre inserido; um slot já existente só é atualizado enquanto
    `agora < horario_inicio`, congelando quando o horário chega ou passa."""
    agora = agora or datetime.now()
    linhas = _achatar_linhas(resultados, agora)
    if not linhas:
        return

    if os.path.exists(caminho_csv):
        df = pd.read_csv(caminho_csv, dtype=str, keep_default_na=False)
    else:
        df = pd.DataFrame(columns=COLUNAS_CSV)

    for linha in linhas:
        inicio = datetime.strptime(linha["horario_inicio"], "%H:%M").time()
        slot_dt = datetime.combine(agora.date(), inicio)
        existente = (
            (df["data"] == linha["data"])
            & (df["esporte"] == linha["esporte"])
            & (df["horario_inicio"] == linha["horario_inicio"])
        )
        if not existente.any():
            nova = pd.DataFrame([linha]).reindex(columns=COLUNAS_CSV, fill_value="")
            df = pd.concat([df, nova], ignore_index=True)
        elif agora < slot_dt:
            df.loc[existente, ["periodo", "horario_fim", "status", "ultima_atualizacao"]] = [
                linha["periodo"],
                linha["horario_fim"],
                linha["status"],
                linha["ultima_atualizacao"],
            ]

    df.reindex(columns=COLUNAS_CSV, fill_value="").to_csv(caminho_csv, index=False)


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

    salvar_extracao(resultados)
    print(f"\n>> Extração salva/atualizada em {CAMINHO_CSV}\n")


if __name__ == "__main__":
    try:
        main()
    except PWTimeout as e:
        print(f"\n[ERRO] Tempo esgotado: {e}", file=sys.stderr)
        sys.exit(1)
    except requests.RequestException as e:
        print(f"\n[ERRO] Falha na API JSON: {e}", file=sys.stderr)
        sys.exit(1)
