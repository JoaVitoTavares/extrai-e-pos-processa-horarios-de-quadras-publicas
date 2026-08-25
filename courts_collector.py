"""Coletor de horários de quadras das arenas do webarena.app."""

import re
import time
import requests
from datetime import date, datetime, timedelta
from urllib.parse import urljoin
from playwright.sync_api import sync_playwright, TimeoutError as PWTimeout

from config import (
    CAMINHO_API_INIT,
    DIAS_A_FRENTE,
    PERIODOS_PADRAO,
    TIMEOUT_NAVEGACAO_MS,
    TIPOS_QUADRA,
)
from persistencia import sem_acento

PADRAO_HORARIO = re.compile(r"(\d{1,2}:\d{2})\s*-\s*(Livre|Indispon\w+)", re.IGNORECASE)
PADRAO_DESCOBERTA = re.compile(r"extern|descobert", re.IGNORECASE)
PADRAO_COBERTA = re.compile(r"intern|cobert|ginasio", re.IGNORECASE)
PADRAO_FUTSAL = re.compile(r"futsal|futebol de sal", re.IGNORECASE)
SELETOR_QUADRAS = "div.bubble-rg-flex-row > div.group-item"
SELETOR_CAMPO_DE_DATA = ".picker__input"
SELETOR_OPCAO_DE_ESPORTE = "div.bubble-rg div.bubble-element.Text.clickable-element"
SELETOR_BOTAO_DE_PERIODO = "div.bubble-element.Text.clickable-element"
SCRIPT_ENDERECO = """
(esporte) => {
  const campo = document.querySelector('.picker__input');
  const limite = campo ? campo.getBoundingClientRect().top : Infinity;
  const textos = [...document.querySelectorAll('div.bubble-element.Text')]
    .map((elemento) => {
      const caixa = elemento.getBoundingClientRect();
      return {topo: caixa.top, altura: caixa.height, texto: (elemento.innerText || '').trim()};
    })
    .filter((item) => item.texto && item.altura > 0 && item.topo < limite)
    .sort((a, b) => a.topo - b.topo)
    .map((item) => item.texto);
  const inicio = textos.indexOf(esporte);
  return inicio < 0 ? '' : textos.slice(inicio + 1).find((texto) => texto.includes(',')) || '';
}
"""
SCRIPT_ESTADO_DA_ARENA = """
(dados) => {
  const visivel = (elemento) => !!elemento && elemento.getBoundingClientRect().height > 0;
  if (visivel(document.querySelector(dados.campo_de_data))) return 'agenda';
  if (document.body.innerText.includes(dados.texto_sem_agenda)) return 'sem-agenda';
  if (!dados.esporte) return '';
  const opcao = [...document.querySelectorAll(dados.opcao)]
    .find((elemento) => visivel(elemento) && (elemento.innerText || '').trim() === dados.esporte);
  return opcao ? 'escolher' : '';
}
"""
SCRIPT_PERIODO_ESCOLHIDO = """
(dados) => {
  const botao = [...document.querySelectorAll(dados.seletor)]
    .find((elemento) => elemento.getBoundingClientRect().height > 0
                        && (elemento.innerText || '').trim() === dados.periodo);
  return !!botao && getComputedStyle(botao).backgroundColor !== dados.fundo_sem_realce;
}
"""
FORMATO_DIA_NO_CALENDARIO = "%d/%m/%y"
ESPERA_CALENDARIO_MS = 3_000
ESPERA_REPINTE_DA_GRADE_MS = 500
ESPERA_HORARIOS_MS = 6_000
TEXTO_HORARIOS_DISPONIVEIS = "Horários disponíveis"
FUNDO_SEM_REALCE = "rgba(0, 0, 0, 0)"
TEXTO_LOCAL_SEM_AGENDA = "indisponível para marcações pela web"
AVISO_SEM_AGENDA = "Esta arena não aceita marcação de horário pela web."
AVISO_PERIODO_VAZIO = "Não foi possível coletar os horários deste período."


def _quadra_coberta(nome: str | None) -> str:
    if not nome:
        return ""
    limpo = sem_acento(nome)
    if PADRAO_DESCOBERTA.search(limpo):
        return "false"
    if PADRAO_COBERTA.search(limpo):
        return "true"
    return ""


def _canonico(esporte: str) -> str:
    """Reduz o nome de um esporte à forma em que ele se compara com os tipos configurados:
    sem acento, sem caixa e com futsal e futebol de salão colapsados num nome só, que é
    como duas arenas chamam a mesma quadra."""
    limpo = sem_acento(esporte).casefold().strip()
    return "futebol de salao" if PADRAO_FUTSAL.search(limpo) else limpo


