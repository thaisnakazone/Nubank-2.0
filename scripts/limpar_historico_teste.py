import argparse
import os
import sys
from pathlib import Path
from dotenv import load_dotenv
from pymongo import MongoClient
from pymongo.errors import PyMongoError

# Garante suporte a UTF-8 no console Windows
if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

TARGET_DB = "nubank_db"
TARGET_COLLECTION = "historico_diario"
CONFIRMATION_PHRASE = "LIMPAR nubank_db.historico_diario"


def get_stats(collection) -> dict:
    """Calcula estatísticas da coleção sem carregar documentos em memória."""
    total_docs = collection.count_documents({})

    # Contagem por ticker
    ticker_pipeline = [
        {"$group": {"_id": "$ticker", "total": {"$sum": 1}}},
        {"$sort": {"_id": 1}},
    ]
    tickers = list(collection.aggregate(ticker_pipeline))

    # Identificação de duplicatas por chave composta (ticker, datetime)
    dup_pipeline = [
        {
            "$group": {
                "_id": {"ticker": "$ticker", "datetime": "$datetime"},
                "count": {"$sum": 1},
            }
        },
        {"$match": {"count": {"$gt": 1}}},
        {
            "$group": {
                "_id": None,
                "chaves_duplicadas": {"$sum": 1},
                "docs_excedentes": {"$sum": {"$subtract": ["$count", 1]}},
            }
        },
    ]
    dup_res = list(collection.aggregate(dup_pipeline))
    chaves_duplicadas = dup_res[0]["chaves_duplicadas"] if dup_res else 0
    docs_excedentes = dup_res[0]["docs_excedentes"] if dup_res else 0

    return {
        "total": total_docs,
        "tickers": tickers,
        "chaves_duplicadas": chaves_duplicadas,
        "docs_excedentes": docs_excedentes,
    }


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Utilitário de inspeção e limpeza controlada para nubank_db.historico_diario."
    )
    parser.add_argument(
        "--executar",
        action="store_true",
        help="Habilita o modo de exclusão (exige confirmação textual interativa).",
    )
    args = parser.parse_args()

    # 1. Carrega .env da raiz do repositório independentemente do diretório de execução
    root_dir = Path(__file__).resolve().parents[1]
    env_path = root_dir / ".env"
    if not env_path.exists():
        # Fallback para o diretório pai caso executado fora da subpasta
        parent_env = root_dir.parent / ".env"
        if parent_env.exists():
            env_path = parent_env

    load_dotenv(dotenv_path=env_path)
    mongo_uri = os.getenv("MONGO_URI")

    if not mongo_uri:
        print("Erro: MONGO_URI não encontrada no arquivo .env.", file=sys.stderr)
        return 1

    client = None
    try:
        client = MongoClient(mongo_uri)
        client.admin.command("ping")

        db = client[TARGET_DB]
        collection = db[TARGET_COLLECTION]

        stats = get_stats(collection)

        # MODO PADRÃO (Sem --executar): Apenas inspeção segura
        if not args.executar:
            print("=" * 60)
            print("🔍 RELATÓRIO DE INSPEÇÃO (Modo Somente Leitura)")
            print("=" * 60)
            print(f"Banco de dados: {TARGET_DB}")
            print(f"Coleção:        {TARGET_COLLECTION}")
            print(f"Total de docs:  {stats['total']}")
            print("\nDistribuição por ticker:")
            if stats["tickers"]:
                for t in stats["tickers"]:
                    name = t["_id"] if t["_id"] else "[Sem ticker]"
                    print(f"  • {name}: {t['total']} registros")
            else:
                print("  (Nenhum registro encontrado)")

            print(f"\nDuplicatas (ticker + datetime):")
            print(f"  • Pares duplicados identificados: {stats['chaves_duplicadas']}")
            print(f"  • Documentos excedentes:          {stats['docs_excedentes']}")
            print("=" * 60)
            print("Nenhum dado foi excluído ou alterado.")
            print("Para efetuar a limpeza controlada, execute:")
            print("  python scripts/limpar_historico_teste.py --executar")
            return 0

        # MODO EXECUÇÃO (Com --executar): Exige confirmação estrita
        print("=" * 60)
        print("⚠️  AVISO DE LIMPEZA CONTROLADA")
        print("=" * 60)
        print(f"Banco de dados:               {TARGET_DB}")
        print(f"Coleção a ser limpa:          {TARGET_COLLECTION}")
        print(f"Total de docs a serem pagos:  {stats['total']}")
        print("=" * 60)
        print("Esta ação apagará todos os documentos da coleção acima.")
        print("A coleção, o banco de dados e os índices serão preservados.")
        print(f"Para prosseguir, digite exatamente a frase abaixo:\n\n  {CONFIRMATION_PHRASE}\n")

        try:
            user_input = input("Confirmação: ").strip()
        except (EOFError, KeyboardInterrupt):
            print("\nOperação cancelada pelo usuário. Nenhum dado foi apagado.")
            return 1

        if user_input != CONFIRMATION_PHRASE:
            print(
                "\n❌ Confirmação incorreta ou cancelada. "
                "Nenhum dado foi excluído da base."
            )
            return 1

        # Executa limpeza preservando a coleção e seus índices (sem usar drop)
        result = collection.delete_many({})
        print(f"\n🗑️  Limpeza concluída com sucesso: {result.deleted_count} documentos apagados.")

        # Garante/verifica a presença do índice único
        try:
            collection.create_index([("ticker", 1), ("datetime", 1)], unique=True)
            print("✓ Índice único composto em ('ticker', 'datetime') verificado/criado com sucesso.")
        except PyMongoError as e:
            print(f"Aviso ao recriar índice único: {type(e).__name__}", file=sys.stderr)

        return 0

    except PyMongoError as e:
        print(f"Erro ao interagir com o MongoDB: {type(e).__name__}", file=sys.stderr)
        return 1
    finally:
        if client:
            client.close()


if __name__ == "__main__":
    sys.exit(main())
