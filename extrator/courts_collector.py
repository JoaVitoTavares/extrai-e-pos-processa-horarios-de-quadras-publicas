"""Coletor de horários de quadras das arenas do webarena.app."""

import re
import time
import requests
from datetime import date, datetime, timedelta
from urllib.parse import urljoin
from playwright.sync_api import sync_playwright, TimeoutError as PWTimeout

from extrator.config import (
    CAMINHO_API_INIT,
    DIAS_A_FRENTE,
    PERIODOS_PADRAO,
    TIMEOUT_NAVEGACAO_MS,
    TIPOS_QUADRA,
)
from extrator.persistencia import sem_acento

SCHEDULE_PATTERN = re.compile(r"(\d{1,2}:\d{2})\s*-\s*(Livre|Indispon\w+)", re.IGNORECASE)
UNCOVERED_PATTERN = re.compile(r"extern|descobert", re.IGNORECASE)
COVERED_PATTERN = re.compile(r"intern|cobert|ginasio", re.IGNORECASE)
FUTSAL_PATTERN = re.compile(r"futsal|futebol de sal", re.IGNORECASE)
COURTS_SELECTOR = "div.bubble-rg-flex-row > div.group-item"
DATE_FIELD_SELECTOR = ".picker__input"
SPORT_OPTION_SELECTOR = "div.bubble-rg div.bubble-element.Text.clickable-element"
PERIOD_BUTTON_SELECTOR = "div.bubble-element.Text.clickable-element"
ADDRESS_SCRIPT = """
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
ARENA_STATE_SCRIPT = """
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
PERIOD_SELECTED_SCRIPT = """
(dados) => {
  const botao = [...document.querySelectorAll(dados.seletor)]
    .find((elemento) => elemento.getBoundingClientRect().height > 0
                        && (elemento.innerText || '').trim() === dados.periodo);
  return !!botao && getComputedStyle(botao).backgroundColor !== dados.fundo_sem_realce;
}
"""
CALENDAR_DAY_FORMAT = "%d/%m/%y"
CALENDAR_WAIT_MS = 3_000
GRID_REPAINT_WAIT_MS = 500
SCHEDULES_WAIT_MS = 6_000
AVAILABLE_SCHEDULES_TEXT = "Horários disponíveis"
UNHIGHLIGHTED_BACKGROUND = "rgba(0, 0, 0, 0)"
VENUE_WITHOUT_SCHEDULE_TEXT = "indisponível para marcações pela web"
NO_SCHEDULE_WARNING = "Esta arena não aceita marcação de horário pela web."
EMPTY_PERIOD_WARNING = "Não foi possível coletar os horários deste período."


def _covered_court(name: str | None) -> str:
    if not name:
        return ""
    cleaned = sem_acento(name)
    if UNCOVERED_PATTERN.search(cleaned):
        return "false"
    if COVERED_PATTERN.search(cleaned):
        return "true"
    return ""


def _canonical(sport: str) -> str:
    cleaned = sem_acento(sport).casefold().strip()
    return "futebol de salao" if FUTSAL_PATTERN.search(cleaned) else cleaned


def _court_type(sport: str, court_name: str | None, types: list[str] = TIPOS_QUADRA) -> str:
    for court_type in types:
        if _canonical(sport) == _canonical(court_type):
            return court_type
    if court_name and FUTSAL_PATTERN.search(sem_acento(court_name)):
        return "Futebol de salão"
    return sport


def api_init_url(arena_url: str) -> str:
    return urljoin(arena_url, CAMINHO_API_INIT)


def list_sports(arena_url: str) -> list[str]:
    response = requests.get(
        api_init_url(arena_url),
        params={"location": arena_url},
        headers={"User-Agent": "Mozilla/5.0"},
        timeout=30,
    )
    response.raise_for_status()
    data = response.json()
    try:
        return [name.strip() for name in data[0]["data"]["esportes_list_text"]]
    except (KeyError, IndexError, TypeError) as error:
        raise ValueError(
            f"{api_init_url(arena_url)} devolveu JSON em formato inesperado: {error}"
        ) from error


def extract_address(page, sport: str, timeout_ms: int = TIMEOUT_NAVEGACAO_MS) -> str:
    try:
        page.locator(DATE_FIELD_SELECTOR).first.wait_for(state="visible", timeout=timeout_ms)
    except PWTimeout:
        return ""
    return page.evaluate(ADDRESS_SCRIPT, sport) or ""


