from __future__ import annotations

from datetime import datetime
from typing import Any
import pandas as pd


def validate_record(raw_record: dict[str, Any], ticker: str) -> tuple[dict[str, Any] | None, str]:
    """
    Valida os campos obrigatórios da cotação.
    Regras:
    - Data válida e no formato YYYY-MM-DD (preservada como string).
    - Preços OHLC obrigatórios, numéricos e positivos.
    - Máxima (high) não pode ser inferior à mínima (low).
    - Volume obrigatório, numérico e não negativo.

    Retorna (dicionário_validado, "") se válido ou (None, motivo) se inválido.
    """
    if not isinstance(raw_record, dict):
        return None, "registro não é um dicionário"

    ticker_clean = str(ticker).strip() if ticker else ""
    if not ticker_clean:
        return None, "ticker ausente ou vazio"

    # 1. Validação de datetime (deve ser string YYYY-MM-DD válida)
    dt_str = raw_record.get("datetime")
    if not dt_str or not isinstance(dt_str, str):
        return None, "campo 'datetime' ausente ou inválido"
    dt_str = dt_str.strip()
    try:
        parsed_dt = datetime.strptime(dt_str, "%Y-%m-%d")
        if parsed_dt.year < 1900 or parsed_dt.year > 2100:
            return None, f"ano fora da faixa aceitável: {parsed_dt.year}"
    except (ValueError, TypeError):
        return None, f"campo 'datetime' não segue o padrão YYYY-MM-DD ou data inexistente: '{dt_str}'"

    # 2. Validação dos preços OHLC
    prices: dict[str, float] = {}
    for field in ("open", "high", "low", "close"):
        val = raw_record.get(field)
        if val is None or pd.isna(val) or str(val).strip() == "":
            return None, f"preço '{field}' ausente"
        try:
            num = float(val)
        except (ValueError, TypeError):
            return None, f"preço '{field}' não numérico: {val}"
        if num < 0:
            return None, f"preço '{field}' negativo: {num}"
        prices[field] = num

    # 3. Consistência: máxima não pode ser menor que a mínima
    if prices["high"] < prices["low"]:
        return (
            None,
            f"máxima ({prices['high']}) inferior à mínima ({prices['low']})",
        )

    # 4. Validação do volume
    vol_val = raw_record.get("volume")
    if vol_val is None or pd.isna(vol_val) or str(vol_val).strip() == "":
        return None, "volume ausente"
    try:
        vol_num = float(vol_val)
    except (ValueError, TypeError):
        return None, f"volume não numérico: {vol_val}"
    if vol_num < 0:
        return None, f"volume negativo: {vol_num}"

    valid_doc = {
        "ticker": ticker_clean,
        "datetime": dt_str,
        "open": prices["open"],
        "high": prices["high"],
        "low": prices["low"],
        "close": prices["close"],
        "volume": vol_num,
    }
    return valid_doc, ""
