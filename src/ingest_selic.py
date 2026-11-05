"""
Coleta automática da taxa Selic (meta definida pelo Copom) na API pública do Banco Central.

Fonte: SGS · série 432 — "Taxa de juros - Meta Selic definida pelo Copom" (% ao ano).
API:   https://api.bcb.gov.br/dados/serie/bcdata.sgs.432/dados?formato=json&dataInicial=...&dataFinal=...

A série é diária, mas o valor só muda nas reuniões do Copom (cerca de 8 por ano). Por isso guardamos
apenas os dias em que a taxa mudou, mais o último dia publicado (para saber até quando a taxa vale):
- data/processed/selic.csv            (cópia versionada, usada como plano B)
- MongoDB Atlas · nubank_db.selic_meta (upsert por data; nada é duplicado)

Uso:
    python -m src.ingest_selic
"""
from __future__ import annotations

import sys
from datetime import date, datetime, timezone
from pathlib import Path

import pandas as pd
import requests

ROOT = Path(__file__).resolve().parents[1]
PROCESSED = ROOT / "data" / "processed"
SELIC_CSV = PROCESSED / "selic.csv"
SERIE = 432
DATA_INICIAL = date(2021, 1, 1)  # mesmo início das demais análises do projeto
API_URL = "https://api.bcb.gov.br/dados/serie/bcdata.sgs.{serie}/dados"
COLUMNS = ["data", "selic_meta_pct"]


def parse_valor(value: object) -> float | None:
    """A API devolve texto ("13.75"); aceita também vírgula decimal ("13,75")."""
    if value is None:
        return None
    text = str(value).strip().replace(",", ".")
    if not text:
        return None
    try:
        return float(text)
    except ValueError:
        return None


def parse_data(value: object) -> str | None:
    """Converte dd/mm/aaaa (formato da API) para aaaa-mm-dd."""
    try:
        return datetime.strptime(str(value).strip(), "%d/%m/%Y").date().isoformat()
    except (TypeError, ValueError):
        return None


def clean_series(raw: list[dict]) -> pd.DataFrame:
    """Valida e ordena a série bruta: descarta datas ou valores inválidos e datas repetidas."""
    rows = []
    for item in raw if isinstance(raw, list) else []:
        if not isinstance(item, dict):
            continue
        d, v = parse_data(item.get("data")), parse_valor(item.get("valor"))
        if d is None or v is None or not 0 <= v <= 100:
            continue
        rows.append({"data": d, "selic_meta_pct": v})
    df = pd.DataFrame(rows, columns=COLUMNS)
    return df.drop_duplicates("data", keep="last").sort_values("data").reset_index(drop=True)


def compress_changes(df: pd.DataFrame) -> pd.DataFrame:
    """Mantém só os dias em que a taxa mudou e o último dia publicado."""
    if df.empty:
        return df
    changed = df["selic_meta_pct"].ne(df["selic_meta_pct"].shift())
    keep = changed.copy()
    keep.iloc[-1] = True
    return df[keep].reset_index(drop=True)


def fetch_series(session: requests.Session, inicio: date, fim: date) -> list[dict]:
    params = {
        "formato": "json",
        "dataInicial": inicio.strftime("%d/%m/%Y"),
        "dataFinal": fim.strftime("%d/%m/%Y"),
    }
    resp = session.get(API_URL.format(serie=SERIE), params=params, timeout=60)
    resp.raise_for_status()
    data = resp.json()
    if not isinstance(data, list):
        raise ValueError("resposta inesperada da API do Banco Central")
    return data


def save_to_mongo(df: pd.DataFrame) -> str:
    try:
        from pymongo import UpdateOne
        from database.connection import get_database, get_mongo_client, get_mongo_uri
    except ImportError as exc:  # pragma: no cover
        return f"MongoDB ignorado ({exc})"

    uri = get_mongo_uri()
    if not uri:
        return "MongoDB ignorado (MONGO_URI não configurada)"

    stamp = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    client = None
    try:
        client = get_mongo_client(uri)
        col = get_database(client)["selic_meta"]
        col.create_index("data", unique=True)
        ops = [
            UpdateOne({"data": r["data"]}, {"$set": {**r, "coletado_em": stamp}}, upsert=True)
            for r in df.to_dict(orient="records")
        ]
        # O "último dia publicado" muda a cada coleta: remove o marcador antigo que não é mudança de taxa
        col.delete_many({"data": {"$nin": df["data"].tolist()}})
        if ops:
            col.bulk_write(ops, ordered=False)
        return f"MongoDB: {len(ops)} registros em selic_meta"
    except Exception as exc:  # noqa: BLE001
        return f"MongoDB indisponível ({type(exc).__name__}); dados mantidos no CSV"
    finally:
        if client:
            client.close()


def run(today: date | None = None) -> int:
    today = today or date.today()
    session = requests.Session()
    session.headers["User-Agent"] = "Nubank-2.0 (projeto academico; github.com/thaisnakazone/Nubank-2.0)"
    try:
        raw = fetch_series(session, DATA_INICIAL, today)
    except Exception as exc:  # noqa: BLE001
        print(f"Falha ao consultar a API do Banco Central: {type(exc).__name__}. Selic mantida como estava.", file=sys.stderr)
        return 1

    df = compress_changes(clean_series(raw))
    if df.empty:
        print("A API do Banco Central não retornou valores válidos. Selic mantida como estava.", file=sys.stderr)
        return 1

    PROCESSED.mkdir(parents=True, exist_ok=True)
    df.to_csv(SELIC_CSV, index=False)
    last = df.iloc[-1]
    print(f"Selic: {len(df)} pontos (mudanças do Copom) de {df['data'].iloc[0]} a {last['data']}; atual {last['selic_meta_pct']:.2f}% a.a.")
    print(save_to_mongo(df))
    return 0


def main() -> int:
    if sys.platform == "win32":
        try:
            sys.stdout.reconfigure(encoding="utf-8", errors="replace")
            sys.stderr.reconfigure(encoding="utf-8", errors="replace")
        except Exception:
            pass
    return run()


if __name__ == "__main__":
    sys.exit(main())
