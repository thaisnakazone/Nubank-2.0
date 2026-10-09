"""
Ingestão automática do Ranking de Reclamações do Banco Central (BCB) para NU, ITUB e BBD.

Tudo é coletado direto do site do BCB, sem nenhum download manual:

1. **Ranking trimestral** (API oficial)
   https://www3.bcb.gov.br/rdrweb/rest/ext/ranking                     -> catálogo de períodos
   https://www3.bcb.gov.br/rdrweb/rest/ext/ranking/arquivo?ano=..&periodicidade=TRIMESTRAL&periodo=..&tipo=Bancos+e+financeiras
   Índice de reclamações, reclamações procedentes e quantidade de clientes por instituição.

2. **Irregularidades por instituição financeira** (página de histórico do ranking)
   https://www3.bcb.gov.br/ranking/historico.do
   O detalhamento por tipo de irregularidade não está na API; o script navega pela página
   de histórico (ano -> trimestre) e baixa o CSV "Irregularidades por instituição financeira".

Metodologia do BCB:
- Até 2024, os arquivos trazem "reclamações reguladas procedentes", "reguladas - outras"
  e "não reguladas".
- A partir do fim de 2024, trazem "reclamações procedentes" (amostra analisada) e
  "procedentes extrapoladas" (estimativa para o total). O índice oficial usa as extrapoladas.
- Para manter a série comparável, a coluna `procedentes` guarda o número usado no índice
  (reguladas procedentes no formato antigo; procedentes extrapoladas no novo).

Saídas:
- data/processed/bcb_ranking.csv e data/processed/bcb_irregularidades.csv (versionados)
- MongoDB Atlas: coleções `ranking_reclamacoes_bcb` e `irregularidades_bcb` (upsert idempotente)

Calendário ("modo dormir"):
- O ranking de um trimestre só pode existir depois que o trimestre termina. Depois de
  coletar o trimestre N, o script não consulta o BC até o fim do trimestre N+1; a partir
  daí volta a checar a cada execução (o workflow roda às sextas) até o novo dado sair.
- Nos últimos dois anos o BC publicou sempre numa quinta-feira, cerca de 3 semanas e meia
  após o fim do trimestre, e não houve correção de rankings já publicados.

Uso:
    python -m src.ingest_bcb_ranking              # coleta incremental (respeita o modo dormir)
    python -m src.ingest_bcb_ranking --forcar     # ignora o modo dormir e consulta o BC agora
    python -m src.ingest_bcb_ranking --completo   # recoleta todos os trimestres desde 2021
"""
from __future__ import annotations

import argparse
import io
import re
import sys
import time
import unicodedata
from datetime import date, datetime, timezone
from html.parser import HTMLParser
from pathlib import Path
from typing import Iterable

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
PROCESSED = ROOT / "data" / "processed"
RANKING_CSV = PROCESSED / "bcb_ranking.csv"
IRREG_CSV = PROCESSED / "bcb_irregularidades.csv"

HOST = "https://www3.bcb.gov.br"
API_BASE = f"{HOST}/rdrweb/rest/ext/ranking"
HISTORY_URL = f"{HOST}/ranking/historico.do"
TIPO = "Bancos e financeiras"
ANO_INICIAL = 2021
TIMEOUT = 60
PAUSE = 0.5  # segundos entre downloads, para não sobrecarregar o site do BCB

# Os bancos aparecem como conglomerados (sem CNPJ) — ex.: "NU PAGAMENTOS (conglomerado)",
# "NUBANK (conglomerado)" (nome usado até 2024), "ITAU (conglomerado)", "BRADESCO (conglomerado)".
BANKS = {
    "NU": {"cnpj": ("18236120",), "nome": r"\bNU PAGAMENTOS\b|\bNUBANK\b|\bNU FINANCEIRA\b"},
    "ITUB": {"cnpj": ("60701190",), "nome": r"\bITAU\b"},
    "BBD": {"cnpj": ("60746948",), "nome": r"\bBRADESCO\b"},
}

RANKING_COLUMNS = [
    "ticker", "periodo", "ano", "periodicidade", "periodo_num", "instituicao", "categoria", "metodologia",
    "indice", "procedentes", "procedentes_amostra", "reguladas_outras", "nao_reguladas", "total", "clientes",
]
IRREG_COLUMNS = [
    "ticker", "periodo", "ano", "periodicidade", "periodo_num", "irregularidade",
    "irregularidade_curta", "tema", "procedentes",
]

