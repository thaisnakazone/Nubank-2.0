from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

import pandas as pd
from dotenv import load_dotenv

from src.data_pipeline import (
    customer_summary,
    load_capital_risk_history,
    load_customer_sample,
    load_financial_history,
)

ROOT = Path(__file__).resolve().parents[1]
OUTPUT = ROOT / "docs" / "data" / "dashboard-data.json"


def clean_value(value: Any) -> Any:
    if pd.isna(value):
        return None
    if isinstance(value, pd.Timestamp):
        return value.strftime("%Y-%m-%d")
    if hasattr(value, "item"):
        return value.item()
    return value


def records(df: pd.DataFrame) -> list[dict[str, Any]]:
    return [
        {key: clean_value(value) for key, value in row.items()}
        for row in df.to_dict(orient="records")
    ]


def fetch_market_quotes_from_mongo() -> tuple[list[dict[str, Any]], str]:
    """
    Tenta carregar as cotações mais recentes da Twelve Data salvas no MongoDB Atlas.
    Retorna (cotações, fonte_descrição).
    """
    env_path = ROOT / ".env"
    if env_path.exists():
        load_dotenv(dotenv_path=env_path)
    else:
        load_dotenv()

    mongo_uri = os.getenv("MONGO_URI")
    if not mongo_uri:
        return _fallback_market_quotes(), "Twelve Data · Demonstração (MongoDB Atlas offline/sem credenciais)"

    client = None
    try:
        from pymongo import MongoClient
        client = MongoClient(mongo_uri, serverSelectionTimeoutMS=3000)
        client.admin.command("ping")
        db = client["nubank_db"]
        col = db["historico_diario"]

        docs = list(col.find({}, {"_id": 0}).sort("datetime", 1))
        if docs:
            # Formata para JSON serializável
            formatted = []
            for doc in docs:
                item = {k: clean_value(v) for k, v in doc.items() if k != "collected_at"}
                formatted.append(item)
            return formatted, "Twelve Data API via MongoDB Atlas (atualização automatizada)"
    except Exception:
        pass
    finally:
        if client:
            client.close()

    return _fallback_market_quotes(), "Twelve Data · Demonstração (falha ao ler o MongoDB Atlas)"


def _fallback_market_quotes() -> list[dict[str, Any]]:
    """Gera dados demonstrativos de mercado para garantir funcionamento contínuo do build estático."""
    dates = pd.date_range(end=pd.Timestamp.now(), periods=30, freq="B")
    items = []
    base_prices = {"NU": 13.50, "ITUB": 6.80, "BBD": 2.50}
    for ticker, base in base_prices.items():
        for i, dt in enumerate(dates):
            items.append({
                "ticker": ticker,
                "datetime": dt.strftime("%Y-%m-%d"),
                "open": round(base * (1 + (i % 7 - 3) * 0.012), 2),
                "high": round(base * (1 + (i % 7 - 1) * 0.018), 2),
                "low": round(base * (1 + (i % 7 - 4) * 0.015), 2),
                "close": round(base * (1 + (i % 7 - 2) * 0.013), 2),
                "volume": 1_200_000 + (i * 25_000),
                "source": "Twelve Data (demonstração)",
            })
    return items


def load_bcb_complaints() -> dict[str, Any]:
    """
    Ranking de Reclamações do Banco Central (NU, ITUB, BBD).
    Lê do MongoDB Atlas quando disponível; caso contrário usa os CSVs processados
    gerados por src/ingest_bcb_ranking.py.
    """
    ranking: list[dict[str, Any]] = []
    irreg: list[dict[str, Any]] = []
    source = "Banco Central do Brasil · Ranking de Reclamações"

    mongo_uri = os.getenv("MONGO_URI")
    if mongo_uri:
        client = None
        try:
            from pymongo import MongoClient
            client = MongoClient(mongo_uri, serverSelectionTimeoutMS=3000)
            db = client["nubank_db"]
            ranking = [
                {k: clean_value(v) for k, v in d.items() if k != "coletado_em"}
                for d in db["ranking_reclamacoes_bcb"].find({}, {"_id": 0}).sort("periodo", 1)
            ]
            irreg = [
                {k: clean_value(v) for k, v in d.items() if k != "coletado_em"}
                for d in db["irregularidades_bcb"].find({}, {"_id": 0}).sort("periodo", 1)
            ]
            if ranking:
                source += " · via MongoDB Atlas"
        except Exception:
            ranking, irreg = [], []
        finally:
            if client:
                client.close()

    processed = ROOT / "data" / "processed"
    if not ranking and (processed / "bcb_ranking.csv").exists():
        ranking = records(pd.read_csv(processed / "bcb_ranking.csv"))
    if not irreg and (processed / "bcb_irregularidades.csv").exists():
        irreg = records(pd.read_csv(processed / "bcb_irregularidades.csv"))

    return {"ranking": ranking, "irregularidades": irreg, "source": source}


