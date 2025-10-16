# core/models.py — CRUD completo + buscas + helpers + status

from datetime import datetime
from .database import conn
import sqlite3

# ----------------- Helpers -----------------
def _parse_valor(valor_str: str) -> float:
    if valor_str is None:
        return 0.0
    s = str(valor_str).strip().replace("R$", "").replace(" ", "")
    if "," in s and "." in s:
        s = s.replace(".", "").replace(",", ".")
    else:
        s = s.replace(",", ".")
    return float(s or 0.0)

def _to_date_yyyy_mm_dd(s: str) -> str:
    s = (s or "").strip()
    if not s:
        return ""
    for fmt in ("%Y-%m-%d", "%d/%m/%Y", "%Y%m%d"):
        try:
            return datetime.strptime(s, fmt).strftime("%Y-%m-%d")
        except Exception:
            pass
    return s  # mantém como veio para não quebrar

def _get_conta_nome(cur, conta_id: int) -> str:
    cur.execute("SELECT nome FROM contas_financeiras WHERE id=?", (conta_id,))
    r = cur.fetchone()
    return r["nome"] if r else ""

def _row_to_dict(row, conta_nome) -> dict:
    d = {
        "id": row["id"],
        "descricao": row["descricao"] or "",
        "valor": float(row["valor"] or 0.0),
        "vencimento": row["data"] or "",
        "conta_id": row["conta_id"],
        "conta_nome": conta_nome or "",
        "categoria": row["categoria"] or "",
    }
    if "pago" in row.keys():
        d["pago"] = bool(row["pago"])
    if "recebido" in row.keys():
        d["recebido"] = bool(row["recebido"])
    return d

# ----------------- Leitura -----------------
def load_all():
    """Retorna (contas_a_pagar, contas_a_receber, contas_financeiras, categorias)"""
    con = conn(); cur = con.cursor()

    cur.execute("SELECT id, nome FROM contas_financeiras ORDER BY nome")
    contas_fin = [{"id": r["id"], "nome": r["nome"]} for r in cur.fetchall()]

    cur.execute("SELECT nome FROM categorias ORDER BY nome")
    categorias = [r["nome"] for r in cur.fetchall()]

    cur.execute("SELECT * FROM contas_a_pagar ORDER BY date(data) ASC, id ASC")
    pagar_rows = cur.fetchall()
    contas_pagar = []
    for r in pagar_rows:
        nome = _get_conta_nome(cur, r["conta_id"])
        contas_pagar.append(_row_to_dict(r, nome))

    cur.execute("SELECT * FROM contas_a_receber ORDER BY date(data) ASC, id ASC")
    receber_rows = cur.fetchall()
    contas_receber = []
    for r in receber_rows:
        nome = _get_conta_nome(cur, r["conta_id"])
        contas_receber.append(_row_to_dict(r, nome))

    con.close()
    return (contas_pagar, contas_receber, contas_fin, categorias)

# ------------- Categorias CRUD -------------
def add_category(name: str):
    name = (name or "").strip()
    if not name:
        raise ValueError("Nome da categoria vazio.")
    con = conn(); cur = con.cursor()
    try:
        cur.execute("INSERT INTO categorias (nome) VALUES (?)", (name,))
        con.commit()
    except sqlite3.IntegrityError:
        pass
    finally:
        con.close()

def edit_category(old: str, new: str):
    old = (old or "").strip(); new = (new or "").strip()
    if not old or not new:
        raise ValueError("Nomes inválidos.")
    con = conn(); cur = con.cursor()
    cur.execute("UPDATE categorias SET nome=? WHERE nome=?", (new, old))
    con.commit(); con.close()

def delete_category(name: str):
    name = (name or "").strip()
    if not name:
        raise ValueError("Nome inválido.")
    con = conn(); cur = con.cursor()
    cur.execute("DELETE FROM categorias WHERE nome=?", (name,))
    con.commit(); con.close()

# ------- Contas Financeiras CRUD -------
def add_financial_account(name: str):
    name = (name or "").strip()
    if not name:
        return "O nome da conta não pode ser vazio."
    con = conn(); cur = con.cursor()
    try:
        cur.execute("INSERT INTO contas_financeiras (nome) VALUES (?)", (name,))
        con.commit()
        return True
    except sqlite3.IntegrityError:
        return f"Conta financeira '{name}' já existe."
    finally:
        con.close()

