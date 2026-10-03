"""Detector da frase de captcha do Google na página da arena."""

CAPTCHA_PHRASE = "não sou um robô"


def captcha_detected(page) -> bool:
    """Indica se a página exibe a frase 'não sou um robô' do captcha do Google."""
    text = page.locator("body").inner_text()
    return CAPTCHA_PHRASE in (text or "").casefold()
