"""Coletor de horários de quadras das arenas do webarena.app."""

import re
import time
import requests
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from urllib.parse import unquote, urljoin, urlsplit
from playwright.sync_api import sync_playwright, TimeoutError as PWTimeout

# Stealth (pip install playwright-stealth)
try:
    from playwright_stealth import stealth_sync
    STEALTH_AVAILABLE = True
except ImportError:
    STEALTH_AVAILABLE = False

from extrator.config import (
    API_INIT_PATH,
    DAYS_AHEAD,
    DEFAULT_PERIODS,
    NAVIGATION_TIMEOUT_MS,
    COURT_TYPES,
)
from extrator.debug import debug
from extrator.persistencia import sem_acento
from extrator.timing import wait_between_accesses, wait_between_clicks
from extrator.human import simulate_human_failure
from extrator.captcha import captcha_detected
from extrator.email_config import send_alert
from extrator.pause import CaptchaPause, engage_captcha_pause, is_paused


def click_with_pause(target, **kwargs):
    """Espera o intervalo curto entre cliques e então dispara o clique no alvo."""
    wait_between_clicks()
    return target.click(**kwargs)

# ---------------------------------------------------------------------------
# Constantes de stealth / fingerprint
# ---------------------------------------------------------------------------
DEFAULT_USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/129.0.0.0 Safari/537.36"
)

LAUNCH_ARGS = [
    "--disable-blink-features=AutomationControlled",
    "--no-sandbox",
    "--disable-dev-shm-usage",
    "--disable-infobars",
    "--window-size=1920,1080",
    "--disable-extensions",
]

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


def _canonical(sport: str) -> str:
    cleaned = sem_acento(sport).casefold().strip()
    return "futebol de salao" if FUTSAL_PATTERN.search(cleaned) else cleaned


@dataclass(frozen=True)
class Court:
    name: str | None
    sport: str
    types: list[str]

    @property
    def court_type(self) -> str:
        for court_type in self.types:
            if _canonical(self.sport) == _canonical(court_type):
                return court_type
        if self.name and FUTSAL_PATTERN.search(sem_acento(self.name)):
            return "Futebol de salão"
        return self.sport

    @property
    def covered(self) -> str:
        if not self.name:
            return ""
        cleaned = sem_acento(self.name)
        if UNCOVERED_PATTERN.search(cleaned):
            return "false"
        if COVERED_PATTERN.search(cleaned):
            return "true"
        return ""

    def record(
        self, period: str, day: date, schedules: list[dict], warning: str | None
    ) -> dict:
        return {
            "coletado_em": datetime.now().isoformat(timespec="seconds"),
            "data": day.isoformat(),
            "esporte": self.sport,
            "periodo": period,
            "quadra": self.name,
            "tipo_quadra": self.court_type,
            "quadra_coberta": self.covered,
            "aviso": warning,
            "horarios": schedules,
        }


def api_init_url(arena_url: str) -> str:
    return urljoin(arena_url, API_INIT_PATH)


def list_sports(arena_url: str) -> list[str]:
    wait_between_accesses()
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


def extract_address(page, sport: str, timeout_ms: int = NAVIGATION_TIMEOUT_MS) -> str:
    try:
        page.locator(DATE_FIELD_SELECTOR).first.wait_for(state="visible", timeout=timeout_ms)
    except PWTimeout:
        return ""
    return page.evaluate(ADDRESS_SCRIPT, sport) or ""


def filter_target_sports(site_sports: list[str], types: list[str] = COURT_TYPES) -> list[str]:
    wanted = {_canonical(court_type) for court_type in types}
    return [name for name in site_sports if _canonical(name) in wanted]


def missing_court_types(targets: list[str], types: list[str] = COURT_TYPES) -> list[str]:
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


def _choose_sport(page, sport: str, timeout_ms: int = NAVIGATION_TIMEOUT_MS) -> bool:
    if _arena_state(page, sport, timeout_ms) == "escolher":
        click_with_pause(page.get_by_text(sport, exact=True).locator("visible=true").first)
    return _arena_state(page, "", timeout_ms) == "agenda"


