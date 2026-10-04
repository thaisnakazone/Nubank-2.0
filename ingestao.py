from __future__ import annotations

import os
import sys
from pathlib import Path
from dotenv import load_dotenv

# Garante suporte a UTF-8 no console Windows
if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

# Exporta símbolos mantendo compatibilidade retroativa com testes e CI
from data_ingestion.sanitizer import sanitize_text
from data_ingestion.validator import validate_record
from data_ingestion.service import IngestionService
from database.operations import ensure_unique_index


def main() -> int:
    env_path = Path(__file__).resolve().parent / ".env"
    if env_path.exists():
        load_dotenv(dotenv_path=env_path)
    else:
        load_dotenv()

    api_key = os.getenv("TWELVE_DATA_API_KEY") or os.getenv("TWELVEDATA_API_KEY")
    mongo_uri = os.getenv("MONGO_URI")

    if not api_key:
        print("Erro: Chave TWELVE_DATA_API_KEY não configurada no ambiente/.env.", file=sys.stderr)
        return 1

    if not mongo_uri:
        print("Erro: MONGO_URI não configurada no ambiente/.env.", file=sys.stderr)
        return 1

    service = IngestionService(
        api_key=api_key,
        mongo_uri=mongo_uri,
        tickers=["NU", "ITUB", "BBD"],
        outputsize=30,
    )
    result = service.run()
    return 0 if result.get("success") else 1


if __name__ == "__main__":
    sys.exit(main())