def edit_financial_account(acc_id: int, new_name: str):
    new_name = (new_name or "").strip()
    if not new_name:
        return "O nome da conta não pode ser vazio."
    con = conn(); cur = con.cursor()
    cur.execute("SELECT id FROM contas_financeiras WHERE nome=? AND id<>?", (new_name, acc_id))
    if cur.fetchone():
        con.close()
        return f"Conta financeira '{new_name}' já existe."
    cur.execute("UPDATE contas_financeiras SET nome=? WHERE id=?", (new_name, acc_id))
    con.commit(); con.close()
    return True

def account_has_entries(acc_id: int) -> bool:
    con = conn(); cur = con.cursor()
    cur.execute("SELECT 1 FROM contas_a_pagar WHERE conta_id=? LIMIT 1", (acc_id,))
    if cur.fetchone():
        con.close(); return True
    cur = con.cursor()
    cur.execute("SELECT 1 FROM contas_a_receber WHERE conta_id=? LIMIT 1", (acc_id,))
    r = cur.fetchone()
    con.close()
    return bool(r)

def delete_financial_account_by_id(acc_id: int):
    con = conn(); cur = con.cursor()
    cur.execute("DELETE FROM contas_financeiras WHERE id=?", (acc_id,))
    con.commit(); con.close()

# --------- Pagar/Receber CRUD ----------
def _resolve_conta_id(cur, conta_id, conta_nome) -> int | None:
    if isinstance(conta_id, int):
        return conta_id
    try:
        return int(conta_id)
    except Exception:
        pass
    nome = (conta_nome or "").strip()
    if nome:
        cur.execute("SELECT id FROM contas_financeiras WHERE nome=?", (nome,))
        r = cur.fetchone()
        if r:
            return r["id"]
        cur.execute("INSERT INTO contas_financeiras (nome) VALUES (?)", (nome,))
        return cur.lastrowid
    cur.execute("SELECT id FROM contas_financeiras ORDER BY id LIMIT 1")
    r = cur.fetchone()
    if r:
        return r["id"]
    cur.execute("INSERT INTO contas_financeiras (nome) VALUES ('Conta Importada')")
    return cur.lastrowid

def add_entry(tipo: str, descricao: str, valor_str: str, data_str: str, conta_id, conta_nome: str, categoria: str):
    if tipo not in ("pagar", "receber"):
        return "Tipo inválido."
    descricao = (descricao or "").strip()
    if not descricao:
        return "Descrição não pode ser vazia."
    try:
        valor = _parse_valor(valor_str)
    except Exception:
        return "Valor inválido."
    data = _to_date_yyyy_mm_dd(data_str)

    con = conn(); cur = con.cursor()
    try:
        cid = _resolve_conta_id(cur, conta_id, conta_nome)
        tabela = "contas_a_pagar" if tipo == "pagar" else "contas_a_receber"
        status_col = "pago" if tipo == "pagar" else "recebido"
        cur.execute(
            f"INSERT INTO {tabela} (descricao, valor, data, conta_id, categoria, {status_col}) VALUES (?, ?, ?, ?, ?, 0)",
            (descricao, float(valor), data, int(cid), (categoria or "").strip())
        )
        con.commit()
        if categoria:
            try:
                cur.execute("INSERT INTO categorias (nome) VALUES (?)", ((categoria or "").strip(),))
                con.commit()
            except sqlite3.IntegrityError:
                pass
        return True
    finally:
        con.close()

def edit_entry(tipo: str, item_id: int, descricao: str, valor_str: str, data_str: str,
               conta_id, conta_nome: str, categoria: str):
    if tipo not in ("pagar", "receber"):
        return "Tipo inválido."
    try:
        valor = _parse_valor(valor_str)
    except Exception:
        return "Valor inválido."
    data = _to_date_yyyy_mm_dd(data_str)

    con = conn(); cur = con.cursor()
    try:
        cid = _resolve_conta_id(cur, conta_id, conta_nome)
        tabela = "contas_a_pagar" if tipo == "pagar" else "contas_a_receber"
        cur.execute(
            f"UPDATE {tabela} SET descricao=?, valor=?, data=?, conta_id=?, categoria=? WHERE id=?",
            (descricao, float(valor), data, int(cid), (categoria or "").strip(), int(item_id))
        )
        con.commit()
        if categoria:
            try:
                cur.execute("INSERT INTO categorias (nome) VALUES (?)", ((categoria or "").strip(),))
                con.commit()
            except sqlite3.IntegrityError:
                pass
        return True
    finally:
        con.close()