def _tipo_quadra(esporte: str, nome_quadra: str | None, tipos: list[str] = TIPOS_QUADRA) -> str:
    """Canoniza o esporte selecionado para um dos tipos configurados na arena. É a grafia
    do config que vai ao CSV, e é ela que faz as arenas que escrevem 'Futebol society' e
    'Futebol Society' caírem na mesma linha do dataset. Quando o esporte não é
    reconhecido, 'FUTSAL' no nome da quadra resolve para 'Futebol de salão'; fora isso o
    esporte é devolvido como veio, sem perder dado."""
    for tipo in tipos:
        if _canonico(esporte) == _canonico(tipo):
            return tipo
    if nome_quadra and PADRAO_FUTSAL.search(sem_acento(nome_quadra)):
        return "Futebol de salão"
    return esporte


def api_init_de(url_arena: str) -> str:
    return urljoin(url_arena, CAMINHO_API_INIT)


def listar_esportes(url_arena: str) -> list[str]:
    """Lista os esportes que a arena publica, sem os espaços das pontas. O site aceita o
    nome como o dono digitou, e um " Futebol society" com espaço à esquerda não casa com o
    texto da tela, que vem aparado: o clique no esporte erra o item e a leitura do endereço
    não acha por onde começar — a arena coleta os horários e fica sem clima."""
    resposta = requests.get(
        api_init_de(url_arena),
        params={"location": url_arena},
        headers={"User-Agent": "Mozilla/5.0"},
        timeout=30,
    )
    resposta.raise_for_status()
    dados = resposta.json()
    try:
        return [nome.strip() for nome in dados[0]["data"]["esportes_list_text"]]
    except (KeyError, IndexError, TypeError) as erro:
        raise ValueError(
            f"{api_init_de(url_arena)} devolveu JSON em formato inesperado: {erro}"
        ) from erro


def extrair_endereco(pagina, esporte: str, timeout_ms: int = TIMEOUT_NAVEGACAO_MS) -> str:
    """Lê o endereço que a arena publica entre o nome do esporte escolhido e o campo de
    data. É a única coisa na página que diz em que cidade a quadra fica, e é dele que
    saem as coordenadas do clima. O que o identifica é a vírgula que separa rua e cidade,
    que o distingue do rótulo logo abaixo. Não achando, devolve vazio: a arena passa a
    rodada com o local que já conhecia, em vez de receber o clima de outro lugar."""
    try:
        pagina.locator(SELETOR_CAMPO_DE_DATA).first.wait_for(state="visible", timeout=timeout_ms)
    except PWTimeout:
        return ""
    return pagina.evaluate(SCRIPT_ENDERECO, esporte) or ""


def esportes_alvo(esportes_do_site: list[str], tipos: list[str] = TIPOS_QUADRA) -> list[str]:
    procurados = {_canonico(tipo) for tipo in tipos}
    return [nome for nome in esportes_do_site if _canonico(nome) in procurados]


def tipos_ausentes(alvos: list[str], tipos: list[str] = TIPOS_QUADRA) -> list[str]:
    encontrados = {_canonico(alvo) for alvo in alvos}
    return [tipo for tipo in tipos if _canonico(tipo) not in encontrados]


def _estado_da_arena(pagina, esporte: str, timeout_ms: int) -> str:
    """Espera a página assumir um dos estados que interessam ao coletor e diz qual: com o
    campo de data na tela há agenda, com o aviso do site não há, e com o esporte na lista
    falta clicar nele. `esporte` vazio pergunta só pelos dois primeiros, que é o que vale
    depois do clique — o item da lista ainda pode estar na tela saindo."""
    estado = pagina.wait_for_function(
        SCRIPT_ESTADO_DA_ARENA,
        arg={
            "campo_de_data": SELETOR_CAMPO_DE_DATA,
            "opcao": SELETOR_OPCAO_DE_ESPORTE,
            "texto_sem_agenda": TEXTO_LOCAL_SEM_AGENDA,
            "esporte": esporte,
        },
        timeout=timeout_ms,
    )
    return estado.json_value()


