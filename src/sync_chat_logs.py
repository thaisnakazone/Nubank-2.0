"""
Copia os registros do chat "Pergunte à IA" para o MongoDB Atlas.

O intermediário do chat (Cloudflare Worker, pasta chat-worker/) grava cada pergunta num banco D1,
sem IP nem identificação. Este script, rodado na coleta diária, busca os registros novos pela rota
/export e faz upsert na coleção nubank_db.chat_perguntas (um documento por registro, chave = id).

Precisa de:
- endereço do chat: variável CHAT_API_URL ou, se vazia, o valor de docs/js/chat-config.js;
- CHAT_EXPORT_TOKEN: a mesma senha cadastrada no Worker como EXPORT_TOKEN;
- MONGO_URI.
Se algo faltar, o script só avisa e termina sem erro (o resto da coleta não é afetado).

Uso:
    python -m src.sync_chat_logs
"""
from __future__ import annotations

import os
import re
import sys
from pathlib import Path
from typing import Any

import requests

ROOT = Path(__file__).resolve().parents[1]
CONFIG_JS = ROOT / "docs" / "js" / "chat-config.js"
COLECAO = "chat_perguntas"
MAX_PAGINAS = 20  # 20 × 1000 registros por execução


def chat_api_url() -> str:
    """Endereço do Worker: variável de ambiente ou a linha window.NU_CHAT_API do site."""
    url = os.getenv("CHAT_API_URL", "").strip()
    if not url and CONFIG_JS.exists():
        m = re.search(r"window\.NU_CHAT_API\s*=\s*['\"]([^'\"]*)['\"]", CONFIG_JS.read_text(encoding="utf-8"))
        url = m.group(1).strip() if m else ""
    return url.rstrip("/")


def fetch_since(session: requests.Session, base: str, token: str, since_id: int) -> list[dict[str, Any]]:
    resp = session.get(f"{base}/export", params={"desde_id": since_id}, headers={"Authorization": f"Bearer {token}"}, timeout=60)
    resp.raise_for_status()
    rows = resp.json().get("registros", [])
    return rows if isinstance(rows, list) else []


def clean(row: dict[str, Any]) -> dict[str, Any] | None:
    """Mantém só os campos esperados; descarta linhas sem id ou sem texto."""
    try:
        rid = int(row["id"])
    except (KeyError, TypeError, ValueError):
        return None
    texto = str(row.get("texto") or "").strip()
    if not texto:
        return None
    return {
        "id": rid,
        "criado_em": row.get("criado_em"),
        "dia_brt": row.get("dia_brt"),
        "tipo": row.get("tipo"),
        "pergunta_id": row.get("pergunta_id"),
        "texto": texto,
        "resposta": row.get("resposta"),
        "situacao": row.get("situacao"),
        "tokens_entrada": int(row.get("tokens_entrada") or 0),
        "tokens_saida": int(row.get("tokens_saida") or 0),
        "custo_usd": float(row.get("custo_usd") or 0),
        "modelo": row.get("modelo"),
    }


def run() -> int:
    base = chat_api_url()
    token = os.getenv("CHAT_EXPORT_TOKEN", "").strip()
    if not base:
        print("Chat ainda sem endereço (docs/js/chat-config.js vazio); nada a copiar.")
        return 0
    if not token:
        print("CHAT_EXPORT_TOKEN não configurado; registros do chat não foram copiados.")
        return 0
    try:
        from pymongo import UpdateOne
        from database.connection import get_database, get_mongo_client, get_mongo_uri
    except ImportError as exc:  # pragma: no cover
        print(f"MongoDB ignorado ({exc})")
        return 0
    uri = get_mongo_uri()
    if not uri:
        print("MONGO_URI não configurada; registros do chat não foram copiados.")
        return 0

    client = None
    try:
        client = get_mongo_client(uri)
        col = get_database(client)[COLECAO]
        col.create_index("id", unique=True)
        last = col.find_one(sort=[("id", -1)], projection={"id": 1})
        since = int(last["id"]) if last else 0
        session = requests.Session()
        total = 0
        for _ in range(MAX_PAGINAS):
            rows = [r for r in (clean(x) for x in fetch_since(session, base, token, since)) if r]
            if not rows:
                break
            col.bulk_write([UpdateOne({"id": r["id"]}, {"$set": r}, upsert=True) for r in rows], ordered=False)
            total += len(rows)
            since = max(r["id"] for r in rows)
        print(f"Chat: {total} registros novos copiados para {COLECAO} (último id {since}).")
        return 0
    except Exception as exc:  # noqa: BLE001
        print(f"Não foi possível copiar os registros do chat ({type(exc).__name__}).", file=sys.stderr)
        return 1
    finally:
        if client:
            client.close()


def main() -> int:
    if sys.platform == "win32":
        try:
            sys.stdout.reconfigure(encoding="utf-8", errors="replace")
            sys.stderr.reconfigure(encoding="utf-8", errors="replace")
        except Exception:
            pass
    return run()


if __name__ == "__main__":
    sys.exit(main())
