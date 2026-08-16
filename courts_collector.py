"""Coletor de horários de quadras do SP Sports (webarena.app)."""

import re
import time
import requests
from datetime import datetime
from playwright.sync_api import sync_playwright, TimeoutError as PWTimeout

from config import (
    API_INIT,
    PERIODOS_PADRAO,
    TIMEOUT_NAVEGACAO_MS,
    TIPOS_QUADRA,
    URL_ARENA,
)
from persistencia import sem_acento

PADRAO_HORARIO = re.compile(r"(\d{1,2}:\d{2})\s*-\s*(Livre|Indispon\w+)", re.IGNORECASE)
PADRAO_DESCOBERTA = re.compile(r"extern|descobert", re.IGNORECASE)
PADRAO_COBERTA = re.compile(r"intern|cobert", re.IGNORECASE)
PADRAO_FUTSAL = re.compile(r"futsal|futebol de sal", re.IGNORECASE)
SELETOR_QUADRAS = "div.bubble-rg-flex-row > div.group-item"


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
        if sem_acento(esporte).casefold() == sem_acento(tipo).casefold():
            return tipo
    if nome_quadra and PADRAO_FUTSAL.search(sem_acento(nome_quadra)):
        return "Futebol de salão"
    return esporte


def listar_esportes() -> list[str]:
    """Lista os esportes chamando a API JSON diretamente, sem abrir navegador. Um JSON
    fora do formato esperado levanta ValueError em vez de estourar um KeyError cru ou
    devolver lista vazia: num coletor agendado, gravar nada em silêncio custa mais caro
    do que falhar alto."""
    resposta = requests.get(
        API_INIT,
        params={"location": URL_ARENA},
        headers={"User-Agent": "Mozilla/5.0"},
        timeout=30,
    )
    resposta.raise_for_status()
    dados = resposta.json()
    try:
        return dados[0]["data"]["esportes_list_text"]
    except (KeyError, IndexError, TypeError) as erro:
        raise ValueError(f"{API_INIT} devolveu JSON em formato inesperado: {erro}") from erro


def esportes_alvo(esportes_do_site: list[str]) -> list[str]:
    """Seleciona, entre os esportes que o site lista hoje, os que correspondem aos tipos
    de quadra de interesse — os demais, como Beach Tennis e Handebol, ficam de fora.
    Devolve o nome como o site escreve, que é o que o clique na tela precisa, e ignora
    acento e caixa apenas na comparação."""
    procurados = {sem_acento(tipo).casefold() for tipo in TIPOS_QUADRA}
    return [nome for nome in esportes_do_site if sem_acento(nome).casefold() in procurados]


def tipos_ausentes(alvos: list[str]) -> list[str]:
    """Diz quais dos tipos de quadra de interesse não apareceram entre os esportes que o
    site lista hoje. Serve de aviso na execução: um tipo que some do site sem ninguém
    notar viraria uma lacuna silenciosa no histórico, e não um erro."""
    encontrados = {_tipo_quadra(alvo, None) for alvo in alvos}
    return [tipo for tipo in TIPOS_QUADRA if tipo not in encontrados]


def _selecionar_periodo(pagina, periodo: str, texto_anterior: str, timeout_ms: int = 6_000) -> str:
    """Clica no período e espera o conteúdo trocar de fato: como a página já
    mostra os horários do período anterior, aguardar "aparecer algum horário"
    não basta, então esperamos o texto mudar em relação ao anterior ao clique.
    Sem a troca dentro de `timeout_ms`, o período é dado como indisponível (PWTimeout);
    o padrão curto existe para a coleta agendada não travar."""
    pagina.get_by_text(periodo, exact=True).first.click()
    pagina.wait_for_function(
        r"""(anterior) => {
            const t = document.body.innerText;
            return t !== anterior && /\d{1,2}:\d{2}\s*-\s*(Livre|Indispon)/i.test(t);
        }""",
        arg=texto_anterior,
        timeout=timeout_ms,
    )
    return pagina.locator("body").inner_text()


def _esperar_quadras(pagina, timeout_ms: int = 5_000, intervalo_ms: int = 250) -> None:
    """Espera todas as quadras do período terminarem de carregar. Cada RepeatingGroup
    interno é preenchido de forma assíncrona e em ordem imprevisível, então ler cedo
    devolve algumas quadras com zero horários — que sumiriam do CSV sem erro nenhum.
    Só considera pronto quando toda quadra tem ao menos um horário; esperar a contagem
    apenas estabilizar não serve, porque não distingue "terminou" de "ainda nem começou".
    Esgotado o limite, segue com o que houver: a quadra pode estar mesmo sem horários."""
    limite = time.monotonic() + timeout_ms / 1000
    while True:
        contagens = [
            len(PADRAO_HORARIO.findall(raiz.inner_text()))
            for raiz in pagina.locator(SELETOR_QUADRAS).all()
        ]
        if contagens and all(contagens):
            return
        if time.monotonic() >= limite:
            return
        pagina.wait_for_timeout(intervalo_ms)


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


def _coletar_precos(raiz, horarios: list[dict]) -> None:
    """Para cada horário 'Livre', clica no cabeçalho do slot para revelar as opções
    de duração e grava em `valor` o preço de 60 min (ou o único disponível) em float.
    Indisponíveis e slots cujo preço não abre a tempo ficam sem `valor`. `raiz` é o
    locator da quadra, e não a página: quadras diferentes repetem o mesmo horário, e
    buscar na página inteira traria sempre o preço da primeira."""
    for h in horarios:
        if h["status"].lower() != "livre":
            continue
        try:
            cabecalho = raiz.get_by_text(h["hora"], exact=True).first.locator(
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
    uma lista, com um item por quadra de cada período coletado."""
    with sync_playwright() as p:
        navegador = p.chromium.launch(headless=headless)
        pagina = navegador.new_page()

        pagina.goto(URL_ARENA, wait_until="networkidle", timeout=60_000)
        pagina.get_by_text(esporte, exact=True).first.click()

        hoje = pagina.locator(".picker__day--today").first
        hoje.wait_for(state="visible", timeout=TIMEOUT_NAVEGACAO_MS)
        hoje.click()

        pagina.get_by_text("Horários disponíveis").first.wait_for(timeout=TIMEOUT_NAVEGACAO_MS)

        periodos = [periodo] if periodo else PERIODOS_PADRAO

        texto_anterior = pagina.locator("body").inner_text()
        resultados = []
        for periodo_atual in periodos:
            try:
                _selecionar_periodo(pagina, periodo_atual, texto_anterior)
            except PWTimeout:
                continue
            _esperar_quadras(pagina)
            for quadra in _extrair_quadras(pagina, esporte, periodo_atual):
                _coletar_precos(quadra.pop("raiz"), quadra["horarios"])
                resultados.append(quadra)
            texto_anterior = pagina.locator("body").inner_text()

        navegador.close()

    return resultados
