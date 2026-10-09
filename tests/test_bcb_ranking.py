import sys
import unittest
from pathlib import Path

REPO_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_DIR))

from src.ingest_bcb_ranking import (  # noqa: E402
    _merge,
    _parse_history,
    classify_theme,
    short_irregularity,
    sleep_until,
    available_quarters,
    decode_bytes,
    parse_number,
    read_bcb_csv,
    select_banks_irregularidades,
    select_banks_ranking,
)

# Trechos reais dos arquivos do BCB (formato até 2024 e formato atual)
RANKING_ANTIGO = (
    "Ano;Trimestre;Categoria;Tipo;CNPJ IF;Instituição financeira;Índice;Quantidade de reclamações reguladas procedentes;"
    "Quantidade de reclamações reguladas - outras;Quantidade de reclamações não reguladas;Quantidade total de reclamações;"
    "Quantidade total de clientes – CCS e SCR;Quantidade de clientes – CCS;Quantidade de clientes – SCR;\n"
    "2023;2º;Top 15 - Bancos, Financeiras e Instituições de Pagamento;Conglomerado; ;BRADESCO (conglomerado);30,90;3229;4046;1823;9098;104486688;99093388;39040112;\n"
    "2023;2º;Top 15 - Bancos, Financeiras e Instituições de Pagamento;Conglomerado; ;ITAU (conglomerado);20,27;2026;4320;1716;8062;99936353;82355126;53998137;\n"
    "2023;2º;Top 15 - Bancos, Financeiras e Instituições de Pagamento;Conglomerado; ;NUBANK (conglomerado);7,82;608;1363;487;2458;77665209;75945491;42902746;\n"
    "2023;2º;Demais;Banco/financeira;60701190;ITAU UNIBANCO S.A.;1,0;10;10;10;30;1000;1000;1000;\n"
)
RANKING_NOVO = (
    "Ano;Trimestre;Categoria;Tipo;CNPJ IF;Instituição financeira;Índice;Quantidade total de reclamações respondidas;"
    "Quantidade de reclamações procedentes;Quantidade de reclamações procedentes extrapoladas;Quantidade total de reclamações analisadas;"
    "Quantidade total de clientes – CCS e SCR;Quantidade de clientes – CCS;Quantidade de clientes – SCR\r\n"
    "2026;2º;Top 15 - Bancos, Financeiras e Instituições de Pagamento;Conglomerado; ;99PAY IP (conglomerado);6,01;1448;68;170;580;28239602;28239599;3\r\n"
    "2026;2º;Top 15 - Bancos, Financeiras e Instituições de Pagamento;Conglomerado; ;BRADESCO (conglomerado);84,90;46204;495;9375;2495;110412514;104510875;44337840\r\n"
    "2026;2º;Top 15 - Bancos, Financeiras e Instituições de Pagamento;Conglomerado; ;ITAU (conglomerado);46,87;28687;426;4596;2811;98052200;83431217;51978796\r\n"
    "2026;2º;Top 15 - Bancos, Financeiras e Instituições de Pagamento;Conglomerado; ;NU PAGAMENTOS (conglomerado);9,20;26330;83;1080;1743;117259020;115294015;72839966\r\n"
)
IRREG_NOVO = (
    "Ano;Trimestre;Categoria;Tipo;CNPJ IF;Instituição financeira;Irregularidade;Quantidade de reclamações procedentes;\n"
    "2026;2º;Top 15;Conglomerado; ;99PAY IP (conglomerado);Cobranças diversas de IPs;3;\n"
    "2026;2º;Top 15;Conglomerado; ;NU PAGAMENTOS (conglomerado);Abertura de conta de pagamento sem documentação necessária ou com documentação falsa;26;\n"
    "2026;2º;Top 15;Conglomerado; ;NU PAGAMENTOS (conglomerado);Bloqueio de valores ou de conta fora do âmbito do Pix;39;\n"
    "2026;2º;Top 15;Conglomerado; ;NU PAGAMENTOS (conglomerado);Ausência de título adequado relativo a cartão de crédito;0;\n"
    "2026;2º;Top 15;Conglomerado; ;ITAU (conglomerado);Bloqueio de valores ou de conta fora do âmbito do Pix;12;\n"
)
IRREG_ANTIGO = (
    "Ano;Trimestre;Categoria;Tipo;CNPJ IF;Instituição financeira;Irregularidade;Quantidade de reclamações reguladas procedentes;"
    "Quantidade de reclamações reguladas - outras;Quantidade de reclamações não reguladas;Quantidade total de reclamações;\n"
    "2021;3º;Top 10 - Bancos e Financeiras;Conglomerado; ;BRADESCO (conglomerado);Abertura de conta de depósito com documentação falsa;71;10;0;81;\n"
    "2021;3º;Top 10 - Bancos e Financeiras;Conglomerado; ;NUBANK (conglomerado);Abertura de conta de depósito com documentação falsa;5;1;0;6;\n"
)
HISTORY_HTML = """
<a href="?wicket:interface=:0:1::::">2026</a><a href="?wicket:interface=:0:3::::">2024</a>
<h2>2024</h2>
<div id="cronoGrupoMes"><h3><span>2° Semestre</span></h3><ul><li><span>
<a href="?wicket:interface=:1:17::::"><span>Consórcios - Irregularidades por administradora de consórcio (CSV - 95,6 kB)</span></a></span></li></ul></div>
<div id="cronoGrupoMes"><h3><span>4° Trimestre</span></h3><ul><li><span>
<a id="linkDownloadArquivo" href="?wicket:interface=:1:21::::"><span>Bancos e financeiras - Irregularidades por instituição financeira (CSV - 912,0 kB)</span></a><br>
</span><span><a href="?wicket:interface=:1:22::::"><span>Bancos e financeiras - Tabela de irregularidades (CSV - 62,9 kB)</span></a></span></li></ul></div>
<div id="cronoGrupoMes"><h3><span>3° Trimestre</span></h3><ul><li><span>
<a href="?wicket:interface=:1:25::::"><span>Bancos e financeiras - Irregularidades por instituição financeira (CSV - 900 kB)</span></a></span></li></ul></div>
"""


