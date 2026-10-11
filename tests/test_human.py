"""Testes das falhas humanas simuladas, com uma página dublê."""

import random

from extrator import human


class Target:
    def __init__(self, name, log):
        self.name = name
        self.log = log

    def click(self, **kwargs):
        self.log.append(f"click:{self.name}")

    def hover(self):
        self.log.append(f"hover:{self.name}")


class Mouse:
    def __init__(self, log):
        self.log = log

    def wheel(self, x, y):
        self.log.append(("wheel", x, y))


class FakePage:
    def __init__(self):
        self.log = []
        self.mouse = Mouse(self.log)

    def go_back(self):
        self.log.append("back")


def test_human_failures_draw_the_four_variants(monkeypatch):
    seen = set()
    monkeypatch.setattr(human, "wait_between_clicks", lambda: None)
    for i in range(40):
        page = FakePage()
        intended = Target("right", page.log)
        distractor = Target("wrong", page.log)
        seen.add(
            human.simulate_human_failure(
                page, intended, distractor, rand_num_gen=random.Random(i)
            )
        )
    assert seen == {"wrong_click", "redo", "hover_hesitate", "overscroll"}


def test_wrong_click_goes_back_and_pauses_between_steps(monkeypatch):
    pauses = []
    monkeypatch.setattr(human, "wait_between_clicks", lambda: pauses.append("pause"))
    page = FakePage()
    intended = Target("right", page.log)
    distractor = Target("wrong", page.log)

    kind = human.simulate_human_failure(
        page, intended, distractor, rand_num_gen=_fixed_rand_num_gen("wrong_click")
    )

    assert kind == "wrong_click"
    assert page.log == ["click:wrong", "back"]
    assert len(pauses) >= 2


def test_redo_goes_back_and_repeats_the_target(monkeypatch):
    monkeypatch.setattr(human, "wait_between_clicks", lambda: None)
    page = FakePage()
    intended = Target("right", page.log)

    kind = human.simulate_human_failure(
        page, intended, rand_num_gen=_fixed_rand_num_gen("redo")
    )

    assert kind == "redo"
    assert page.log == ["back", "click:right"]


def test_hesitates_on_the_target_without_clicking(monkeypatch):
    monkeypatch.setattr(human, "wait_between_clicks", lambda: None)
    page = FakePage()
    intended = Target("right", page.log)

    kind = human.simulate_human_failure(
        page, intended, rand_num_gen=_fixed_rand_num_gen("hover_hesitate")
    )

    assert kind == "hover_hesitate"
    assert page.log == ["hover:right"]
    assert "click:right" not in page.log


def test_wrong_click_without_a_distractor_only_goes_back(monkeypatch):
    monkeypatch.setattr(human, "wait_between_clicks", lambda: None)
    page = FakePage()

    kind = human.simulate_human_failure(
        page,
        intended=Target("right", page.log),
        rand_num_gen=_fixed_rand_num_gen("wrong_click"),
    )

    assert kind == "wrong_click"
    assert page.log == ["back"]


def test_scrolls_past_and_returns(monkeypatch):
    monkeypatch.setattr(human, "wait_between_clicks", lambda: None)
    page = FakePage()

    kind = human.simulate_human_failure(page, rand_num_gen=_fixed_rand_num_gen("overscroll"))

    assert kind == "overscroll"
    assert page.log[0][0] == "wheel"
    assert page.log[0][2] > 0
    assert page.log[1][0] == "wheel"
    assert page.log[1][2] < 0


class _fixed_rand_num_gen:
    def __init__(self, chosen):
        self.chosen = chosen

    def choice(self, options):
        return self.chosen
