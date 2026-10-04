"""Testes do proxy, da janela de dias e do stealth na abertura do navegador."""

from datetime import date

import pytest

from extrator import courts_collector
import main


@pytest.mark.parametrize(
    "proxy, expected",
    [
        (None, None),
        ("", None),
        ("http://proxy.local:8080", {"server": "http://proxy.local:8080"}),
        ("socks5://proxy.local", {"server": "socks5://proxy.local"}),
        ("//10.0.0.1:8888", {"server": "http://10.0.0.1:8888"}),
        (
            "http://user:p%40ss@proxy.local:8080",
            {
                "server": "http://proxy.local:8080",
                "username": "user",
                "password": "p@ss",
            },
        ),
    ],
)
def test_proxy_url_becomes_playwright_settings(proxy, expected):
    assert courts_collector.proxy_launch_settings(proxy) == expected


@pytest.mark.parametrize("proxy", ["apenas-texto", "http://"])
def test_proxy_without_a_host_is_rejected(proxy):
    with pytest.raises(ValueError, match="proxy inválido"):
        courts_collector.proxy_launch_settings(proxy)


def test_invalid_proxy_from_the_environment_stops_the_run(monkeypatch, capsys):
    monkeypatch.setenv("ARENA_PROXY", "sem-host")

    with pytest.raises(SystemExit) as exit_info:
        main.parse_arguments([])

    assert exit_info.value.code == 2
    assert "proxy inválido" in capsys.readouterr().err


def test_explicit_proxy_overrides_the_environment(monkeypatch):
    monkeypatch.setenv("ARENA_PROXY", "http://10.0.0.8:8888")

    arguments = main.parse_arguments(["--proxy", "http://outro.local:9"])

    assert arguments.proxy == "http://outro.local:9"


def test_negative_start_day_is_rejected(capsys):
    with pytest.raises(SystemExit) as exit_info:
        main.parse_arguments(["--de", "-1"])

    assert exit_info.value.code == 2
    assert "--de" in capsys.readouterr().err


def test_end_day_before_start_day_is_rejected(capsys):
    with pytest.raises(SystemExit) as exit_info:
        main.parse_arguments(["--de", "4", "--ate", "1"])

    assert exit_info.value.code == 2
    assert "--ate" in capsys.readouterr().err


def test_day_window_includes_both_ends():
    today = date(2026, 10, 4)

    assert courts_collector.collection_days(today, days_ahead=0, days_from=0) == [today]
    assert courts_collector.collection_days(today, days_ahead=2, days_from=1) == [
        date(2026, 10, 5),
        date(2026, 10, 6),
    ]


class _Browser:
    def __init__(self, launches, order):
        self.launches = launches
        self.order = order

    def launch(self, **kwargs):
        self.launches.append(kwargs)
        return self

    def new_context(self, **kwargs):
        return self

    def new_page(self):
        return self

    def goto(self, *args, **kwargs):
        self.order.append("goto")

    def close(self):
        return None


class _Playwright:
    def __init__(self, launches, order):
        self.browser = _Browser(launches, order)

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False

    @property
    def chromium(self):
        return self.browser


def _collect(monkeypatch, available, enabled):
    launches = []
    order = []
    monkeypatch.setattr(courts_collector, "STEALTH_AVAILABLE", available)
    monkeypatch.setattr(courts_collector, "stealth_sync", lambda page: order.append("stealth"))
    monkeypatch.setattr(courts_collector, "captcha_detected", lambda page: False)
    monkeypatch.setattr(courts_collector, "_choose_sport", lambda *args, **kwargs: False)
    monkeypatch.setattr(
        courts_collector, "sync_playwright", lambda: _Playwright(launches, order)
    )

    courts_collector.collect_schedules(
        "Grama 5",
        "https://webarena.app/arena/x",
        proxy="http://user:p%40ss@proxy.local:8080",
        use_stealth=enabled,
    )
    return launches, order


@pytest.mark.parametrize(
    "available, enabled, expect_stealth",
    [(True, True, True), (True, False, False), (False, True, False)],
)
def test_stealth_runs_only_when_requested_and_installed(
    monkeypatch, available, enabled, expect_stealth
):
    launches, order = _collect(monkeypatch, available, enabled)

    assert launches[0]["proxy"] == {
        "server": "http://proxy.local:8080",
        "username": "user",
        "password": "p@ss",
    }
    assert ("stealth" in order) is expect_stealth
    assert order[-1] == "goto"
    if expect_stealth:
        assert order.index("stealth") < order.index("goto")
