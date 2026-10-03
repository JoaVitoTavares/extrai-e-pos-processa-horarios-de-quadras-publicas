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


def test_lista_tem_entre_oito_e_doze_user_agents_de_chrome_desktop():
    agentes = [ua for profile in profiles.ACCESS_PROFILES for ua in profile["user_agents"]]
    texto = " ".join(agentes).lower()

    assert 8 <= len(agentes) <= 12
    assert len(set(agentes)) == len(agentes)
    assert all("Chrome/" in ua for ua in agentes)
    assert "iphone" not in texto
    assert "android" not in texto
    assert "mobile" not in texto
    assert any("Windows" in ua for ua in agentes)
    assert any("Macintosh" in ua for ua in agentes)
    assert any("Linux" in ua for ua in agentes)


def test_user_agent_so_combina_com_viewport_do_mesmo_sistema():
    rng = random.Random(2)
    for _ in range(80):
        perfil = profiles.draw_access_profile(rng)
        origem = next(item for item in profiles.ACCESS_PROFILES if item["system"] == perfil["system"])
        assert perfil["user_agent"] in origem["user_agents"]
        assert perfil["viewport"] in origem["viewports"]
        if perfil["system"] == "windows":
            assert "Windows" in perfil["user_agent"]
        elif perfil["system"] == "macos":
            assert "Macintosh" in perfil["user_agent"]
        else:
            assert "Linux" in perfil["user_agent"]


def test_verificacao_da_arena_repassa_o_viewport_sorteado(monkeypatch):
    recebido = {}
    perfil = {
        "system": "windows",
        "viewport": {"width": 1366, "height": 768},
        "user_agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/141.0.0.0",
    }
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
    assert recebido["user_agent"] == perfil["user_agent"]