def _csv(text):
    return read_bcb_csv(decode_bytes(text.encode("cp1252")))


class TestParseNumber(unittest.TestCase):
    def test_brazilian_formats(self):
        self.assertEqual(parse_number("1.234"), 1234.0)
        self.assertEqual(parse_number("12,34"), 12.34)
        self.assertEqual(parse_number(" 0 "), 0.0)
        self.assertEqual(parse_number("100.000.000"), 100000000.0)
        self.assertIsNone(parse_number(""))


class TestRanking(unittest.TestCase):
    def test_formato_antigo(self):
        out = select_banks_ranking(_csv(RANKING_ANTIGO))
        self.assertEqual(sorted(out["ticker"]), ["BBD", "ITUB", "NU"])
        nu = out[out.ticker == "NU"].iloc[0]
        self.assertEqual(nu["periodo"], "2023-T2")
        self.assertEqual(nu["procedentes"], 608)
        self.assertEqual(nu["metodologia"], "reguladas procedentes")
        self.assertEqual(nu["total"], 2458)
        # Usa a linha do conglomerado, não a entidade avulsa do Itaú
        itub = out[out.ticker == "ITUB"].iloc[0]
        self.assertAlmostEqual(itub["indice"], 20.27)

    def test_formato_novo(self):
        out = select_banks_ranking(_csv(RANKING_NOVO))
        self.assertEqual(sorted(out["ticker"]), ["BBD", "ITUB", "NU"])
        nu = out[out.ticker == "NU"].iloc[0]
        self.assertEqual(nu["procedentes"], 1080)  # extrapoladas (base do índice)
        self.assertEqual(nu["procedentes_amostra"], 83)
        self.assertEqual(nu["total"], 26330)  # respondidas
        self.assertEqual(nu["clientes"], 117259020)
        self.assertAlmostEqual(nu["indice"], 9.20)
        self.assertEqual(nu["metodologia"], "procedentes extrapoladas")


class TestIrregularidades(unittest.TestCase):
    def test_formato_novo(self):
        out = select_banks_irregularidades(_csv(IRREG_NOVO))
        self.assertEqual(set(out["ticker"]), {"NU", "ITUB"})
        nu = out[out.ticker == "NU"]
        self.assertEqual(len(nu), 2)  # linhas com zero são descartadas
        self.assertEqual(nu.iloc[0]["procedentes"], 39)
        self.assertEqual(nu.iloc[0]["periodo"], "2026-T2")

    def test_formato_antigo(self):
        out = select_banks_irregularidades(_csv(IRREG_ANTIGO))
        self.assertEqual(set(out["ticker"]), {"NU", "BBD"})
        self.assertEqual(out[out.ticker == "BBD"].iloc[0]["procedentes"], 71)


