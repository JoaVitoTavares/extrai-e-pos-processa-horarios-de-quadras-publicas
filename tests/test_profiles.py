"""Testes da estrutura de perfis de acesso e do sorteio de viewport."""

import random

from extrator import arena_extractor
from extrator import profiles
import main
from test_main import ARENA


def test_cada_perfil_tem_viewports_de_desktop():
    assert profiles.ACCESS_PROFILES
    for profile in profiles.ACCESS_PROFILES:
        assert profile["viewports"]
        for viewport in profile["viewports"]:
            assert viewport["width"] >= 1280
            assert viewport["height"] >= 720


def test_sorteio_escolhe_viewport_de_algum_perfil():
    permitidos = {
        (item["width"], item["height"])
        for profile in profiles.ACCESS_PROFILES
        for item in profile["viewports"]
    }
    rng = random.Random(0)
    escolhidos = {
        (perfil["viewport"]["width"], perfil["viewport"]["height"])
        for perfil in [profiles.draw_access_profile(rng) for _ in range(50)]
    }

    assert escolhidos <= permitidos
    assert len(escolhidos) >= 2


def test_verificacao_da_arena_repassa_o_viewport_sorteado(monkeypatch):
    recebido = {}
    perfil = {"system": "windows", "viewport": {"width": 1366, "height": 768}}
    monkeypatch.setattr(arena_extractor, "draw_access_profile", lambda: perfil)
    monkeypatch.setattr(arena_extractor, "list_sports", lambda url: ["Grama 5"])
    monkeypatch.setattr(arena_extractor, "filter_target_sports", lambda sports, types: sports)
    monkeypatch.setattr(arena_extractor, "missing_court_types", lambda targets, types: [])
    monkeypatch.setattr(
        arena_extractor, "collect_schedules",
        lambda sport, arena_url, period=None, headless=True, types=None, **kwargs:
            recebido.update(kwargs) or [],
    )

    arena_extractor.ArenaExtractor(main.normalize_arena_info(ARENA))._collect_courts()

    assert recebido["viewport"] == perfil["viewport"]
