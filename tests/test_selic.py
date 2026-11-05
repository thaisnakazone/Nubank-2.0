from __future__ import annotations

import unittest
from datetime import date
from unittest import mock

import pandas as pd

from src import ingest_selic as sel


class TestSelic(unittest.TestCase):
    def test_parse_valor_aceita_ponto_e_virgula(self):
        self.assertEqual(sel.parse_valor("13.75"), 13.75)
        self.assertEqual(sel.parse_valor("13,75"), 13.75)
        self.assertIsNone(sel.parse_valor(""))
        self.assertIsNone(sel.parse_valor("abc"))

    def test_parse_data(self):
        self.assertEqual(sel.parse_data("17/09/2026"), "2026-09-17")
        self.assertIsNone(sel.parse_data("2026-09-17"))
        self.assertIsNone(sel.parse_data("31/02/2026"))

    def test_clean_series_descarta_invalidos_e_ordena(self):
        raw = [
            {"data": "03/01/2021", "valor": "2.00"},
            {"data": "01/01/2021", "valor": "2.00"},
            {"data": "xx", "valor": "2.00"},
            {"data": "04/01/2021", "valor": ""},
            {"data": "05/01/2021", "valor": "250"},
            "lixo",
        ]
        df = sel.clean_series(raw)
        self.assertEqual(df["data"].tolist(), ["2021-01-01", "2021-01-03"])

    def test_compress_mantem_mudancas_e_ultimo_dia(self):
        df = pd.DataFrame({
            "data": ["2026-09-16", "2026-09-17", "2026-09-18", "2026-11-05"],
            "selic_meta_pct": [14.0, 13.75, 13.75, 13.75],
        })
        out = sel.compress_changes(df)
        self.assertEqual(out["data"].tolist(), ["2026-09-16", "2026-09-17", "2026-11-05"])

    def test_run_falha_na_api_nao_apaga_csv(self):
        with mock.patch.object(sel, "fetch_series", side_effect=OSError("offline")), \
                mock.patch.object(sel, "SELIC_CSV") as csv_path:
            self.assertEqual(sel.run(today=date(2026, 11, 5)), 1)
            csv_path.assert_not_called()


if __name__ == "__main__":
    unittest.main()
