from __future__ import annotations

from database.connection import get_database, get_mongo_client, get_mongo_uri
from database.operations import (
    ensure_unique_index,
    get_collection_stats,
    get_financial_series,
    get_market_history,
    save_financial_series,
    upsert_market_records,
)

__all__ = [
    "get_mongo_client",
    "get_mongo_uri",
    "get_database",
    "ensure_unique_index",
    "upsert_market_records",
    "get_market_history",
    "get_collection_stats",
    "save_financial_series",
    "get_financial_series",
]