def delete_entry(tipo: str, item_id: int | None = None, descricao: str | None = None,
                 valor: float | None = None, data_str: str | None = None, conta_id=None, conta_nome: str | None = None):
    """Exclui por ID; se faltar ID, tenta localizar por (descricao, valor, data[, conta_id])."""
    if tipo not in ("pagar", "receber"):
        return "Tipo inválido."
    tabela = "contas_a_pagar" if tipo == "pagar" else "contas_a_receber"
    con = conn(); cur = con.cursor()
    try:
        if item_id is not None:
            cur.execute(f"DELETE FROM {tabela} WHERE id=?", (int(item_id),))
            con.commit()
            return True

        if descricao is None or data_str is None or valor is None:
            return "Registro sem ID e sem dados suficientes para excluir."
        data = _to_date_yyyy_mm_dd(data_str)

        cid = None
        try:
            cid = int(conta_id) if conta_id is not None else None
        except Exception:
            cid = _resolve_conta_id(cur, conta_id, conta_nome)

        if isinstance(cid, int):
            cur.execute(
                f"""SELECT id FROM {tabela}
                    WHERE descricao=? AND ABS(valor-?)<1e-6 AND data=? AND conta_id=?
                    ORDER BY id DESC LIMIT 1""",
                (descricao, float(valor), data, cid)
            )
        else:
            cur.execute(
                f"""SELECT id FROM {tabela}
                    WHERE descricao=? AND ABS(valor-?)<1e-6 AND data=?
                    ORDER BY id DESC LIMIT 1""",
                (descricao, float(valor), data)
            )

        row = cur.fetchone()
        if not row:
            return "Registro sem ID. Não foi possível localizar no banco para excluir."

        db_id = row["id"]
        cur.execute(f"DELETE FROM {tabela} WHERE id=?", (int(db_id),))
        con.commit()
        return True
    finally:
        con.close()

# ------------- Status (Pago/Recebido) -------------
def set_paid(item_id: int, paid: bool) -> bool:
    con = conn(); cur = con.cursor()
    try:
        cur.execute("UPDATE contas_a_pagar SET pago=? WHERE id=?", (1 if paid else 0, int(item_id)))
        con.commit()
        return True
    finally:
        con.close()

def set_received(item_id: int, received: bool) -> bool:
    con = conn(); cur = con.cursor()
    try:
        cur.execute("UPDATE contas_a_receber SET recebido=? WHERE id=?", (1 if received else 0, int(item_id)))
        con.commit()
        return True
    finally:
        con.close()

# ================= BUSCAS FLEXÍVEIS =================
def _build_where_and_params(alias: str, descricao=None, data_ini=None, data_fim=None,
                            valor_min=None, valor_max=None, mes=None, ano=None,
                            conta_id=None, categoria=None, status=None):
    where = []
    params = []

    if descricao:
        where.append(f"UPPER({alias}.descricao) LIKE UPPER(?)")
        params.append(f"%{descricao}%")

    if data_ini:
        where.append(f"date({alias}.data) >= date(?)")
        params.append(_to_date_yyyy_mm_dd(data_ini))
    if data_fim:
        where.append(f"date({alias}.data) <= date(?)")
        params.append(_to_date_yyyy_mm_dd(data_fim))

    if valor_min is not None and str(valor_min) != "":
        try:
            vmin = _parse_valor(valor_min)
            where.append(f"{alias}.valor >= ?")
            params.append(vmin)
        except Exception:
            pass
    if valor_max is not None and str(valor_max) != "":
        try:
            vmax = _parse_valor(valor_max)
            where.append(f"{alias}.valor <= ?")
            params.append(vmax)
        except Exception:
            pass

    if mes:
        where.append(f"strftime('%m', {alias}.data) = ?")
        params.append(f"{int(mes):02d}")
    if ano:
        where.append(f"strftime('%Y', {alias}.data) = ?")
        params.append(str(ano))

    if conta_id:
        try:
            cid = int(conta_id)
            where.append(f"{alias}.conta_id = ?")
            params.append(cid)
        except Exception:
            pass

    if categoria:
        where.append(f"{alias}.categoria = ?")
        params.append(categoria)

    if status in ("pendente", "pago", "recebido"):
        where.append("__STATUS_PLACEHOLDER__")

    return where, params

