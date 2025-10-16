# gui/finance_gui.py — Tkinter GUI com:
# - datas BR (DD/MM/AAAA) na grid
# - filtros ao digitar (Descrição, Valor, Data) + busca geral
# - totais dinâmicos (quantidade e soma) conforme os filtros (Pagar)
# - clique na coluna "Status" (toggle Pago/Recebido)
# - importação OFX, exportação Excel
# - relatório mensal por categoria
# - multiseleção e exclusão em massa nas abas Pagar/Receber

import tkinter as tk
from tkinter import ttk, messagebox, filedialog
from datetime import datetime

from core import models
from core import ofx_importer
from core import export_excel

# --------------- Estado em memória (listas e índices) --------------- #
contas_a_pagar, contas_a_receber, contas_financeiras, categorias = [], [], [], []
conta_pagar_idx = None
conta_receber_idx = None
conta_financeira_idx = None
categoria_idx = None

# --------------- Utilidades --------------- #
def formatar_data_br(data_str: str) -> str:
    """Converte 'YYYY-MM-DD' -> 'DD/MM/YYYY' (se falhar, retorna original)."""
    try:
        return datetime.strptime(data_str, "%Y-%m-%d").strftime("%d/%m/%Y")
    except Exception:
        return data_str or ""

def _parse_valor_local(s: str) -> float:
    """Aceita '1.234,56' ou '1234.56'. Lança ValueError se não for número."""
    s = (s or "").strip().replace("R$", "").replace(" ", "")
    if not s:
        raise ValueError("vazio")
    if "," in s and "." in s:
        s = s.replace(".", "").replace(",", ".")
    else:
        s = s.replace(",", ".")
    return float(s)

def _format_money(v: float) -> str:
    return f"R$ {float(v):.2f}".replace(".", ",")

# --------------- Totais helpers (Pagar/Receber) --------------- #
def _set_pg_total_by_indices(indices, pg_total_var):
    total = 0.0
    for i in indices:
        try:
            total += float(contas_a_pagar[i].get("valor", 0.0))
        except Exception:
            pass
    pg_total_var.set(f"Total: {len(indices)} itens • {_format_money(total)}")

def _set_rc_total_all(rc_total_var):
    total = sum(float(x.get("valor", 0.0)) for x in contas_a_receber)
    rc_total_var.set(f"Total: {len(contas_a_receber)} itens • {_format_money(total)}")

# --------------- Recarregar tela --------------- #
def _refresh_all(tree_pagar, tree_receber, tree_cats, tree_contas,
                 combo_conta_pagar, combo_conta_receber, combo_import,
                 combo_cat_pagar, combo_cat_receber,
                 pg_total_var, rc_total_var):
    """Recarrega dados do banco e repovoa grids/combos/totais."""
    global contas_a_pagar, contas_a_receber, contas_financeiras, categorias
    contas_a_pagar, contas_a_receber, contas_financeiras, categorias = models.load_all()

    # Pagar
    for r in tree_pagar.get_children():
        tree_pagar.delete(r)
    for i, c in enumerate(contas_a_pagar):
        status = "☑ Pago" if c.get("pago") else "☐ Pendente"
        tree_pagar.insert("", "end", iid=str(i),
            values=(c.get("descricao",""),
                    f"R$ {float(c.get('valor',0)):.2f}",
                    formatar_data_br(c.get("vencimento","")),
                    c.get("conta_nome",""),
                    c.get("categoria",""),
                    status))
    _set_pg_total_by_indices(list(range(len(contas_a_pagar))), pg_total_var)

    # Receber
    for r in tree_receber.get_children():
        tree_receber.delete(r)
    for i, c in enumerate(contas_a_receber):
        status = "☑ Recebido" if c.get("recebido") else "☐ Pendente"
        tree_receber.insert("", "end", iid=str(i),
            values=(c.get("descricao",""),
                    f"R$ {float(c.get('valor',0)):.2f}",
                    formatar_data_br(c.get("vencimento","")),
                    c.get("conta_nome",""),
                    c.get("categoria",""),
                    status))
    _set_rc_total_all(rc_total_var)

    # Categorias
    for r in tree_cats.get_children():
        tree_cats.delete(r)
    for i, nome in enumerate(categorias):
        tree_cats.insert("", "end", iid=str(i), values=(nome,))

    # Contas financeiras
    for r in tree_contas.get_children():
        tree_contas.delete(r)
    for i, cf in enumerate(contas_financeiras):
        tree_contas.insert("", "end", iid=str(i), values=(cf["nome"],))

    # Combos
    nomes_contas = [c["nome"] for c in contas_financeiras]
    combo_conta_pagar["values"] = nomes_contas
    combo_conta_receber["values"] = nomes_contas
    combo_import["values"] = nomes_contas
    combo_cat_pagar["values"] = categorias
    combo_cat_receber["values"] = categorias

