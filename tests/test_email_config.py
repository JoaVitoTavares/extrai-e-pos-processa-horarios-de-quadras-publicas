"""Testes da estrutura de configuração de e-mail, sem envio."""

import os

from extrator import email_config


def test_env_example_lista_os_campos_de_email():
    texto = open(".env.example", encoding="utf-8").read()
    for campo in (
        "EMAIL_SMTP_HOST",
        "EMAIL_SMTP_PORT",
        "EMAIL_SMTP_USER",
        "EMAIL_SMTP_PASSWORD",
        "EMAIL_TO",
    ):
        assert campo in texto


def test_le_configuracao_de_email_do_ambiente(monkeypatch):
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


def test_carrega_arquivo_env_sem_enviar(tmp_path, monkeypatch):
    caminho = tmp_path / ".env"
    caminho.write_text(
        "EMAIL_SMTP_HOST=smtp.local\nEMAIL_SMTP_PORT=465\n",
        encoding="utf-8",
    )
    monkeypatch.delenv("EMAIL_SMTP_HOST", raising=False)
    monkeypatch.delenv("EMAIL_SMTP_PORT", raising=False)

    email_config.load_dotenv(caminho)

    assert os.environ["EMAIL_SMTP_HOST"] == "smtp.local"
    assert os.environ["EMAIL_SMTP_PORT"] == "465"