# Temas para agrupar as ~200 irregularidades do BCB (a ordem importa: a 1ª regra que casar vence)
THEMES: list[tuple[str, tuple[str, ...]]] = [
    ("Segurança e fraude", ("integridade, confiabilidade", "transacoes nao reconhecidas", "invasao de conta", "documentacao falsa", "documentacao ausente")),
    ("Cadastros (SCR, CCS, SVR)", ("(scr)", "(ccs)", " svr ")),
    ("Tarifas e débitos", ("tarifa", "debito", "pacote de servicos")),
    ("Cartão de crédito", ("cartao de credito", "cartoes de credito")),
    ("Crédito e empréstimos", ("credito",)),
    ("Atendimento e informação", (" sac ", "ouvidoria", "atendimento", "resposta", "oferta ou prestacao", "transparencia", "fornecimento de")),
    ("Conta (abertura, bloqueio, encerramento)", ("conta", "cancelamento de contrato")),
]


def short_irregularity(name: str) -> str:
    """Remove o sufixo ' - instituição de pagamento' e espaços duplicados (une as variantes banco/IP)."""
    text = " ".join(str(name).split())
    return re.sub(r"\s*-\s*institui[cç][aã]o de pagamento$", "", text, flags=re.IGNORECASE).strip()


def classify_theme(name: str) -> str:
    n = f" {_norm(name)} "
    n = n.split(" exceto ")[0] + " "  # ignora o que vem depois de "exceto ..."
    if n.strip().startswith("pix"):
        return "Pix"
    for theme, keys in THEMES:
        if any(k in n for k in keys):
            return theme
    return "Outros"


NUMERIC_ROLES = [
    "indice", "procedentes_extrap", "procedentes_reg", "procedentes_new", "reguladas_outras",
    "nao_reguladas", "total", "respondidas", "analisadas", "clientes",
]


# ----------------------------------------------------------------------------
# Leitura e normalização dos CSVs do BCB
# ----------------------------------------------------------------------------
def _norm(text: object) -> str:
    value = "" if text is None else str(text)
    value = value.replace("–", "-").replace("—", "-")
    value = unicodedata.normalize("NFKD", value).encode("ascii", "ignore").decode("ascii")
    return " ".join(value.lower().strip().split())


def decode_bytes(raw: bytes) -> str:
    """Os arquivos do BCB vêm em Windows-1252 (apesar do cabeçalho HTTP dizer UTF-8)."""
    for enc in ("utf-8-sig", "cp1252", "latin-1"):
        try:
            return raw.decode(enc)
        except UnicodeDecodeError:
            continue
    return raw.decode("latin-1", errors="replace")


def parse_number(value: object) -> float | None:
    """Converte números no padrão brasileiro ('1.234', '12,34', '1.234,5', ' 0 ') para float."""
    if value is None:
        return None
    text = str(value).strip().replace("\xa0", "").replace(" ", "")
    if text in {"", "-", "--", "nan", "None"}:
        return None
    if "," in text:
        text = text.replace(".", "").replace(",", ".")
    elif re.fullmatch(r"-?\d{1,3}(\.\d{3})+", text):
        text = text.replace(".", "")
    try:
        return float(text)
    except ValueError:
        return None


def _column_role(header: str) -> str | None:
    h = _norm(header)
    if not h:
        return None
    if h == "ano":
        return "ano"
    if h in {"trimestre", "semestre", "bimestre", "mes"}:
        return f"per:{h}"
    if h == "categoria":
        return "categoria"
    if h == "tipo":
        return "tipo"
    if h.startswith("cnpj"):
        return "cnpj"
    if h.startswith("instituicao") or h.startswith("administradora"):
        return "instituicao"
    if h.startswith("irregularidade"):
        return "irregularidade"
    if h.startswith("indice"):
        return "indice"
    if "nao reguladas" in h:
        return "nao_reguladas"
    if "procedentes extrapoladas" in h:
        return "procedentes_extrap"
    if "reguladas procedentes" in h:
        return "procedentes_reg"
    if "reguladas" in h and "outras" in h:
        return "reguladas_outras"
    if "procedentes" in h:
        return "procedentes_new"
    if "reclamacoes respondidas" in h:
        return "respondidas"
    if "reclamacoes analisadas" in h:
        return "analisadas"
    if "total de reclamacoes" in h:
        return "total"
    if "total de clientes" in h:
        return "clientes"
    return None


