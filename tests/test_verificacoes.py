import sys
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

# Adiciona o diretório da aplicação e scripts ao sys.path
REPO_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_DIR))
sys.path.insert(0, str(REPO_DIR / "scripts"))

from ingestao import ensure_unique_index, sanitize_text, validate_record
from pymongo import UpdateOne
from pymongo.errors import OperationFailure
import limpar_historico_teste


class TestIngestaoValidacao(unittest.TestCase):
    def test_valid_record(self):
        raw = {
            "datetime": "2026-09-30",
            "open": "11.50",
            "high": "12.00",
            "low": "11.20",
            "close": "11.80",
            "volume": "1500000",
        }
        doc, reason = validate_record(raw, "NU")
        self.assertIsNotNone(doc)
        self.assertEqual(reason, "")
        self.assertEqual(doc["ticker"], "NU")
        self.assertEqual(doc["datetime"], "2026-09-30")
        self.assertEqual(doc["open"], 11.50)
        self.assertEqual(doc["volume"], 1500000.0)

    def test_invalid_datetime(self):
        raw = {
            "datetime": "2026-02-30",  # Data inexistente
            "open": "10",
            "high": "11",
            "low": "9",
            "close": "10",
            "volume": "100",
        }
        doc, reason = validate_record(raw, "NU")
        self.assertIsNone(doc)
        self.assertIn("datetime", reason)

    def test_missing_price(self):
        raw = {
            "datetime": "2026-09-30",
            "open": "",
            "high": "11",
            "low": "9",
            "close": "10",
            "volume": "100",
        }
        doc, reason = validate_record(raw, "NU")
        self.assertIsNone(doc)
        self.assertIn("ausente", reason)

    def test_high_lower_than_low(self):
        raw = {
            "datetime": "2026-09-30",
            "open": "10",
            "high": "8.5",  # Máxima menor que mínima
            "low": "9.0",
            "close": "10",
            "volume": "100",
        }
        doc, reason = validate_record(raw, "NU")
        self.assertIsNone(doc)
        self.assertIn("inferior à mínima", reason)

    def test_negative_volume(self):
        raw = {
            "datetime": "2026-09-30",
            "open": "10",
            "high": "11",
            "low": "9",
            "close": "10",
            "volume": "-500",
        }
        doc, reason = validate_record(raw, "NU")
        self.assertIsNone(doc)
        self.assertIn("volume negativo", reason)


class TestUpsertSemDuplicatas(unittest.TestCase):
    def test_duas_ingestoes_nao_geram_duplicatas(self):
        """
        Simula duas ingestões consecutivas com o mesmo lote de pregões
        e valida que o modelo de upsert por (ticker, datetime) previne duplicatas.
        """
        cotacoes = [
            {"datetime": "2026-09-29", "open": "10", "high": "11", "low": "9", "close": "10.5", "volume": "1000"},
            {"datetime": "2026-09-30", "open": "10.5", "high": "12", "low": "10", "close": "11.5", "volume": "2000"},
        ]

        # Simulação de base de dados em memória
        in_memory_db = {}

        def apply_bulk_upsert(raw_list, ticker):
            for raw in raw_list:
                doc, _ = validate_record(raw, ticker)
                key = (doc["ticker"], doc["datetime"])
                # Lógica do UpdateOne com upsert=True
                in_memory_db[key] = doc

        # Ingestão 1
        apply_bulk_upsert(cotacoes, "NU")
        self.assertEqual(len(in_memory_db), 2)

        # Ingestão 2 (mesmos dados simulados)
        apply_bulk_upsert(cotacoes, "NU")
        self.assertEqual(len(in_memory_db), 2, "A segunda ingestão não deve criar duplicatas!")