def build_payload() -> dict[str, Any]:
    financial = load_financial_history()
    risk, risk_source = load_capital_risk_history()
    complaints, complaints_source = load_customer_sample()
    risk_detail = pd.read_csv(ROOT / "data" / "processed" / "risk_2025_detail.csv")
    manifest = pd.read_csv(ROOT / "data" / "source_manifest.csv")

    summary = customer_summary(complaints)
    latest = financial.iloc[-1]
    first = financial.iloc[0]

    # Carrega cotações de mercado da Twelve Data via MongoDB
    market_records, market_source = fetch_market_quotes_from_mongo()

    customer = {
        "total": int(len(complaints)),
        "loss_share_pct": None,
        "security_signals": None,
        "categories": records(summary["categories"]),
        "severity": records(summary["severity"]),
        "clusters": records(summary["clusters"]),
        "source_label": complaints_source,
    }

    if not complaints.empty and "Perda_Financeira" in complaints.columns:
        customer["loss_share_pct"] = round(
            float(pd.to_numeric(complaints["Perda_Financeira"], errors="coerce").fillna(0).mean() * 100),
            1,
        )
    if not complaints.empty and "Problema_Seguranca" in complaints.columns:
        customer["security_signals"] = int(
            pd.to_numeric(complaints["Problema_Seguranca"], errors="coerce").fillna(0).sum()
        )

    bcb = load_bcb_complaints()

    # Adiciona a fonte Twelve Data ao manifesto de fontes
    sources_list = records(manifest)
    sources_list.insert(1, {
        "dataset": "ranking_reclamacoes_bcb",
        "period": "Trimestral (desde 2021)",
        "source_type": "regulatório",
        "source": "Banco Central do Brasil / Ranking de Reclamações",
        "notes": "Índice e reclamações procedentes via API do BCB; irregularidades a partir dos arquivos trimestrais.",
    })
    sources_list.insert(0, {
        "dataset": "historico_diario",
        "period": "Recente (contínuo)",
        "source_type": "mercado (OHLCV)",
        "source": market_source,
        "notes": "Coletado via API Twelve Data e persistido no MongoDB Atlas sem manipulação manual de arquivos.",
    })

    return {
        "meta": {
            "title": "Nubank em Dados 2.0",
            "period": "2021–2025 + Cotações Atuais",
            "generated_from": "Twelve Data API & MongoDB Atlas + Relatórios Oficiais",
            "risk_source": risk_source,
            "market_source": market_source,
            "updated_at": pd.Timestamp.now(tz="UTC").strftime("%Y-%m-%d %H:%M:%S UTC"),
        },
        "headline": {
            "latest_year": int(latest["year"]),
            "customers_m": float(latest["customers_m"]),
            "revenue_usd_b": float(latest["revenue_usd_b"]),
            "net_income_usd_b": float(latest["net_income_usd_b"]),
            "deposits_usd_b": float(latest["deposits_usd_b"]),
            "customer_growth_pct": round(float((latest["customers_m"] / first["customers_m"] - 1) * 100), 1),
            "revenue_multiple": round(float(latest["revenue_usd_b"] / first["revenue_usd_b"]), 1),
            "deposit_multiple": round(float(latest["deposits_usd_b"] / first["deposits_usd_b"]), 1),
        },
        "market": market_records,
        "financial": records(financial),
        "risk": records(risk),
        "risk_2025": records(risk_detail),
        "customer": customer,
        "bcb_complaints": bcb,
        "sources": sources_list,
    }


def main() -> None:
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    payload = build_payload()
    OUTPUT.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    print(f"Payload web criado em {OUTPUT}")


if __name__ == "__main__":
    main()
