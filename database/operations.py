from __future__ import annotations

import sys
from typing import Any
from pymongo import UpdateOne
from pymongo.collection import Collection
from pymongo.database import Database
from pymongo.errors import DuplicateKeyError, OperationFailure, PyMongoError


def ensure_unique_index(collection: Collection) -> bool:
    """
    Garante a presença do índice composto único em ('ticker', 'datetime').
    Se duplicatas impedirem sua criação, interrompe com mensagem clara sem apagar dados.
    """
    try:
        for idx in collection.list_indexes():
            keys = list(idx.get("key", {}).items())
            if keys == [("ticker", 1), ("datetime", 1)] and idx.get("unique"):
                return True
    except PyMongoError as e:
        print(f"Erro ao verificar índices existentes: {type(e).__name__}", file=sys.stderr)
        return False

    try:
        collection.create_index([("ticker", 1), ("datetime", 1)], unique=True)
        return True
    except (DuplicateKeyError, OperationFailure) as e:
        err_msg = str(e).lower()
        if "duplicate key" in err_msg or getattr(e, "code", None) == 11000:
            print(
                "\n❌ ERRO CRÍTICO: Existem registros duplicados na coleção 'historico_diario' "
                "que impedem a criação do índice composto único ('ticker', 'datetime').\n"
                "A ingestão foi cancelada para evitar inconsistências nos dados existentes.\n"
                "Nenhum dado foi apagado automaticamente.\n"
                "Execute o script de inspeção e limpeza controlada "
                "(scripts/limpar_historico_teste.py) antes de tentar novamente.",
                file=sys.stderr,
            )
            return False
        print(f"Erro inesperado ao criar índice único: {type(e).__name__}", file=sys.stderr)
        return False


def upsert_market_records(collection: Collection, records: list[dict[str, Any]]) -> dict[str, int]:
    """
    Executa upsert em lote para cotações no MongoDB Atlas.
    Garante idempotência: reexecuções não duplicam documentos.
    """
    if not records:
        return {"inserted": 0, "modified": 0, "matched": 0}

    operations = [
        UpdateOne(
            {"ticker": doc["ticker"], "datetime": doc["datetime"]},
            {"$set": doc},
            upsert=True,
        )
        for doc in records
    ]

    bulk_result = collection.bulk_write(operations, ordered=False)
    return {
        "inserted": bulk_result.upserted_count,
        "modified": bulk_result.modified_count,
        "matched": bulk_result.matched_count,
    }


def get_market_history(
    collection: Collection,
    ticker: str | None = None,
    start_date: str | None = None,
    end_date: str | None = None,
    limit: int = 500,
) -> list[dict[str, Any]]:
    """Consulta o histórico de cotações com filtros opcionais de ticker e data."""
    query: dict[str, Any] = {}
    if ticker:
        query["ticker"] = ticker

    if start_date or end_date:
        query["datetime"] = {}
        if start_date:
            query["datetime"]["$gte"] = start_date
        if end_date:
            query["datetime"]["$lte"] = end_date

    cursor = collection.find(query, {"_id": 0}).sort("datetime", 1).limit(limit)
    return list(cursor)


def get_collection_stats(collection: Collection) -> dict[str, Any]:
    """Retorna estatísticas operacionais da coleção de cotações."""
    total = collection.count_documents({})
    pipeline = [
        {
            "$group": {
                "_id": "$ticker",
                "total": {"$sum": 1},
                "min_date": {"$min": "$datetime"},
                "max_date": {"$max": "$datetime"},
                "latest_close": {"$last": "$close"},
            }
        },
        {"$sort": {"_id": 1}},
    ]
    ticker_stats = list(collection.aggregate(pipeline))
    return {
        "total_documents": total,
        "tickers": ticker_stats,
    }


def save_financial_series(db: Database, records: list[dict[str, Any]]) -> int:
    """Salva série histórica financeira da Nu Holdings no MongoDB Atlas."""
    collection = db["financeiro_anual"]
    collection.create_index("year", unique=True)
    ops = [
        UpdateOne({"year": int(row["year"])}, {"$set": row}, upsert=True)
        for row in records
        if "year" in row
    ]
    if not ops:
        return 0
    res = collection.bulk_write(ops, ordered=False)
    return res.upserted_count + res.modified_count


def get_financial_series(db: Database) -> list[dict[str, Any]]:
    """Carrega série histórica financeira da Nu Holdings a partir do MongoDB Atlas."""
    collection = db["financeiro_anual"]
    return list(collection.find({}, {"_id": 0}).sort("year", 1))