def collection_days(today: date, days_ahead: int = DAYS_AHEAD, days_from: int = 0) -> list[date]:
    return [today + timedelta(days=n) for n in range(days_from, days_ahead + 1)]


def _try_day(page, label: str, timeout_ms: int) -> bool:
    click_with_pause(page.locator(".picker__input").first, timeout=timeout_ms)
    page.locator(".picker--opened").first.wait_for(state="attached", timeout=timeout_ms)

    cell = page.locator(f".picker__day[aria-label^='{label}']:not(.picker__day--disabled)")
    try:
        cell.first.wait_for(state="visible", timeout=CALENDAR_WAIT_MS)
    except PWTimeout:
        click_with_pause(page.locator(".picker__nav--next").first)
        try:
            cell.first.wait_for(state="visible", timeout=CALENDAR_WAIT_MS)
        except PWTimeout:
            return False
    page.wait_for_timeout(GRID_REPAINT_WAIT_MS)
    click_with_pause(cell.first)

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
    page, day: date, timeout_ms: int = NAVIGATION_TIMEOUT_MS, attempts: int = 3
) -> None:
    label = day.strftime(CALENDAR_DAY_FORMAT)
    for attempt in range(1, attempts + 1):
        if _try_day(page, label, timeout_ms) and _schedules_on_screen(page):
            debug(f"dia {label} fixado na tentativa {attempt}")
            return
        debug(f"dia {label}: tentativa {attempt} de {attempts} falhou")
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
    click_with_pause(page.get_by_text(period, exact=True).first)
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
            debug(f"quadras prontas na tela: {len(counts)} bloco(s), horarios {counts}")
            return
        if time.monotonic() >= deadline:
            debug(f"espera por quadras esgotou {timeout_ms}ms; blocos {counts}")
            return
        page.wait_for_timeout(interval_ms)


def _extract_courts(
    page, sport: str, period: str, day: date, types: list[str] = COURT_TYPES
) -> list[dict]:
    courts = []
    for root in page.locator(COURTS_SELECTOR).all():
        text = root.inner_text()
        name = text.strip().splitlines()[0].strip()
        schedules = [
            {"hora": hour, "status": status.capitalize()}
            for hour, status in SCHEDULE_PATTERN.findall(text)
        ]
        record = Court(name, sport, types).record(period, day, schedules, None)
        courts.append(dict(record, raiz=root))
    if courts:
        return courts
    empty = Court(None, sport, types).record(period, day, [], EMPTY_PERIOD_WARNING)
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
            click_with_pause(header, timeout=3_000)
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
        debug(f"{day.isoformat()} / {current_period}: selecionando periodo")
        try:
            _select_period(page, current_period, previous_text)
        except PWTimeout:
            debug(f"{day.isoformat()} / {current_period}: periodo nao respondeu, pulando")
            previous_text = page.locator("body").inner_text()
            continue
        _wait_for_courts(page)
        for court in _extract_courts(page, sport, current_period, day, types):
            root = court.pop("raiz")
            if with_price:
                _collect_prices(root, court["horarios"])
            debug(f"{day.isoformat()} / {current_period}: quadra '{court['quadra'] or '-'}' "
                  f"com {len(court['horarios'])} horario(s)"
                  f"{' aviso=' + court['aviso'] if court['aviso'] else ''}")
            collected.append(court)
        previous_text = page.locator("body").inner_text()
    return collected


def proxy_launch_settings(proxy: str | None) -> dict | None:
    """Converte uma URL de proxy (`http://usuario:senha@host:porta`) no dicionário que o
    Playwright espera em `chromium.launch(proxy=...)`. Retorna None quando não há proxy."""
    if not proxy:
        return None
    parts = urlsplit(proxy)
    if not parts.hostname:
        raise ValueError(f"proxy inválido: {proxy}")
    port = f":{parts.port}" if parts.port else ""
    settings = {"server": f"{parts.scheme or 'http'}://{parts.hostname}{port}"}
    if parts.username:
        settings["username"] = unquote(parts.username)
        settings["password"] = unquote(parts.password or "")
    return settings


