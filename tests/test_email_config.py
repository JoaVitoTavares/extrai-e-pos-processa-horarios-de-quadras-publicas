"""Testes da estrutura de configuração de e-mail, sem envio."""

import os

from extrator import email_config


def test_env_example_lists_the_email_fields():
    text = open(".env.example", encoding="utf-8").read()
    for field in (
        "EMAIL_SMTP_HOST",
        "EMAIL_SMTP_PORT",
        "EMAIL_SMTP_USER",
        "EMAIL_SMTP_PASSWORD",
        "EMAIL_TO",
    ):
        assert field in text


def test_reads_email_settings_from_the_environment(monkeypatch):
    monkeypatch.setenv("EMAIL_SMTP_HOST", "smtp.exemplo.com")
    monkeypatch.setenv("EMAIL_SMTP_PORT", "587")
    monkeypatch.setenv("EMAIL_SMTP_USER", "aviso@exemplo.com")
    monkeypatch.setenv("EMAIL_SMTP_PASSWORD", "segredo")
    monkeypatch.setenv("EMAIL_TO", "destino@exemplo.com")

    settings = email_config.email_settings()

    assert settings == {
        "host": "smtp.exemplo.com",
        "port": 587,
        "user": "aviso@exemplo.com",
        "password": "segredo",
        "recipient": "destino@exemplo.com",
    }


def test_loads_env_file_without_sending(tmp_path, monkeypatch):
    path = tmp_path / ".env"
    path.write_text(
        "EMAIL_SMTP_HOST=smtp.local\nEMAIL_SMTP_PORT=465\n",
        encoding="utf-8",
    )
    monkeypatch.delenv("EMAIL_SMTP_HOST", raising=False)
    monkeypatch.delenv("EMAIL_SMTP_PORT", raising=False)

    email_config.load_dotenv(path)

    assert os.environ["EMAIL_SMTP_HOST"] == "smtp.local"
    assert os.environ["EMAIL_SMTP_PORT"] == "465"


def test_dotenv_preserva_senha_com_igual_e_aspas(tmp_path, monkeypatch):
    path = tmp_path / ".env"
    path.write_text('EMAIL_SMTP_PASSWORD = "ab=cd"\n', encoding="utf-8")
    monkeypatch.delenv("EMAIL_SMTP_PASSWORD", raising=False)

    email_config.load_dotenv(path)

    assert os.environ["EMAIL_SMTP_PASSWORD"] == "ab=cd"
