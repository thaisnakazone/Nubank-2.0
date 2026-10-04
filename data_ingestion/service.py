from __future__ import annotations

import sys
from datetime import datetime, timezone
from typing import Any
from pymongo.errors import PyMongoError

from data_ingestion.client import TwelveDataClient
from data_ingestion.sanitizer import sanitize_text
from data_ingestion.validator import validate_record
from database.connection import get_database, get_mongo_client
from database.operations import ensure_unique_index, upsert_market_records

DEFAULT_TICKERS = ["NU", "ITUB", "BBD"]


class IngestionService:
    """
    Serviço central de ingestão de dados da API Twelve Data para o MongoDB Atlas.
    """

    def __init__(
        self,
        api_key: str,
        mongo_uri: str,
        tickers: list[str] | None = None,
        db_name: str = "nubank_db",
        collection_name: str = "historico_diario",
        outputsize: int = 30,
    ) -> None:
        self.api_key = api_key
        self.mongo_uri = mongo_uri
        self.tickers = tickers or DEFAULT_TICKERS
        self.db_name = db_name
        self.collection_name = collection_name
        self.outputsize = outputsize
        self.client = TwelveDataClient(api_key=api_key)

    def run(self) -> dict[str, Any]:
        """
        Executa o fluxo completo de ingestão:
        1. Validação de credenciais e parâmetros
        2. Coleta de dados via API Twelve Data com rate-limiting
        3. Validação individual de cada cotação OHLCV
        4. Gravação com upsert idempotente no MongoDB Atlas
        """
        result: dict[str, Any] = {
            "success": False,
            "tickers_processed": [],
            "failed_tickers": [],
            "total_valid": 0,
            "total_rejected": 0,
            "rejected_samples": [],
            "db_stats": {},
            "error": "",
        }

        print(f"Iniciando coleta para os tickers: {self.tickers}\n")

        valid_records: list[dict[str, Any]] = []
        rejected_records: list[dict[str, Any]] = []

        for index, ticker in enumerate(self.tickers):
            print(f"[{index + 1}/{len(self.tickers)}] Buscando cotações diárias para '{ticker}'...")
            raw_values, err = self.client.fetch_time_series(
                ticker=ticker,
                outputsize=self.outputsize,
            )

            if err:
                print(f"  ❌ {err}", file=sys.stderr)
                result["failed_tickers"].append(ticker)
                continue

            collection_time = datetime.now(timezone.utc)
            ticker_valid = 0

            for raw_item in raw_values:
                valid_doc, reason = validate_record(raw_item, ticker)
                if valid_doc is not None:
                    valid_doc["source"] = "Twelve Data"
                    valid_doc["collected_at"] = collection_time
                    valid_records.append(valid_doc)
                    ticker_valid += 1
                else:
                    rejected_records.append({
                        "ticker": ticker,
                        "reason": reason,
                        "raw": raw_item.get("datetime") if isinstance(raw_item, dict) else str(raw_item),
                    })

            print(f"  ✓ '{ticker}': {ticker_valid} cotações válidas processadas.")
            result["tickers_processed"].append(ticker)

            if index < len(self.tickers) - 1:
                self.client.pause()

        result["total_valid"] = len(valid_records)
        result["total_rejected"] = len(rejected_records)
        result["rejected_samples"] = rejected_records[:5]

        print(f"\nResumo da coleta: {len(valid_records)} válidos, {len(rejected_records)} rejeitados.")
        if rejected_records:
            print("Amostra de registros rejeitados:")
            for rej in rejected_records[:3]:
                print(f"  • {rej['ticker']} (data: {rej['raw']}): {rej['reason']}")

        # Gravação no MongoDB Atlas
        mongo_client = None
        try:
            mongo_client = get_mongo_client(self.mongo_uri)
            db = get_database(mongo_client, self.db_name)
            collection = db[self.collection_name]

            if not ensure_unique_index(collection):
                result["error"] = "Falha ao garantir índice único no MongoDB Atlas"
                return result

            if not valid_records:
                print("Nenhum registro válido para gravar no banco.", file=sys.stderr)
                result["success"] = len(result["failed_tickers"]) == 0
                return result

            db_stats = upsert_market_records(collection, valid_records)
            result["db_stats"] = db_stats

            print("\n📊 Resultado da ingestão no MongoDB:")
            print(f"  • Documentos novos inseridos: {db_stats['inserted']}")
            print(f"  • Documentos existentes atualizados: {db_stats['modified']}")
            print(f"  • Documentos correspondentes sem alteração: {db_stats['matched'] - db_stats['modified']}")
            print(f"  • Registros rejeitados na validação: {len(rejected_records)}")

            result["success"] = len(result["failed_tickers"]) == 0
            if result["success"]:
                print("\n✅ Ingestão finalizada com sucesso para todos os tickers configurados.")
            else:
                print(f"\n❌ Atenção: Coleta incompleta. Falhas em: {result['failed_tickers']}", file=sys.stderr)

            return result

        except PyMongoError as e:
            err_msg = f"Erro durante operação no MongoDB: {type(e).__name__}"
            print(f"\n❌ {err_msg}", file=sys.stderr)
            result["error"] = err_msg
            return result
        finally:
            if mongo_client:
                mongo_client.close()