def search_pagar(descricao=None, data_ini=None, data_fim=None,
                 valor_min=None, valor_max=None, mes=None, ano=None,
                 conta_id=None, categoria=None, status=None):
    """Retorna lista de dicionários de contas a PAGAR conforme filtros."""
    con = conn(); cur = con.cursor()
    where, params = _build_where_and_params("p", descricao, data_ini, data_fim,
                                            valor_min, valor_max, mes, ano,
                                            conta_id, categoria, status)

    sql_where = " AND ".join(w.replace("__STATUS_PLACEHOLDER__", "p.pago=0" if status == "pendente" else "p.pago=1") for w in where)
    if sql_where:
        sql_where = "WHERE " + sql_where

    sql = f"""
        SELECT p.*, cf.nome AS conta_nome
          FROM contas_a_pagar p
          JOIN contas_financeiras cf ON cf.id = p.conta_id
        {sql_where}
        ORDER BY date(p.data) ASC, p.id ASC
    """
    cur.execute(sql, params)
    rows = cur.fetchall()
    out = []
    for r in rows:
        out.append({
            "id": r["id"],
            "tipo": "pagar",
            "descricao": r["descricao"] or "",
            "valor": float(r["valor"] or 0.0),
            "vencimento": r["data"] or "",
            "conta_id": r["conta_id"],
            "conta_nome": r["conta_nome"] or "",
            "categoria": r["categoria"] or "",
            "pago": bool(r["pago"]),
        })
    con.close()
    return out

def search_receber(descricao=None, data_ini=None, data_fim=None,
                   valor_min=None, valor_max=None, mes=None, ano=None,
                   conta_id=None, categoria=None, status=None):
    """Retorna lista de dicionários de contas a RECEBER conforme filtros."""
    con = conn(); cur = con.cursor()
    where, params = _build_where_and_params("r", descricao, data_ini, data_fim,
                                            valor_min, valor_max, mes, ano,
                                            conta_id, categoria, status)

    sql_where = " AND ".join(w.replace("__STATUS_PLACEHOLDER__", "r.recebido=0" if status == "pendente" else "r.recebido=1") for w in where)
    if sql_where:
        sql_where = "WHERE " + sql_where

    sql = f"""
        SELECT r.*, cf.nome AS conta_nome
          FROM contas_a_receber r
          JOIN contas_financeiras cf ON cf.id = r.conta_id
        {sql_where}
        ORDER BY date(r.data) ASC, r.id ASC
    """
    cur.execute(sql, params)
    rows = cur.fetchall()
    out = []
    for r in rows:
        out.append({
            "id": r["id"],
            "tipo": "receber",
            "descricao": r["descricao"] or "",
            "valor": float(r["valor"] or 0.0),
            "vencimento": r["data"] or "",
            "conta_id": r["conta_id"],
            "conta_nome": r["conta_nome"] or "",
            "categoria": r["categoria"] or "",
            "recebido": bool(r["recebido"]),
        })
    con.close()
    return out

def search_combined(tipo=None, descricao=None, data_ini=None, data_fim=None,
                    valor_min=None, valor_max=None, mes=None, ano=None,
                    conta_id=None, categoria=None, status=None):
    """
    Busca combinada. 'tipo': None/'todos' | 'pagar' | 'receber'
    'status': None | 'pendente' | 'pago' | 'recebido'
    """
    tipo = (tipo or "todos").lower()
    if tipo == "pagar":
        return search_pagar(descricao, data_ini, data_fim, valor_min, valor_max, mes, ano, conta_id, categoria,
                            status if status in (None, "pendente", "pago") else None)
    if tipo == "receber":
        return search_receber(descricao, data_ini, data_fim, valor_min, valor_max, mes, ano, conta_id, categoria,
                              status if status in (None, "pendente", "recebido") else None)

    pagar = search_pagar(descricao, data_ini, data_fim, valor_min, valor_max, mes, ano, conta_id, categoria,
                         status if status in (None, "pendente", "pago") else None)
    receber = search_receber(descricao, data_ini, data_fim, valor_min, valor_max, mes, ano, conta_id, categoria,
                             status if status in (None, "pendente", "recebido") else None)

    def keyfun(x):
        return (x.get("vencimento",""), x.get("id", 0))
    return sorted(pagar + receber, key=keyfun)