def filter_target_sports(site_sports: list[str], types: list[str] = TIPOS_QUADRA) -> list[str]:
    wanted = {_canonical(court_type) for court_type in types}
    return [name for name in site_sports if _canonical(name) in wanted]


def missing_court_types(targets: list[str], types: list[str] = TIPOS_QUADRA) -> list[str]:
    found = {_canonical(target) for target in targets}
    return [court_type for court_type in types if _canonical(court_type) not in found]


def _arena_state(page, sport: str, timeout_ms: int) -> str:
    state = page.wait_for_function(
        ARENA_STATE_SCRIPT,
        arg={
            "campo_de_data": DATE_FIELD_SELECTOR,
            "opcao": SPORT_OPTION_SELECTOR,
            "texto_sem_agenda": VENUE_WITHOUT_SCHEDULE_TEXT,
            "esporte": sport,
        },
        timeout=timeout_ms,
    )
    return state.json_value()


def _choose_sport(page, sport: str, timeout_ms: int = TIMEOUT_NAVEGACAO_MS) -> bool:
    if _arena_state(page, sport, timeout_ms) == "escolher":
        page.get_by_text(sport, exact=True).locator("visible=true").first.click()
    return _arena_state(page, "", timeout_ms) == "agenda"


def collection_days(today: date, days_ahead: int = DIAS_A_FRENTE) -> list[date]:
    return [today + timedelta(days=n) for n in range(days_ahead + 1)]


def _try_day(page, label: str, timeout_ms: int) -> bool:
    page.locator(".picker__input").first.click(timeout=timeout_ms)
    page.locator(".picker--opened").first.wait_for(state="attached", timeout=timeout_ms)

    cell = page.locator(f".picker__day[aria-label^='{label}']:not(.picker__day--disabled)")
    try:
        cell.first.wait_for(state="visible", timeout=CALENDAR_WAIT_MS)
    except PWTimeout:
        page.locator(".picker__nav--next").first.click()
        try:
            cell.first.wait_for(state="visible", timeout=CALENDAR_WAIT_MS)
        except PWTimeout:
            return False
    page.wait_for_timeout(GRID_REPAINT_WAIT_MS)
    cell.first.click()

    try:
        page.wait_for_function(
            "(rotulo) => document.querySelector('.picker__input').value.startsWith(rotulo)",
            arg=label,
            timeout=CALENDAR_WAIT_MS,
        )
        return True
    except PWTimeout:
        return False


def _schedules_on_screen(page, timeout_ms: int = SCHEDULES_WAIT_MS) -> bool:
    try:
        page.get_by_text(AVAILABLE_SCHEDULES_TEXT).first.wait_for(timeout=timeout_ms)
        return True
    except PWTimeout:
        return False


def _select_day(
    page, day: date, timeout_ms: int = TIMEOUT_NAVEGACAO_MS, attempts: int = 3
) -> None:
    label = day.strftime(CALENDAR_DAY_FORMAT)
    for _ in range(attempts):
        if _try_day(page, label, timeout_ms) and _schedules_on_screen(page):
            return
    raise PWTimeout(f"o calendário não fixou o dia {label} em {attempts} tentativas")


def _period_argument(period: str) -> dict:
    return {
        "seletor": PERIOD_BUTTON_SELECTOR,
        "periodo": period,
        "fundo_sem_realce": UNHIGHLIGHTED_BACKGROUND,
    }


def _period_selected(page, period: str) -> bool:
    return page.evaluate(PERIOD_SELECTED_SCRIPT, _period_argument(period))


def _select_period(page, period: str, previous_text: str, timeout_ms: int = 6_000) -> str:
    already_selected = _period_selected(page, period)
    page.get_by_text(period, exact=True).first.click()
    page.wait_for_function(
        PERIOD_SELECTED_SCRIPT, arg=_period_argument(period), timeout=timeout_ms
    )
    if not already_selected:
        page.wait_for_function(
            "(anterior) => document.body.innerText !== anterior",
            arg=previous_text,
            timeout=timeout_ms,
        )
    return page.locator("body").inner_text()


def _wait_for_courts(page, timeout_ms: int = 5_000, interval_ms: int = 250) -> None:
    deadline = time.monotonic() + timeout_ms / 1000
    while True:
        counts = [
            len(SCHEDULE_PATTERN.findall(root.inner_text()))
            for root in page.locator(COURTS_SELECTOR).all()
        ]
        if counts and all(counts):
            return
        if time.monotonic() >= deadline:
            return
        page.wait_for_timeout(interval_ms)