def read_bcb_csv(text: str) -> pd.DataFrame:
    """Lê um CSV do BCB (separador ';', ';' sobrando no fim da linha, linhas \\r\\n)."""
    lines = [ln.rstrip("\r") for ln in text.splitlines()]
    header_idx = next((i for i, ln in enumerate(lines) if "cnpj" in _norm(ln)), None)
    if header_idx is None:
        raise ValueError("Cabeçalho com 'CNPJ' não encontrado no arquivo do BCB.")
    header = lines[header_idx]
    sep = ";" if header.count(";") >= header.count(",") else ","
    body = "\n".join(lines[header_idx:])
    df = pd.read_csv(io.StringIO(body), sep=sep, dtype=str, keep_default_na=False, engine="python")
    df = df.loc[:, [c for c in df.columns if str(c).strip() and not str(c).startswith("Unnamed")]]

    renamed: dict[str, str] = {}
    periodicidade = None
    for col in df.columns:
        role = _column_role(col)
        if role is None or role in renamed.values():
            continue
        if role.startswith("per:"):
            periodicidade = role.split(":", 1)[1]
            renamed[col] = "periodo_num"
        else:
            renamed[col] = role
    out = df.rename(columns=renamed)[list(renamed.values())].copy()
    for col in out.columns:
        out[col] = out[col].astype(str).str.strip()
    if "instituicao" in out.columns:
        out = out[out["instituicao"] != ""]
    out.attrs["periodicidade"] = periodicidade
    return out


def _period_label(ano: int, periodicidade: str | None, num: int | None) -> str:
    code = {"trimestre": "T", "semestre": "S", "bimestre": "B", "mes": "M"}.get(periodicidade or "", "T")
    return f"{ano}-{code}{num}" if num else str(ano)


def _match_ticker(cnpj: str, nome: str) -> str | None:
    digits = re.sub(r"\D", "", cnpj or "")
    if digits:
        for ticker, rule in BANKS.items():
            if any(digits.startswith(root) for root in rule["cnpj"]):
                return ticker
    name = _norm(nome).upper()
    for ticker, rule in BANKS.items():
        if re.search(rule["nome"], name):
            return ticker
    return None


def _tag_banks(df: pd.DataFrame) -> pd.DataFrame:
    """Marca o ticker de cada linha e, quando existe a linha do conglomerado, descarta as entidades avulsas."""
    df = df.copy()
    cnpjs = df["cnpj"] if "cnpj" in df.columns else pd.Series([""] * len(df), index=df.index)
    df["ticker"] = [_match_ticker(c, n) for c, n in zip(cnpjs, df["instituicao"])]
    df = df[df["ticker"].notna()].copy()
    if df.empty:
        return df
    tipo = df["tipo"] if "tipo" in df.columns else pd.Series([""] * len(df), index=df.index)
    df["_cong"] = df["instituicao"].str.contains("conglomerado", case=False) | tipo.str.contains("conglomerado", case=False)
    has_cong = df.groupby("ticker")["_cong"].transform("any")
    return df[~has_cong | df["_cong"]].drop(columns="_cong")


def _numeric(df: pd.DataFrame, cols: Iterable[str]) -> pd.DataFrame:
    for col in cols:
        df[col] = df[col].map(parse_number) if col in df.columns else None
    return df


def _with_period(df: pd.DataFrame, ano: int | None, periodicidade: str | None, num: int | None) -> pd.DataFrame:
    per = periodicidade or df.attrs.get("periodicidade") or "trimestre"
    if "ano" in df.columns:
        df["ano"] = df["ano"].map(lambda v: int(parse_number(v) or 0) or ano)
    else:
        df["ano"] = ano
    if "periodo_num" in df.columns:
        df["periodo_num"] = df["periodo_num"].map(lambda v: int(re.sub(r"\D", "", str(v)) or 0) or num)
    else:
        df["periodo_num"] = num
    df["periodicidade"] = per
    df["periodo"] = [_period_label(int(a), per, int(n) if n else None) for a, n in zip(df["ano"], df["periodo_num"])]
    return df


