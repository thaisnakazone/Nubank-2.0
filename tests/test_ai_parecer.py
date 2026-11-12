from __future__ import annotations

import json
import unittest
from pathlib import Path
from unittest import mock

from src import ai_parecer as ai

ROOT = Path(__file__).resolve().parents[1]


def _parecer(**over):
    base = {
        "resumo": "O Nubank cresce e lucra, mas a folga de capital diminuiu.",
        "areas": {a: {"status": "bom", "motivo": "Motivo curto com número 18%."} for a in ai.AREAS},
        "conselho": "Priorizar a qualidade do crédito e reforçar o capital.",
    }
    base.update(over)
    return base


class TestValidacao(unittest.TestCase):
    def test_parecer_valido(self):
        self.assertEqual(ai.validate(_parecer()), [])

    def test_area_faltando(self):
        p = _parecer()
        del p["areas"]["capital"]
        self.assertIn("área 'capital' ausente", ai.validate(p))

    def test_status_invalido(self):
        p = _parecer()
        p["areas"]["mercado"]["status"] = "ótimo"
        self.assertIn("status inválido em 'mercado'", ai.validate(p))

    def test_bloqueia_recomendacao_de_compra_e_venda(self):
        for frase in ("Compre ações do Nubank.", "Vale vender as ações agora.", "Mantenha as ações.", "Comprar NU agora."):
            with self.subTest(frase=frase):
                self.assertIn("contém recomendação de compra/venda de ações", ai.validate(_parecer(conselho=frase)))

    def test_permite_vender_produtos(self):
        self.assertEqual(ai.validate(_parecer(conselho="Vender mais produtos para quem já é cliente.")), [])


class TestIndicadores(unittest.TestCase):
    def test_indicadores_do_payload_real(self):
        payload = json.loads((ROOT / "docs" / "data" / "dashboard-data.json").read_text(encoding="utf-8"))
        ind = ai.build_indicators(payload)
        for chave in ("crescimento", "rentabilidade", "capital", "mercado", "clientes"):
            self.assertIn(chave, ind)
        self.assertEqual(ind["capital"]["minimo_exigido_pct"], 10.5)
        self.assertIn("NU", ind["mercado"])


class TestGeracao(unittest.TestCase):
    def test_tenta_de_novo_quando_resposta_invalida(self):
        ruim = _parecer(conselho="Compre ações.")
        bom = _parecer(areas={a: {"status": "ATENCAO", "motivo": "ok"} for a in ai.AREAS})
        with mock.patch.object(ai, "call_claude", side_effect=[ruim, bom]) as call:
            out = ai.generate({}, "chave-falsa")
        self.assertEqual(call.call_count, 2)
        self.assertEqual(out["areas"]["capital"]["status"], "atencao")

    def test_sem_chave_mantem_parecer_anterior(self):
        with mock.patch.dict("os.environ", {"ANTHROPIC_API_KEY": ""}), \
                mock.patch.object(ai, "load_previous", return_value=None), \
                mock.patch.object(ai, "inject") as inject, \
                mock.patch.object(ai, "call_claude") as call:
            self.assertEqual(ai.run(), 0)
        call.assert_not_called()
        inject.assert_called_once_with(None)


class TestLinhasPilar3(unittest.TestCase):
    def test_usa_linha_principal_do_basileia(self):
        from src.data_pipeline import _metric_name
        self.assertEqual(_metric_name("Índice de Basileia"), "basel_index_pct")
        self.assertEqual(_metric_name("Índice de Basileia (IB)"), "basel_index_pct")
        self.assertIsNone(_metric_name("Índice de Basileia, considerando:\n- Numerador: corresponde à linha 3a"))
        self.assertIsNone(_metric_name("Margem excedente de Capital Principal (%) considerando o Capital Principal conforme linha 1a"))


if __name__ == "__main__":
    unittest.main()