def _court_without_schedules(
    sport: str, period: str, day: date, warning: str, types: list[str] = TIPOS_QUADRA
) -> dict:
    return {
        "coletado_em": datetime.now().isoformat(timespec="seconds"),
        "data": day.isoformat(),
        "esporte": sport,
        "periodo": period,
        "quadra": None,
        "tipo_quadra": _court_type(sport, None, types),
        "quadra_coberta": "",
        "aviso": warning,
        "horarios": [],
    }


def _extract_courts(
    page, sport: str, period: str, day: date, types: list[str] = TIPOS_QUADRA
) -> list[dict]:
    courts = []
    for root in page.locator(COURTS_SELECTOR).all():
        text = root.inner_text()
        name = text.strip().splitlines()[0].strip()
        courts.append({
            "coletado_em": datetime.now().isoformat(timespec="seconds"),
            "data": day.isoformat(),
            "esporte": sport,
            "periodo": period,
            "quadra": name,
            "tipo_quadra": _court_type(sport, name, types),
            "quadra_coberta": _covered_court(name),
            "aviso": None,
            "horarios": [
                {"hora": hour, "status": status.capitalize()}
                for hour, status in SCHEDULE_PATTERN.findall(text)
            ],
            "raiz": root,
        })
    if courts:
        return courts
    empty = _court_without_schedules(sport, period, day, EMPTY_PERIOD_WARNING, types)
    return [dict(empty, raiz=None)]


def _price_to_float(raw: str) -> float | None:
    cleaned = re.sub(r"[^\d,]", "", raw).replace(",", ".")
    try:
        return float(cleaned)
    except ValueError:
        return None


def _slot_price(texts: list[str]) -> float | None:
    candidates = []
    for text in texts:
        price = re.search(r"R\$\s*([\d.,]+)", text)
        if not price:
            continue
        minutes = re.search(r"(\d+)\s*min", text, re.IGNORECASE)
        candidates.append(
            (int(minutes.group(1)) if minutes else None, _price_to_float(price.group(1)))
        )
    for minutes, value in candidates:
        if minutes == 60:
            return value
    return candidates[0][1] if candidates else None


def _collect_prices(root, schedules: list[dict]) -> None:
    for schedule in schedules:
        if schedule["status"].lower() != "livre":
            continue
        try:
            header = root.get_by_text(schedule["hora"], exact=True).first.locator(
                "xpath=ancestor::div[contains(@class,'clickable-element')][1]"
            )
            options = header.locator(
                "xpath=following-sibling::div[contains(@class,'RepeatingGroup')]"
                "//div[contains(@class,'group-item')]"
            )
            header.click(timeout=3_000)
            try:
                options.first.wait_for(state="attached", timeout=3_000)
            except PWTimeout:
                pass
            texts = options.all_text_contents() + [header.text_content() or ""]
        except PWTimeout:
            continue
        value = _slot_price(texts)
        if value is not None:
            schedule["valor"] = value


def _collect_day(
    page, sport: str, day: date, periods: list[str], with_price: bool, types: list[str]
) -> list[dict]:
    _wait_for_courts(page)
    previous_text = page.locator("body").inner_text()
    collected = []
    for current_period in periods:
        try:
            _select_period(page, current_period, previous_text)
        except PWTimeout:
            previous_text = page.locator("body").inner_text()
            continue
        _wait_for_courts(page)
        for court in _extract_courts(page, sport, current_period, day, types):
            root = court.pop("raiz")
            if with_price:
                _collect_prices(root, court["horarios"])
            collected.append(court)
        previous_text = page.locator("body").inner_text()
    return collected


def collect_schedules(
    sport: str,
    arena_url: str,
    period: str | None = None,
    headless: bool = True,
    days_ahead: int = DIAS_A_FRENTE,
    types: list[str] = TIPOS_QUADRA,
) -> list[dict]:
    periods = [period] if period else PERIODOS_PADRAO

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=headless)
        page = browser.new_page()

        page.goto(arena_url, wait_until="networkidle", timeout=60_000)
        if not _choose_sport(page, sport):
            browser.close()
            return [
                _court_without_schedules(
                    sport, periods[0], date.today(), NO_SCHEDULE_WARNING, types
                )
            ]
        address = extract_address(page, sport)

        results = []
        for index, day in enumerate(collection_days(date.today(), days_ahead)):
            try:
                _select_day(page, day)
            except PWTimeout:
                continue
            results.extend(_collect_day(page, sport, day, periods, index == 0, types))

        browser.close()

    return [dict(court, endereco=address) for court in results]
