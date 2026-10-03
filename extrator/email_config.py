"""Leitura da configuração de e-mail. O envio em si ainda não é feito aqui."""

import os

EMAIL_HOST_VAR = "EMAIL_SMTP_HOST"
EMAIL_PORT_VAR = "EMAIL_SMTP_PORT"
EMAIL_USER_VAR = "EMAIL_SMTP_USER"
EMAIL_PASSWORD_VAR = "EMAIL_SMTP_PASSWORD"
EMAIL_TO_VAR = "EMAIL_TO"


def load_dotenv(path: str | os.PathLike = ".env") -> None:
    """Lê um arquivo .env e preenche variáveis ainda ausentes no ambiente."""
    if not os.path.isfile(path):
        return
    with open(path, encoding="utf-8") as arquivo:
        for line in arquivo:
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
