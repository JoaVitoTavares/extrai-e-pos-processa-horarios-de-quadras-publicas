"""Coletor de horários de quadras do SP Sports (webarena.app)."""

import os
import re
import sys
import time
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
TIMEOUT_NAVEGACAO_MS = 30_000
TIPOS_QUADRA = ["Vôlei de praia", "Futebol de salão", "Grama 7", "Grama 5"]
SELETOR_QUADRAS = "div.bubble-rg-flex-row > div.group-item"
SUFIXO_CSV = "-extracoes.csv"
DIRETORIO_EXTRACOES = ".extracoes"
COLUNAS_CSV = [
    "data", "esporte", "periodo", "horario_inicio", "horario_fim", "status",
    "valor_horario", "ultima_atualizacao", "tipo_quadra", "quadra_coberta", "clima",
    "temperatura", "umidade", "precipitacao", "velocidade_vento", "feriado",
    "evento_grande", "jogo_em_porto_alegre",
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


def _esportes_alvo(esportes_do_site: list[str]) -> list[str]:
    """Seleciona, entre os esportes que o site lista hoje, os que correspondem aos tipos
    de quadra de interesse — os demais, como Beach Tennis e Handebol, ficam de fora.
    Devolve o nome como o site escreve, que é o que o clique na tela precisa, e ignora
    acento e caixa apenas na comparação."""
    procurados = {_sem_acento(tipo).casefold() for tipo in TIPOS_QUADRA}
    return [nome for nome in esportes_do_site if _sem_acento(nome).casefold() in procurados]


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


def _achatar_linhas(resultados: list[dict], agora: datetime) -> list[dict]:
    """Achata as quadras coletadas em linhas de reserva prontas para o CSV, pulando as
    que vieram com aviso, derivando horario_fim (início + 1h) e colapsando horários
    repetidos na mesma extração — de cada slot fica sempre o último. A chave de colapso
    inclui a quadra, senão o mesmo horário em quadras diferentes viraria uma linha só."""
    data = agora.date().isoformat()
    por_chave = {}
    for quadra in resultados:
        if quadra["aviso"]:
            continue
        for h in quadra["horarios"]:
            inicio = datetime.strptime(h["hora"], "%H:%M")
            fim = (inicio + timedelta(hours=1)).strftime("%H:%M")
            por_chave[(data, quadra["quadra"], h["hora"])] = {
                "data": data,
                "esporte": quadra["esporte"],
                "periodo": quadra["periodo"],
                "horario_inicio": h["hora"],
                "horario_fim": fim,
                "status": h["status"],
                "valor_horario": h.get("valor", ""),
                "ultima_atualizacao": agora.isoformat(timespec="seconds"),
                "tipo_quadra": quadra["tipo_quadra"],
                "quadra_coberta": quadra["quadra_coberta"],
                "quadra": quadra["quadra"],
            }
    return list(por_chave.values())


def _gravar_csv(caminho_csv: str, linhas: list[dict], agora: datetime) -> None:
    """Grava as linhas de uma quadra no seu CSV com upsert por (data, esporte,
    horario_inicio): um slot novo é sempre inserido; um slot já existente só é
    atualizado enquanto `agora < horario_inicio`, congelando quando o horário chega ou
    passa. A coluna auxiliar `quadra` cai fora no reindex, já que o arquivo é dela."""
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
            df = nova if df.empty else pd.concat([df, nova], ignore_index=True)
        elif agora < slot_dt:
            df.loc[existente, ["periodo", "horario_fim", "status", "valor_horario", "ultima_atualizacao"]] = [
                linha["periodo"],
                linha["horario_fim"],
                linha["status"],
                linha["valor_horario"],
                linha["ultima_atualizacao"],
            ]

    df.reindex(columns=COLUNAS_CSV, fill_value="").to_csv(caminho_csv, index=False)


def salvar_extracao(
    resultados: list[dict], diretorio: str = DIRETORIO_EXTRACOES, agora=None
) -> list[str]:
    """Distribui a extração em um CSV por quadra, dentro de `diretorio`, criado junto com
    o primeiro arquivo. É o que garante a unicidade do horário: o 17:00 de uma quadra
    nunca disputa linha com o 17:00 de outra. Devolve os caminhos gravados."""
    agora = agora or datetime.now()
    por_quadra = {}
    for linha in _achatar_linhas(resultados, agora):
        por_quadra.setdefault(linha["quadra"], []).append(linha)

    if por_quadra and diretorio:
        os.makedirs(diretorio, exist_ok=True)

    caminhos = []
    for nome, linhas in por_quadra.items():
        caminho_csv = caminho_csv_da_quadra(nome, diretorio)
        _gravar_csv(caminho_csv, linhas, agora)
        caminhos.append(caminho_csv)
    return caminhos


def main() -> None:
    """Executa as duas técnicas em sequência e imprime os horários no terminal. A
    técnica 2 percorre todos os tipos de quadra de interesse; um esporte que falhe é
    reportado e pulado, para não derrubar a coleta dos demais, e uma execução que não
    colete nada sai com erro em vez de gravar silêncio."""
    modo_visivel = "--ver" in sys.argv

    print(">> TÉCNICA 1 (API JSON, sem navegador): listando esportes...\n")
    esportes = listar_esportes()
    for i, e in enumerate(esportes, 1):
        print(f"   {i}. {e}")

    alvos = _esportes_alvo(esportes)
    ausentes = [tipo for tipo in TIPOS_QUADRA if tipo not in {_tipo_quadra(a, None) for a in alvos}]
    if ausentes:
        print(f"\n[AVISO] tipos de quadra não encontrados no site: {', '.join(ausentes)}")

    resultados = []
    for esporte in alvos:
        print(f"\n>> TÉCNICA 2 (Playwright): horários de '{esporte}' (todos os períodos)...")
        try:
            resultados.extend(coletar_horarios(esporte, periodo=None, headless=not modo_visivel))
        except PWTimeout as erro:
            print(f"[AVISO] '{esporte}' pulado por tempo esgotado: {erro}", file=sys.stderr)

    for dados in resultados:
        print("\n" + "=" * 46)
        print(f"  {dados['esporte']}  |  Período: {dados['periodo']}")
        if dados["quadra"]:
            cobertura = {"true": "coberta", "false": "descoberta"}.get(dados["quadra_coberta"], "?")
            print(f"  {dados['quadra']}  ({cobertura})")
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

    caminhos = salvar_extracao(resultados)
    if not caminhos:
        print("\n[ERRO] nenhuma quadra coletada em nenhum esporte.", file=sys.stderr)
        sys.exit(1)

    print(f"\n>> Extração salva/atualizada em {len(caminhos)} arquivo(s):")
    for caminho in caminhos:
        print(f"   {caminho}")
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
