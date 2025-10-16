# core/database.py — conexão SQLite + criação e migração de schema

import os
import sqlite3

DB_PATH = os.environ.get("FINANCEIRO_DB", "financeiro.db")

def conn(db_path: str = DB_PATH) -> sqlite3.Connection:
    c = sqlite3.connect(db_path)
    c.row_factory = sqlite3.Row
    c.execute("PRAGMA foreign_keys = ON")
    return c

def _column_exists(cur, table: str, col: str) -> bool:
    cur.execute(f"PRAGMA table_info({table})")
    return any(row["name"] == col for row in cur.fetchall())

def _safe_add_column(cur, table: str, col: str, coltype: str):
    if not _column_exists(cur, table, col):
        cur.execute(f"ALTER TABLE {table} ADD COLUMN {col} {coltype}")

def init_schema():
    con = conn()
    cur = con.cursor()

    cur.execute("""
        CREATE TABLE IF NOT EXISTS contas_financeiras (
            id   INTEGER PRIMARY KEY AUTOINCREMENT,
            nome TEXT NOT NULL UNIQUE
        )
    """)

    cur.execute("""
        CREATE TABLE IF NOT EXISTS categorias (
            id   INTEGER PRIMARY KEY AUTOINCREMENT,
            nome TEXT NOT NULL UNIQUE
        )
    """)

    cur.execute("""
        CREATE TABLE IF NOT EXISTS contas_a_pagar (
            id         INTEGER PRIMARY KEY AUTOINCREMENT,
            descricao  TEXT,
            valor      REAL,
            data       TEXT,
            conta_id   INTEGER NOT NULL,
            categoria  TEXT,
            pago       INTEGER DEFAULT 0,
            fitid      TEXT,
            FOREIGN KEY(conta_id) REFERENCES contas_financeiras(id) ON DELETE RESTRICT
        )
    """)

    cur.execute("""
        CREATE TABLE IF NOT EXISTS contas_a_receber (
            id         INTEGER PRIMARY KEY AUTOINCREMENT,
            descricao  TEXT,
            valor      REAL,
            data       TEXT,
            conta_id   INTEGER NOT NULL,
            categoria  TEXT,
            recebido   INTEGER DEFAULT 0,
            fitid      TEXT,
            FOREIGN KEY(conta_id) REFERENCES contas_financeiras(id) ON DELETE RESTRICT
        )
    """)

    con.commit()
    con.close()

def migrate_schema_if_needed():
    """Migra bancos antigos sem apagar nada:
       - adiciona colunas data/pago/recebido/fitid se faltarem;
       - copia 'vencimento' -> 'data' se existir (bancos antigos);
       - cria índices únicos condicionais para FITID (dedupe OFX)."""
    con = conn()
    cur = con.cursor()

    # contas_a_pagar
    _safe_add_column(cur, "contas_a_pagar", "data", "TEXT")
    _safe_add_column(cur, "contas_a_pagar", "pago", "INTEGER DEFAULT 0")
    _safe_add_column(cur, "contas_a_pagar", "fitid", "TEXT")
    cur.execute("PRAGMA table_info(contas_a_pagar)")
    cols_pagar = [r["name"] for r in cur.fetchall()]
    if "vencimento" in cols_pagar:
        cur.execute("""
            UPDATE contas_a_pagar
               SET data = COALESCE(NULLIF(data, ''), vencimento)
             WHERE (data IS NULL OR data = '')
        """)

    # contas_a_receber
    _safe_add_column(cur, "contas_a_receber", "data", "TEXT")
    _safe_add_column(cur, "contas_a_receber", "recebido", "INTEGER DEFAULT 0")
    _safe_add_column(cur, "contas_a_receber", "fitid", "TEXT")
    cur.execute("PRAGMA table_info(contas_a_receber)")
    cols_receber = [r["name"] for r in cur.fetchall()]
    if "vencimento" in cols_receber:
        cur.execute("""
            UPDATE contas_a_receber
               SET data = COALESCE(NULLIF(data, ''), vencimento)
             WHERE (data IS NULL OR data = '')
        """)

    # Índices únicos condicionais por (conta_id, fitid)
    cur.execute("""
        CREATE UNIQUE INDEX IF NOT EXISTS ux_pagar_conta_fitid
        ON contas_a_pagar (conta_id, fitid)
        WHERE fitid IS NOT NULL
    """)
    cur.execute("""
        CREATE UNIQUE INDEX IF NOT EXISTS ux_receber_conta_fitid
        ON contas_a_receber (conta_id, fitid)
        WHERE fitid IS NOT NULL
    """)

    con.commit()
    con.close()