def select_banks_ranking(df: pd.DataFrame, ano: int | None = None, periodicidade: str | None = None, num: int | None = None) -> pd.DataFrame:
    """Filtra NU/ITUB/BBD no arquivo de ranking, nos dois formatos de metodologia do BCB."""
    if df.empty or "instituicao" not in df.columns:
        return pd.DataFrame(columns=RANKING_COLUMNS)
    df = _tag_banks(df)
    if df.empty:
        return pd.DataFrame(columns=RANKING_COLUMNS)
    df = _numeric(df, NUMERIC_ROLES)
    df = _with_period(df, ano, periodicidade, num)

    new_method = df["procedentes_extrap"].notna().any()
    df["metodologia"] = "procedentes extrapoladas" if new_method else "reguladas procedentes"
    df["procedentes"] = df["procedentes_extrap"] if new_method else df["procedentes_reg"]
    df["procedentes_amostra"] = df["procedentes_new"] if new_method else None
    df["total"] = df["total"].where(df["total"].notna(), df["respondidas"])

    df["_ord"] = df["clientes"].fillna(-1) * 1e6 + df["total"].fillna(-1)
    df = df.sort_values("_ord", ascending=False).drop_duplicates(["ticker", "periodo"]).drop(columns="_ord")
    missing_idx = df["indice"].isna() & df["clientes"].fillna(0).gt(0)
    df.loc[missing_idx, "indice"] = df.loc[missing_idx, "procedentes"] / df.loc[missing_idx, "clientes"] * 1e6
    if "categoria" not in df.columns:
        df["categoria"] = ""
    return df[RANKING_COLUMNS].sort_values(["periodo", "ticker"]).reset_index(drop=True)


def select_banks_irregularidades(df: pd.DataFrame, ano: int | None = None, periodicidade: str | None = None, num: int | None = None) -> pd.DataFrame:
    """Filtra NU/ITUB/BBD no arquivo de irregularidades e soma por banco/período/irregularidade."""
    if df.empty or "irregularidade" not in df.columns:
        return pd.DataFrame(columns=IRREG_COLUMNS)
    df = _tag_banks(df)
    if df.empty:
        return pd.DataFrame(columns=IRREG_COLUMNS)
    df = _numeric(df, NUMERIC_ROLES)
    df = _with_period(df, ano, periodicidade, num)
    df["procedentes"] = df["procedentes_reg"].where(df["procedentes_reg"].notna(), df["procedentes_new"])
    df["procedentes"] = df["procedentes"].where(df["procedentes"].notna(), df["procedentes_extrap"])
    df["irregularidade"] = df["irregularidade"].str.strip()
    grouped = df.groupby(["ticker", "periodo", "ano", "periodicidade", "periodo_num", "irregularidade"], as_index=False)["procedentes"].sum(min_count=1)
    grouped = grouped[grouped["procedentes"].fillna(0) > 0].copy()
    grouped["irregularidade_curta"] = grouped["irregularidade"].map(short_irregularity)
    grouped["tema"] = grouped["irregularidade"].map(classify_theme)
    return grouped[IRREG_COLUMNS].sort_values(["periodo", "ticker", "procedentes"], ascending=[True, True, False]).reset_index(drop=True)


# ----------------------------------------------------------------------------
# API do ranking
# ----------------------------------------------------------------------------
def available_quarters(catalog: dict, start_year: int = ANO_INICIAL) -> list[tuple[int, int]]:
    """Extrai do catálogo os trimestres de 'Bancos e financeiras' a partir de start_year."""
    out: list[tuple[int, int]] = []
    for year in catalog.get("anos", []):
        ano = int(year.get("ano", 0))
        if ano < start_year:
            continue
        for per in year.get("periodicidades", []):
            if str(per.get("periodicidade", "")).upper() != "TRIMESTRAL":
                continue
            for p in per.get("periodos", []):
                tipos = {_norm(t.get("tipo")) for t in p.get("tipos", [])}
                if _norm(TIPO) in tipos:
                    out.append((ano, int(p["periodo"])))
    return sorted(set(out))


