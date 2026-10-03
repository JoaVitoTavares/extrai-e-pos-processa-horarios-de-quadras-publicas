"""Testes da estrutura de perfis de acesso e do sorteio de viewport."""

import random

from extrator import arena_extractor
from extrator import profiles
import main
from test_main import ARENA


def test_each_profile_has_desktop_viewports():
    assert profiles.ACCESS_PROFILES
    for profile in profiles.ACCESS_PROFILES:
        assert profile["viewports"]
        for viewport in profile["viewports"]:
            assert viewport["width"] >= 1280
            assert viewport["height"] >= 720


def test_draw_picks_a_viewport_from_some_profile():
    allowed = {
        (item["width"], item["height"])
        for profile in profiles.ACCESS_PROFILES
        for item in profile["viewports"]
    }
    rng = random.Random(0)
    chosen = {
        (profile["viewport"]["width"], profile["viewport"]["height"])
        for profile in [profiles.draw_access_profile(rng) for _ in range(50)]
    }

    assert chosen <= allowed
    assert len(chosen) >= 2


def test_list_has_between_eight_and_twelve_desktop_chrome_user_agents():
    agents = [ua for profile in profiles.ACCESS_PROFILES for ua in profile["user_agents"]]
    text = " ".join(agents).lower()

    assert 8 <= len(agents) <= 12
    assert len(set(agents)) == len(agents)
    assert all("Chrome/" in ua for ua in agents)
    assert "iphone" not in text
    assert "android" not in text
    assert "mobile" not in text
    assert any("Windows" in ua for ua in agents)
    assert any("Macintosh" in ua for ua in agents)
    assert any("Linux" in ua for ua in agents)


def test_user_agent_only_matches_a_viewport_of_the_same_system():
    rng = random.Random(2)
    for _ in range(80):
        profile = profiles.draw_access_profile(rng)
        source = next(item for item in profiles.ACCESS_PROFILES if item["system"] == profile["system"])
        assert profile["user_agent"] in source["user_agents"]
        assert profile["viewport"] in source["viewports"]
        if profile["system"] == "windows":
            assert "Windows" in profile["user_agent"]
        elif profile["system"] == "macos":
            assert "Macintosh" in profile["user_agent"]
        else:
            assert "Linux" in profile["user_agent"]


def test_arena_check_forwards_the_drawn_viewport(monkeypatch):
    received = {}
    profile = {
        "system": "windows",
        "viewport": {"width": 1366, "height": 768},
        "user_agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/141.0.0.0",
    }
    monkeypatch.setattr(arena_extractor, "draw_access_profile", lambda: profile)
    monkeypatch.setattr(arena_extractor, "list_sports", lambda url: ["Grama 5"])
    monkeypatch.setattr(arena_extractor, "filter_target_sports", lambda sports, types: sports)
    monkeypatch.setattr(arena_extractor, "missing_court_types", lambda targets, types: [])
    monkeypatch.setattr(
        arena_extractor, "collect_schedules",
        lambda sport, arena_url, period=None, headless=True, types=None, **kwargs:
            received.update(kwargs) or [],
    )

    arena_extractor.ArenaExtractor(main.normalize_arena_info(ARENA))._collect_courts()

    assert received["viewport"] == profile["viewport"]
    assert received["user_agent"] == profile["user_agent"]
