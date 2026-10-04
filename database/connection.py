from __future__ import annotations

import os
import sys
from pathlib import Path
from dotenv import load_dotenv
from pymongo import MongoClient
from pymongo.errors import ConnectionFailure, PyMongoError

import re

DEFAULT_DB_NAME = "nubank_db"


def _sanitize_uri(text: str) -> str:
    """Mascara credenciais em mensagens e strings de conexão."""
    if not text:
        return ""
    return re.sub(
        r"mongodb(?:\+srv)?://[^@\s'\"]+@",
        "mongodb://***REDACTED***@",
        str(text),
        flags=re.IGNORECASE,
    )


def get_mongo_uri() -> str:
    """Carrega e retorna a URI do MongoDB a partir do ambiente ou do arquivo .env."""
    root_dir = Path(__file__).resolve().parents[1]
    env_path = root_dir / ".env"
    if env_path.exists():
        load_dotenv(dotenv_path=env_path)
    else:
        load_dotenv()
    return os.getenv("MONGO_URI", "")


def get_mongo_client(mongo_uri: str | None = None, timeout_ms: int = 5000) -> MongoClient:
    """
    Cria e retorna uma conexão com o MongoDB Atlas com verificação de conectividade (ping).
    Garante tratamento seguro de credenciais em mensagens de erro.
    """
    uri = mongo_uri or get_mongo_uri()
    if not uri:
        raise ValueError("Variável de ambiente MONGO_URI não está definida.")

    try:
        client = MongoClient(uri, serverSelectionTimeoutMS=timeout_ms)
        client.admin.command("ping")
        return client
    except ConnectionFailure as e:
        safe_msg = _sanitize_uri(str(e))
        raise ConnectionFailure(f"Falha ao conectar no MongoDB Atlas: {safe_msg}") from None
    except PyMongoError as e:
        safe_msg = _sanitize_uri(str(e))
        raise PyMongoError(f"Erro de conexão com MongoDB Atlas: {safe_msg}") from None


def get_database(client: MongoClient | None = None, db_name: str = DEFAULT_DB_NAME):
    """Retorna o banco de dados especificado."""
    c = client or get_mongo_client()
    return c[db_name]