def fetch_catalog(session) -> dict:
    resp = session.get(API_BASE, timeout=TIMEOUT)
    resp.raise_for_status()
    return resp.json()


def fetch_ranking(session, ano: int, trimestre: int) -> pd.DataFrame:
    params = {"ano": ano, "periodicidade": "TRIMESTRAL", "periodo": trimestre, "tipo": TIPO}
    resp = session.get(f"{API_BASE}/arquivo", params=params, timeout=TIMEOUT)
    resp.raise_for_status()
    return select_banks_ranking(read_bcb_csv(decode_bytes(resp.content)), ano, "trimestre", trimestre)


# ----------------------------------------------------------------------------
# Página de histórico (irregularidades)
# ----------------------------------------------------------------------------
class _HistoryParser(HTMLParser):
    """
    Lê a página historico.do. Estrutura relevante:
        <a href="?wicket:interface=:0:3::::">2024</a>                      (links dos anos)
        <div id="cronoGrupoMes"><h3><span>4° Trimestre</span></h3>
            <ul><li><span><a href="?wicket:..."><span>Bancos e financeiras - Irregularidades por ...</span></a>
    """

    def __init__(self) -> None:
        super().__init__()
        self.links: list[tuple[str, str, str]] = []  # (texto, href, título do grupo h3)
        self._href: str | None = None
        self._text: list[str] = []
        self._in_h3 = False
        self._h3: list[str] = []
        self.current_group = ""

    def handle_starttag(self, tag, attrs):
        if tag == "a":
            self._href = dict(attrs).get("href")
            self._text = []
        elif tag == "h3":
            self._in_h3 = True
            self._h3 = []

    def handle_endtag(self, tag):
        if tag == "a" and self._href is not None:
            self.links.append((" ".join("".join(self._text).split()), self._href, self.current_group))
            self._href = None
        elif tag == "h3":
            self._in_h3 = False
            self.current_group = " ".join("".join(self._h3).split())

    def handle_data(self, data):
        if self._href is not None:
            self._text.append(data)
        if self._in_h3:
            self._h3.append(data)


def _parse_history(html: str) -> list[tuple[str, str, str]]:
    parser = _HistoryParser()
    parser.feed(html)
    return parser.links


def irregularity_links_for_year(session, ano: int) -> dict[int, str]:
    """Abre o histórico, entra no ano e devolve {trimestre: href do CSV de irregularidades}."""
    home = session.get(HISTORY_URL, timeout=TIMEOUT)
    home.raise_for_status()
    year_href = next((href for text, href, _ in _parse_history(home.text) if text == str(ano)), None)
    if not year_href:
        return {}
    page = session.get(HISTORY_URL + year_href, timeout=TIMEOUT)
    page.raise_for_status()
    found: dict[int, str] = {}
    for text, href, group in _parse_history(page.text):
        g = _norm(group)
        if "trimestre" not in g or "irregularidades por instituicao" not in _norm(text):
            continue
        if "bancos e financeiras" not in _norm(text):
            continue
        num = re.search(r"\d+", g)
        if num:
            found.setdefault(int(num.group()), href)
    return found


def fetch_irregularities(session, quarters: list[tuple[int, int]]) -> pd.DataFrame:
    frames = []
    for ano in sorted({a for a, _ in quarters}):
        wanted = sorted(t for a, t in quarters if a == ano)
        try:
            links = irregularity_links_for_year(session, ano)
        except Exception as exc:  # noqa: BLE001
            print(f"  · {ano}: histórico indisponível ({exc})", file=sys.stderr)
            continue
        for tri in wanted:
            href = links.get(tri)
            if not href:
                print(f"  · {ano}-T{tri}: arquivo de irregularidades não encontrado", file=sys.stderr)
                continue
            try:
                resp = session.get(HISTORY_URL + href, timeout=TIMEOUT)
                resp.raise_for_status()
                df = select_banks_irregularidades(read_bcb_csv(decode_bytes(resp.content)), ano, "trimestre", tri)
                print(f"  · {ano}-T{tri}: {len(df)} linhas ({', '.join(sorted(df['ticker'].unique())) or 'nenhum banco'})")
                frames.append(df)
            except Exception as exc:  # noqa: BLE001
                print(f"  · {ano}-T{tri}: falhou ({exc})", file=sys.stderr)
            time.sleep(PAUSE)
    if not frames:
        return pd.DataFrame(columns=IRREG_COLUMNS)
    return pd.concat(frames, ignore_index=True)


