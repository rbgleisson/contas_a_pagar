# core/ofx_importer.py — parser de OFX com dedupe via FITID/fingerprint

import os
import re
import hashlib
from datetime import datetime
from .database import conn
from .models import _to_date_yyyy_mm_dd, _resolve_conta_id

OFX_BLOCK = re.compile(r"<STMTTRN>(.*?)</STMTTRN>", re.DOTALL | re.IGNORECASE)
TAG_TRNAMT = re.compile(r"<TRNAMT>([-+]?\d+[.,]?\d*)", re.IGNORECASE)
TAG_DTPOSTED = re.compile(r"<DTPOSTED>(\d{8})", re.IGNORECASE)
TAG_MEMO = re.compile(r"<MEMO>(.*?)\s*(?:<|$)", re.IGNORECASE | re.DOTALL)
TAG_FITID = re.compile(r"<FITID>(.*?)\s*(?:<|$)", re.IGNORECASE | re.DOTALL)

def _ofx_to_date(dt: str) -> str:
    try:
        return datetime.strptime(dt[:8], "%Y%m%d").strftime("%Y-%m-%d")
    except Exception:
        return dt

def _normalize_text(s: str) -> str:
    return " ".join((s or "").strip().lower().split())

def _make_fingerprint(descricao: str, valor: float, data: str) -> str:
    base = f"{_normalize_text(descricao)}|{valor:.6f}|{data}"
    return hashlib.sha1(base.encode("utf-8")).hexdigest()  # 40 chars

def process_ofx(path: str, conta_id, conta_nome: str):
    """Lê OFX e retorna (transacoes, erro). Cada transação traz 'fitid' (do arquivo ou fingerprint)."""
    if not os.path.exists(path):
        return [], f"Arquivo não encontrado: {path}"
    try:
        with open(path, "r", encoding="utf-8", errors="ignore") as f:
            content = f.read()
    except Exception as e:
        return [], f"Erro ao ler OFX: {e}"

    trans = []
    for m in OFX_BLOCK.finditer(content):
        block = m.group(1)

        amt_m = TAG_TRNAMT.search(block)
        if not amt_m:
            continue
        valor_raw = amt_m.group(1).strip().replace(",", ".")
        try:
            valor = float(valor_raw)
        except Exception:
            continue

        dt_m = TAG_DTPOSTED.search(block)
        data = _ofx_to_date(dt_m.group(1)) if dt_m else ""

        memo_m = TAG_MEMO.search(block)
        descricao = (memo_m.group(1).strip() if memo_m else "Transação")

        fit_m = TAG_FITID.search(block)
        fitid = (fit_m.group(1).strip() if fit_m else None)

        tipo = "receber" if valor > 0 else "pagar"

        # Se não houver FITID no arquivo, cria fingerprint estável
        if not fitid:
            fitid = _make_fingerprint(descricao, abs(valor), data)

        trans.append({
            "tipo": tipo,
            "descricao": descricao,
            "valor": abs(valor),
            "data": data,
            "conta_id": conta_id,
            "conta_nome": conta_nome,
            "categoria": "",
            "fitid": fitid,
        })
    return trans, None

def add_imported_transactions(transacoes: list) -> int:
    """Insere OFX no banco com dedupe:
       - Se vier fitid: UNIQUE(conta_id, fitid) bloqueia duplicatas.
       - Se não vier fitid, usamos fingerprint calculado.
       Retorna quantidade adicionada."""
    con = conn(); cur = con.cursor()
    adicionadas = 0
    try:
        for t in transacoes:
            tipo = t.get("tipo")
            descricao = t.get("descricao", "")
            valor = float(t.get("valor", 0.0))
            data = _to_date_yyyy_mm_dd(t.get("data", ""))
            cid = _resolve_conta_id(cur, t.get("conta_id"), t.get("conta_nome"))
            categoria = (t.get("categoria") or "").strip()
            fitid = (t.get("fitid") or "").strip() or None

            if tipo == "pagar":
                if fitid:
                    cur.execute("""
                        SELECT id FROM contas_a_pagar
                        WHERE conta_id=? AND fitid=?
                        LIMIT 1
                    """, (cid, fitid))
                    if cur.fetchone():
                        continue
                else:
                    cur.execute("""
                        SELECT id FROM contas_a_pagar
                        WHERE descricao=? AND ABS(valor-?)<1e-6 AND data=? AND conta_id=?
                        LIMIT 1
                    """, (descricao, valor, data, cid))
                    if cur.fetchone():
                        continue

                cur.execute("""
                    INSERT INTO contas_a_pagar (descricao, valor, data, conta_id, categoria, pago, fitid)
                    VALUES (?, ?, ?, ?, ?, 0, ?)
                """, (descricao, valor, data, cid, categoria, fitid))
                con.commit()
                adicionadas += 1

            else:  # receber
                if fitid:
                    cur.execute("""
                        SELECT id FROM contas_a_receber
                        WHERE conta_id=? AND fitid=?
                        LIMIT 1
                    """, (cid, fitid))
                    if cur.fetchone():
                        continue
                else:
                    cur.execute("""
                        SELECT id FROM contas_a_receber
                        WHERE descricao=? AND ABS(valor-?)<1e-6 AND data=? AND conta_id=?
                        LIMIT 1
                    """, (descricao, valor, data, cid))
                    if cur.fetchone():
                        continue

                cur.execute("""
                    INSERT INTO contas_a_receber (descricao, valor, data, conta_id, categoria, recebido, fitid)
                    VALUES (?, ?, ?, ?, ?, 0, ?)
                """, (descricao, valor, data, cid, categoria, fitid))
                con.commit()
                adicionadas += 1

            if categoria:
                try:
                    cur.execute("INSERT INTO categorias (nome) VALUES (?)", (categoria,))
                    con.commit()
                except Exception:
                    pass
    finally:
        con.close()

    return adicionadas