# --------------- Janela principal --------------- #
def main_window():
    global conta_pagar_idx, conta_receber_idx, conta_financeira_idx, categoria_idx

    root = tk.Tk()
    root.title("Sistema de Controle Financeiro")

    # Vars de totais DEVEM ser criadas após o root
    pg_total_var = tk.StringVar(root, value="Total: 0 itens • R$ 0,00")
    rc_total_var = tk.StringVar(root, value="Total: 0 itens • R$ 0,00")

    nb = ttk.Notebook(root); nb.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)

    aba_pagar = ttk.Frame(nb)
    aba_receber = ttk.Frame(nb)
    aba_cats = ttk.Frame(nb)
    aba_contas = ttk.Frame(nb)

    nb.add(aba_pagar, text="Contas a Pagar")
    nb.add(aba_receber, text="Contas a Receber")
    nb.add(aba_cats, text="Categorias")
    nb.add(aba_contas, text="Contas Financeiras")

    # -------- Contas a Pagar -------- #
    f_pg = ttk.LabelFrame(aba_pagar, text="Detalhes da Conta a Pagar"); f_pg.pack(fill="x", padx=10, pady=5)
    ttk.Label(f_pg, text="Descrição:").grid(row=0, column=0, sticky=tk.W, padx=5, pady=2)
    e_pg_desc = ttk.Entry(f_pg); e_pg_desc.grid(row=0, column=1, sticky=tk.EW, padx=5, pady=2)

    ttk.Label(f_pg, text="Valor:").grid(row=1, column=0, sticky=tk.W, padx=5, pady=2)
    e_pg_valor = ttk.Entry(f_pg); e_pg_valor.grid(row=1, column=1, sticky=tk.EW, padx=5, pady=2)

    ttk.Label(f_pg, text="Vencimento (AAAA-MM-DD):").grid(row=2, column=0, sticky=tk.W, padx=5, pady=2)
    e_pg_data = ttk.Entry(f_pg); e_pg_data.grid(row=2, column=1, sticky=tk.EW, padx=5, pady=2)

    ttk.Label(f_pg, text="Conta Financeira:").grid(row=3, column=0, sticky=tk.W, padx=5, pady=2)
    cb_pg_conta = ttk.Combobox(f_pg, state="readonly"); cb_pg_conta.grid(row=3, column=1, sticky=tk.EW, padx=5, pady=2)

    ttk.Label(f_pg, text="Categoria:").grid(row=4, column=0, sticky=tk.W, padx=5, pady=2)
    cb_pg_cat = ttk.Combobox(f_pg, state="readonly"); cb_pg_cat.grid(row=4, column=1, sticky=tk.EW, padx=5, pady=2)

    pago_var = tk.BooleanVar(root, value=False)
    ttk.Checkbutton(f_pg, text="Pago", variable=pago_var).grid(row=5, column=1, sticky=tk.W, padx=5, pady=2)

    f_pg.columnconfigure(1, weight=1)

    # Barra de busca geral
    fb_busca = ttk.Frame(aba_pagar); fb_busca.pack(fill="x", padx=10, pady=0)
    ttk.Label(fb_busca, text="Buscar (Descrição/Valor/Data):").pack(side=tk.LEFT, padx=5)
    e_pg_busca = ttk.Entry(fb_busca, width=40); e_pg_busca.pack(side=tk.LEFT, padx=5, fill="x", expand=True)
    btn_limpar_filtros = ttk.Button(fb_busca, text="Limpar filtros")
    btn_limpar_filtros.pack(side=tk.LEFT, padx=5)

    tv_pg = ttk.Treeview(
        aba_pagar,
        columns=("Descricao","Valor","Vencimento","Conta","Categoria","Status"),
        show="headings",
        selectmode="extended"  # multiseleção
    )
    for col, txt in [("Descricao","Descrição"),("Valor","Valor"),("Vencimento","Vencimento"),
                     ("Conta","Conta"),("Categoria","Categoria"),("Status","Status")]:
        tv_pg.heading(col, text=txt)
    tv_pg.pack(fill=tk.BOTH, expand=True, padx=10, pady=5)

    # Total Pagar (dinâmico)
    lbl_pg_total = ttk.Label(aba_pagar, textvariable=pg_total_var, anchor="e")
    lbl_pg_total.pack(fill="x", padx=12, pady=(0,8))

    # -------- Contas a Receber -------- #
    f_rc = ttk.LabelFrame(aba_receber, text="Detalhes da Conta a Receber"); f_rc.pack(fill="x", padx=10, pady=5)
    ttk.Label(f_rc, text="Descrição:").grid(row=0, column=0, sticky=tk.W, padx=5, pady=2)
    e_rc_desc = ttk.Entry(f_rc); e_rc_desc.grid(row=0, column=1, sticky=tk.EW, padx=5, pady=2)

    ttk.Label(f_rc, text="Valor:").grid(row=1, column=0, sticky=tk.W, padx=5, pady=2)
    e_rc_valor = ttk.Entry(f_rc); e_rc_valor.grid(row=1, column=1, sticky=tk.EW, padx=5, pady=2)

    ttk.Label(f_rc, text="Vencimento (AAAA-MM-DD):").grid(row=2, column=0, sticky=tk.W, padx=5, pady=2)
    e_rc_data = ttk.Entry(f_rc); e_rc_data.grid(row=2, column=1, sticky=tk.EW, padx=5, pady=2)

    ttk.Label(f_rc, text="Conta Financeira:").grid(row=3, column=0, sticky=tk.W, padx=5, pady=2)
    cb_rc_conta = ttk.Combobox(f_rc, state="readonly"); cb_rc_conta.grid(row=3, column=1, sticky=tk.EW, padx=5, pady=2)

    ttk.Label(f_rc, text="Categoria:").grid(row=4, column=0, sticky=tk.W, padx=5, pady=2)
    cb_rc_cat = ttk.Combobox(f_rc, state="readonly"); cb_rc_cat.grid(row=4, column=1, sticky=tk.EW, padx=5, pady=2)

    recebido_var = tk.BooleanVar(root, value=False)
    ttk.Checkbutton(f_rc, text="Recebido", variable=recebido_var).grid(row=5, column=1, sticky=tk.W, padx=5, pady=2)

    f_rc.columnconfigure(1, weight=1)

    tv_rc = ttk.Treeview(
        aba_receber,
        columns=("Descricao","Valor","Vencimento","Conta","Categoria","Status"),
        show="headings",
        selectmode="extended"  # multiseleção
    )
    for col, txt in [("Descricao","Descrição"),("Valor","Valor"),("Vencimento","Vencimento"),
                     ("Conta","Conta"),("Categoria","Categoria"),("Status","Status")]:
        tv_rc.heading(col, text=txt)
    tv_rc.pack(fill=tk.BOTH, expand=True, padx=10, pady=5)

    # Total Receber (geral)
    lbl_rc_total = ttk.Label(aba_receber, textvariable=rc_total_var, anchor="e")
    lbl_rc_total.pack(fill="x", padx=12, pady=(0,8))

    # -------- Categorias -------- #
    f_cat = ttk.LabelFrame(aba_cats, text="Gerenciar Categorias"); f_cat.pack(fill="x", padx=10, pady=5)
    ttk.Label(f_cat, text="Nome:").grid(row=0, column=0, sticky=tk.W, padx=5, pady=2)
    e_cat_nome = ttk.Entry(f_cat); e_cat_nome.grid(row=0, column=1, sticky=tk.EW, padx=5, pady=2)
    f_cat.columnconfigure(1, weight=1)
    tv_cat = ttk.Treeview(aba_cats, columns=("Nome",), show="headings")
    tv_cat.heading("Nome", text="Nome da Categoria")
    tv_cat.pack(fill=tk.BOTH, expand=True, padx=10, pady=5)

    # -------- Contas Financeiras -------- #
    f_cf = ttk.LabelFrame(aba_contas, text="Gerenciar Contas"); f_cf.pack(fill="x", padx=10, pady=5)
    ttk.Label(f_cf, text="Nome:").grid(row=0, column=0, sticky=tk.W, padx=5, pady=2)
    e_cf_nome = ttk.Entry(f_cf); e_cf_nome.grid(row=0, column=1, sticky=tk.EW, padx=5, pady=2)
    f_cf.columnconfigure(1, weight=1)
    tv_cf = ttk.Treeview(aba_contas, columns=("Nome",), show="headings")
    tv_cf.heading("Nome", text="Nome da Conta")
    tv_cf.pack(fill=tk.BOTH, expand=True, padx=10, pady=5)

    f_ofx = ttk.LabelFrame(aba_contas, text="Importar OFX"); f_ofx.pack(fill="x", padx=10, pady=5)
    ttk.Label(f_ofx, text="Conta:").pack(side=tk.LEFT, padx=5, pady=5)
    cb_import_conta = ttk.Combobox(f_ofx, state="readonly")
    cb_import_conta.pack(side=tk.LEFT, padx=5, pady=5, expand=True, fill="x")
    btn_import_ofx = ttk.Button(f_ofx, text="Importar OFX")
    btn_import_ofx.pack(side=tk.LEFT, padx=5, pady=5)

    btn_export = ttk.Button(root, text="Exportar para Excel")
    btn_export.pack(pady=6)

    btn_relatorio = ttk.Button(root, text="Relatório Mensal")
    btn_relatorio.pack(pady=0)

    # ------- Helpers preenchimento de campos ------- #
    def fill_pg_fields(idx):
        c = contas_a_pagar[idx]
        e_pg_desc.delete(0, tk.END); e_pg_desc.insert(0, c["descricao"])
        e_pg_valor.delete(0, tk.END); e_pg_valor.insert(0, str(c["valor"]))
        e_pg_data.delete(0, tk.END); e_pg_data.insert(0, c["vencimento"])  # entrada segue AAAA-MM-DD
        cb_pg_conta.set(c["conta_nome"]); cb_pg_cat.set(c["categoria"])
        pago_var.set(bool(c.get("pago", False)))

    def fill_rc_fields(idx):
        c = contas_a_receber[idx]
        e_rc_desc.delete(0, tk.END); e_rc_desc.insert(0, c["descricao"])
        e_rc_valor.delete(0, tk.END); e_rc_valor.insert(0, str(c["valor"]))
        e_rc_data.delete(0, tk.END); e_rc_data.insert(0, c["vencimento"])
        cb_rc_conta.set(c["conta_nome"]); cb_rc_cat.set(c["categoria"])
        recebido_var.set(bool(c.get("recebido", False)))

    def fill_cat_fields(idx):
        e_cat_nome.delete(0, tk.END); e_cat_nome.insert(0, categorias[idx])

    def fill_cf_fields(idx):
        e_cf_nome.delete(0, tk.END); e_cf_nome.insert(0, contas_financeiras[idx]["nome"])

    # ------- Binds de seleção ------- #
    def on_select_pg(event):
        global conta_pagar_idx
        item_id = tv_pg.focus()
        if not item_id: conta_pagar_idx = None; return
        conta_pagar_idx = int(item_id); fill_pg_fields(conta_pagar_idx)

    def on_select_rc(event):
        global conta_receber_idx
        item_id = tv_rc.focus()
        if not item_id: conta_receber_idx = None; return
        conta_receber_idx = int(item_id); fill_rc_fields(conta_receber_idx)

    def on_select_cat(event):
        global categoria_idx
        item_id = tv_cat.focus()
        if not item_id: categoria_idx = None; return
        categoria_idx = int(item_id); fill_cat_fields(categoria_idx)

    def on_select_cf(event):
        global conta_financeira_idx
        item_id = tv_cf.focus()
        if not item_id: conta_financeira_idx = None; return
        conta_financeira_idx = int(item_id); fill_cf_fields(conta_financeira_idx)

    tv_pg.bind("<<TreeviewSelect>>", on_select_pg)
    tv_rc.bind("<<TreeviewSelect>>", on_select_rc)
    tv_cat.bind("<<TreeviewSelect>>", on_select_cat)
    tv_cf.bind("<<TreeviewSelect>>", on_select_cf)

    # ------- Clique na coluna Status (simula checkbox) ------- #
    def on_click_pg(event):
        region = tv_pg.identify("region", event.x, event.y)
        if region != "cell": return
        if tv_pg.identify_column(event.x) != '#6': return
        item_id = tv_pg.identify_row(event.y)
        if not item_id: return
        try:
            idx = int(item_id)
        except Exception:
            return
        item = contas_a_pagar[idx]
        models.set_paid(item["id"], not bool(item.get("pago")))
        _refresh_all(tv_pg, tv_rc, tv_cat, tv_cf, cb_pg_conta, cb_rc_conta,
                     cb_import_conta, cb_pg_cat, cb_rc_cat, pg_total_var, rc_total_var)
        try:
            tv_pg.selection_set(item_id); tv_pg.focus(item_id); fill_pg_fields(idx)
        except Exception:
            pass
        return "break"

    def on_click_rc(event):
        region = tv_rc.identify("region", event.x, event.y)
        if region != "cell": return
        if tv_rc.identify_column(event.x) != '#6': return
        item_id = tv_rc.identify_row(event.y)
        if not item_id: return
        try:
            idx = int(item_id)
        except Exception:
            return
        item = contas_a_receber[idx]
        models.set_received(item["id"], not bool(item.get("recebido")))
        _refresh_all(tv_pg, tv_rc, tv_cat, tv_cf, cb_pg_conta, cb_rc_conta,
                     cb_import_conta, cb_pg_cat, cb_rc_cat, pg_total_var, rc_total_var)
        try:
            tv_rc.selection_set(item_id); tv_rc.focus(item_id); fill_rc_fields(idx)
        except Exception:
            pass
        return "break"

    tv_pg.bind("<Button-1>", on_click_pg)
    tv_rc.bind("<Button-1>", on_click_rc)

    # ------- Limpar campos ------- #
    def limpar_pg():
        global conta_pagar_idx
        e_pg_desc.delete(0, tk.END); e_pg_valor.delete(0, tk.END); e_pg_data.delete(0, tk.END)
        e_pg_busca.delete(0, tk.END)
        cb_pg_conta.set(""); cb_pg_cat.set(""); pago_var.set(False); conta_pagar_idx = None
        _refresh_all(tv_pg, tv_rc, tv_cat, tv_cf, cb_pg_conta, cb_rc_conta,
                     cb_import_conta, cb_pg_cat, cb_rc_cat, pg_total_var, rc_total_var)

    def limpar_rc():
        global conta_receber_idx
        e_rc_desc.delete(0, tk.END); e_rc_valor.delete(0, tk.END); e_rc_data.delete(0, tk.END)
        cb_rc_conta.set(""); cb_rc_cat.set(""); recebido_var.set(False); conta_receber_idx = None

    def limpar_cat():
        global categoria_idx
        e_cat_nome.delete(0, tk.END); categoria_idx = None

    def limpar_cf():
        global conta_financeira_idx
        e_cf_nome.delete(0, tk.END); conta_financeira_idx = None

    btn_limpar_filtros.configure(command=limpar_pg)

    # ------- CRUD Contas Financeiras ------- #
    def add_cf():
        nome = e_cf_nome.get().strip()
        res = models.add_financial_account(nome)
        if res is True:
            limpar_cf()
            _refresh_all(tv_pg, tv_rc, tv_cat, tv_cf, cb_pg_conta, cb_rc_conta,
                         cb_import_conta, cb_pg_cat, cb_rc_cat, pg_total_var, rc_total_var)
            messagebox.showinfo("Sucesso", "Conta financeira adicionada.")
        else:
            messagebox.showwarning("Erro", res)

    def edit_cf():
        if conta_financeira_idx is None:
            messagebox.showwarning("Atenção", "Selecione uma conta."); return
        acc = contas_financeiras[conta_financeira_idx]
        novo = e_cf_nome.get().strip()
        res = models.edit_financial_account(acc["id"], novo)
        if res is True:
            limpar_cf()
            _refresh_all(tv_pg, tv_rc, tv_cat, tv_cf, cb_pg_conta, cb_rc_conta,
                         cb_import_conta, cb_pg_cat, cb_rc_cat, pg_total_var, rc_total_var)
            messagebox.showinfo("Sucesso", "Conta editada.")
        else:
            messagebox.showwarning("Erro", res)

    def del_cf():
        if conta_financeira_idx is None:
            messagebox.showwarning("Atenção", "Selecione uma conta."); return
        acc = contas_financeiras[conta_financeira_idx]
        if models.account_has_entries(acc["id"]):
            messagebox.showwarning("Atenção", "Não é possível excluir: há lançamentos associados."); return
        if not messagebox.askyesno("Confirmar", f"Excluir conta '{acc['nome']}'?"): return
        models.delete_financial_account_by_id(acc["id"])
        limpar_cf()
        _refresh_all(tv_pg, tv_rc, tv_cat, tv_cf, cb_pg_conta, cb_rc_conta,
                     cb_import_conta, cb_pg_cat, cb_rc_cat, pg_total_var, rc_total_var)
        messagebox.showinfo("Sucesso", "Conta excluída.")

    # ------- CRUD Categorias ------- #
    def add_cat():
        nome = e_cat_nome.get().strip()
        if not nome:
            messagebox.showwarning("Atenção", "Nome da categoria vazio."); return
        try:
            models.add_category(nome)
            limpar_cat()
            _refresh_all(tv_pg, tv_rc, tv_cat, tv_cf, cb_pg_conta, cb_rc_conta,
                         cb_import_conta, cb_pg_cat, cb_rc_cat, pg_total_var, rc_total_var)
            messagebox.showinfo("Sucesso", "Categoria adicionada.")
        except Exception as e:
            messagebox.showerror("Erro", f"Falha ao adicionar: {e}")

    def edit_cat():
        if categoria_idx is None:
            messagebox.showwarning("Atenção", "Selecione uma categoria."); return
        atual = categorias[categoria_idx]
        novo = e_cat_nome.get().strip()
        if not novo:
            messagebox.showwarning("Atenção", "Nome não pode ser vazio."); return
        if novo in categorias and novo != atual:
            messagebox.showwarning("Atenção", "Categoria já existe."); return
        models.edit_category(atual, novo)
        limpar_cat()
        _refresh_all(tv_pg, tv_rc, tv_cat, tv_cf, cb_pg_conta, cb_rc_conta,
                     cb_import_conta, cb_pg_cat, cb_rc_cat, pg_total_var, rc_total_var)
        messagebox.showinfo("Sucesso", "Categoria editada.")

    def del_cat():
        if categoria_idx is None:
            messagebox.showwarning("Atenção", "Selecione uma categoria."); return
        nome = categorias[categoria_idx]
        if not messagebox.askyesno("Confirmar", f"Excluir categoria '{nome}'?"): return
        models.delete_category(nome)
        limpar_cat()
        _refresh_all(tv_pg, tv_rc, tv_cat, tv_cf, cb_pg_conta, cb_rc_conta,
                     cb_import_conta, cb_pg_cat, cb_rc_cat, pg_total_var, rc_total_var)
        messagebox.showinfo("Sucesso", "Categoria excluída.")

    # ------- CRUD Pagar ------- #
    def add_pg():
        desc = e_pg_desc.get().strip(); val = e_pg_valor.get().strip()
        data = e_pg_data.get().strip(); conta_nome = cb_pg_conta.get().strip(); cat = cb_pg_cat.get().strip()
        res = models.add_entry("pagar", desc, val, data, None, conta_nome, cat)
        if res is True:
            limpar_pg()
            messagebox.showinfo("Sucesso", "Conta a pagar adicionada.")
        else:
            messagebox.showwarning("Erro", res)

    def edit_pg():
        if conta_pagar_idx is None:
            messagebox.showwarning("Atenção", "Selecione um item."); return
        item = contas_a_pagar[conta_pagar_idx]
        desc = e_pg_desc.get().strip(); val = e_pg_valor.get().strip()
        data = e_pg_data.get().strip(); conta_nome = cb_pg_conta.get().strip(); cat = cb_pg_cat.get().strip()
        res = models.edit_entry("pagar", item["id"], desc, val, data, item.get("conta_id"), conta_nome, cat)
        if res is True:
            limpar_pg()
            messagebox.showinfo("Sucesso", "Conta a pagar editada.")
        else:
            messagebox.showwarning("Erro", res)

    def del_pg():
        # multiseleção
        sel = tv_pg.selection()
        if not sel:
            messagebox.showwarning("Atenção", "Selecione uma ou mais contas a pagar.")
            return
        if not messagebox.askyesno("Confirmar", f"Excluir {len(sel)} conta(s) a pagar selecionada(s)?"):
            return

        ok = 0
        falhas = []
        for iid in sel:
            try:
                idx = int(iid)
                it = contas_a_pagar[idx]
            except Exception:
                continue

            res = models.delete_entry(
                "pagar",
                item_id=it.get("id"),
                descricao=it.get("descricao"),
                valor=float(it.get("valor", 0.0)),
                data_str=it.get("vencimento"),
                conta_id=it.get("conta_id"),
                conta_nome=it.get("conta_nome"),
            )
            if res is True:
                ok += 1
            else:
                falhas.append(it.get("descricao","(sem descrição)"))

        _refresh_all(
            tv_pg, tv_rc, tv_cat, tv_cf,
            cb_pg_conta, cb_rc_conta, cb_import_conta,
            cb_pg_cat, cb_rc_cat,
            pg_total_var, rc_total_var
        )

        if ok and not falhas:
            messagebox.showinfo("Sucesso", f"{ok} conta(s) a pagar excluída(s).")
        elif ok and falhas:
            messagebox.showwarning("Parcial",
                f"{ok} excluída(s), {len(falhas)} falhou(aram):\n- " + "\n- ".join(falhas))
        else:
            messagebox.showerror("Erro", "Não foi possível excluir os itens selecionados.")

    # ------- CRUD Receber ------- #
    def add_rc():
        desc = e_rc_desc.get().strip(); val = e_rc_valor.get().strip()
        data = e_rc_data.get().strip(); conta_nome = cb_rc_conta.get().strip(); cat = cb_rc_cat.get().strip()
        res = models.add_entry("receber", desc, val, data, None, conta_nome, cat)
        if res is True:
            limpar_rc()
            _refresh_all(tv_pg, tv_rc, tv_cat, tv_cf, cb_pg_conta, cb_rc_conta,
                         cb_import_conta, cb_pg_cat, cb_rc_cat, pg_total_var, rc_total_var)
            messagebox.showinfo("Sucesso", "Conta a receber adicionada.")
        else:
            messagebox.showwarning("Erro", res)

    def edit_rc():
        if conta_receber_idx is None:
            messagebox.showwarning("Atenção", "Selecione um item."); return
        item = contas_a_receber[conta_receber_idx]
        desc = e_rc_desc.get().strip(); val = e_rc_valor.get().strip()
        data = e_rc_data.get().strip(); conta_nome = cb_rc_conta.get().strip(); cat = cb_rc_cat.get().strip()
        res = models.edit_entry("receber", item["id"], desc, val, data, item.get("conta_id"), conta_nome, cat)
        if res is True:
            limpar_rc()
            _refresh_all(tv_pg, tv_rc, tv_cat, tv_cf, cb_pg_conta, cb_rc_conta,
                         cb_import_conta, cb_pg_cat, cb_rc_cat, pg_total_var, rc_total_var)
            messagebox.showinfo("Sucesso", "Conta a receber editada.")
        else:
            messagebox.showwarning("Erro", res)

    def del_rc():
        # multiseleção
        sel = tv_rc.selection()
        if not sel:
            messagebox.showwarning("Atenção", "Selecione uma ou mais contas a receber.")
            return
        if not messagebox.askyesno("Confirmar", f"Excluir {len(sel)} conta(s) a receber selecionada(s)?"):
            return

        ok = 0
        falhas = []
        for iid in sel:
            try:
                idx = int(iid)
                it = contas_a_receber[idx]
            except Exception:
                continue

            res = models.delete_entry(
                "receber",
                item_id=it.get("id"),
                descricao=it.get("descricao"),
                valor=float(it.get("valor", 0.0)),
                data_str=it.get("vencimento"),
                conta_id=it.get("conta_id"),
                conta_nome=it.get("conta_nome"),
            )
            if res is True:
                ok += 1
            else:
                falhas.append(it.get("descricao","(sem descrição)"))

        _refresh_all(
            tv_pg, tv_rc, tv_cat, tv_cf,
            cb_pg_conta, cb_rc_conta, cb_import_conta,
            cb_pg_cat, cb_rc_cat,
            pg_total_var, rc_total_var
        )

        if ok and not falhas:
            messagebox.showinfo("Sucesso", f"{ok} conta(s) a receber excluída(s).")
        elif ok and falhas:
            messagebox.showwarning("Parcial",
                f"{ok} excluída(s), {len(falhas)} falhou(aram):\n- " + "\n- ".join(falhas))
        else:
            messagebox.showerror("Erro", "Não foi possível excluir os itens selecionados.")

    # ------- Importar OFX / Exportar / Relatório Mensal ------- #
    def importar_ofx():
        path = filedialog.askopenfilename(defaultextension=".ofx",
                                          filetypes=[("OFX","*.ofx"),("Todos","*.*")])
        if not path: return
        conta_nome = cb_import_conta.get().strip()
        if not conta_nome:
            messagebox.showwarning("Atenção", "Selecione uma conta para importar."); return
        conta = next((c for c in contas_financeiras if c["nome"] == conta_nome), None)
        if not conta:
            messagebox.showerror("Erro", "Conta selecionada não encontrada."); return
        trans, err = ofx_importer.process_ofx(path, conta["id"], conta["nome"])
        if err:
            messagebox.showerror("Erro", err); return
        qtd = ofx_importer.add_imported_transactions(trans)
        _refresh_all(tv_pg, tv_rc, tv_cat, tv_cf, cb_pg_conta, cb_rc_conta,
                     cb_import_conta, cb_pg_cat, cb_rc_cat, pg_total_var, rc_total_var)
        if qtd: messagebox.showinfo("Sucesso", f"{qtd} transações importadas.")
        else:   messagebox.showinfo("Informação", "Nenhuma nova transação encontrada.")

    def exportar():
        ok, msg = export_excel.export_to_excel(contas_a_pagar, contas_a_receber)
        (messagebox.showinfo if ok else messagebox.showerror)("Exportar", msg)

    def abrir_relatorio_mensal():
        # popup para escolher mês/ano/categoria
        win = tk.Toplevel(root)
        win.title("Relatório Mensal")

        ttk.Label(win, text="Mês (1-12):").grid(row=0, column=0, padx=5, pady=5, sticky=tk.W)
        cb_mes = ttk.Combobox(win, state="readonly", values=[str(i) for i in range(1,13)], width=10)
        cb_mes.grid(row=0, column=1, padx=5, pady=5, sticky=tk.EW)

        ttk.Label(win, text="Ano (YYYY):").grid(row=1, column=0, padx=5, pady=5, sticky=tk.W)
        e_ano = ttk.Entry(win, width=12)
        e_ano.insert(0, str(datetime.now().year))
        e_ano.grid(row=1, column=1, padx=5, pady=5, sticky=tk.EW)

        ttk.Label(win, text="Categoria:").grid(row=2, column=0, padx=5, pady=5, sticky=tk.W)
        cb_cat = ttk.Combobox(win, state="readonly", values=["Todas"] + categorias)
        cb_cat.set("Todas")
        cb_cat.grid(row=2, column=1, padx=5, pady=5, sticky=tk.EW)

        def _gerar():
            m = cb_mes.get().strip()
            a = e_ano.get().strip()
            if not m or not a:
                messagebox.showwarning("Atenção", "Informe mês e ano.")
                return
            try:
                mes = int(m); ano = int(a)
                if mes < 1 or mes > 12 or ano < 1900:
                    raise ValueError()
            except Exception:
                messagebox.showwarning("Atenção", "Mês/Ano inválidos.")
                return

            cat = cb_cat.get().strip()
            cat = None if (not cat or cat.lower()=="todas") else cat

            ok, msg = export_excel.export_monthly_report(mes, ano, cat)
            (messagebox.showinfo if ok else messagebox.showerror)("Relatório Mensal", msg)
            if ok:
                try: win.destroy()
                except: pass

        ttk.Button(win, text="Gerar", command=_gerar).grid(row=3, column=0, columnspan=2, padx=5, pady=10)
        win.columnconfigure(1, weight=1)

    btn_import_ofx.configure(command=importar_ofx)
    btn_export.configure(command=exportar)
    btn_relatorio.configure(command=abrir_relatorio_mensal)

    # ------- FILTROS ao digitar (Pagar) ------- #
    def _rebuild_tv_pagar_from_indices(indices):
        for r in tv_pg.get_children():
            tv_pg.delete(r)
        for i in indices:
            c = contas_a_pagar[i]
            status = "☑ Pago" if c.get("pago") else "☐ Pendente"
            tv_pg.insert("", "end", iid=str(i),
                values=(c.get("descricao",""),
                        f"R$ {float(c.get('valor',0)):.2f}",
                        formatar_data_br(c.get("vencimento","")),
                        c.get("conta_nome",""),
                        c.get("categoria",""),
                        status))
        _set_pg_total_by_indices(indices, pg_total_var)

    def _apply_filters_pagar():
        """
        Filtros na aba Pagar:
        - Valor: exato (numérico) OU substring do valor mostrado "R$ X,XX"
        - Descrição: substring case-insensitive
        - Data (campo): substring do ISO (AAAA-MM-DD) — a grid exibe BR
        - Busca geral: em descrição, data BR e valor mostrado
        """
        texto_valor = e_pg_valor.get().strip()
        texto_desc  = e_pg_desc.get().strip().lower()
        texto_data  = e_pg_data.get().strip().lower()
        texto_busca = e_pg_busca.get().strip().lower()

        if not (texto_valor or texto_desc or texto_data or texto_busca):
            _refresh_all(tv_pg, tv_rc, tv_cat, tv_cf, cb_pg_conta, cb_rc_conta,
                         cb_import_conta, cb_pg_cat, cb_rc_cat, pg_total_var, rc_total_var)
            return

        indices = []
        valor_num = None
        valor_is_number = False
        if texto_valor:
            try:
                valor_num = _parse_valor_local(texto_valor)
                valor_is_number = True
            except Exception:
                valor_is_number = False

        for i, c in enumerate(contas_a_pagar):
            desc = (c.get("descricao","") or "").lower()
            data_iso = (c.get("vencimento","") or "").lower()
            data_br = formatar_data_br(c.get("vencimento","")).lower()
            shown_val = f"R$ {float(c.get('valor',0)):.2f}".replace(".", ",").replace(" ", "").lower()

            ok = True
            if texto_valor:
                if valor_is_number:
                    if abs(float(c.get("valor",0.0)) - valor_num) >= 0.01:
                        ok = False
                else:
                    if texto_valor.replace(".", ",").replace(" ", "").lower() not in shown_val:
                        ok = False
            if ok and texto_desc and (texto_desc not in desc):
                ok = False
            if ok and texto_data and (texto_data not in data_iso):
                ok = False
            if ok and texto_busca:
                if (texto_busca not in desc) and (texto_busca not in data_br) and (texto_busca not in shown_val):
                    ok = False
            if ok:
                indices.append(i)

        _rebuild_tv_pagar_from_indices(indices)

    def on_valor_key(event=None): _apply_filters_pagar()
    def on_desc_key(event=None):  _apply_filters_pagar()
    def on_data_key(event=None):  _apply_filters_pagar()
    def on_busca_key(event=None): _apply_filters_pagar()

    e_pg_valor.bind("<KeyRelease>", on_valor_key)
    e_pg_desc.bind("<KeyRelease>", on_desc_key)
    e_pg_data.bind("<KeyRelease>", on_data_key)
    e_pg_busca.bind("<KeyRelease>", on_busca_key)

    # ------- Botões ------- #
    fb_pg = ttk.Frame(aba_pagar); fb_pg.pack(fill="x", padx=10, pady=5)
    ttk.Button(fb_pg, text="Adicionar", command=add_pg).pack(side=tk.LEFT, padx=5)
    ttk.Button(fb_pg, text="Editar",   command=edit_pg).pack(side=tk.LEFT, padx=5)
    ttk.Button(fb_pg, text="Excluir selecionadas",  command=del_pg).pack(side=tk.LEFT, padx=5)
    ttk.Button(fb_pg, text="Limpar",   command=limpar_pg).pack(side=tk.LEFT, padx=5)
    # Dica: para marcar como Pago/Não pago, clique na coluna "Status" da tabela.

    fb_rc = ttk.Frame(aba_receber); fb_rc.pack(fill="x", padx=10, pady=5)
    ttk.Button(fb_rc, text="Adicionar", command=add_rc).pack(side=tk.LEFT, padx=5)
    ttk.Button(fb_rc, text="Editar",    command=edit_rc).pack(side=tk.LEFT, padx=5)
    ttk.Button(fb_rc, text="Excluir selecionadas",   command=del_rc).pack(side=tk.LEFT, padx=5)
    ttk.Button(fb_rc, text="Limpar",    command=limpar_rc).pack(side=tk.LEFT, padx=5)

    fb_cat = ttk.Frame(aba_cats); fb_cat.pack(fill="x", padx=10, pady=5)
    ttk.Button(fb_cat, text="Adicionar", command=add_cat).pack(side=tk.LEFT, padx=5)
    ttk.Button(fb_cat, text="Editar",    command=edit_cat).pack(side=tk.LEFT, padx=5)
    ttk.Button(fb_cat, text="Excluir",   command=del_cat).pack(side=tk.LEFT, padx=5)
    ttk.Button(fb_cat, text="Limpar",    command=limpar_cat).pack(side=tk.LEFT, padx=5)

    fb_cf = ttk.Frame(aba_contas); fb_cf.pack(fill="x", padx=10, pady=5)
    ttk.Button(fb_cf, text="Adicionar", command=add_cf).pack(side=tk.LEFT, padx=5)
    ttk.Button(fb_cf, text="Editar",    command=edit_cf).pack(side=tk.LEFT, padx=5)
    ttk.Button(fb_cf, text="Excluir",   command=del_cf).pack(side=tk.LEFT, padx=5)
    btn_import_ofx.configure(command=importar_ofx)

    # ------- Atalhos de teclado ------- #
    def _is_pagar_active():
        return nb.select() == aba_pagar._w
    def _is_receber_active():
        return nb.select() == aba_receber._w

    def _enter_add(event=None):
        if _is_pagar_active(): add_pg()
        elif _is_receber_active(): add_rc()

    def _ctrl_e_edit(event=None):
        if _is_pagar_active(): edit_pg()
        elif _is_receber_active(): edit_rc()

    def _del_delete(event=None):
        if _is_pagar_active(): del_pg()
        elif _is_receber_active(): del_rc()

    root.bind("<Return>", _enter_add)
    root.bind("<Control-e>", _ctrl_e_edit)
    root.bind("<Delete>", _del_delete)

    # Liga botões principais
    btn_export.configure(command=exportar)
    btn_relatorio.configure(command=abrir_relatorio_mensal)

    # ------- Inicialização ------- #
    _refresh_all(tv_pg, tv_rc, tv_cat, tv_cf, cb_pg_conta, cb_rc_conta,
                 cb_import_conta, cb_pg_cat, cb_rc_cat, pg_total_var, rc_total_var)
    root.mainloop()

if __name__ == "__main__":
    main_window()
