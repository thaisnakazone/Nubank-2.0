from __future__ import annotations

import unicodedata
from pathlib import Path

import pandas as pd

from src.ingest_pillar3 import build_long_history


ROOT = Path(__file__).resolve().parents[1]
PROCESSED = ROOT / "data" / "processed"
RAW_CUSTOMER = ROOT / "data" / "raw" / "customer"


def load_financial_history() -> pd.DataFrame:
    df = pd.read_csv(PROCESSED / "financial_history.csv")
    df["year"] = df["year"].astype(int)
    return df.sort_values("year").reset_index(drop=True)


def _normalize(text: object) -> str:
    value = "" if pd.isna(text) else str(text)
    value = unicodedata.normalize("NFKD", value).encode("ascii", "ignore").decode("ascii")
    return " ".join(value.lower().strip().split())


def _metric_name(description: object) -> str | None:
    d = _normalize(description)
    # O Pilar 3 traz linhas alternativas ("7a", "5a", "12a"...) "considerando" outro numerador/denominador.
    # Usamos só as linhas principais (ex.: linha 7, Índice de Basileia), as mesmas das projeções.
    if "considerando" in d or "conforme linha" in d:
        return None
    if d == "capital principal":
        return "capital_principal_brl_b"
    if "rwa total" in d:
        return "rwa_total_brl_b"
    if "indice de capital principal" in d:
        return "icp_pct"
    if "indice de basileia" in d:
        return "basel_index_pct"
    if "margem excedente de capital principal" in d:
        return "capital_buffer_pct"
    return None


def _shape_capital_history(raw: pd.DataFrame) -> pd.DataFrame:
    df = raw.copy()
    source_period = "periodo" if "periodo" in df.columns else "period"
    df["period"] = pd.to_datetime(df[source_period], errors="coerce")
    df["metric"] = df["descricao"].map(_metric_name)
    df["valor"] = pd.to_numeric(df["valor"], errors="coerce")
    df = df.dropna(subset=["period", "metric", "valor"])

    if df.empty:
        return df

    wide = (
        df.sort_values("period")
        .groupby(["period", "metric"], as_index=False)["valor"]
        .last()
        .pivot(index="period", columns="metric", values="valor")
        .reset_index()
        .sort_values("period")
    )
    wide.columns.name = None

    for col in ["capital_principal_brl_b", "rwa_total_brl_b"]:
        if col in wide and not wide[col].dropna().empty and wide[col].dropna().median() > 1_000_000:
            wide[col] = wide[col] / 1e9

    for col in ["icp_pct", "basel_index_pct", "capital_buffer_pct"]:
        if col in wide and not wide[col].dropna().empty and wide[col].dropna().median() <= 1.5:
            wide[col] = wide[col] * 100

    wide["year"] = wide["period"].dt.year
    return wide[wide["year"].between(2021, 2025)].reset_index(drop=True)


def load_capital_risk_history(refresh: bool = False) -> tuple[pd.DataFrame, str]:
    """Load the local Pilar 3 history; rebuild it from versioned XLSX files when needed."""
    long_path = PROCESSED / "capital_risk_history_long.csv"

    if refresh or not long_path.exists():
        raw = build_long_history()
    else:
        raw = pd.read_csv(long_path)

    shaped = _shape_capital_history(raw)
    if not shaped.empty:
        return shaped, "Pilar 3 · dados regulatórios locais 2021–2025"

    fallback = pd.read_csv(PROCESSED / "risk_2025_detail.csv", parse_dates=["period"])
    fallback["year"] = fallback["period"].dt.year
    return fallback, "Detalhe regulatório local de 2025"


def load_customer_sample() -> tuple[pd.DataFrame, str]:
    """Load the locally versioned academic complaint sample."""
    path = RAW_CUSTOMER / "reclamacoes_com_insights.csv"
    if not path.exists():
        return pd.DataFrame(), "Amostra de reclamações indisponível"
    return pd.read_csv(path), "Amostra acadêmica de reclamações públicas"


def customer_summary(df: pd.DataFrame) -> dict[str, pd.DataFrame]:
    if df.empty:
        return {"categories": pd.DataFrame(), "severity": pd.DataFrame(), "clusters": pd.DataFrame()}

    categories = pd.DataFrame()
    severity = pd.DataFrame()
    clusters = pd.DataFrame()

    if "Categoria_Primaria" in df.columns:
        categories = (
            df["Categoria_Primaria"]
            .fillna("Não classificada")
            .value_counts()
            .rename_axis("categoria")
            .reset_index(name="reclamacoes")
        )
    if "Severidade_Estimada" in df.columns:
        severity = (
            df["Severidade_Estimada"]
            .fillna("Não classificada")
            .value_counts()
            .rename_axis("severidade")
            .reset_index(name="reclamacoes")
        )
    if "Cluster" in df.columns:
        clusters = (
            df["Cluster"]
            .fillna(-1)
            .astype(int)
            .value_counts()
            .sort_index()
            .rename_axis("cluster")
            .reset_index(name="reclamacoes")
        )

    return {"categories": categories, "severity": severity, "clusters": clusters}
