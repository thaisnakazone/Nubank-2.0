from __future__ import annotations

import os
import sys
from pathlib import Path
import pandas as pd
from dotenv import load_dotenv

# Garante suporte a UTF-8 no console Windows
if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

from database.connection import get_database, get_mongo_client, get_mongo_uri
from database.operations import get_collection_stats, get_market_history


def main() -> None:
    uri = get_mongo_uri()
    if not uri:
        print("❌ Erro: MONGO_URI não configurada no ambiente ou no arquivo .env.", file=sys.stderr)
        sys.exit(1)

    client = None
    try:
        client = get_mongo_client(uri)
        db = get_database(client)
        collection = db["historico_diario"]

        stats = get_collection_stats(collection)
        total = stats["total_documents"]

        print("=" * 60)
        print("📊 STATUS DA COLEÇÃO NO MONGODB ATLAS (nubank_db.historico_diario)")
        print("=" * 60)
        print(f"Total de cotações armazenadas: {total}\n")

        if stats["tickers"]:
            print("📈 Ativos monitorados e amplitude de dados:")
            for item in stats["tickers"]:
                name = item["_id"] or "Sem ticker"
                min_d = item.get("min_date", "—")
                max_d = item.get("max_date", "—")
                cnt = item.get("total", 0)
                print(f"  • {name:5s}: {cnt:3d} pregões ({min_d} até {max_d})")
            print()
        else:
            print("⚠️  Nenhum dado por ticker encontrado.\n")

        docs = get_market_history(collection, limit=5)
        # Mais recentes primeiro para exibição
        cursor = collection.find({}, {"_id": 0}).sort("datetime", -1).limit(5)
        docs_recent = list(cursor)

        if docs_recent:
            df = pd.DataFrame(docs_recent)
            cols_order = [c for c in ["ticker", "datetime", "open", "high", "low", "close", "volume", "source"] if c in df.columns]
            print("🔍 Amostra dos 5 registros mais recentes:")
            print(df[cols_order].to_string(index=False))
        else:
            print("Nenhum documento encontrado.")

        print("=" * 60)

    except Exception as e:
        print(f"❌ Erro ao consultar MongoDB Atlas: {e}", file=sys.stderr)
        sys.exit(1)
    finally:
        if client:
            client.close()


if __name__ == "__main__":
    main()