def _escolher_esporte(pagina, esporte: str, timeout_ms: int = TIMEOUT_NAVEGACAO_MS) -> bool:
    """Deixa a página no esporte pedido e diz se ele tem agenda para coletar. A arena de um
    esporte só já abre com ele escolhido e mantém o item da lista escondido, então clicar
    seria esperar por um elemento que nunca fica visível. A que não vende pela web anuncia
    isso no lugar do campo de data, e é aqui que ela sai da rodada: insistir no calendário
    custaria o horizonte inteiro de dias, a cada esporte e a cada quinze minutos."""
    if _estado_da_arena(pagina, esporte, timeout_ms) == "escolher":
        pagina.get_by_text(esporte, exact=True).locator("visible=true").first.click()
    return _estado_da_arena(pagina, "", timeout_ms) == "agenda"


def dias_de_coleta(hoje: date, dias_a_frente: int = DIAS_A_FRENTE) -> list[date]:
    return [hoje + timedelta(days=n) for n in range(dias_a_frente + 1)]


def _tentar_o_dia(pagina, rotulo: str, timeout_ms: int) -> bool:
    """Abre o calendário pelo campo de data, avança o mês se a data não estiver na grade,
    clica na célula e diz se a escolha pegou. O clique no campo não é cerimônia: com os
    horários na tela um bloco do Bubble cobre as células, e é `picker--opened` que traz a
    grade para a frente. O respiro antes do clique espera o repinte que vem logo depois de
    abrir: sem ele o clique cai na grade velha e se perde, e a arena não fixa dia nenhum
    em tentativa nenhuma — quem confirma é o valor do campo, e não a classe da célula. Não
    achando a célula nem no mês seguinte, desiste em vez de insistir na grade que ficou
    para trás: reabrir o calendário a repinta, e é de lá que a tentativa seguinte parte."""
    pagina.locator(".picker__input").first.click(timeout=timeout_ms)
    pagina.locator(".picker--opened").first.wait_for(state="attached", timeout=timeout_ms)

    celula = pagina.locator(f".picker__day[aria-label^='{rotulo}']:not(.picker__day--disabled)")
    try:
        celula.first.wait_for(state="visible", timeout=ESPERA_CALENDARIO_MS)
    except PWTimeout:
        pagina.locator(".picker__nav--next").first.click()
        try:
            celula.first.wait_for(state="visible", timeout=ESPERA_CALENDARIO_MS)
        except PWTimeout:
            return False
    pagina.wait_for_timeout(ESPERA_REPINTE_DA_GRADE_MS)
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


def _horarios_na_tela(pagina, timeout_ms: int = ESPERA_HORARIOS_MS) -> bool:
    try:
        pagina.get_by_text(TEXTO_HORARIOS_DISPONIVEIS).first.wait_for(timeout=timeout_ms)
        return True
    except PWTimeout:
        return False


def _selecionar_dia(
    pagina, dia: date, timeout_ms: int = TIMEOUT_NAVEGACAO_MS, tentativas: int = 3
) -> None:
    """Deixa o calendário parado no dia pedido **com os horários dele na tela**, insistindo
    enquanto uma das duas coisas não acontece — reabrir o calendário o repinta em torno da
    data já selecionada, então a tentativa seguinte parte de um estado limpo. As duas
    entram na mesma volta porque o site às vezes carimba a data no campo e não chega a
    carregar a agenda: sem repetir o clique, a arena ficaria parada em "Escolha uma data"
    até o tempo acabar. Não fixando, levanta PWTimeout: horários carimbados com a data
    errada são piores do que o dia faltando."""
    rotulo = dia.strftime(FORMATO_DIA_NO_CALENDARIO)
    for _ in range(tentativas):
        if _tentar_o_dia(pagina, rotulo, timeout_ms) and _horarios_na_tela(pagina):
            return
    raise PWTimeout(f"o calendário não fixou o dia {rotulo} em {tentativas} tentativas")


def _argumento_do_periodo(periodo: str) -> dict:
    return {
        "seletor": SELETOR_BOTAO_DE_PERIODO,
        "periodo": periodo,
        "fundo_sem_realce": FUNDO_SEM_REALCE,
    }


def _periodo_escolhido(pagina, periodo: str) -> bool:
    return pagina.evaluate(SCRIPT_PERIODO_ESCOLHIDO, _argumento_do_periodo(periodo))


