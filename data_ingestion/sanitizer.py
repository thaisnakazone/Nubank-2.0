from __future__ import annotations

import re


def sanitize_text(text: str, secret: str | None = None) -> str:
    """
    Higieniza textos de log e exceções para evitar vazamento de credenciais.
    Mascara chaves de API, senhas e URLs completas.
    """
    if not text:
        return ""
    sanitized = str(text)
    if secret and len(secret) > 3:
        sanitized = sanitized.replace(secret, "***REDACTED***")
    # Mascara padrões comuns de apikey em URLs ou mensagens
    sanitized = re.sub(r"apikey=[^&\s'\"]+", "apikey=***REDACTED***", sanitized, flags=re.IGNORECASE)
    # Mascara credenciais em URIs do MongoDB
    sanitized = re.sub(
        r"mongodb(?:\+srv)?://[^@\s'\"]+@",
        "mongodb://***REDACTED***@",
        sanitized,
        flags=re.IGNORECASE,
    )
    return sanitized
