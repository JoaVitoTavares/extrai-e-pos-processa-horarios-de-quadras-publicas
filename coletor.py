"""Coletor de horários de quadras do SP Sports (webarena.app)."""

import os
import re
import sys
import unicodedata
import requests
import pandas as pd
from datetime import datetime, timedelta
from playwright.sync_api import sync_playwright, TimeoutError as PWTimeout

URL_ARENA = "https://webarena.app/arena/sp-sports"
API_INIT = "https://webarena.app/api/1.1/init/data"
PADRAO_HORARIO = re.compile(r"(\d{1,2}:\d{2})\s*-\s*(Livre|Indispon\w+)", re.IGNORECASE)
PADRAO_DESCOBERTA = re.compile(r"extern|descobert", re.IGNORECASE)
PADRAO_COBERTA = re.compile(r"intern|cobert", re.IGNORECASE)
PADRAO_FUTSAL = re.compile(r"futsal|futebol de sal", re.IGNORECASE)
PERIODOS_PADRAO = ["Manhã", "Tarde", "Noite"]
TIPOS_QUADRA = ["Vôlei de praia", "Futebol de salão", "Grama 7", "Grama 5"]
SELETOR_QUADRAS = "div.bubble-rg-flex-row > div.group-item"
CAMINHO_CSV = "extracoes.csv"
SUFIXO_CSV = "-extracoes.csv"
COLUNAS_CSV = [
    "data", "esporte", "periodo", "horario_inicio", "horario_fim", "status",
    "valor_horario", "ultima_atualizacao", "tipo_quadra", "quadra_coberta", "clima",
    "temperatura", "umidade", "feriado", "evento_grande", "jogo_em_porto_alegre",
]


def _sem_acento(texto: str) -> str:
    """Devolve o texto sem sinais diacríticos, para comparar e montar nomes de arquivo
    sem depender de o site escrever 'Vôlei' ou 'Volei'."""
    decomposto = unicodedata.normalize("NFKD", texto)
    return "".join(c for c in decomposto if not unicodedata.combining(c))


def _slug(nome: str) -> str:
    """Converte o nome de uma quadra em identificador de arquivo: minúsculo, sem acento
    e com qualquer sequência de pontuação ou espaço virando um hífen só."""
    return re.sub(r"[^a-z0-9]+", "-", _sem_acento(nome).lower()).strip("-")


def caminho_csv_da_quadra(nome: str, diretorio: str = "") -> str:
    """Monta o caminho do CSV daquela quadra, já que cada quadra tem o seu: assim o
    horário de uma nunca disputa linha com o horário de outra."""
    return os.path.join(diretorio, _slug(nome) + SUFIXO_CSV)


def _quadra_coberta(nome: str | None) -> str:
    """Classifica a quadra pelo nome: interna ou coberta é 'true', externa ou descoberta
    é 'false'. Descoberta é testada primeiro porque contém 'coberta'. Sem nome ou sem
    palavra-chave devolve vazio, para não afirmar um 'false' que não foi observado."""
    if not nome:
        return ""
    if PADRAO_DESCOBERTA.search(nome):
        return "false"
    if PADRAO_COBERTA.search(nome):
        return "true"
    return ""


def _tipo_quadra(esporte: str, nome_quadra: str | None) -> str:
    """Canoniza o esporte selecionado para um dos tipos de TIPOS_QUADRA, ignorando
    acento. Quando o esporte não é reconhecido, 'FUTSAL' no nome da quadra resolve para
    'Futebol de salão'; fora isso o esporte é devolvido como veio, sem perder dado."""
    for tipo in TIPOS_QUADRA:
        if _sem_acento(esporte).casefold() == _sem_acento(tipo).casefold():
            return tipo
    if nome_quadra and PADRAO_FUTSAL.search(_sem_acento(nome_quadra)):
        return "Futebol de salão"
    return esporte


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


