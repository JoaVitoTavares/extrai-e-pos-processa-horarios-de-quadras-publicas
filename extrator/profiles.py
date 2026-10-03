"""Perfis de acesso com variações de tamanho de tela."""

import random

ACCESS_PROFILES = [
    {
        "system": "windows",
        "viewports": [
            {"width": 1920, "height": 1080},
            {"width": 1366, "height": 768},
            {"width": 1536, "height": 864},
        ],
    },
    {
        "system": "macos",
        "viewports": [
            {"width": 1440, "height": 900},
            {"width": 2560, "height": 1440},
            {"width": 1680, "height": 1050},
        ],
    },
    {
        "system": "linux",
        "viewports": [
            {"width": 1920, "height": 1080},
            {"width": 1366, "height": 768},
            {"width": 1280, "height": 800},
        ],
    },
]


def draw_access_profile(rng=None) -> dict:
    """Sorteia um perfil de acesso e um viewport dentre os tamanhos daquele perfil."""
    generator = rng if rng is not None else random
    profile = generator.choice(ACCESS_PROFILES)
    viewport = generator.choice(profile["viewports"])
    return {"system": profile["system"], "viewport": dict(viewport)}