class TestTemas(unittest.TestCase):
    def test_classificacao(self):
        self.assertEqual(classify_theme("Pix - chaves"), "Pix")
        self.assertEqual(classify_theme("Bloqueio de valores ou de conta fora do âmbito do Pix"), "Conta (abertura, bloqueio, encerramento)")
        self.assertEqual(classify_theme("Transações não reconhecidas pelo titular da conta, realizadas por terceiros (invasão de conta)"), "Segurança e fraude")
        self.assertEqual(classify_theme("Limites de transação"), "Outros")
        self.assertEqual(
            classify_theme("Irregularidades relacionadas ao fornecimento de outros documentos, exceto os relativos a cartão de crédito"),
            "Atendimento e informação",
        )
        self.assertEqual(classify_theme("Irregularidades relativas a operações de crédito de saldo devedor de fatura de cartão de crédito"), "Cartão de crédito")

    def test_nome_curto(self):
        self.assertEqual(short_irregularity("Pix - liquidação - instituição de pagamento"), "Pix - liquidação")
        self.assertEqual(short_irregularity("Pix  - chaves"), "Pix - chaves")


class TestModoDormir(unittest.TestCase):
    def _dfs(self, ultimo_ranking, ultimo_irreg):
        import pandas as pd
        return (pd.DataFrame({"periodo": ["2026-T1", ultimo_ranking]}),
                pd.DataFrame({"periodo": ["2026-T1", ultimo_irreg]}))

    def test_dorme_ate_fim_do_proximo_trimestre(self):
        from datetime import date
        r, i = self._dfs("2026-T2", "2026-T2")
        self.assertEqual(sleep_until(r, i, date(2026, 8, 15)), date(2026, 9, 30))
        self.assertEqual(sleep_until(r, i, date(2026, 9, 30)), date(2026, 9, 30))

    def test_acorda_quando_o_trimestre_fecha(self):
        from datetime import date
        r, i = self._dfs("2026-T2", "2026-T2")
        self.assertIsNone(sleep_until(r, i, date(2026, 10, 9)))

    def test_virada_de_ano(self):
        from datetime import date
        r, i = self._dfs("2026-T4", "2026-T4")
        self.assertEqual(sleep_until(r, i, date(2027, 2, 1)), date(2027, 3, 31))

    def test_nao_dorme_se_faltam_irregularidades(self):
        from datetime import date
        r, i = self._dfs("2026-T2", "2026-T1")
        self.assertIsNone(sleep_until(r, i, date(2026, 8, 15)))


class TestHistorico(unittest.TestCase):
    def test_links(self):
        links = _parse_history(HISTORY_HTML)
        years = {t: h for t, h, _ in links if t.isdigit()}
        self.assertEqual(years["2024"], "?wicket:interface=:0:3::::")
        irr = [(g, h) for t, h, g in links if "Bancos e financeiras - Irregularidades" in t]
        self.assertEqual(irr, [("4° Trimestre", "?wicket:interface=:1:21::::"), ("3° Trimestre", "?wicket:interface=:1:25::::")])


class TestCatalogEMerge(unittest.TestCase):
    def test_available_quarters(self):
        catalog = {"anos": [
            {"ano": "2020", "periodicidades": [{"periodicidade": "TRIMESTRAL", "periodos": [{"periodo": 4, "tipos": [{"tipo": "Bancos e financeiras"}]}]}]},
            {"ano": "2025", "periodicidades": [
                {"periodicidade": "SEMESTRAL", "periodos": [{"periodo": 1, "tipos": [{"tipo": "Consorcios"}]}]},
                {"periodicidade": "TRIMESTRAL", "periodos": [
                    {"periodo": 1, "tipos": [{"tipo": "Bancos e financeiras"}]},
                    {"periodo": 2, "tipos": []},
                ]},
            ]},
        ]}
        self.assertEqual(available_quarters(catalog), [(2025, 1)])

    def test_merge_substitui_periodo(self):
        old = select_banks_irregularidades(_csv(IRREG_NOVO))
        new = old[old.ticker == "ITUB"].copy()
        merged = _merge(old, new, ["periodo", "ticker", "irregularidade"])
        self.assertEqual(set(merged["ticker"]), {"ITUB"})


if __name__ == "__main__":
    unittest.main()