class TestProtecaoCredenciais(unittest.TestCase):
    def test_sanitize_text_mascara_chaves_e_urls(self):
        fake_key = "segredo_super_secreto_12345"
        texto_vazado = f"Erro ao acessar https://api.twelvedata.com/time_series?symbol=NU&apikey={fake_key}&interval=1day"
        sanitizado = sanitize_text(texto_vazado, fake_key)

        self.assertNotIn(fake_key, sanitizado)
        self.assertIn("***REDACTED***", sanitizado)

    def test_sanitize_text_mascara_mongo_uri(self):
        raw_uri = "Erro de conexão para mongodb+srv://meu_usuario:minha_senha_secreta@cluster0.mongodb.net/?app=1"
        sanitizado = sanitize_text(raw_uri)
        self.assertNotIn("minha_senha_secreta", sanitizado)
        self.assertIn("mongodb://***REDACTED***", sanitizado)


class TestLimpezaControlada(unittest.TestCase):
    @patch("limpar_historico_teste.MongoClient")
    @patch("limpar_historico_teste.load_dotenv")
    def test_modo_padrao_nao_exclui_dados(self, mock_dotenv, mock_client_cls):
        mock_client = MagicMock()
        mock_col = MagicMock()
        mock_col.count_documents.return_value = 90
        mock_col.aggregate.return_value = []
        mock_client.__getitem__.return_value.__getitem__.return_value = mock_col
        mock_client_cls.return_value = mock_client

        with patch.dict("os.environ", {"MONGO_URI": "mongodb://fake:uri@localhost:27017"}):
            with patch.object(sys, "argv", ["limpar_historico_teste.py"]):
                exit_code = limpar_historico_teste.main()

        self.assertEqual(exit_code, 0)
        # NUNCA deve chamar delete_many no modo padrão
        mock_col.delete_many.assert_not_called()
        mock_col.drop.assert_not_called()

    @patch("limpar_historico_teste.MongoClient")
    @patch("limpar_historico_teste.load_dotenv")
    def test_modo_executar_com_confirmacao_errada_nao_exclui(self, mock_dotenv, mock_client_cls):
        mock_client = MagicMock()
        mock_col = MagicMock()
        mock_col.count_documents.return_value = 90
        mock_col.aggregate.return_value = []
        mock_client.__getitem__.return_value.__getitem__.return_value = mock_col
        mock_client_cls.return_value = mock_client

        with patch.dict("os.environ", {"MONGO_URI": "mongodb://fake:uri@localhost:27017"}):
            with patch.object(sys, "argv", ["limpar_historico_teste.py", "--executar"]):
                with patch("builtins.input", return_value="SIM QUERO APAGAR"):
                    exit_code = limpar_historico_teste.main()

        self.assertEqual(exit_code, 1)
        mock_col.delete_many.assert_not_called()

    @patch("limpar_historico_teste.MongoClient")
    @patch("limpar_historico_teste.load_dotenv")
    def test_modo_executar_com_confirmacao_correta_exclui_e_cria_indice(self, mock_dotenv, mock_client_cls):
        mock_client = MagicMock()
        mock_col = MagicMock()
        mock_col.count_documents.return_value = 90
        mock_col.aggregate.return_value = []
        mock_del_res = MagicMock()
        mock_del_res.deleted_count = 90
        mock_col.delete_many.return_value = mock_del_res
        mock_client.__getitem__.return_value.__getitem__.return_value = mock_col
        mock_client_cls.return_value = mock_client

        with patch.dict("os.environ", {"MONGO_URI": "mongodb://fake:uri@localhost:27017"}):
            with patch.object(sys, "argv", ["limpar_historico_teste.py", "--executar"]):
                with patch("builtins.input", return_value="LIMPAR nubank_db.historico_diario"):
                    exit_code = limpar_historico_teste.main()

        self.assertEqual(exit_code, 0)
        mock_col.delete_many.assert_called_once_with({})
        mock_col.create_index.assert_called_once_with([("ticker", 1), ("datetime", 1)], unique=True)
        # NUNCA drop
        mock_col.drop.assert_not_called()


class TestIndiceDuplicatas(unittest.TestCase):
    def test_ensure_unique_index_aborta_se_duplicatas(self):
        mock_col = MagicMock()
        mock_col.list_indexes.return_value = []
        # Simula erro de chave duplicada no MongoDB (código 11000)
        mock_col.create_index.side_effect = OperationFailure("E11000 duplicate key error", code=11000)

        success = ensure_unique_index(mock_col)
        self.assertFalse(success, "Deveria retornar False se duplicatas impedirem criação de índice único")


