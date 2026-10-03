"""Perfis de acesso com viewport e User-Agent coerentes por sistema."""

import random

ACCESS_PROFILES = [
    {
        "system": "windows",
        "viewports": [
            {"width": 1920, "height": 1080},
            {"width": 1366, "height": 768},
            {"width": 1536, "height": 864},
        ],
        "user_agents": [
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/141.0.7390.76 Safari/537.36",
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/140.0.7339.186 Safari/537.36",
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/139.0.7258.154 Safari/537.36",
            "Mozilla/5.0 (Windows NT 10.0; WOW64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/141.0.7390.76 Safari/537.36",
        ],
    },
    {
        "system": "macos",
        "viewports": [
            {"width": 1440, "height": 900},
            {"width": 2560, "height": 1440},
            {"width": 1680, "height": 1050},
        ],
        "user_agents": [
            "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/141.0.7390.76 Safari/537.36",
            "Mozilla/5.0 (Macintosh; Intel Mac OS X 14_6_1) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/140.0.7339.186 Safari/537.36",
            "Mozilla/5.0 (Macintosh; Intel Mac OS X 13_6_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/141.0.7390.65 Safari/537.36",
            "Mozilla/5.0 (Macintosh; Intel Mac OS X 15_0) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/139.0.7258.154 Safari/537.36",
        ],
    },
    {
        "system": "linux",
        "viewports": [
            {"width": 1920, "height": 1080},
            {"width": 1366, "height": 768},
            {"width": 1280, "height": 800},
        ],
        "user_agents": [
            "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/141.0.7390.76 Safari/537.36",
            "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/140.0.7339.186 Safari/537.36",
            "Mozilla/5.0 (X11; Ubuntu; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/141.0.7390.76 Safari/537.36",
        ],
    },
]


def draw_access_profile(rng=None) -> dict:
    """Sorteia um perfil coerente: User-Agent e viewport do mesmo sistema."""
    generator = rng if rng is not None else random
    profile = generator.choice(ACCESS_PROFILES)
    viewport = generator.choice(profile["viewports"])
    user_agent = generator.choice(profile["user_agents"])
    return {
        "system": profile["system"],
        "viewport": dict(viewport),
        "user_agent": user_agent,
    }
