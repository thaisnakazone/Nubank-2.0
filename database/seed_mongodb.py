from __future__ import annotations

import sys
from pathlib import Path
import pandas as pd
from pymongo.errors import PyMongoError

# Garante suporte a UTF-8 no console Windows
if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

from database.connection import get_database, get_mongo_client, get_mongo_uri
from database.operations import save_financial_series


def seed_database() -> int:
    """
    Carrega as séries de indicadores financeiros fundamentais para o MongoDB Atlas,
    permitindo que o banco NoSQL centralize tanto os dados de mercado (Twelve Data)
    quanto os dados contábeis/regulatórios do Nubank.
    """
    uri = get_mongo_uri()
    if not uri:
        print("Aviso: MONGO_URI não configurada. Carga inicial ignorada.", file=sys.stderr)
        return 1

    root = Path(__file__).resolve().parents[1]
    fin_path = root / "data" / "processed" / "financial_history.csv"

    if not fin_path.exists():
        print(f"Erro: Arquivo {fin_path} não encontrado.", file=sys.stderr)
        return 1

    df_fin = pd.read_csv(fin_path)
    records = df_fin.to_dict(orient="records")

    client = None
    try:
        client = get_mongo_client(uri)
        db = get_database(client)

        count = save_financial_series(db, records)
        print(f"✓ Carga concluída: {count} registros gravados na coleção 'financeiro_anual' do MongoDB Atlas.")
        return 0
    except PyMongoError as e:
        print(f"Erro ao gravar no MongoDB Atlas: {e}", file=sys.stderr)
        return 1
    finally:
        if client:
            client.close()


if __name__ == "__main__":
    sys.exit(seed_database())