class TestTwelveDataClient(unittest.TestCase):
    @patch("data_ingestion.client.requests.get")
    def test_fetch_time_series_success(self, mock_get):
        from data_ingestion.client import TwelveDataClient
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {
            "status": "ok",
            "values": [
                {"datetime": "2026-10-01", "open": "14.0", "high": "14.5", "low": "13.8", "close": "14.2", "volume": "2000000"}
            ]
        }
        mock_get.return_value = mock_resp

        client = TwelveDataClient(api_key="teste_chave_123")
        values, err = client.fetch_time_series("NU", outputsize=1)
        self.assertEqual(err, "")
        self.assertEqual(len(values), 1)
        self.assertEqual(values[0]["datetime"], "2026-10-01")

    @patch("data_ingestion.client.requests.get")
    def test_fetch_time_series_api_error(self, mock_get):
        from data_ingestion.client import TwelveDataClient
        mock_resp = MagicMock()
        mock_resp.status_code = 400
        mock_resp.json.return_value = {
            "status": "error",
            "message": "apikey=teste_chave_123 is invalid",
        }
        mock_get.return_value = mock_resp

        client = TwelveDataClient(api_key="teste_chave_123")
        values, err = client.fetch_time_series("NU")
        self.assertEqual(len(values), 0)
        self.assertIn("Erro da API Twelve Data", err)
        # Garante que a chave foi mascarada
        self.assertNotIn("teste_chave_123", err)
        self.assertIn("***REDACTED***", err)

    def test_fetch_time_series_sem_chave(self):
        from data_ingestion.client import TwelveDataClient
        client = TwelveDataClient(api_key="")
        values, err = client.fetch_time_series("NU")
        self.assertEqual(len(values), 0)
        self.assertIn("não configurada", err)


class TestDatabaseOperations(unittest.TestCase):
    def test_upsert_market_records(self):
        from database.operations import upsert_market_records
        mock_col = MagicMock()
        mock_bulk_res = MagicMock()
        mock_bulk_res.upserted_count = 2
        mock_bulk_res.modified_count = 1
        mock_bulk_res.matched_count = 3
        mock_col.bulk_write.return_value = mock_bulk_res

        records = [
            {"ticker": "NU", "datetime": "2026-10-01", "close": 14.5},
            {"ticker": "NU", "datetime": "2026-10-02", "close": 14.8},
        ]
        result = upsert_market_records(mock_col, records)
        self.assertEqual(result["inserted"], 2)
        self.assertEqual(result["modified"], 1)
        mock_col.bulk_write.assert_called_once()

    def test_upsert_market_records_vazio(self):
        from database.operations import upsert_market_records
        mock_col = MagicMock()
        result = upsert_market_records(mock_col, [])
        self.assertEqual(result["inserted"], 0)
        mock_col.bulk_write.assert_not_called()

    def test_get_collection_stats(self):
        from database.operations import get_collection_stats
        mock_col = MagicMock()
        mock_col.count_documents.return_value = 60
        mock_col.aggregate.return_value = [{"_id": "NU", "total": 30, "min_date": "2026-08-01", "max_date": "2026-09-30"}]

        stats = get_collection_stats(mock_col)
        self.assertEqual(stats["total_documents"], 60)
        self.assertEqual(len(stats["tickers"]), 1)
        self.assertEqual(stats["tickers"][0]["_id"], "NU")


class TestWebDataPayload(unittest.TestCase):
    def test_build_payload_includes_market_and_financial(self):
        from src.build_web_data import build_payload
        payload = build_payload()
        self.assertIn("market", payload)
        self.assertIn("financial", payload)
        self.assertIn("risk", payload)
        self.assertIn("customer", payload)
        self.assertGreater(len(payload["financial"]), 0)
        self.assertGreater(len(payload["market"]), 0)


if __name__ == "__main__":
    unittest.main()