def collect_schedules(
    sport: str,
    arena_url: str,
    period: str | None = None,
    headless: bool = True,
    days_ahead: int = DAYS_AHEAD,
    days_from: int = 0,
    types: list[str] = COURT_TYPES,
    proxy: str | None = None,
    # Novos parâmetros anti-bot
    use_stealth: bool = True,
    slow_mo: int = 50,
    user_agent: str | None = None,
    viewport: dict | None = None,
) -> list[dict]:
    """
    Coleta horários com proteção anti-bot (stealth + fingerprint).

    Args:
        use_stealth: aplica playwright-stealth (recomendado True)
        slow_mo: atraso em ms entre ações do Playwright (ajuda a parecer humano)
        user_agent: sobrescreve o User-Agent padrão
    """
    if is_paused():
        raise CaptchaPause("coleta pausada por captcha")
    periods = [period] if period else DEFAULT_PERIODS
    proxy_settings = proxy_launch_settings(proxy)
    ua = user_agent or DEFAULT_USER_AGENT
    screen = viewport or {"width": 1920, "height": 1080}
    wait_between_accesses()

    with sync_playwright() as p:
        debug(
            f"'{sport}': abrindo navegador (headless={headless}, "
            f"stealth={use_stealth and STEALTH_AVAILABLE}, "
            f"proxy={proxy_settings['server'] if proxy_settings else 'nenhum'})"
        )

        browser = p.chromium.launch(
            headless=headless,
            slow_mo=slow_mo,
            args=LAUNCH_ARGS,
            proxy=proxy_settings,
        )

        # Context com fingerprint mais realista
        context = browser.new_context(
            user_agent=ua,
            viewport=screen,
            locale="pt-BR",
            timezone_id="America/Sao_Paulo",
            # color_scheme="light",
        )

        page = context.new_page()

        # Aplica stealth (se disponível e solicitado)
        if use_stealth and STEALTH_AVAILABLE:
            stealth_sync(page)
            debug(f"'{sport}': stealth aplicado")
        elif use_stealth and not STEALTH_AVAILABLE:
            debug(
                f"'{sport}': playwright-stealth não instalado "
                "(pip install playwright-stealth) — continuando sem stealth"
            )

        try:
            page.goto(arena_url, wait_until="networkidle", timeout=60_000)
            if captcha_detected(page):
                send_alert(
                    "Captcha detectado na extração",
                    f"A frase 'não sou um robô' apareceu em {arena_url} ({sport}).",
                )
                engage_captcha_pause()
                raise CaptchaPause("captcha detectado")
            debug(f"'{sport}': pagina carregada, escolhendo esporte")

            if not _choose_sport(page, sport):
                debug(f"'{sport}': arena sem agenda na web, encerrando")
                return [
                    Court(None, sport, types).record(
                        periods[0], date.today(), [], NO_SCHEDULE_WARNING
                    )
                ]
            simulate_human_failure(page, intended=page.locator("body"))

            address = extract_address(page, sport)
            debug(f"'{sport}': endereco lido: {address or '(vazio)'}")

            today = date.today()
            days = collection_days(today, days_ahead, days_from)
            results = []

            for index, day in enumerate(days):
                if is_paused():
                    raise CaptchaPause("coleta pausada por captcha")
                debug(f"'{sport}': dia {index + 1}/{len(days)} ({day.isoformat()})")
                try:
                    _select_day(page, day)
                except PWTimeout as error:
                    debug(f"'{sport}': dia {day.isoformat()} pulado: {error}")
                    continue
                results.extend(
                    _collect_day(page, sport, day, periods, day == today, types)
                )

            debug(f"'{sport}': fechando navegador com {len(results)} registro(s)")
            return [dict(court, endereco=address) for court in results]

        finally:
            context.close()
            browser.close()