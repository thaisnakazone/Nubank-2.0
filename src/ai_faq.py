"""
Pergunte à IA — perguntas prontas e contexto do chat.

Faz duas coisas, a cada coleta:
1. Gera docs/data/chat-context.json: o resumo de indicadores (o mesmo do Parecer da IA),
   uma série anual curta e o parecer do dia. É SÓ isso que o chat livre envia para a IA
   (o intermediário do chat — pasta chat-worker/ — lê este arquivo do próprio site).
   Não usa IA: é gerado sempre, mesmo sem chave.
2. Pede ao Claude, em UMA chamada, a resposta de um conjunto fixo de perguntas
   ("O Nubank está bem?", "Dá lucro ou prejuízo?"...). As respostas ficam em
   data/processed/chat_faq.json e no dashboard-data.json. No site, clicar numa pergunta
   pronta mostra a resposta na hora, sem gastar IA.

As respostas são geradas no máximo uma vez por dia para os mesmos números.
Sem chave ou com a API fora do ar, as respostas anteriores são mantidas.

Uso:
    python -m src.ai_faq             # gera o contexto e (se preciso) as respostas
    python -m src.ai_faq --forcar    # gera as respostas de novo
    python -m src.ai_faq --so-contexto
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
from datetime import datetime, timezone
from typing import Any

import requests

from src.ai_parecer import API_URL, AVISO, MODEL, PARECER_JSON, PAYLOAD, PROIBIDO, ROOT, build_indicators

FAQ_JSON = ROOT / "data" / "processed" / "chat_faq.json"
CONTEXT_JSON = ROOT / "docs" / "data" / "chat-context.json"

# Perguntas fixas (id estável → o site e o registro de uso referenciam por id)
PERGUNTAS: list[tuple[str, str]] = [
    ("esta_bem", "O Nubank está bem?"),
    ("lucro_prejuizo", "O Nubank dá lucro ou prejuízo? Quanto?"),
    ("quando_lucro", "Quando o Nubank começou a dar lucro?"),
    ("por_que_lucro", "Por que o lucro cresceu?"),
    ("crescimento", "O Nubank ainda está crescendo?"),
    ("capital", "O capital do Nubank é suficiente?"),
    ("acao", "Como está a ação do Nubank na bolsa?"),
    ("reclamacoes", "Os clientes reclamam muito do Nubank?"),
    ("selic", "Como os juros (Selic) afetam o Nubank?"),
    ("riscos", "Quais são os principais riscos do Nubank?"),
    ("melhorar", "O que o Nubank deveria fazer para melhorar?"),
]
MAX_RESPOSTA = 700  # caracteres

SYSTEM_PROMPT = """Você é um analista financeiro que responde perguntas de leigos em um dashboard acadêmico sobre o Nubank (Nu Holdings), comparado a Itaú e Bradesco.
Regras:
- Use SOMENTE os números do JSON enviado. Não invente dados nem use conhecimento externo. Se o dado não estiver no JSON, diga que o dashboard não tem essa informação.
- Responda em português do Brasil, em 2 a 4 frases curtas e claras (até ~500 caracteres por resposta), citando os números e os anos/datas que sustentam a resposta.
- Valores de receita e lucro estão em dólares (US$ bilhões); capital (Basileia) refere-se ao conglomerado no Brasil.
- Quando a pergunta pedir "por quê", explique a causa usando os próprios dados (ex.: receita por cliente, crédito, margem).
- Quando a pergunta pedir "o que fazer", fale do que a EMPRESA deveria priorizar.
- NUNCA recomende comprar, vender ou manter ações, nem dê conselho de investimento pessoal.
- Capital: o Índice de Basileia mínimo exigido (com colchão) é 10,5%.
- Responda TODAS as perguntas, usando exatamente o "id" de cada uma."""

SCHEMA = {
    "type": "object",
    "properties": {
        "respostas": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {"id": {"type": "string"}, "resposta": {"type": "string"}},
                "required": ["id", "resposta"],
                "additionalProperties": False,
            },
        }
    },
    "required": ["respostas"],
    "additionalProperties": False,
}


# ---------------------------------------------------------------- contexto
def build_context(payload: dict[str, Any]) -> dict[str, Any]:
    """Tudo o que a IA do chat pode saber: indicadores, série anual curta e o parecer do dia."""
    fin = sorted(payload.get("financial", []), key=lambda r: r["year"])
    historico = [
        {
            "ano": r["year"],
            "clientes_milhoes": r.get("customers_m"),
            "receita_usd_bi": round(r["revenue_usd_b"], 2) if r.get("revenue_usd_b") is not None else None,
            "lucro_liquido_usd_bi": round(r["net_income_usd_b"], 2) if r.get("net_income_usd_b") is not None else None,
            "resultado": "lucro" if (r.get("net_income_usd_b") or 0) > 0 else "prejuízo",
        }
        for r in fin
    ]
    parecer = payload.get("parecer_ia") or {}
    if not parecer and PARECER_JSON.exists():
        try:
            parecer = json.loads(PARECER_JSON.read_text(encoding="utf-8"))
        except ValueError:
            parecer = {}
    ctx: dict[str, Any] = {
        "indicadores": build_indicators(payload),
        "historico_anual": historico,
    }
    if parecer.get("areas"):
        ctx["parecer_do_dia"] = {
            "resumo": parecer.get("resumo"),
            "areas": {k: v.get("status") for k, v in parecer["areas"].items()},
            "conselho": parecer.get("conselho"),
        }
    return ctx


def context_hash(ctx: dict[str, Any]) -> str:
    stable = {**ctx, "indicadores": {k: v for k, v in ctx["indicadores"].items() if k != "dados_atualizados_em"}}
    stable.pop("parecer_do_dia", None)
    return hashlib.sha256(json.dumps(stable, ensure_ascii=False, sort_keys=True).encode("utf-8")).hexdigest()[:16]


# ---------------------------------------------------------------- IA
def call_claude(ctx: dict[str, Any], api_key: str, extra: str = "") -> dict[str, Any]:
    perguntas = [{"id": i, "pergunta": q} for i, q in PERGUNTAS]
    user = (
        "Dados do dashboard (JSON):\n"
        + json.dumps(ctx, ensure_ascii=False, indent=1)
        + "\n\nPerguntas (JSON):\n"
        + json.dumps(perguntas, ensure_ascii=False, indent=1)
        + (f"\n\nAtenção: {extra}" if extra else "")
    )
    body = {
        "model": MODEL,
        "max_tokens": 6000,
        "system": SYSTEM_PROMPT,
        "messages": [{"role": "user", "content": user}],
        "output_config": {"format": {"type": "json_schema", "schema": SCHEMA}},
    }
    headers = {"x-api-key": api_key, "anthropic-version": "2023-06-01", "content-type": "application/json"}
    resp = requests.post(API_URL, headers=headers, json=body, timeout=180)
    if resp.status_code != 200:
        try:
            err = resp.json().get("error", {})
            detail = f"{err.get('type', '')}: {err.get('message', '')}"[:300]
        except ValueError:
            detail = ""
        raise RuntimeError(f"API do Claude respondeu HTTP {resp.status_code} {detail}")
    data = resp.json()
    text = "".join(b.get("text", "") for b in data.get("content", []) if b.get("type") == "text")
    return json.loads(text)


def validate(result: Any) -> list[str]:
    """Devolve a lista de problemas (vazia = respostas válidas)."""
    if not isinstance(result, dict) or not isinstance(result.get("respostas"), list):
        return ["resposta sem a lista 'respostas'"]
    by_id = {r.get("id"): r.get("resposta") for r in result["respostas"] if isinstance(r, dict)}
    problems: list[str] = []
    for pid, _ in PERGUNTAS:
        text = by_id.get(pid)
        if not isinstance(text, str) or not text.strip():
            problems.append(f"pergunta '{pid}' sem resposta")
        elif len(text) > MAX_RESPOSTA:
            problems.append(f"resposta de '{pid}' longa demais")
        elif PROIBIDO.search(text):
            problems.append(f"resposta de '{pid}' contém recomendação de compra/venda de ações")
    return problems


def generate(ctx: dict[str, Any], api_key: str) -> list[dict[str, str]]:
    extra = ""
    problems: list[str] = []
    for _ in range(2):
        result = call_claude(ctx, api_key, extra)
        problems = validate(result)
        if not problems:
            by_id = {r["id"]: r["resposta"].strip() for r in result["respostas"]}
            return [{"id": pid, "pergunta": q, "resposta": by_id[pid]} for pid, q in PERGUNTAS]
        extra = "a resposta anterior foi rejeitada: " + "; ".join(problems) + ". Corrija."
    raise ValueError("respostas rejeitadas na validação: " + "; ".join(problems))


# ---------------------------------------------------------------- gravação
def load_previous() -> dict[str, Any] | None:
    if FAQ_JSON.exists():
        try:
            return json.loads(FAQ_JSON.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return None
    return None


def inject(faq: dict[str, Any] | None) -> None:
    """Coloca as perguntas prontas no dashboard-data.json, que é o arquivo lido pelo site."""
    if not faq or not PAYLOAD.exists():
        return
    payload = json.loads(PAYLOAD.read_text(encoding="utf-8"))
    payload["chat_faq"] = faq
    PAYLOAD.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def write_context(ctx: dict[str, Any]) -> None:
    CONTEXT_JSON.parent.mkdir(parents=True, exist_ok=True)
    CONTEXT_JSON.write_text(json.dumps(ctx, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")


def run(force: bool = False, context_only: bool = False) -> int:
    if not PAYLOAD.exists():
        print("dashboard-data.json não encontrado; rode antes: python -m src.build_web_data", file=sys.stderr)
        return 1
    payload = json.loads(PAYLOAD.read_text(encoding="utf-8"))
    ctx = build_context(payload)
    write_context(ctx)
    print(f"Contexto do chat gravado em {CONTEXT_JSON.relative_to(ROOT)} ({CONTEXT_JSON.stat().st_size} bytes).")
    if context_only:
        return 0

    previous = load_previous()
    assinatura = context_hash(ctx)
    if previous and previous.get("contexto_hash") == assinatura and not force:
        print("Perguntas prontas já respondidas para estes mesmos números; reaproveitando (use --forcar).")
        inject(previous)
        return 0

    api_key = os.getenv("ANTHROPIC_API_KEY", "").strip()
    if not api_key:
        print("ANTHROPIC_API_KEY não configurada; mantendo as respostas anteriores.", file=sys.stderr)
        inject(previous)
        return 0

    try:
        itens = generate(ctx, api_key)
    except Exception as exc:  # noqa: BLE001
        print(f"Não foi possível gerar as respostas ({type(exc).__name__}: {exc}). Mantendo as anteriores.", file=sys.stderr)
        inject(previous)
        return 1

    faq = {
        "itens": itens,
        "gerado_em": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "modelo": MODEL,
        "contexto_hash": assinatura,
        "aviso": AVISO,
    }
    FAQ_JSON.parent.mkdir(parents=True, exist_ok=True)
    FAQ_JSON.write_text(json.dumps(faq, ensure_ascii=False, indent=2), encoding="utf-8")
    inject(faq)
    print(f"Perguntas prontas: {len(itens)} respostas geradas.")
    return 0


def main(argv: list[str] | None = None) -> int:
    if sys.platform == "win32":
        try:
            sys.stdout.reconfigure(encoding="utf-8", errors="replace")
            sys.stderr.reconfigure(encoding="utf-8", errors="replace")
        except Exception:
            pass
    parser = argparse.ArgumentParser(description="Gera o contexto do chat e as perguntas prontas respondidas pela IA.")
    parser.add_argument("--forcar", action="store_true", help="gera as respostas de novo mesmo sem mudança nos números")
    parser.add_argument("--so-contexto", action="store_true", help="só grava docs/data/chat-context.json (não chama a IA)")
    args = parser.parse_args(argv)
    return run(force=args.forcar, context_only=args.so_contexto)


if __name__ == "__main__":
    sys.exit(main())
