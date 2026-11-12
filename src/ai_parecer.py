"""
Parecer da IA: uma leitura automática e diária dos números do dashboard.

Como funciona
1. Lê o payload já montado (docs/data/dashboard-data.json) e calcula um resumo
   pequeno de indicadores: crescimento, rentabilidade, capital, mercado, clientes e Selic.
2. Envia SÓ esse resumo para a API do Claude (Anthropic), pedindo uma resposta em JSON
   com formato fixo (structured outputs): um status por área (bom / atenção / ruim),
   um resumo curto e um conselho para a empresa.
3. Valida a resposta (formato, tamanho e ausência de recomendação de compra/venda).
4. Grava em data/processed/parecer_ia.json, no MongoDB (histórico) e no próprio
   dashboard-data.json, que o site lê.

Se a chave não estiver configurada ou a API falhar, o parecer anterior é mantido.
O parecer é gerado no máximo uma vez por dia (use --forcar para gerar de novo).

Uso:
    python -m src.ai_parecer                 # gera (ou reaproveita o de hoje)
    python -m src.ai_parecer --mostrar-dados # só mostra o que seria enviado à IA
    python -m src.ai_parecer --forcar        # gera de novo mesmo já existindo o de hoje
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import requests

ROOT = Path(__file__).resolve().parents[1]
PAYLOAD = ROOT / "docs" / "data" / "dashboard-data.json"
PARECER_JSON = ROOT / "data" / "processed" / "parecer_ia.json"

API_URL = "https://api.anthropic.com/v1/messages"
MODEL = os.getenv("ANTHROPIC_MODEL", "claude-haiku-5-5")
AREAS = ["crescimento", "rentabilidade", "capital", "mercado", "clientes"]
STATUS = ["bom", "atencao", "ruim"]
BASILEIA_MINIMO = 10.5  # mínimo regulatório + colchão de conservação (%)
AVISO = "Análise automática gerada por IA a partir dos dados do dashboard, para fins educacionais. Não é recomendação de investimento."

# Recomendação de compra/venda de ações é vetada (não somos analistas certificados pela CVM).
PROIBIDO = re.compile(
    r"\b(compr\w*|vend\w*|mant\w*)\s+(as\s+|a\s+|suas\s+|essas\s+)?(a[çc][õo]es|a[çc][ãa]o|pap[ée]is|ativos?|NU|ITUB|BBD)\b",
    re.IGNORECASE,
)

SYSTEM_PROMPT = """Você é um analista financeiro que escreve para um dashboard acadêmico sobre o Nubank (Nu Holdings), comparado a Itaú e Bradesco.
Regras:
- Use SOMENTE os números do JSON enviado pelo usuário. Não invente dados nem use conhecimento externo.
- Escreva em português do Brasil, frases curtas e claras para leigos. Cite números quando ajudar.
- Avalie cada área com status "bom", "atencao" ou "ruim" e um motivo de no máximo 1 frase (até ~160 caracteres).
- "resumo": 2 ou 3 frases dizendo se a empresa está bem e por quê (até ~400 caracteres).
- "conselho": 1 frase com o que a EMPRESA deveria priorizar para melhorar (até ~220 caracteres).
- NUNCA recomende comprar, vender ou manter ações, nem dê conselho de investimento pessoal.
- Capital: o Índice de Basileia mínimo exigido (com colchão) é 10,5%; avalie a folga acima disso.
- Mercado: considere que a variação da ação depende muito do período escolhido; compare com Itaú e Bradesco.
- Selic é contexto (custo do dinheiro e risco de crédito), não uma área avaliada."""

SCHEMA = {
    "type": "object",
    "properties": {
        "resumo": {"type": "string"},
        "areas": {
            "type": "object",
            "properties": {
                area: {
                    "type": "object",
                    "properties": {
                        "status": {"type": "string", "enum": STATUS},
                        "motivo": {"type": "string"},
                    },
                    "required": ["status", "motivo"],
                    "additionalProperties": False,
                }
                for area in AREAS
            },
            "required": AREAS,
            "additionalProperties": False,
        },
        "conselho": {"type": "string"},
    },
    "required": ["resumo", "areas", "conselho"],
    "additionalProperties": False,
}


# ---------------------------------------------------------------- indicadores
def _pct(a: float | None, b: float | None) -> float | None:
    if a is None or b in (None, 0):
        return None
    return round((a / b - 1) * 100, 1)


def _r(v: Any, n: int = 2) -> Any:
    return round(float(v), n) if isinstance(v, (int, float)) else v


def _market_returns(market: list[dict]) -> dict[str, Any]:
    by: dict[str, list[dict]] = {}
    for row in market:
        by.setdefault(row["ticker"], []).append(row)
    out: dict[str, Any] = {}
    for t, rows in by.items():
        rows = sorted(rows, key=lambda r: r["datetime"])
        last = rows[-1]["close"]

        def ret(n: int | None) -> float | None:
            if not rows:
                return None
            base = rows[0] if n is None or n >= len(rows) else rows[-n]
            return _pct(last, base["close"])

        out[t] = {
            "ultimo_fechamento_usd": _r(last),
            "data": rows[-1]["datetime"][:10],
            "variacao_1m_pct": ret(21),
            "variacao_6m_pct": ret(126),
            "variacao_1a_pct": ret(252),
            "variacao_periodo_total_pct": ret(None),
            "inicio_periodo_total": rows[0]["datetime"][:10],
        }
    return out


def build_indicators(payload: dict[str, Any]) -> dict[str, Any]:
    fin = sorted(payload.get("financial", []), key=lambda r: r["year"])
    ind: dict[str, Any] = {"dados_atualizados_em": payload.get("meta", {}).get("updated_at")}

    if len(fin) >= 2:
        a, b, first = fin[-1], fin[-2], fin[0]
        ind["crescimento"] = {
            "ano": a["year"],
            "clientes_milhoes": a.get("customers_m"),
            "clientes_ano_anterior_milhoes": b.get("customers_m"),
            "crescimento_clientes_no_ano_pct": _pct(a.get("customers_m"), b.get("customers_m")),
            "crescimento_clientes_ano_anterior_pct": _pct(b.get("customers_m"), fin[-3].get("customers_m")) if len(fin) >= 3 else None,
            "clientes_desde": {"ano": first["year"], "milhoes": first.get("customers_m")},
            "taxa_atividade_pct": a.get("activity_rate_pct"),
        }
        margem = lambda r: _r(r["net_income_usd_b"] / r["revenue_usd_b"] * 100, 1) if r.get("revenue_usd_b") else None  # noqa: E731
        ind["rentabilidade"] = {
            "ano": a["year"],
            "receita_usd_bi": _r(a.get("revenue_usd_b")),
            "crescimento_receita_no_ano_pct": _pct(a.get("revenue_usd_b"), b.get("revenue_usd_b")),
            "lucro_liquido_usd_bi": _r(a.get("net_income_usd_b")),
            "lucro_liquido_ano_anterior_usd_bi": _r(b.get("net_income_usd_b")),
            "margem_liquida_pct": margem(a),
            "margem_liquida_ano_anterior_pct": margem(b),
            "anos_com_lucro": [r["year"] for r in fin if (r.get("net_income_usd_b") or 0) > 0],
            "receita_mensal_por_cliente_ativo_usd": a.get("arpac_usd"),
            "custo_mensal_por_cliente_usd": a.get("cost_to_serve_usd"),
            "carteira_credito_usd_bi": a.get("credit_portfolio_usd_b"),
            "crescimento_carteira_credito_no_ano_pct": _pct(a.get("credit_portfolio_usd_b"), b.get("credit_portfolio_usd_b")),
            "depositos_usd_bi": a.get("deposits_usd_b"),
        }

    risk = [r for r in payload.get("risk", []) if r.get("basel_index_pct") is not None]
    risk = sorted({r["period"][:10]: r for r in risk}.values(), key=lambda r: r["period"])
    if risk:
        last = risk[-1]
        year_ago = next((r for r in reversed(risk) if r["period"][:10] <= f"{int(last['period'][:4]) - 1}{last['period'][4:10]}"), None)
        ind["capital"] = {
            "data": last["period"][:10],
            "indice_basileia_pct": _r(last["basel_index_pct"]),
            "minimo_exigido_pct": BASILEIA_MINIMO,
            "folga_pp": _r(last["basel_index_pct"] - BASILEIA_MINIMO),
            "indice_basileia_um_ano_antes_pct": _r(year_ago["basel_index_pct"]) if year_ago else None,
            "maior_indice_da_serie_pct": _r(max(r["basel_index_pct"] for r in risk)),
            "crescimento_ativos_ponderados_risco_um_ano_pct": _pct(last.get("rwa_total_brl_b"), (year_ago or {}).get("rwa_total_brl_b")),
        }

    market = payload.get("market", [])
    if market:
        ind["mercado"] = _market_returns(market)

    ranking = payload.get("bcb_complaints", {}).get("ranking", [])
    if ranking:
        periods = sorted({r["periodo"] for r in ranking})
        latest = periods[-1]
        prev4 = periods[-5] if len(periods) >= 5 else None
        idx = {(r["ticker"], r["periodo"]): r.get("indice") for r in ranking}
        ind["clientes"] = {
            "reclamacoes_procedentes_por_milhao_de_clientes_bcb": {
                "trimestre": latest,
                **{t: idx.get((t, latest)) for t in ("NU", "ITUB", "BBD")},
                "NU_um_ano_antes": idx.get(("NU", prev4)) if prev4 else None,
            },
        }
        irreg = payload.get("bcb_complaints", {}).get("irregularidades", [])
        nu4 = [r for r in irreg if r.get("ticker") == "NU" and r.get("periodo") in periods[-4:]]
        tot = sum(r.get("procedentes") or 0 for r in nu4)
        if tot:
            temas: dict[str, float] = {}
            for r in nu4:
                temas[r.get("tema") or "Outros"] = temas.get(r.get("tema") or "Outros", 0) + (r.get("procedentes") or 0)
            top = sorted(temas.items(), key=lambda kv: -kv[1])[:3]
            ind["clientes"]["principais_temas_nubank_ultimos_4_tri_pct"] = {k: _r(v / tot * 100, 1) for k, v in top}
    clusters = payload.get("customer", {}).get("clusters", [])
    if clusters:
        perda = sum(c.get("perda", 0) for c in clusters)
        maior = max(clusters, key=lambda c: c.get("perda", 0))
        ind.setdefault("clientes", {})["amostra_reclame_aqui"] = {
            "reclamacoes": sum(c.get("reclamacoes", 0) for c in clusters),
            "com_perda_financeira": perda,
            "grupo_com_mais_perdas": maior.get("nome"),
            "perdas_nesse_grupo": maior.get("perda"),
        }

    selic = payload.get("selic", {}).get("serie", [])
    if selic:
        last = selic[-1]
        i = len(selic) - 1
        while i > 0 and selic[i - 1]["selic_meta_pct"] == last["selic_meta_pct"]:
            i -= 1
        ind["contexto_selic"] = {
            "selic_meta_pct_ao_ano": last["selic_meta_pct"],
            "vigente_desde": selic[i]["data"],
            "anterior_pct": selic[i - 1]["selic_meta_pct"] if i > 0 else None,
            "pico_do_periodo_pct": max(r["selic_meta_pct"] for r in selic),
        }
    return ind


# ---------------------------------------------------------------- IA
def call_claude(indicators: dict[str, Any], api_key: str, extra: str = "") -> dict[str, Any]:
    user = (
        "Indicadores do dashboard (JSON):\n"
        + json.dumps(indicators, ensure_ascii=False, indent=1)
        + "\n\nGere o parecer seguindo as regras."
        + (f"\n\nAtenção: {extra}" if extra else "")
    )
    body = {
        "model": MODEL,
        "max_tokens": 4000,
        "system": SYSTEM_PROMPT,
        "messages": [{"role": "user", "content": user}],
        "output_config": {"format": {"type": "json_schema", "schema": SCHEMA}},
    }
    headers = {"x-api-key": api_key, "anthropic-version": "2023-06-01", "content-type": "application/json"}
    resp = requests.post(API_URL, headers=headers, json=body, timeout=120)
    if resp.status_code != 200:
        # nunca imprime a chave; só o tipo de erro devolvido pela API
        try:
            err = resp.json().get("error", {})
            detail = f"{err.get('type', '')}: {err.get('message', '')}"[:300]
        except ValueError:
            detail = ""
        raise RuntimeError(f"API do Claude respondeu HTTP {resp.status_code} {detail}")
    data = resp.json()
    text = "".join(b.get("text", "") for b in data.get("content", []) if b.get("type") == "text")
    return json.loads(text)


def validate(parecer: Any) -> list[str]:
    """Devolve a lista de problemas (vazia = parecer válido)."""
    problems: list[str] = []
    if not isinstance(parecer, dict):
        return ["resposta não é um objeto JSON"]
    for key, limit in (("resumo", 600), ("conselho", 320)):
        val = parecer.get(key)
        if not isinstance(val, str) or not val.strip():
            problems.append(f"'{key}' vazio")
        elif len(val) > limit:
            problems.append(f"'{key}' longo demais")
    areas = parecer.get("areas")
    if not isinstance(areas, dict):
        problems.append("'areas' ausente")
        areas = {}
    for area in AREAS:
        item = areas.get(area)
        if not isinstance(item, dict):
            problems.append(f"área '{area}' ausente")
            continue
        if str(item.get("status", "")).lower() not in STATUS:
            problems.append(f"status inválido em '{area}'")
        motivo = item.get("motivo")
        if not isinstance(motivo, str) or not motivo.strip() or len(motivo) > 260:
            problems.append(f"motivo inválido em '{area}'")
    texts = [parecer.get("resumo", ""), parecer.get("conselho", "")] + [
        (areas.get(a) or {}).get("motivo", "") for a in AREAS
    ]
    if any(PROIBIDO.search(str(t)) for t in texts):
        problems.append("contém recomendação de compra/venda de ações")
    return problems


def generate(indicators: dict[str, Any], api_key: str) -> dict[str, Any]:
    """Chama a IA; se a resposta não passar na validação, tenta mais uma vez explicando o problema."""
    extra = ""
    for _ in range(2):
        parecer = call_claude(indicators, api_key, extra)
        problems = validate(parecer)
        if not problems:
            for area in AREAS:
                parecer["areas"][area]["status"] = parecer["areas"][area]["status"].lower()
            return parecer
        extra = "a resposta anterior foi rejeitada: " + "; ".join(problems) + ". Corrija."
    raise ValueError("parecer rejeitado na validação: " + "; ".join(problems))


# ---------------------------------------------------------------- gravação
def load_previous() -> dict[str, Any] | None:
    if PARECER_JSON.exists():
        try:
            return json.loads(PARECER_JSON.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return None
    return None


def save_to_mongo(parecer: dict[str, Any]) -> str:
    try:
        from database.connection import get_database, get_mongo_client, get_mongo_uri
    except ImportError as exc:  # pragma: no cover
        return f"MongoDB ignorado ({exc})"
    uri = get_mongo_uri()
    if not uri:
        return "MongoDB ignorado (MONGO_URI não configurada)"
    client = None
    try:
        client = get_mongo_client(uri)
        col = get_database(client)["pareceres_ia"]
        col.create_index("data", unique=True)
        col.update_one({"data": parecer["gerado_em"][:10]}, {"$set": {**parecer, "data": parecer["gerado_em"][:10]}}, upsert=True)
        return "MongoDB: parecer salvo em pareceres_ia"
    except Exception as exc:  # noqa: BLE001
        return f"MongoDB indisponível ({type(exc).__name__}); parecer mantido no arquivo"
    finally:
        if client:
            client.close()


def inject(parecer: dict[str, Any] | None) -> None:
    """Coloca o parecer no dashboard-data.json, que é o arquivo lido pelo site."""
    if not parecer or not PAYLOAD.exists():
        return
    payload = json.loads(PAYLOAD.read_text(encoding="utf-8"))
    payload["parecer_ia"] = parecer
    PAYLOAD.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def run(force: bool = False, show_only: bool = False) -> int:
    if not PAYLOAD.exists():
        print("dashboard-data.json não encontrado; rode antes: python -m src.build_web_data", file=sys.stderr)
        return 1
    payload = json.loads(PAYLOAD.read_text(encoding="utf-8"))
    indicators = build_indicators(payload)
    if show_only:
        print(json.dumps(indicators, ensure_ascii=False, indent=2))
        return 0

    previous = load_previous()
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    # Assinatura dos indicadores, sem a data de atualização: se os números mudaram, gera de novo
    assinatura = hashlib.sha256(json.dumps({k: v for k, v in indicators.items() if k != "dados_atualizados_em"},
                                           ensure_ascii=False, sort_keys=True).encode("utf-8")).hexdigest()[:16]
    if (previous and previous.get("gerado_em", "")[:10] == today and previous.get("indicadores_hash") == assinatura
            and not force):
        print("Parecer de hoje já existe para estes mesmos números; reaproveitando (use --forcar para gerar de novo).")
        inject(previous)
        return 0

    api_key = os.getenv("ANTHROPIC_API_KEY", "").strip()
    if not api_key:
        print("ANTHROPIC_API_KEY não configurada; mantendo o parecer anterior.", file=sys.stderr)
        inject(previous)
        return 0

    try:
        parecer = generate(indicators, api_key)
    except Exception as exc:  # noqa: BLE001
        print(f"Não foi possível gerar o parecer ({type(exc).__name__}: {exc}). Mantendo o anterior.", file=sys.stderr)
        inject(previous)
        return 1

    parecer = {
        **parecer,
        "gerado_em": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "modelo": MODEL,
        "dados_ate": indicators.get("dados_atualizados_em"),
        "indicadores_hash": assinatura,
        "aviso": AVISO,
    }
    PARECER_JSON.parent.mkdir(parents=True, exist_ok=True)
    PARECER_JSON.write_text(json.dumps(parecer, ensure_ascii=False, indent=2), encoding="utf-8")
    inject(parecer)
    print("Parecer gerado: " + ", ".join(f"{a}={parecer['areas'][a]['status']}" for a in AREAS))
    print(save_to_mongo(parecer))
    return 0


def main(argv: list[str] | None = None) -> int:
    if sys.platform == "win32":
        try:
            sys.stdout.reconfigure(encoding="utf-8", errors="replace")
            sys.stderr.reconfigure(encoding="utf-8", errors="replace")
        except Exception:
            pass
    parser = argparse.ArgumentParser(description="Gera o Parecer da IA a partir dos dados do dashboard.")
    parser.add_argument("--forcar", action="store_true", help="gera de novo mesmo se já existir o parecer de hoje")
    parser.add_argument("--mostrar-dados", action="store_true", help="só mostra os indicadores enviados à IA")
    args = parser.parse_args(argv)
    return run(force=args.forcar, show_only=args.mostrar_dados)


if __name__ == "__main__":
    sys.exit(main())