# ----------------------------------------------------------------------------
# Persistência
# ----------------------------------------------------------------------------
def _load_existing(path: Path, columns: list[str]) -> pd.DataFrame:
    if path.exists():
        return pd.read_csv(path)
    return pd.DataFrame(columns=columns)


def _merge(old: pd.DataFrame, new: pd.DataFrame, keys: list[str], replace_periods: Iterable[str] = ()) -> pd.DataFrame:
    """Junta séries; períodos recoletados substituem integralmente os antigos."""
    if new.empty:
        return old
    replace = set(replace_periods) | set(new["periodo"].astype(str))
    if not old.empty:
        old = old[~old["periodo"].astype(str).isin(replace)]
    both = pd.concat([old, new], ignore_index=True) if not old.empty else new.copy()
    return both.drop_duplicates(keys, keep="last").sort_values(keys).reset_index(drop=True)


def save_to_mongo(ranking: pd.DataFrame, irreg: pd.DataFrame) -> str:
    try:
        from pymongo import DeleteMany, UpdateOne
        from database.connection import get_database, get_mongo_client, get_mongo_uri
    except ImportError as exc:  # pragma: no cover
        return f"MongoDB ignorado ({exc})"

    uri = get_mongo_uri()
    if not uri:
        return "MongoDB ignorado (MONGO_URI não configurada)"

    stamp = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    client = None
    try:
        client = get_mongo_client(uri)
        db = get_database(client)
        col_r = db["ranking_reclamacoes_bcb"]
        col_i = db["irregularidades_bcb"]
        col_r.create_index([("ticker", 1), ("periodo", 1)], unique=True)
        col_i.create_index([("ticker", 1), ("periodo", 1), ("irregularidade", 1)], unique=True)

        def docs(df: pd.DataFrame) -> list[dict]:
            clean = df.astype(object).where(pd.notna(df), None)
            return [{**row, "coletado_em": stamp} for row in clean.to_dict(orient="records")]

        ops_r = [UpdateOne({"ticker": d["ticker"], "periodo": d["periodo"]}, {"$set": d}, upsert=True) for d in docs(ranking)]
        # Irregularidades: cada período é regravado por inteiro (o BCB pode renomear tipos)
        periods = sorted(set(irreg["periodo"].astype(str))) if not irreg.empty else []
        ops_i = [DeleteMany({"periodo": {"$in": periods}})] if periods else []
        ops_i += [
            UpdateOne({"ticker": d["ticker"], "periodo": d["periodo"], "irregularidade": d["irregularidade"]}, {"$set": d}, upsert=True)
            for d in docs(irreg)
        ]
        n_r = col_r.bulk_write(ops_r, ordered=True).upserted_count if ops_r else 0
        n_i = col_i.bulk_write(ops_i, ordered=True).upserted_count if ops_i else 0
        return f"MongoDB Atlas atualizado ({n_r} novos registros de ranking, {n_i} registros de irregularidades)"
    except Exception as exc:  # noqa: BLE001 - não interrompe o pipeline por falha de banco
        return f"Falha ao gravar no MongoDB Atlas: {type(exc).__name__}"
    finally:
        if client:
            client.close()


def _quarter_of(periodo: object) -> tuple[int, int] | None:
    m = re.fullmatch(r"(\d{4})-T([1-4])", str(periodo).strip())
    return (int(m.group(1)), int(m.group(2))) if m else None


def _quarter_end(ano: int, tri: int) -> date:
    return {1: date(ano, 3, 31), 2: date(ano, 6, 30), 3: date(ano, 9, 30), 4: date(ano, 12, 31)}[tri]


def sleep_until(ranking: pd.DataFrame, irreg: pd.DataFrame, today: date) -> date | None:
    """
    Devolve a data até a qual não vale consultar o BC, ou None se é hora de checar.

    Regra: com o trimestre N já coletado (ranking E irregularidades), o próximo dado
    possível é o do trimestre N+1, que só pode ser publicado depois que ele termina.
    """
    if ranking.empty or irreg.empty:
        return None
    qs_r = [q for q in map(_quarter_of, ranking["periodo"]) if q]
    qs_i = [q for q in map(_quarter_of, irreg["periodo"]) if q]
    if not qs_r or not qs_i:
        return None
    latest = max(qs_r)
    if max(qs_i) != latest:  # irregularidades do último trimestre faltando: tenta de novo
        return None
    ano, tri = latest
    nxt = (ano + 1, 1) if tri == 4 else (ano, tri + 1)
    end = _quarter_end(*nxt)
    return end if today <= end else None