def _selecionar_periodo(pagina, periodo: str, texto_anterior: str, timeout_ms: int = 6_000) -> str:
    """Clica no período e espera a tela ser a dele. Quem confirma o clique é o realce do
    botão, e não o conteúdo: a página abre com um período já escolhido, e exigir que o
    texto mude tiraria da coleta justamente a arena que só vende naquele período. Trocado
    o realce, o conteúdo ainda precisa acompanhar, senão o que se lê são os horários do
    período anterior; sem a troca dentro de `timeout_ms` o período é dado como
    indisponível (PWTimeout), que é o caso do período sem nenhum horário à venda."""
    ja_escolhido = _periodo_escolhido(pagina, periodo)
    pagina.get_by_text(periodo, exact=True).first.click()
    pagina.wait_for_function(
        SCRIPT_PERIODO_ESCOLHIDO, arg=_argumento_do_periodo(periodo), timeout=timeout_ms
    )
    if not ja_escolhido:
        pagina.wait_for_function(
            "(anterior) => document.body.innerText !== anterior",
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


def _quadra_sem_horarios(
    esporte: str, periodo: str, dia: date, aviso: str, tipos: list[str] = TIPOS_QUADRA
) -> dict:
    return {
        "coletado_em": datetime.now().isoformat(timespec="seconds"),
        "data": dia.isoformat(),
        "esporte": esporte,
        "periodo": periodo,
        "quadra": None,
        "tipo_quadra": _tipo_quadra(esporte, None, tipos),
        "quadra_coberta": "",
        "aviso": aviso,
        "horarios": [],
    }


def _extrair_quadras(
    pagina, esporte: str, periodo: str, dia: date, tipos: list[str] = TIPOS_QUADRA
) -> list[dict]:
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
            "tipo_quadra": _tipo_quadra(esporte, nome, tipos),
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
    vazia = _quadra_sem_horarios(esporte, periodo, dia, AVISO_PERIODO_VAZIO, tipos)
    return [dict(vazia, raiz=None)]


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
    pagina, esporte: str, dia: date, periodos: list[str], com_preco: bool, tipos: list[str]
) -> list[dict]:
    """Percorre os períodos do dia já selecionado no calendário e devolve as quadras de
    cada um. Espera as quadras estabilizarem antes de fotografar o texto da tela: a troca
    de dia mantém o período anterior marcado e repinta o conteúdo, e um retrato tirado
    cedo demais faria o clique seguinte achar que a página já trocou. O período pulado
    refotografa a tela antes de sair, senão o seguinte compararia com um retrato de dois
    períodos atrás e daria por trocado o que ainda é do vizinho."""
    _esperar_quadras(pagina)
    texto_anterior = pagina.locator("body").inner_text()
    coletadas = []
    for periodo_atual in periodos:
        try:
            _selecionar_periodo(pagina, periodo_atual, texto_anterior)
        except PWTimeout:
            texto_anterior = pagina.locator("body").inner_text()
            continue
        _esperar_quadras(pagina)
        for quadra in _extrair_quadras(pagina, esporte, periodo_atual, dia, tipos):
            raiz = quadra.pop("raiz")
            if com_preco:
                _coletar_precos(raiz, quadra["horarios"])
            coletadas.append(quadra)
        texto_anterior = pagina.locator("body").inner_text()
    return coletadas


def coletar_horarios(
    esporte: str,
    url_arena: str,
    periodo: str | None = None,
    headless: bool = True,
    dias_a_frente: int = DIAS_A_FRENTE,
    tipos: list[str] = TIPOS_QUADRA,
) -> list[dict]:
    """Abre o navegador uma vez e extrai os horários de um esporte da arena em hoje e nos
    `dias_a_frente` seguintes. Com `periodo` informado coleta apenas aquele; com None
    percorre PERIODOS_PADRAO. Um dia que o calendário não libere e um período cujo
    conteúdo não troca em 6s são pulados, e a arena que não vende pela web volta só com o
    aviso. O preço só é aberto no dia de hoje: são dezenas de cliques por rodada, e o
    horário futuro ainda será visitado no seu próprio dia. O endereço acompanha cada
    quadra porque é ele que diz de onde vem o clima daquela."""
    periodos = [periodo] if periodo else PERIODOS_PADRAO

    with sync_playwright() as p:
        navegador = p.chromium.launch(headless=headless)
        pagina = navegador.new_page()

        pagina.goto(url_arena, wait_until="networkidle", timeout=60_000)
        if not _escolher_esporte(pagina, esporte):
            navegador.close()
            return [
                _quadra_sem_horarios(
                    esporte, periodos[0], date.today(), AVISO_SEM_AGENDA, tipos
                )
            ]
        endereco = extrair_endereco(pagina, esporte)

        resultados = []
        for indice, dia in enumerate(dias_de_coleta(date.today(), dias_a_frente)):
            try:
                _selecionar_dia(pagina, dia)
            except PWTimeout:
                continue
            resultados.extend(_coletar_dia(pagina, esporte, dia, periodos, indice == 0, tipos))

        navegador.close()

    return [dict(quadra, endereco=endereco) for quadra in resultados]
