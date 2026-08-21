"""Coletor de horários de quadras do SP Sports (webarena.app)."""

import re
import time
import requests
from datetime import date, datetime, timedelta
from playwright.sync_api import sync_playwright, TimeoutError as PWTimeout

from config import (
    API_INIT,
    DIAS_A_FRENTE,
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
FORMATO_DIA_NO_CALENDARIO = "%d/%m/%y"
ESPERA_CALENDARIO_MS = 3_000


def _quadra_coberta(nome: str | None) -> str:
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
    procurados = {sem_acento(tipo).casefold() for tipo in TIPOS_QUADRA}
    return [nome for nome in esportes_do_site if sem_acento(nome).casefold() in procurados]


def tipos_ausentes(alvos: list[str]) -> list[str]:
    encontrados = {_tipo_quadra(alvo, None) for alvo in alvos}
    return [tipo for tipo in TIPOS_QUADRA if tipo not in encontrados]


def dias_de_coleta(hoje: date, dias_a_frente: int = DIAS_A_FRENTE) -> list[date]:
    return [hoje + timedelta(days=n) for n in range(dias_a_frente + 1)]


def _tentar_o_dia(pagina, rotulo: str, timeout_ms: int) -> bool:
    """Abre o calendário pelo campo de data, avança o mês se a data não estiver na grade,
    clica na célula e diz se a escolha pegou. O clique no campo não é cerimônia: com os
    horários na tela um bloco do Bubble cobre as células, e é `picker--opened` que traz a
    grade para a frente. Quem confirma é o valor do campo, e não a classe da célula: a
    grade é repintada no meio do caminho e o clique às vezes se perde nessa troca."""
    pagina.locator(".picker__input").first.click(timeout=timeout_ms)
    pagina.locator(".picker--opened").first.wait_for(state="attached", timeout=timeout_ms)

    celula = pagina.locator(f".picker__day[aria-label^='{rotulo}']:not(.picker__day--disabled)")
    try:
        celula.first.wait_for(state="visible", timeout=ESPERA_CALENDARIO_MS)
    except PWTimeout:
        pagina.locator(".picker__nav--next").first.click()
        celula.first.wait_for(state="visible", timeout=timeout_ms)
    celula.first.click()

    try:
        pagina.wait_for_function(
            "(rotulo) => document.querySelector('.picker__input').value.startsWith(rotulo)",
            arg=rotulo,
            timeout=ESPERA_CALENDARIO_MS,
        )
        return True
    except PWTimeout:
        return False


def _selecionar_dia(
    pagina, dia: date, timeout_ms: int = TIMEOUT_NAVEGACAO_MS, tentativas: int = 3
) -> None:
    """Deixa o calendário parado no dia pedido, insistindo enquanto a escolha não fixa —
    reabrir o calendário o repinta em torno da data já selecionada, então a tentativa
    seguinte parte de um estado limpo. Sem confirmar a data, levanta PWTimeout em vez de
    seguir: os horários da tela seriam carimbados com a data errada, que é pior do que o
    dia faltando. Dia fora do horizonte chega desabilitado e cai no mesmo caminho."""
    rotulo = dia.strftime(FORMATO_DIA_NO_CALENDARIO)
    for _ in range(tentativas):
        if _tentar_o_dia(pagina, rotulo, timeout_ms):
            pagina.get_by_text("Horários disponíveis").first.wait_for(timeout=timeout_ms)
            return
    raise PWTimeout(f"o calendário não fixou o dia {rotulo} em {tentativas} tentativas")


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


def _extrair_quadras(pagina, esporte: str, periodo: str, dia: date) -> list[dict]:
    """Devolve um dicionário por quadra listada no período, lendo o texto de cada bloco
    isoladamente para que os horários de uma quadra não se misturem com os da vizinha.
    O nome da quadra é a primeira linha do bloco, e dele saem tipo e cobertura. O `dia`
    vem do calendário, e não do relógio, porque a rodada percorre vários. Sem nenhum
    bloco na tela, devolve um item único com `aviso`."""
    quadras = []
    for raiz in pagina.locator(SELETOR_QUADRAS).all():
        texto = raiz.inner_text()
        nome = texto.strip().splitlines()[0].strip()
        quadras.append({
            "coletado_em": datetime.now().isoformat(timespec="seconds"),
            "data": dia.isoformat(),
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
        "data": dia.isoformat(),
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
    limpo = re.sub(r"[^\d,]", "", bruto).replace(",", ".")
    try:
        return float(limpo)
    except ValueError:
        return None


def _preco_do_slot(textos: list[str]) -> float | None:
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


def _coletar_dia(
    pagina, esporte: str, dia: date, periodos: list[str], com_preco: bool
) -> list[dict]:
    """Percorre os períodos do dia já selecionado no calendário e devolve as quadras de
    cada um. Espera as quadras estabilizarem antes de fotografar o texto da tela: a troca
    de dia mantém o período anterior marcado e repinta o conteúdo, e um retrato tirado
    cedo demais faria o clique seguinte achar que a página já trocou."""
    _esperar_quadras(pagina)
    texto_anterior = pagina.locator("body").inner_text()
    coletadas = []
    for periodo_atual in periodos:
        try:
            _selecionar_periodo(pagina, periodo_atual, texto_anterior)
        except PWTimeout:
            continue
        _esperar_quadras(pagina)
        for quadra in _extrair_quadras(pagina, esporte, periodo_atual, dia):
            raiz = quadra.pop("raiz")
            if com_preco:
                _coletar_precos(raiz, quadra["horarios"])
            coletadas.append(quadra)
        texto_anterior = pagina.locator("body").inner_text()
    return coletadas


def coletar_horarios(
    esporte: str,
    periodo: str | None = None,
    headless: bool = True,
    dias_a_frente: int = DIAS_A_FRENTE,
) -> list[dict]:
    """Abre o navegador uma vez e extrai os horários de um esporte em hoje e nos
    `dias_a_frente` seguintes. Com `periodo` informado coleta apenas aquele; com None
    percorre PERIODOS_PADRAO. Um dia que o calendário não libere e um período cujo
    conteúdo não troca em 6s são pulados. O preço só é aberto no dia de hoje: são dezenas
    de cliques por rodada, e o horário futuro ainda será visitado no seu próprio dia."""
    with sync_playwright() as p:
        navegador = p.chromium.launch(headless=headless)
        pagina = navegador.new_page()

        pagina.goto(URL_ARENA, wait_until="networkidle", timeout=60_000)
        pagina.get_by_text(esporte, exact=True).first.click()

        periodos = [periodo] if periodo else PERIODOS_PADRAO

        resultados = []
        for indice, dia in enumerate(dias_de_coleta(date.today(), dias_a_frente)):
            try:
                _selecionar_dia(pagina, dia)
            except PWTimeout:
                continue
            resultados.extend(_coletar_dia(pagina, esporte, dia, periodos, indice == 0))

        navegador.close()

    return resultados