def run(full: bool = False, force: bool = False, today: date | None = None) -> int:
    PROCESSED.mkdir(parents=True, exist_ok=True)
    ranking = _load_existing(RANKING_CSV, RANKING_COLUMNS)
    irreg = _load_existing(IRREG_CSV, IRREG_COLUMNS)

    today = today or datetime.now(timezone.utc).date()
    wake = None if (full or force) else sleep_until(ranking, irreg, today)
    if wake:
        last = max(q for q in map(_quarter_of, ranking["periodo"]) if q)
        print(
            f"Modo dormir: o último trimestre coletado é {last[0]}-T{last[1]}; o próximo ranking "
            f"só pode sair depois de {wake:%d/%m/%Y}. Nada a consultar hoje ({today:%d/%m/%Y})."
        )
        return 0

    import requests

    session = requests.Session()
    session.headers["User-Agent"] = "Nubank-2.0 (projeto academico; github.com/thaisnakazone/Nubank-2.0)"
    try:
        quarters = available_quarters(fetch_catalog(session))
    except Exception as exc:  # noqa: BLE001
        print(f"Não foi possível ler o catálogo do BCB: {exc}", file=sys.stderr)
        return 1
    if not quarters:
        print("Catálogo do BCB sem trimestres disponíveis.", file=sys.stderr)
        return 1
    latest = max(quarters)

    def pending(existing: pd.DataFrame) -> list[tuple[int, int]]:
        have = set() if full or existing.empty else set(existing["periodo"].astype(str))
        return [q for q in quarters if f"{q[0]}-T{q[1]}" not in have or q == latest]

    todo_r = pending(ranking)
    print(f"Ranking BCB: {len(quarters)} trimestres desde {ANO_INICIAL}; coletando {len(todo_r)}")
    frames = []
    for ano, tri in todo_r:
        try:
            df = fetch_ranking(session, ano, tri)
            print(f"  · {ano}-T{tri}: {', '.join(sorted(df['ticker'])) or 'nenhum banco encontrado'}")
            frames.append(df)
        except Exception as exc:  # noqa: BLE001
            print(f"  · {ano}-T{tri}: falhou ({exc})", file=sys.stderr)
        time.sleep(PAUSE)
    if frames:
        ranking = _merge(ranking, pd.concat(frames, ignore_index=True), ["periodo", "ticker"])

    todo_i = pending(irreg)
    print(f"Irregularidades BCB: coletando {len(todo_i)} trimestres")
    new_irreg = fetch_irregularities(session, todo_i)
    irreg = _merge(irreg, new_irreg, ["periodo", "ticker", "irregularidade"])

    if not ranking.empty:
        ranking.to_csv(RANKING_CSV, index=False)
    if not irreg.empty:
        irreg.to_csv(IRREG_CSV, index=False)
    print(f"Arquivos processados: {len(ranking)} linhas de ranking, {len(irreg)} linhas de irregularidades")
    print(save_to_mongo(ranking, irreg))
    return 0 if not ranking.empty else 1


def main(argv: list[str] | None = None) -> int:
    if sys.platform == "win32":
        try:
            sys.stdout.reconfigure(encoding="utf-8", errors="replace")
            sys.stderr.reconfigure(encoding="utf-8", errors="replace")
        except Exception:  # noqa: BLE001
            pass
    if str(ROOT) not in sys.path:
        sys.path.insert(0, str(ROOT))
    parser = argparse.ArgumentParser(description="Ingestão automática do Ranking de Reclamações do BCB")
    parser.add_argument("--completo", action="store_true", help="recoleta todos os trimestres desde 2021")
    parser.add_argument("--forcar", action="store_true", help="ignora o modo dormir e consulta o BC agora")
    args = parser.parse_args(argv)
    return run(full=args.completo, force=args.forcar)


if __name__ == "__main__":
    sys.exit(main())
