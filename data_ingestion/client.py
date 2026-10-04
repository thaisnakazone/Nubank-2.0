from __future__ import annotations

import sys
import time
from typing import Any
import requests

from data_ingestion.sanitizer import sanitize_text


class TwelveDataClient:
    """
    Cliente para integração direta com a API Twelve Data.
    Gerencia requisições com rate limiting, sanitização de credenciais e tratamento de erros.
    """

    DEFAULT_BASE_URL = "https://api.twelvedata.com"

    def __init__(
        self,
        api_key: str,
        base_url: str | None = None,
        timeout: int = 30,
        rate_limit_pause: float = 1.0,
    ) -> None:
        self.api_key = api_key.strip() if api_key else ""
        self.base_url = (base_url or self.DEFAULT_BASE_URL).rstrip("/")
        self.timeout = timeout
        self.rate_limit_pause = rate_limit_pause

    def fetch_time_series(
        self,
        ticker: str,
        interval: str = "1day",
        outputsize: int = 30,
    ) -> tuple[list[dict[str, Any]], str]:
        """
        Coleta a série temporal de cotações para o ticker especificado.
        Retorna (lista_de_valores_brutos, mensagem_erro).
        Se bem-sucedido, mensagem_erro será vazia ("").
        """
        if not self.api_key:
            return [], "Chave de API da Twelve Data não configurada."

        url = f"{self.base_url}/time_series"
        params = {
            "symbol": ticker,
            "interval": interval,
            "apikey": self.api_key,
            "outputsize": outputsize,
        }

        try:
            response = requests.get(url, params=params, timeout=self.timeout)
            status_code = response.status_code
            try:
                data = response.json()
            except Exception:
                data = {}
        except requests.RequestException as e:
            return [], f"Falha de conexão com Twelve Data: {type(e).__name__}"

        if status_code != 200 or data.get("status") == "error":
            raw_msg = data.get("message", f"HTTP {status_code}")
            safe_msg = sanitize_text(str(raw_msg), self.api_key)
            return [], f"Erro da API Twelve Data (HTTP {status_code}): {safe_msg}"

        values = data.get("values")
        if not values or not isinstance(values, list):
            return [], f"Nenhum registro retornado para '{ticker}'"

        return values, ""

    def pause(self) -> None:
        """Pausa para respeitar os limites da API (plano gratuito: até 8 req/min)."""
        if self.rate_limit_pause > 0:
            time.sleep(self.rate_limit_pause)