def _extrair_quadras(pagina, esporte: str, periodo: str) -> list[dict]:
    """Devolve um dicionário por quadra listada no período, lendo o texto de cada bloco
    isoladamente para que os horários de uma quadra não se misturem com os da vizinha.
    O nome da quadra é a primeira linha do bloco, e dele saem tipo e cobertura. Sem
    nenhum bloco na tela, devolve um item único com `aviso`, sinalizando que não foi
    possível coletar aquele período."""
    quadras = []
    for raiz in pagina.locator(SELETOR_QUADRAS).all():
        texto = raiz.inner_text()
        nome = texto.strip().splitlines()[0].strip()
        quadras.append({
            "coletado_em": datetime.now().isoformat(timespec="seconds"),
            "esporte": esporte,
            "periodo": periodo,
            "quadra": nome,
            "tipo_quadra": _tipo_quadra(esporte, nome),
            "quadra_coberta": _quadra_coberta(nome),
            "aviso": None,
            "horarios": [
                {"hora": h, "status": s.capitalize()}
                for h, s in PADRAO_HORARIO.findall(texto)
            ],
            "raiz": raiz,
        })
    if quadras:
        return quadras
    return [{
        "coletado_em": datetime.now().isoformat(timespec="seconds"),
        "esporte": esporte,
        "periodo": periodo,
        "quadra": None,
        "tipo_quadra": _tipo_quadra(esporte, None),
        "quadra_coberta": "",
        "aviso": "Não foi possível coletar os horários deste período.",
        "horarios": [],
        "raiz": None,
    }]


def _preco_para_float(bruto: str) -> float | None:
    """Converte um preço em texto (ex.: 'R$ 1.500,00' ou 'R$150') para float,
    descartando o que não for dígito ou vírgula e tratando o ponto como separador
    de milhar e a vírgula como decimal. Retorna None se não sobrar número."""
    limpo = re.sub(r"[^\d,]", "", bruto).replace(",", ".")
    try:
        return float(limpo)
    except ValueError:
        return None


def _preco_do_slot(textos: list[str]) -> float | None:
    """Escolhe o preço de um slot a partir dos textos das opções de duração (ex.:
    '60 min. R$150'): prefere sempre a opção de 60 min e, na falta dela, usa a
    primeira opção com preço. Retorna o valor em float ou None."""
    candidatos = []
    for texto in textos:
        preco = re.search(r"R\$\s*([\d.,]+)", texto)
        if not preco:
            continue
        minutos = re.search(r"(\d+)\s*min", texto, re.IGNORECASE)
        candidatos.append(
            (int(minutos.group(1)) if minutos else None, _preco_para_float(preco.group(1)))
        )
    for minutos, valor in candidatos:
        if minutos == 60:
            return valor
    return candidatos[0][1] if candidatos else None


def _coletar_precos(pagina, horarios: list[dict]) -> None:
    """Para cada horário 'Livre', clica no cabeçalho do slot para revelar as opções
    de duração e grava em `valor` o preço de 60 min (ou o único disponível) em float.
    Indisponíveis e slots cujo preço não abre a tempo ficam sem `valor`."""
    for h in horarios:
        if h["status"].lower() != "livre":
            continue
        try:
            cabecalho = pagina.get_by_text(h["hora"], exact=True).first.locator(
                "xpath=ancestor::div[contains(@class,'clickable-element')][1]"
            )
            opcoes = cabecalho.locator(
                "xpath=following-sibling::div[contains(@class,'RepeatingGroup')]"
                "//div[contains(@class,'group-item')]"
            )
            cabecalho.click(timeout=3_000)
            try:
                opcoes.first.wait_for(state="attached", timeout=3_000)
            except PWTimeout:
                pass
            textos = opcoes.all_text_contents() + [cabecalho.text_content() or ""]
        except PWTimeout:
            continue
        valor = _preco_do_slot(textos)
        if valor is not None:
            h["valor"] = valor


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
            except PWTimeout:
                continue
            dados = _extrair_dados(texto, esporte, periodo_atual)
            _coletar_precos(pagina, dados["horarios"])
            resultados.append(dados)
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
                "valor_horario": h.get("valor", ""),
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
            df.loc[existente, ["periodo", "horario_fim", "status", "valor_horario", "ultima_atualizacao"]] = [
                linha["periodo"],
                linha["horario_fim"],
                linha["status"],
                linha["valor_horario"],
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
            preco = f"  R$ {h['valor']:.2f}" if h.get("valor") is not None else ""
            print(f"  {marca} {h['hora']}  -  {h['status']}{preco}")
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
