"""Leitura da configuração de e-mail e envio de avisos de falha."""

import os
import smtplib
from email.message import EmailMessage

EMAIL_HOST_VAR = "EMAIL_SMTP_HOST"
EMAIL_PORT_VAR = "EMAIL_SMTP_PORT"
EMAIL_USER_VAR = "EMAIL_SMTP_USER"
EMAIL_PASSWORD_VAR = "EMAIL_SMTP_PASSWORD"
EMAIL_TO_VAR = "EMAIL_TO"


def load_dotenv(path: str | os.PathLike = ".env") -> None:
    """Lê um arquivo .env e preenche variáveis ainda ausentes no ambiente."""
    if not os.path.isfile(path):
        return
    with open(path, encoding="utf-8") as env_file:
        for line in env_file:
            stripped = line.strip()
            if not stripped or stripped.startswith("#") or "=" not in stripped:
                continue
            key, _, value = stripped.partition("=")
            os.environ.setdefault(key.strip(), value.strip().strip('"').strip("'"))


def email_settings(environ=None) -> dict:
    """Devolve servidor, porta, usuário, senha e destinatário lidos do ambiente."""
    env = environ if environ is not None else os.environ
    port = env.get(EMAIL_PORT_VAR, "")
    return {
        "host": env.get(EMAIL_HOST_VAR, ""),
        "port": int(port) if str(port).isdigit() else port,
        "user": env.get(EMAIL_USER_VAR, ""),
        "password": env.get(EMAIL_PASSWORD_VAR, ""),
        "recipient": env.get(EMAIL_TO_VAR, ""),
    }


def send_alert(subject: str, body: str, settings: dict | None = None) -> None:
    """Envia um e-mail de aviso para uma falha. Sem servidor, destinatário ou porta
    válida, ou com o SMTP fora do ar, não faz nada e não interrompe a extração."""
    cfg = settings if settings is not None else email_settings()
    if not cfg["host"] or not cfg["recipient"]:
        return
    message = EmailMessage()
    message["From"] = cfg["user"] or cfg["recipient"]
    message["To"] = cfg["recipient"]
    message["Subject"] = subject
    message.set_content(body)
    port = cfg["port"] or 587
    try:
        smtp_port = int(port)
    except ValueError:
        return
    try:
        with smtplib.SMTP(cfg["host"], smtp_port) as smtp:
            smtp.starttls()
            if cfg["user"]:
                smtp.login(cfg["user"], cfg["password"] or "")
            smtp.send_message(message)
    except OSError:
        return
