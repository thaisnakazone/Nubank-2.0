from __future__ import annotations

import json
import unittest
from pathlib import Path
from unittest import mock

from src import ai_faq as faq
from src import sync_chat_logs as sync

ROOT = Path(__file__).resolve().parents[1]


def _resultado(**troca):
    respostas = [{"id": pid, "resposta": f"Resposta curta para {pid}, com o número 18,2%."} for pid, _ in faq.PERGUNTAS]
    for r in respostas:
        if r["id"] in troca:
            r["resposta"] = troca[r["id"]]
    return {"respostas": respostas}


class TestContexto(unittest.TestCase):
    def setUp(self):
        self.payload = json.loads((ROOT / "docs" / "data" / "dashboard-data.json").read_text(encoding="utf-8"))

    def test_contexto_tem_indicadores_e_historico(self):
        ctx = faq.build_context(self.payload)
        self.assertIn("rentabilidade", ctx["indicadores"])
        anos = {h["ano"]: h for h in ctx["historico_anual"]}
        self.assertEqual(anos[2021]["resultado"], "prejuízo")
        self.assertEqual(anos[2025]["resultado"], "lucro")

    def test_contexto_e_pequeno(self):
        texto = json.dumps(faq.build_context(self.payload), ensure_ascii=False, separators=(",", ":"))
        self.assertLess(len(texto), 8000)  # o chat envia isso a cada pergunta: precisa ser barato

    def test_hash_ignora_data_de_atualizacao_e_parecer(self):
        a = faq.build_context(self.payload)
        b = json.loads(json.dumps(a))
        b["indicadores"]["dados_atualizados_em"] = "outro horário"
        b["parecer_do_dia"] = {"resumo": "mudou"}
        self.assertEqual(faq.context_hash(a), faq.context_hash(b))
        b["indicadores"]["rentabilidade"]["margem_liquida_pct"] = 1.0
        self.assertNotEqual(faq.context_hash(a), faq.context_hash(b))


class TestRespostasProntas(unittest.TestCase):
    def test_validas(self):
        self.assertEqual(faq.validate(_resultado()), [])

    def test_pergunta_sem_resposta(self):
        r = _resultado()
        r["respostas"] = r["respostas"][:-1]
        self.assertIn("pergunta 'melhorar' sem resposta", faq.validate(r))

    def test_bloqueia_recomendacao_de_compra(self):
        problemas = faq.validate(_resultado(acao="Compre ações do Nubank."))
        self.assertIn("resposta de 'acao' contém recomendação de compra/venda de ações", problemas)

    def test_resposta_longa_demais(self):
        self.assertIn("resposta de 'esta_bem' longa demais", faq.validate(_resultado(esta_bem="x" * 800)))

    def test_tenta_de_novo_e_mantem_ordem_das_perguntas(self):
        with mock.patch.object(faq, "call_claude", side_effect=[_resultado(acao="Venda as ações."), _resultado()]) as call:
            itens = faq.generate({}, "chave-falsa")
        self.assertEqual(call.call_count, 2)
        self.assertEqual([i["id"] for i in itens], [pid for pid, _ in faq.PERGUNTAS])
        self.assertEqual(itens[0]["pergunta"], "O Nubank está bem?")

    def test_sem_chave_nao_chama_a_ia(self):
        with mock.patch.dict("os.environ", {"ANTHROPIC_API_KEY": ""}), \
                mock.patch.object(faq, "write_context"), \
                mock.patch.object(faq, "CONTEXT_JSON") as ctx_path, \
                mock.patch.object(faq, "load_previous", return_value=None), \
                mock.patch.object(faq, "inject") as inject, \
                mock.patch.object(faq, "call_claude") as call:
            ctx_path.relative_to.return_value = "docs/data/chat-context.json"
            ctx_path.stat.return_value.st_size = 1
            self.assertEqual(faq.run(), 0)
        call.assert_not_called()
        inject.assert_called_once_with(None)


class TestSincronizacao(unittest.TestCase):
    def test_limpa_registro(self):
        r = sync.clean({"id": "7", "texto": " O Nubank teve lucro? ", "tipo": "livre", "tokens_entrada": "2000", "custo_usd": "0.00025", "ip": "1.2.3.4"})
        self.assertEqual(r["id"], 7)
        self.assertEqual(r["texto"], "O Nubank teve lucro?")
        self.assertEqual(r["tokens_entrada"], 2000)
        self.assertNotIn("ip", r)  # só os campos esperados entram no banco

    def test_descarta_registro_invalido(self):
        self.assertIsNone(sync.clean({"texto": "sem id"}))
        self.assertIsNone(sync.clean({"id": 1, "texto": "  "}))

    def test_endereco_vem_do_config_do_site(self):
        with mock.patch.dict("os.environ", {"CHAT_API_URL": ""}), mock.patch.object(sync, "CONFIG_JS") as cfg:
            cfg.exists.return_value = True
            cfg.read_text.return_value = "window.NU_CHAT_API = 'https://nubank-chat.exemplo.workers.dev/';"
            self.assertEqual(sync.chat_api_url(), "https://nubank-chat.exemplo.workers.dev")

    def test_sem_endereco_ou_token_nao_faz_nada(self):
        with mock.patch.object(sync, "chat_api_url", return_value=""):
            self.assertEqual(sync.run(), 0)
        with mock.patch.object(sync, "chat_api_url", return_value="https://x.workers.dev"), mock.patch.dict("os.environ", {"CHAT_EXPORT_TOKEN": ""}):
            self.assertEqual(sync.run(), 0)


if __name__ == "__main__":
    unittest.main()
