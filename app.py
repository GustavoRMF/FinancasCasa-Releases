import csv
import os
import shutil
import sqlite3
import sys
import tkinter as tk
from calendar import monthrange
from datetime import datetime
from tkinter import filedialog, messagebox, ttk
import json
import threading
import urllib.request
import urllib.error
import subprocess
import re


DB_NAME = "financas_casa.db"
from version import VERSAO_ATUAL
UPDATE_MANIFEST_URL = "https://SEU-SERVIDOR.com/financascasa/update.json"  # Configure antes de publicar o atualizador
UPDATE_MANIFEST_TIMEOUT = 10



# ============================================================
# BANCO DE DADOS
# ============================================================


def conectar():
    return sqlite3.connect(DB_NAME)


def criar_banco():
    conn = conectar()
    cur = conn.cursor()

    cur.execute("""
        CREATE TABLE IF NOT EXISTS lancamentos (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            tipo TEXT NOT NULL,
            descricao TEXT NOT NULL,
            categoria TEXT NOT NULL,
            valor REAL NOT NULL,
            data TEXT NOT NULL,
            observacao TEXT DEFAULT '',
            pago INTEGER DEFAULT 1
        )
    """)

    cur.execute("""
        CREATE TABLE IF NOT EXISTS contas (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            nome TEXT NOT NULL,
            valor REAL NOT NULL,
            vencimento TEXT NOT NULL,
            categoria TEXT NOT NULL,
            status TEXT NOT NULL DEFAULT 'Pendente'
        )
    """)

    cur.execute("""
        CREATE TABLE IF NOT EXISTS metas (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            nome TEXT NOT NULL,
            objetivo REAL NOT NULL,
            atual REAL NOT NULL DEFAULT 0
        )
    """)

    cur.execute("""
        CREATE TABLE IF NOT EXISTS cartoes (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            nome TEXT NOT NULL,
            limite REAL NOT NULL,
            fechamento INTEGER NOT NULL DEFAULT 1,
            vencimento INTEGER NOT NULL DEFAULT 10
        )
    """)

    cur.execute("""
        CREATE TABLE IF NOT EXISTS parcelas (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            descricao TEXT NOT NULL,
            valor REAL NOT NULL,
            total INTEGER NOT NULL,
            atual INTEGER NOT NULL,
            vencimento TEXT NOT NULL,
            categoria TEXT NOT NULL DEFAULT 'Cartão',
            cartao TEXT NOT NULL DEFAULT ''
        )
    """)

    cur.execute("""
        CREATE TABLE IF NOT EXISTS recorrentes (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            descricao TEXT NOT NULL,
            valor REAL NOT NULL,
            categoria TEXT NOT NULL,
            dia INTEGER NOT NULL,
            tipo TEXT NOT NULL DEFAULT 'Despesa',
            ativo INTEGER NOT NULL DEFAULT 1
        )
    """)

    conn.commit()
    conn.close()


# ============================================================
# UTILITÁRIOS
# ============================================================


def dinheiro(valor):
    """Formata valores monetários no padrão brasileiro usando o símbolo $."""
    return (
        "$ "
        + f"{float(valor):,.2f}".replace(",", "X")
        .replace(".", ",")
        .replace("X", ".")
    )


def valor_float(valor):
    valor = (
        str(valor)
        .strip()
        .replace("R$", "")
        .replace("$", "")
        .replace(" ", "")
    )
    if "," in valor:
        valor = valor.replace(".", "").replace(",", ".")
    try:
        return float(valor)
    except ValueError:
        return None


def data_valida(data):
    try:
        datetime.strptime(data, "%d/%m/%Y")
        return True
    except ValueError:
        return False


# ============================================================
# APLICAÇÃO
# ============================================================


class FinanceiroApp:

    def __init__(self, root):
        self.root = root
        self.root.title(
            f"FINANÇAS CASA 3.0 • CASA FAMILIAR (Versão {VERSAO_ATUAL})"
        )
        self.root.geometry("1250x760")
        self.root.minsize(1050, 680)
        self.root.configure(bg="#FFF8F0")

        # CARREGAMENTO DO ÍCONE COM TRATAMENTO DE ERRO
        try:
            self.root.iconbitmap("icone.ico")
        except Exception:
            pass

        self.id_edicao = None
        self.current_page = None
        self.tema_escuro = False

        self.configurar_estilo()
        self.criar_interface()
        self.mostrar_dashboard()
        self.aplicar_tema()

    # ========================================================
    # ESTILO
    # ========================================================

    def configurar_estilo(self):
        self.style = ttk.Style(self.root)
        try:
            self.style.theme_use("clam")
        except tk.TclError:
            pass

        self.atualizar_estilo_ttk()

    def atualizar_estilo_ttk(self):
        """Atualiza os estilos ttk para o tema atual."""
        if getattr(self, "tema_escuro", False):
            bg = "#1E2421"
            panel = "#29312D"
            fg = "#F1F5F3"
            muted = "#B7C2BC"
            heading = "#35413B"
            selected = "#3D5147"
            field = "#29312D"
        else:
            bg = "#FFF8F0"
            panel = "white"
            fg = "#31443A"
            muted = "#7A817B"
            heading = "#E7DED2"
            selected = "#F3E7D8"
            field = "white"

        self.style.configure(
            "Treeview",
            background=panel,
            foreground=fg,
            rowheight=34,
            fieldbackground=field,
            font=("Segoe UI", 10),
        )
        self.style.configure(
            "Treeview.Heading",
            background=heading,
            foreground=fg,
            font=("Segoe UI", 10, "bold"),
        )
        self.style.map(
            "Treeview",
            background=[("selected", selected)],
            foreground=[("selected", fg)],
        )
        self.style.configure(
            "TCombobox",
            fieldbackground=field,
            background=heading,
            foreground=fg,
            arrowcolor=fg,
        )
        self.style.map(
            "TCombobox",
            fieldbackground=[("readonly", field)],
            foreground=[("readonly", fg)],
        )
        self.style.configure(
            "TLabel",
            background=bg,
            foreground=fg,
        )
        self.style.configure(
            "TProgressbar",
            troughcolor=heading,
            background="#6C9B73",
        )

    def alternar_tema(self):
        """Alterna entre tema claro e tema escuro."""
        self.tema_escuro = not self.tema_escuro
        self.atualizar_estilo_ttk()
        if hasattr(self, "botao_tema"):
            self.botao_tema.configure(
                text="☀️  Tema Claro" if self.tema_escuro else "🌙  Tema Escuro"
            )
        self.root.configure(bg=self.cor("bg"))
        self.atualizar_pagina()

    def cor(self, nome):
        """Retorna uma cor do tema atual."""
        claro = {
            "bg": "#FFF8F0",
            "panel": "white",
            "text": "#31443A",
            "muted": "#7A817B",
            "secondary": "#475569",
            "border": "#E7DED2",
            "selected": "#F3E7D8",
        }
        escuro = {
            "bg": "#1E2421",
            "panel": "#29312D",
            "text": "#F1F5F3",
            "muted": "#B7C2BC",
            "secondary": "#D2DDD7",
            "border": "#3A4540",
            "selected": "#3D5147",
        }
        return (escuro if self.tema_escuro else claro)[nome]

    def aplicar_tema(self):
        """Recolore widgets Tk já criados sem alterar os dados."""
        bg = self.cor("bg")
        panel = self.cor("panel")
        text = self.cor("text")
        muted = self.cor("muted")
        secondary = self.cor("secondary")
        border = self.cor("border")
        selected = self.cor("selected")

        mapa_bg = {
            "#FFF8F0": bg,
            "white": panel,
            "#FFFFFF": panel,
            "#E7DED2": border,
            "#F3E7D8": selected,
        }
        mapa_fg = {
            "#31443A": text,
            "#7A817B": muted,
            "#475569": secondary,
        }

        def visitar(widget):
            try:
                wbg = widget.cget("bg")
                if wbg in mapa_bg:
                    widget.configure(bg=mapa_bg[wbg])
            except (tk.TclError, TypeError):
                pass

            try:
                wfg = widget.cget("fg")
                if wfg in mapa_fg:
                    widget.configure(fg=mapa_fg[wfg])
            except (tk.TclError, TypeError):
                pass

            try:
                # Mantém a barra lateral verde, mas melhora o contraste no escuro.
                if widget is self.sidebar:
                    widget.configure(bg="#263A32" if self.tema_escuro else "#355C4D")
                elif str(widget).startswith(str(self.sidebar)):
                    pass
            except Exception:
                pass

            for child in widget.winfo_children():
                visitar(child)

        visitar(self.root)

        # Elementos fixos da barra lateral
        try:
            sidebar_bg = "#263A32" if self.tema_escuro else "#355C4D"
            for child in self.sidebar.winfo_children():
                try:
                    child.configure(bg=sidebar_bg)
                    for sub in child.winfo_children():
                        try:
                            if sub.cget("bg") in ("#355C4D", "#263A32"):
                                sub.configure(bg=sidebar_bg)
                        except tk.TclError:
                            pass
                except tk.TclError:
                    pass
            self.sidebar.configure(bg=sidebar_bg)
        except Exception:
            pass

        try:
            self.root.update_idletasks()
        except tk.TclError:
            pass

    # ========================================================
    # INTERFACE PRINCIPAL
    # ========================================================

    def criar_interface(self):
        self.sidebar = tk.Frame(self.root, bg="#355C4D", width=235)
        self.sidebar.pack(side="left", fill="y")
        self.sidebar.pack_propagate(False)

        self.conteudo = tk.Frame(self.root, bg="#FFF8F0")
        self.conteudo.pack(side="right", fill="both", expand=True)

        # Logo
        logo = tk.Frame(self.sidebar, bg="#355C4D")
        logo.pack(fill="x", pady=(25, 25))

        tk.Label(
            logo, text="💰", bg="#355C4D", fg="white", font=("Segoe UI Emoji", 28)
        ).pack()

        linha = tk.Frame(logo, bg="#355C4D")
        linha.pack()

        tk.Label(
            linha,
            text="FINANÇAS ",
            bg="#355C4D",
            fg="white",
            font=("Segoe UI", 14, "bold"),
        ).pack(side="left")

        tk.Label(
            linha,
            text="CASA",
            bg="#355C4D",
            fg="#E8B04A",
            font=("Segoe UI", 14, "bold"),
        ).pack(side="left")

        tk.Label(
            self.sidebar,
            text=f"Tema Casa Familiar (v{VERSAO_ATUAL})",
            bg="#355C4D",
            fg="#D7E2DC",
            font=("Segoe UI", 9),
        ).pack()

        self.criar_menu("🏠  Dashboard", self.mostrar_dashboard)
        self.criar_menu("➕  Lançamentos", self.mostrar_lancamentos)
        self.criar_menu("💳  Contas a pagar", self.mostrar_contas)
        self.criar_menu("🎯  Metas", self.mostrar_metas)
        self.criar_menu("💳  Cartões", self.mostrar_cartoes)
        self.criar_menu("🔁  Recorrentes", self.mostrar_recorrentes)
        self.criar_menu("📈  Análise", self.mostrar_analise)
        self.criar_menu("⚙️  Ferramentas", self.mostrar_ferramentas)

        self.botao_tema = tk.Button(
            self.sidebar,
            text="🌙  Tema Escuro",
            command=self.alternar_tema,
            bg="#355C4D",
            fg="#E7DED2",
            activebackground="#29483C",
            activeforeground="white",
            relief="flat",
            anchor="w",
            font=("Segoe UI", 11, "bold"),
            padx=22,
            pady=10,
            cursor="hand2",
        )
        self.botao_tema.pack(fill="x", padx=8, pady=2)

        tk.Frame(self.sidebar, bg="#6B7D72", height=1).pack(
            fill="x", padx=18, pady=20
        )

        self.criar_menu("🔄  Atualizar Página", self.atualizar_pagina)
        self.criar_menu(
            "⬆️  Verificar Atualização", self.verificar_atualizacao
        )
        self.criar_menu("❌  Sair", self.root.destroy)

    def criar_menu(self, texto, comando):
        btn = tk.Button(
            self.sidebar,
            text=texto,
            command=comando,
            bg="#355C4D",
            fg="#E7DED2",
            activebackground="#29483C",
            activeforeground="white",
            relief="flat",
            anchor="w",
            font=("Segoe UI", 11, "bold"),
            padx=22,
            pady=10,
            cursor="hand2",
        )
        btn.pack(fill="x", padx=8, pady=2)

    def limpar_conteudo(self):
        for widget in self.conteudo.winfo_children():
            widget.destroy()
        # A página é reconstruída com seus widgets; aplica o tema depois da construção.
        try:
            self.root.after_idle(self.aplicar_tema)
        except tk.TclError:
            pass

    def titulo_pagina(self, titulo, subtitulo):
        cab = tk.Frame(self.conteudo, bg="#FFF8F0")
        cab.pack(fill="x", padx=30, pady=(25, 10))

        tk.Label(
            cab,
            text=titulo,
            bg="#FFF8F0",
            fg="#31443A",
            font=("Segoe UI", 24, "bold"),
        ).pack(anchor="w")

        tk.Label(
            cab,
            text=subtitulo,
            bg="#FFF8F0",
            fg="#7A817B",
            font=("Segoe UI", 10),
        ).pack(anchor="w", pady=(3, 0))

    def atualizar_pagina(self):
        mapa = {
            "dashboard": self.mostrar_dashboard,
            "lancamentos": self.mostrar_lancamentos,
            "contas": self.mostrar_contas,
            "metas": self.mostrar_metas,
            "cartoes": self.mostrar_cartoes,
            "recorrentes": self.mostrar_recorrentes,
            "analise": self.mostrar_analise,
            "ferramentas": self.mostrar_ferramentas,
        }
        fn = mapa.get(self.current_page, self.mostrar_dashboard)
        fn()
        self.aplicar_tema()

    # ========================================================
    # ATUALIZADOR DE SOFTWARE & UPLOAD DE ATUALIZAÇÃO
    # ========================================================

    def verificar_atualizacao(self):
        """Verifica a versão disponível no servidor."""
        def verificar():
            try:
                req = urllib.request.Request(
                    UPDATE_MANIFEST_URL,
                    headers={"User-Agent": "FinancasCasa-Updater"}
                )
                with urllib.request.urlopen(
                    req, timeout=UPDATE_MANIFEST_TIMEOUT
                ) as response:
                    dados = json.loads(response.read().decode("utf-8"))

                versao_remota = str(dados.get("version", "")).strip()
                url_pacote = str(dados.get("url", "")).strip()
                notas = str(dados.get("notes", "")).strip()

                if not versao_remota or not url_pacote:
                    raise ValueError("Manifesto de atualização incompleto.")

                def versao_tuple(v):
                    nums = re.findall(r"\d+", str(v))
                    return tuple(int(x) for x in nums) if nums else (0,)

                if versao_tuple(versao_remota) <= versao_tuple(VERSAO_ATUAL):
                    self.root.after(
                        0,
                        lambda: messagebox.showinfo(
                            "Atualização",
                            f"Você já está usando a versão mais recente ({VERSAO_ATUAL})."
                        ),
                    )
                    return

                texto = (
                    f"Nova versão disponível!\n\n"
                    f"Versão atual: {VERSAO_ATUAL}\n"
                    f"Nova versão: {versao_remota}\n"
                )
                if notas:
                    texto += f"\nAlterações:\n{notas}\n"
                texto += "\nDeseja baixar e instalar agora?"

                def confirmar():
                    if messagebox.askyesno("Nova atualização", texto):
                        self.iniciar_atualizacao(url_pacote, versao_remota)

                self.root.after(0, confirmar)

            except Exception as e:
                self.root.after(
                    0,
                    lambda: messagebox.showerror(
                        "Atualização",
                        f"Falha ao verificar atualização:\n\n{e}"
                    ),
                )

        threading.Thread(target=verificar, daemon=True).start()

    def iniciar_atualizacao(self, url_pacote, versao_remota):
        """Inicia o updater separado e fecha o programa principal."""
        try:
            app_dir = os.path.dirname(os.path.abspath(sys.argv[0]))
            updater = os.path.join(app_dir, "updater.exe")

            if not os.path.exists(updater):
                messagebox.showerror(
                    "Atualização",
                    "updater.exe não foi encontrado na pasta do programa."
                )
                return

            subprocess.Popen(
                [
                    updater,
                    "--url", url_pacote,
                    "--version", str(versao_remota),
                    "--pid", str(os.getpid()),
                ],
                cwd=app_dir,
                close_fds=True,
            )
            self.root.destroy()

        except Exception as e:
            messagebox.showerror(
                "Atualização",
                f"Não foi possível iniciar o atualizador:\n\n{e}"
            )
    def fazer_upload_atualizacao(self):
        arquivo = filedialog.askopenfilename(
            title="Selecionar pacote de atualização Versão 2",
            filetypes=[
                ("Arquivos de Código Python", "*.py"),
                ("Todos os arquivos", "*.*"),
            ],
        )
        if arquivo:
            nome_arquivo = os.path.basename(arquivo)
            if messagebox.askyesno(
                "Confirmar Atualização",
                f"Deseja aplicar a atualização contida em:\n{nome_arquivo}?\n\nIsso atualizará os módulos e reiniciará a aplicação.",
            ):
                try:
                    script_atual = os.path.abspath(sys.argv[0])
                    shutil.copy(arquivo, script_atual)
                    messagebox.showinfo(
                        "Sucesso v2",
                        "Atualização instalada com sucesso! O aplicativo será reiniciado.",
                    )
                    self.root.destroy()
                    os.startfile(script_atual)
                except Exception as e:
                    messagebox.showerror(
                        "Erro", f"Falha ao substituir arquivo de código:\n{e}"
                    )

    # ========================================================
    # DASHBOARD
    # ========================================================

    def mostrar_dashboard(self):
        self.current_page = "dashboard"
        self.limpar_conteudo()
        self.titulo_pagina(
            "Dashboard",
            "Uma visão simples e aconchegante das finanças da família",
        )

        mes = datetime.now().strftime("%m")
        ano = datetime.now().strftime("%Y")
        hoje_str = datetime.now().strftime("%d/%m/%Y")

        conn = conectar()
        cur = conn.cursor()

        cur.execute(
            """
            SELECT
                COALESCE(SUM(CASE WHEN tipo='Receita' THEN valor ELSE 0 END), 0),
                COALESCE(SUM(CASE WHEN tipo='Despesa' THEN valor ELSE 0 END), 0)
            FROM lancamentos
            WHERE substr(data,4,2)=? AND substr(data,7,4)=?
        """,
            (mes, ano),
        )

        receitas, despesas = cur.fetchone()
        saldo = receitas - despesas

        cur.execute(
            """
            SELECT categoria, SUM(valor)
            FROM lancamentos
            WHERE tipo='Despesa'
              AND substr(data,4,2)=?
              AND substr(data,7,4)=?
            GROUP BY categoria
            ORDER BY SUM(valor) DESC
            LIMIT 6
        """,
            (mes, ano),
        )

        categorias = cur.fetchall()

        cur.execute("SELECT COUNT(*) FROM contas WHERE status='Pendente'")
        contas_pendentes = cur.fetchone()[0]

        # V2 Novo Recurso: Verificação de Contas Vencendo
        cur.execute(
            "SELECT COUNT(*) FROM contas WHERE status='Pendente' AND vencimento <= ?",
            (hoje_str,),
        )
        contas_vencidas = cur.fetchone()[0]

        cur.execute(
            "SELECT COALESCE(SUM(objetivo),0), COALESCE(SUM(atual),0) FROM metas"
        )
        total_objetivo, total_atual = cur.fetchone()

        conn.close()

        cards = tk.Frame(self.conteudo, bg="#FFF8F0")
        cards.pack(fill="x", padx=30, pady=15)

        self.card(cards, "Receitas", receitas, "#4F8A68", "💵", 0)
        self.card(cards, "Despesas", despesas, "#C96B5B", "💸", 1)
        self.card(
            cards,
            "Saldo",
            saldo,
            "#4F8A68" if saldo >= 0 else "#C96B5B",
            "💰",
            2,
        )
        self.card(
            cards,
            "Contas Pendentes",
            f"{contas_pendentes} ({contas_vencidas} hoje/vencidas)",
            "#C58B45" if contas_vencidas == 0 else "#C96B5B",
            "📅",
            3,
        )

        corpo = tk.Frame(self.conteudo, bg="#FFF8F0")
        corpo.pack(fill="both", expand=True, padx=30, pady=10)

        painel = tk.Frame(
            corpo,
            bg="white",
            highlightthickness=1,
            highlightbackground="#E7DED2",
        )
        painel.pack(side="left", fill="both", expand=True, padx=(0, 10))

        tk.Label(
            painel,
            text="🏠 Gastos da casa por categoria",
            bg="white",
            fg="#31443A",
            font=("Segoe UI", 13, "bold"),
        ).pack(anchor="w", padx=18, pady=15)

        if not categorias:
            tk.Label(
                painel,
                text="Nenhuma despesa registrada neste mês.",
                bg="white",
                fg="#7A817B",
                font=("Segoe UI", 10),
            ).pack(pady=40)
        else:
            for categoria, valor in categorias:
                linha = tk.Frame(painel, bg="white")
                linha.pack(fill="x", padx=18, pady=7)

                tk.Label(
                    linha,
                    text=categoria,
                    bg="white",
                    fg="#6B7D72",
                    font=("Segoe UI", 10, "bold"),
                ).pack(side="left")

                tk.Label(
                    linha,
                    text=dinheiro(valor),
                    bg="white",
                    fg="#C96B5B",
                    font=("Segoe UI", 10, "bold"),
                ).pack(side="right")

        painel2 = tk.Frame(
            corpo,
            bg="white",
            highlightthickness=1,
            highlightbackground="#E7DED2",
            width=330,
        )
        painel2.pack(side="right", fill="y", padx=(10, 0))
        painel2.pack_propagate(False)

        tk.Label(
            painel2,
            text="🎯 Metas da família",
            bg="white",
            fg="#31443A",
            font=("Segoe UI", 13, "bold"),
        ).pack(anchor="w", padx=18, pady=15)

        if total_objetivo > 0:
            percentual = min((total_atual / total_objetivo) * 100, 100)
            tk.Label(
                painel2,
                text=f"{percentual:.1f}% concluído",
                bg="white",
                fg="#C58B45",
                font=("Segoe UI", 20, "bold"),
            ).pack(pady=20)

            barra = ttk.Progressbar(
                painel2, maximum=100, value=percentual, length=270
            )
            barra.pack(pady=10)

            tk.Label(
                painel2,
                text=f"{dinheiro(total_atual)} de {dinheiro(total_objetivo)}",
                bg="white",
                fg="#7A817B",
                font=("Segoe UI", 10),
            ).pack(pady=5)
        else:
            tk.Label(
                painel2,
                text="Nenhuma meta cadastrada.",
                bg="white",
                fg="#7A817B",
            ).pack(pady=40)

        tk.Button(
            self.conteudo,
            text="📊 Abrir análise mensal",
            command=self.mostrar_analise,
            bg="#31443A",
            fg="white",
            relief="flat",
            font=("Segoe UI", 10, "bold"),
            padx=18,
            pady=8,
            cursor="hand2",
        ).pack(anchor="e", padx=30, pady=(0, 15))

    def card(self, parent, titulo, valor, cor, icone, coluna):
        frame = tk.Frame(
            parent,
            bg="white",
            highlightthickness=1,
            highlightbackground="#E7DED2",
        )
        frame.grid(row=0, column=coluna, sticky="nsew", padx=6)
        parent.grid_columnconfigure(coluna, weight=1)

        tk.Label(frame, text=icone, bg="white", font=("Segoe UI Emoji", 20)).pack(
            side="left", padx=15, pady=18
        )

        box = tk.Frame(frame, bg="white")
        box.pack(side="left", pady=14)

        tk.Label(
            box,
            text=titulo,
            bg="white",
            fg="#7A817B",
            font=("Segoe UI", 9, "bold"),
        ).pack(anchor="w")
        tk.Label(
            box,
            text=dinheiro(valor)
            if isinstance(valor, (int, float))
            else str(valor),
            bg="white",
            fg=cor,
            font=("Segoe UI", 14, "bold"),
        ).pack(anchor="w", pady=(3, 0))

    # ========================================================
    # LANÇAMENTOS
    # ========================================================

    def mostrar_lancamentos(self):
        self.current_page = "lancamentos"
        self.limpar_conteudo()
        self.titulo_pagina(
            "Lançamentos", "Cadastre e acompanhe receitas e despesas"
        )

        form = tk.LabelFrame(
            self.conteudo,
            text=" Novo lançamento ",
            bg="#FFF8F0",
            fg="#31443A",
            font=("Segoe UI", 11, "bold"),
            padx=15,
            pady=12,
        )
        form.pack(fill="x", padx=30, pady=5)

        self.tipo_var = tk.StringVar(value="Despesa")
        self.desc_var = tk.StringVar()
        self.cat_var = tk.StringVar()
        self.valor_var = tk.StringVar()
        self.data_var = tk.StringVar(
            value=datetime.now().strftime("%d/%m/%Y")
        )

        campos = [
            ("Tipo", self.tipo_var, ["Receita", "Despesa"]),
            ("Descrição", self.desc_var, None),
            (
                "Categoria",
                self.cat_var,
                [
                    "Salário",
                    "Alimentação",
                    "Transporte",
                    "Moradia",
                    "Contas",
                    "Lazer",
                    "Saúde",
                    "Educação",
                    "Compras",
                    "Investimentos",
                    "Outros",
                ],
            ),
            ("Valor", self.valor_var, None),
            ("Data", self.data_var, None),
        ]

        for i, (nome, var, valores) in enumerate(campos):
            tk.Label(form, text=nome, bg="#FFF8F0", fg="#475569").grid(
                row=0, column=i, sticky="w", padx=5
            )

            if valores:
                widget = ttk.Combobox(
                    form,
                    textvariable=var,
                    values=valores,
                    state="readonly",
                    width=17,
                )
            else:
                widget = tk.Entry(
                    form, textvariable=var, width=20, relief="solid", bd=1
                )

            widget.grid(row=1, column=i, padx=5, pady=5)

        tk.Button(
            form,
            text="➕ Adicionar",
            command=self.adicionar_lancamento,
            bg="#6C9B73",
            fg="white",
            relief="flat",
            font=("Segoe UI", 10, "bold"),
            padx=15,
            pady=7,
            cursor="hand2",
        ).grid(row=1, column=5, padx=10)

        filtro = tk.Frame(self.conteudo, bg="#FFF8F0")
        filtro.pack(fill="x", padx=30, pady=12)

        tk.Label(filtro, text="Mês:", bg="#FFF8F0").pack(side="left")

        self.filtro_mes = tk.StringVar(value=datetime.now().strftime("%m"))
        ttk.Combobox(
            filtro,
            textvariable=self.filtro_mes,
            values=[f"{i:02d}" for i in range(1, 13)],
            state="readonly",
            width=5,
        ).pack(side="left", padx=5)

        tk.Label(filtro, text="Ano:", bg="#FFF8F0").pack(
            side="left", padx=(10, 0)
        )

        self.filtro_ano = tk.StringVar(value=datetime.now().strftime("%Y"))
        tk.Entry(filtro, textvariable=self.filtro_ano, width=8).pack(
            side="left", padx=5
        )

        tk.Button(
            filtro,
            text="🔎 Filtrar",
            command=self.carregar_lancamentos,
            bg="#5D8B75",
            fg="white",
            relief="flat",
            padx=12,
            pady=5,
        ).pack(side="left", padx=8)

        box = tk.Frame(self.conteudo, bg="white")
        box.pack(fill="both", expand=True, padx=30, pady=(0, 20))

        cols = ("id", "tipo", "descricao", "categoria", "valor", "data")
        self.tabela = ttk.Treeview(box, columns=cols, show="headings")

        nomes = {
            "id": "ID",
            "tipo": "Tipo",
            "descricao": "Descrição",
            "categoria": "Categoria",
            "valor": "Valor",
            "data": "Data",
        }
        larguras = {
            "id": 50,
            "tipo": 90,
            "descricao": 280,
            "categoria": 150,
            "valor": 130,
            "data": 100,
        }

        for c in cols:
            self.tabela.heading(c, text=nomes[c])
            self.tabela.column(c, width=larguras[c])

        scroll = ttk.Scrollbar(
            box, orient="vertical", command=self.tabela.yview
        )
        self.tabela.configure(yscrollcommand=scroll.set)

        self.tabela.pack(side="left", fill="both", expand=True)
        scroll.pack(side="right", fill="y")

        botoes = tk.Frame(self.conteudo, bg="#FFF8F0")
        botoes.pack(fill="x", padx=30, pady=(0, 15))

        tk.Button(
            botoes,
            text="🗑 Excluir selecionado",
            command=self.excluir_lancamento,
            bg="#C96B5B",
            fg="white",
            relief="flat",
            padx=15,
            pady=7,
        ).pack(side="left")

        self.carregar_lancamentos()

    def adicionar_lancamento(self):
        tipo = self.tipo_var.get()
        descricao = self.desc_var.get().strip()
        categoria = self.cat_var.get().strip()
        valor = valor_float(self.valor_var.get())
        data = self.data_var.get().strip()

        if not descricao or not categoria:
            messagebox.showwarning(
                "Atenção", "Preencha descrição e categoria."
            )
            return

        if valor is None or valor <= 0:
            messagebox.showwarning("Atenção", "Informe um valor válido.")
            return

        if not data_valida(data):
            messagebox.showwarning(
                "Atenção", "Use a data no formato DD/MM/AAAA."
            )
            return

        conn = conectar()
        cur = conn.cursor()
        cur.execute(
            """
            INSERT INTO lancamentos (tipo, descricao, categoria, valor, data)
            VALUES (?, ?, ?, ?, ?)
        """,
            (tipo, descricao, categoria, valor, data),
        )
        conn.commit()
        conn.close()

        self.desc_var.set("")
        self.cat_var.set("")
        self.valor_var.set("")
        self.data_var.set(datetime.now().strftime("%d/%m/%Y"))

        self.carregar_lancamentos()
        messagebox.showinfo("Sucesso", "Lançamento adicionado.")

    def carregar_lancamentos(self):
        if not hasattr(self, "tabela"):
            return

        mes = self.filtro_mes.get()
        ano = self.filtro_ano.get()

        conn = conectar()
        cur = conn.cursor()

        cur.execute(
            """
            SELECT id, tipo, descricao, categoria, valor, data
            FROM lancamentos
            WHERE substr(data,4,2)=? AND substr(data,7,4)=?
            ORDER BY id DESC
        """,
            (mes, ano),
        )

        registros = cur.fetchall()
        conn.close()

        for item in self.tabela.get_children():
            self.tabela.delete(item)

        for registro in registros:
            id_, tipo, desc, cat, valor, data = registro
            self.tabela.insert(
                "", "end", values=(id_, tipo, desc, cat, dinheiro(valor), data)
            )

    def excluir_lancamento(self):
        selecionado = self.tabela.selection()

        if not selecionado:
            messagebox.showwarning("Atenção", "Selecione um lançamento.")
            return

        item = self.tabela.item(selecionado[0])
        id_ = item["values"][0]

        if not messagebox.askyesno(
            "Confirmar", "Deseja excluir este lançamento?"
        ):
            return

        conn = conectar()
        cur = conn.cursor()
        cur.execute("DELETE FROM lancamentos WHERE id=?", (id_,))
        conn.commit()
        conn.close()

        self.carregar_lancamentos()

    # ========================================================
    # CONTAS
    # ========================================================

    def mostrar_contas(self):
        self.current_page = "contas"
        self.limpar_conteudo()
        self.titulo_pagina("Contas a pagar", "Controle vencimentos e pagamentos")

        form = tk.Frame(self.conteudo, bg="white")
        form.pack(fill="x", padx=30, pady=5)

        self.conta_nome = tk.StringVar()
        self.conta_valor = tk.StringVar()
        self.conta_venc = tk.StringVar(
            value=datetime.now().strftime("%d/%m/%Y")
        )
        self.conta_cat = tk.StringVar(value="Contas")

        campos = [
            ("Conta", self.conta_nome, 22),
            ("Valor", self.conta_valor, 15),
            ("Vencimento", self.conta_venc, 13),
        ]

        for i, (nome, var, largura) in enumerate(campos):
            tk.Label(form, text=nome, bg="white", fg="#475569").grid(
                row=0, column=i, padx=10, pady=(12, 3), sticky="w"
            )
            tk.Entry(form, textvariable=var, width=largura).grid(
                row=1, column=i, padx=10, pady=(0, 12)
            )

        tk.Button(
            form,
            text="➕ Cadastrar conta",
            command=self.adicionar_conta,
            bg="#A87855",
            fg="white",
            relief="flat",
            padx=15,
            pady=7,
        ).grid(row=1, column=4, padx=15)

        box = tk.Frame(self.conteudo, bg="white")
        box.pack(fill="both", expand=True, padx=30, pady=20)

        cols = ("id", "nome", "valor", "vencimento", "status")
        self.tabela_contas = ttk.Treeview(box, columns=cols, show="headings")

        for c, nome, largura in [
            ("id", "ID", 50),
            ("nome", "Conta", 300),
            ("valor", "Valor", 150),
            ("vencimento", "Vencimento", 140),
            ("status", "Status", 150),
        ]:
            self.tabela_contas.heading(c, text=nome)
            self.tabela_contas.column(c, width=largura)

        scroll = ttk.Scrollbar(
            box, orient="vertical", command=self.tabela_contas.yview
        )
        self.tabela_contas.configure(yscrollcommand=scroll.set)

        self.tabela_contas.pack(side="left", fill="both", expand=True)
        scroll.pack(side="right", fill="y")

        botoes = tk.Frame(self.conteudo, bg="#FFF8F0")
        botoes.pack(fill="x", padx=30, pady=(0, 15))

        tk.Button(
            botoes,
            text="✓ Marcar como paga",
            command=self.pagar_conta,
            bg="#6C9B73",
            fg="white",
            relief="flat",
            padx=15,
            pady=7,
        ).pack(side="left", padx=(0, 8))

        tk.Button(
            botoes,
            text="🗑 Excluir",
            command=self.excluir_conta,
            bg="#C96B5B",
            fg="white",
            relief="flat",
            padx=15,
            pady=7,
        ).pack(side="left")

        self.carregar_contas()

    def adicionar_conta(self):
        nome = self.conta_nome.get().strip()
        valor = valor_float(self.conta_valor.get())
        venc = self.conta_venc.get().strip()

        if not nome or valor is None or valor <= 0 or not data_valida(venc):
            messagebox.showwarning(
                "Atenção",
                "Preencha conta, valor e vencimento corretamente.",
            )
            return

        conn = conectar()
        cur = conn.cursor()
        cur.execute(
            """
            INSERT INTO contas (nome, valor, vencimento, categoria, status)
            VALUES (?, ?, ?, ?, 'Pendente')
        """,
            (nome, valor, venc, "Contas"),
        )
        conn.commit()
        conn.close()

        self.conta_nome.set("")
        self.conta_valor.set("")
        self.carregar_contas()

    def carregar_contas(self):
        conn = conectar()
        cur = conn.cursor()
        cur.execute(
            "SELECT id, nome, valor, vencimento, status FROM contas ORDER BY status DESC, id DESC"
        )
        registros = cur.fetchall()
        conn.close()

        for item in self.tabela_contas.get_children():
            self.tabela_contas.delete(item)

        for registro in registros:
            id_, nome, valor, venc, status = registro
            self.tabela_contas.insert(
                "", "end", values=(id_, nome, dinheiro(valor), venc, status)
            )

    def pagar_conta(self):
        sel = self.tabela_contas.selection()
        if not sel:
            messagebox.showwarning("Atenção", "Selecione uma conta.")
            return

        id_ = self.tabela_contas.item(sel[0])["values"][0]

        conn = conectar()
        cur = conn.cursor()
        cur.execute("UPDATE contas SET status='Paga' WHERE id=?", (id_,))
        conn.commit()
        conn.close()

        self.carregar_contas()

    def excluir_conta(self):
        sel = self.tabela_contas.selection()
        if not sel:
            messagebox.showwarning("Atenção", "Selecione uma conta.")
            return

        id_ = self.tabela_contas.item(sel[0])["values"][0]

        if not messagebox.askyesno("Confirmar", "Deseja excluir esta conta?"):
            return

        conn = conectar()
        cur = conn.cursor()
        cur.execute("DELETE FROM contas WHERE id=?", (id_,))
        conn.commit()
        conn.close()

        self.carregar_contas()

    # ========================================================
    # METAS
    # ========================================================

    def mostrar_metas(self):
        self.current_page = "metas"
        self.limpar_conteudo()
        self.titulo_pagina(
            "Metas financeiras", "Crie objetivos e acompanhe seu progresso"
        )

        form = tk.Frame(self.conteudo, bg="white")
        form.pack(fill="x", padx=30, pady=5)

        self.meta_nome = tk.StringVar()
        self.meta_obj = tk.StringVar()
        self.meta_atual = tk.StringVar(value="0")

        for i, (nome, var, largura) in enumerate(
            [
                ("Meta", self.meta_nome, 25),
                ("Objetivo", self.meta_obj, 15),
                ("Valor atual", self.meta_atual, 15),
            ]
        ):
            tk.Label(form, text=nome, bg="white", fg="#475569").grid(
                row=0, column=i, padx=10, pady=(12, 3), sticky="w"
            )
            tk.Entry(form, textvariable=var, width=largura).grid(
                row=1, column=i, padx=10, pady=(0, 12)
            )

        tk.Button(
            form,
            text="🎯 Criar meta",
            command=self.adicionar_meta,
            bg="#D28A63",
            fg="white",
            relief="flat",
            padx=15,
            pady=7,
        ).grid(row=1, column=3, padx=15)

        box = tk.Frame(self.conteudo, bg="#FFF8F0")
        box.pack(fill="both", expand=True, padx=30, pady=20)

        self.frame_metas = box
        self.carregar_metas()

    def adicionar_meta(self):
        nome = self.meta_nome.get().strip()
        objetivo = valor_float(self.meta_obj.get())
        atual = valor_float(self.meta_atual.get())

        if not nome or objetivo is None or objetivo <= 0:
            messagebox.showwarning(
                "Atenção", "Informe o nome e um objetivo válido."
            )
            return

        atual = atual if atual is not None else 0

        conn = conectar()
        cur = conn.cursor()
        cur.execute(
            "INSERT INTO metas (nome, objetivo, atual) VALUES (?, ?, ?)",
            (nome, objetivo, atual),
        )
        conn.commit()
        conn.close()

        self.meta_nome.set("")
        self.meta_obj.set("")
        self.meta_atual.set("0")

        self.carregar_metas()

    def carregar_metas(self):
        if not hasattr(self, "frame_metas"):
            return

        for widget in self.frame_metas.winfo_children():
            widget.destroy()

        conn = conectar()
        cur = conn.cursor()
        cur.execute(
            "SELECT id, nome, objetivo, atual FROM metas ORDER BY id DESC"
        )
        metas = cur.fetchall()
        conn.close()

        if not metas:
            tk.Label(
                self.frame_metas,
                text="Nenhuma meta cadastrada.",
                bg="#FFF8F0",
                fg="#7A817B",
                font=("Segoe UI", 11),
            ).pack(pady=50)
            return

        for id_, nome, objetivo, atual in metas:
            percentual = (
                min((atual / objetivo) * 100, 100) if objetivo > 0 else 0
            )

            card = tk.Frame(
                self.frame_metas,
                bg="white",
                highlightthickness=1,
                highlightbackground="#E7DED2",
            )
            card.pack(fill="x", pady=6)

            info = tk.Frame(card, bg="white")
            info.pack(fill="x", padx=15, pady=(12, 5))

            tk.Label(
                info,
                text=nome,
                bg="white",
                fg="#31443A",
                font=("Segoe UI", 11, "bold"),
            ).pack(side="left")
            tk.Label(
                info,
                text=f"{dinheiro(atual)} / {dinheiro(objetivo)} ({percentual:.1f}%)",
                bg="white",
                fg="#7A817B",
                font=("Segoe UI", 10),
            ).pack(side="right")

            barra = ttk.Progressbar(card, maximum=100, value=percentual)
            barra.pack(fill="x", padx=15, pady=(0, 10))

            btn_frame = tk.Frame(card, bg="white")
            btn_frame.pack(fill="x", padx=15, pady=(0, 10))

            tk.Button(
                btn_frame,
                text="➕ Adicionar valor",
                command=lambda m_id=id_, m_at=atual: self.aporte_meta(
                    m_id, m_at
                ),
                bg="#6C9B73",
                fg="white",
                relief="flat",
                padx=8,
            ).pack(side="left", padx=2)

            tk.Button(
                btn_frame,
                text="🗑 Excluir",
                command=lambda m_id=id_: self.excluir_meta(m_id),
                bg="#C96B5B",
                fg="white",
                relief="flat",
                padx=8,
            ).pack(side="left", padx=2)

    def aporte_meta(self, meta_id, atual_val):
        win = tk.Toplevel(self.root)
        win.title("Aporte em Meta")
        win.geometry("300x150")
        win.configure(bg="#FFF8F0")

        tk.Label(
            win, text="Valor a adicionar:", bg="#FFF8F0", font=("Segoe UI", 10)
        ).pack(pady=10)
        val_var = tk.StringVar()
        tk.Entry(win, textvariable=val_var, width=15).pack(pady=5)

        def salvar():
            val = valor_float(val_var.get())
            if val and val > 0:
                conn = conectar()
                cur = conn.cursor()
                cur.execute(
                    "UPDATE metas SET atual=? WHERE id=?",
                    (atual_val + val, meta_id),
                )
                conn.commit()
                conn.close()
                win.destroy()
                self.carregar_metas()

        tk.Button(
            win,
            text="Confirmar",
            command=salvar,
            bg="#6C9B73",
            fg="white",
            relief="flat",
        ).pack(pady=10)

    def excluir_meta(self, meta_id):
        if messagebox.askyesno("Confirmar", "Deseja excluir esta meta?"):
            conn = conectar()
            cur = conn.cursor()
            cur.execute("DELETE FROM metas WHERE id=?", (meta_id,))
            conn.commit()
            conn.close()
            self.carregar_metas()

    # ========================================================
    # CARTÕES DE CRÉDITO
    # ========================================================

    def mostrar_cartoes(self):
        self.current_page = "cartoes"
        self.limpar_conteudo()
        self.titulo_pagina(
            "Cartões e Parcelamento",
            "Acompanhe faturas, compras parceladas e limites",
        )

        form = tk.Frame(self.conteudo, bg="white")
        form.pack(fill="x", padx=30, pady=5)

        self.c_desc = tk.StringVar()
        self.c_val = tk.StringVar()
        self.c_parc = tk.StringVar(value="1")

        campos = [
            ("Compra/Descrição", self.c_desc, 25),
            ("Valor Total", self.c_val, 15),
            ("Qtd Parcelas", self.c_parc, 10),
        ]

        for i, (nome, var, largura) in enumerate(campos):
            tk.Label(form, text=nome, bg="white", fg="#475569").grid(
                row=0, column=i, padx=10, pady=(12, 3), sticky="w"
            )
            tk.Entry(form, textvariable=var, width=largura).grid(
                row=1, column=i, padx=10, pady=(0, 12)
            )

        tk.Button(
            form,
            text="💳 Lançar no Cartão",
            command=self.adicionar_parcela,
            bg="#355C4D",
            fg="white",
            relief="flat",
            padx=15,
            pady=7,
        ).grid(row=1, column=3, padx=15)

        box = tk.Frame(self.conteudo, bg="white")
        box.pack(fill="both", expand=True, padx=30, pady=20)

        cols = ("id", "desc", "valor", "parcela", "vencimento")
        self.tabela_cartao = ttk.Treeview(box, columns=cols, show="headings")

        for c, nome, largura in [
            ("id", "ID", 50),
            ("desc", "Descrição", 300),
            ("valor", "Valor Parcela", 150),
            ("parcela", "Parcela", 120),
            ("vencimento", "Vencimento", 140),
        ]:
            self.tabela_cartao.heading(c, text=nome)
            self.tabela_cartao.column(c, width=largura)

        scroll = ttk.Scrollbar(
            box, orient="vertical", command=self.tabela_cartao.yview
        )
        self.tabela_cartao.configure(yscrollcommand=scroll.set)

        self.tabela_cartao.pack(side="left", fill="both", expand=True)
        scroll.pack(side="right", fill="y")

        botoes = tk.Frame(self.conteudo, bg="#FFF8F0")
        botoes.pack(fill="x", padx=30, pady=(0, 15))

        tk.Button(
            botoes,
            text="🗑 Excluir Parcela",
            command=self.excluir_parcela,
            bg="#C96B5B",
            fg="white",
            relief="flat",
            padx=15,
            pady=7,
        ).pack(side="left")

        self.carregar_parcelas()

    def adicionar_parcela(self):
        desc = self.c_desc.get().strip()
        val_total = valor_float(self.c_val.get())
        try:
            total_parc = int(self.c_parc.get().strip())
        except ValueError:
            total_parc = 0

        if not desc or val_total is None or val_total <= 0 or total_parc <= 0:
            messagebox.showwarning(
                "Atenção", "Preencha a descrição, valor e parcelas válidas."
            )
            return

        val_parcela = val_total / total_parc
        venc_hoje = datetime.now().strftime("%d/%m/%Y")

        conn = conectar()
        cur = conn.cursor()

        for i in range(1, total_parc + 1):
            cur.execute(
                """
                INSERT INTO parcelas (descricao, valor, total, atual, vencimento)
                VALUES (?, ?, ?, ?, ?)
            """,
                (desc, val_parcela, total_parc, i, venc_hoje),
            )

        conn.commit()
        conn.close()

        self.c_desc.set("")
        self.c_val.set("")
        self.c_parc.set("1")
        self.carregar_parcelas()

    def carregar_parcelas(self):
        conn = conectar()
        cur = conn.cursor()
        cur.execute(
            "SELECT id, descricao, valor, atual, total, vencimento FROM parcelas ORDER BY id DESC"
        )
        registros = cur.fetchall()
        conn.close()

        for item in self.tabela_cartao.get_children():
            self.tabela_cartao.delete(item)

        for id_, desc, val, at, tot, venc in registros:
            parc_str = f"{at}/{tot}"
            self.tabela_cartao.insert(
                "", "end", values=(id_, desc, dinheiro(val), parc_str, venc)
            )

    def excluir_parcela(self):
        sel = self.tabela_cartao.selection()
        if not sel:
            messagebox.showwarning("Atenção", "Selecione um item.")
            return

        id_ = self.tabela_cartao.item(sel[0])["values"][0]

        if messagebox.askyesno("Confirmar", "Excluir esta parcela?"):
            conn = conectar()
            cur = conn.cursor()
            cur.execute("DELETE FROM parcelas WHERE id=?", (id_,))
            conn.commit()
            conn.close()
            self.carregar_parcelas()

    # ========================================================
    # DESPESAS RECORRENTES
    # ========================================================

    def mostrar_recorrentes(self):
        self.current_page = "recorrentes"
        self.limpar_conteudo()
        self.titulo_pagina(
            "Recorrentes", "Gerencie gastos e receitas fixas mensais"
        )

        form = tk.Frame(self.conteudo, bg="white")
        form.pack(fill="x", padx=30, pady=5)

        self.rec_desc = tk.StringVar()
        self.rec_val = tk.StringVar()
        self.rec_cat = tk.StringVar(value="Moradia")
        self.rec_dia = tk.StringVar(value="5")

        campos = [
            ("Descrição", self.rec_desc, 25),
            ("Valor Mensal", self.rec_val, 15),
            ("Categoria", self.rec_cat, 15),
            ("Dia Vencimento", self.rec_dia, 10),
        ]

        for i, (nome, var, largura) in enumerate(campos):
            tk.Label(form, text=nome, bg="white", fg="#475569").grid(
                row=0, column=i, padx=10, pady=(12, 3), sticky="w"
            )
            tk.Entry(form, textvariable=var, width=largura).grid(
                row=1, column=i, padx=10, pady=(0, 12)
            )

        tk.Button(
            form,
            text="🔁 Adicionar Recorrente",
            command=self.adicionar_recorrente,
            bg="#5D8B75",
            fg="white",
            relief="flat",
            padx=15,
            pady=7,
        ).grid(row=1, column=4, padx=15)

        box = tk.Frame(self.conteudo, bg="white")
        box.pack(fill="both", expand=True, padx=30, pady=20)

        cols = ("id", "desc", "valor", "cat", "dia")
        self.tabela_rec = ttk.Treeview(box, columns=cols, show="headings")

        for c, nome, largura in [
            ("id", "ID", 50),
            ("desc", "Descrição", 280),
            ("valor", "Valor", 150),
            ("cat", "Categoria", 150),
            ("dia", "Dia do Mês", 100),
        ]:
            self.tabela_rec.heading(c, text=nome)
            self.tabela_rec.column(c, width=largura)

        scroll = ttk.Scrollbar(
            box, orient="vertical", command=self.tabela_rec.yview
        )
        self.tabela_rec.configure(yscrollcommand=scroll.set)

        self.tabela_rec.pack(side="left", fill="both", expand=True)
        scroll.pack(side="right", fill="y")

        botoes = tk.Frame(self.conteudo, bg="#FFF8F0")
        botoes.pack(fill="x", padx=30, pady=(0, 15))

        tk.Button(
            botoes,
            text="🗑 Excluir",
            command=self.excluir_recorrente,
            bg="#C96B5B",
            fg="white",
            relief="flat",
            padx=15,
            pady=7,
        ).pack(side="left")

        self.carregar_recorrentes()

    def adicionar_recorrente(self):
        desc = self.rec_desc.get().strip()
        val = valor_float(self.rec_val.get())
        cat = self.rec_cat.get().strip()
        try:
            dia = int(self.rec_dia.get().strip())
        except ValueError:
            dia = 0

        if not desc or val is None or val <= 0 or dia < 1 or dia > 31:
            messagebox.showwarning(
                "Atenção", "Preencha todos os campos corretamente."
            )
            return

        conn = conectar()
        cur = conn.cursor()
        cur.execute(
            """
            INSERT INTO recorrentes (descricao, valor, categoria, dia)
            VALUES (?, ?, ?, ?)
        """,
            (desc, val, cat, dia),
        )
        conn.commit()
        conn.close()

        self.rec_desc.set("")
        self.rec_val.set("")
        self.carregar_recorrentes()

    def carregar_recorrentes(self):
        conn = conectar()
        cur = conn.cursor()
        cur.execute(
            "SELECT id, descricao, valor, categoria, dia FROM recorrentes ORDER BY id DESC"
        )
        registros = cur.fetchall()
        conn.close()

        for item in self.tabela_rec.get_children():
            self.tabela_rec.delete(item)

        for id_, desc, val, cat, dia in registros:
            self.tabela_rec.insert(
                "", "end", values=(id_, desc, dinheiro(val), cat, f"Dia {dia}")
            )

    def excluir_recorrente(self):
        sel = self.tabela_rec.selection()
        if not sel:
            messagebox.showwarning("Atenção", "Selecione um item.")
            return

        id_ = self.tabela_rec.item(sel[0])["values"][0]

        if messagebox.askyesno("Confirmar", "Excluir este item recorrente?"):
            conn = conectar()
            cur = conn.cursor()
            cur.execute("DELETE FROM recorrentes WHERE id=?", (id_,))
            conn.commit()
            conn.close()
            self.carregar_recorrentes()

    # ========================================================
    # ANÁLISE MENSAL
    # ========================================================

    def mostrar_analise(self):
        self.current_page = "analise"
        self.limpar_conteudo()
        self.titulo_pagina("Análise Mensal", "Resumo detalhado dos lançamentos")

        mes = datetime.now().strftime("%m")
        ano = datetime.now().strftime("%Y")

        conn = conectar()
        cur = conn.cursor()

        cur.execute(
            """
            SELECT categoria, SUM(valor)
            FROM lancamentos
            WHERE tipo='Despesa' AND substr(data,4,2)=? AND substr(data,7,4)=?
            GROUP BY categoria ORDER BY SUM(valor) DESC
        """,
            (mes, ano),
        )

        dados = cur.fetchall()
        conn.close()

        frame = tk.Frame(self.conteudo, bg="white", padx=20, pady=20)
        frame.pack(fill="both", expand=True, padx=30, pady=20)

        tk.Label(
            frame,
            text=f"Detalhamento de Gastos ({mes}/{ano})",
            bg="white",
            fg="#31443A",
            font=("Segoe UI", 12, "bold"),
        ).pack(anchor="w", pady=(0, 15))

        if not dados:
            tk.Label(
                frame,
                text="Sem lançamentos no mês atual.",
                bg="white",
                fg="#7A817B",
            ).pack(pady=30)
            return

        for cat, val in dados:
            linha = tk.Frame(frame, bg="white")
            linha.pack(fill="x", pady=5)
            tk.Label(
                linha,
                text=cat,
                bg="white",
                fg="#31443A",
                font=("Segoe UI", 10, "bold"),
            ).pack(side="left")
            tk.Label(
                linha,
                text=dinheiro(val),
                bg="white",
                fg="#C96B5B",
                font=("Segoe UI", 10),
            ).pack(side="right")

    # ========================================================
    # FERRAMENTAS & BACKUP
    # ========================================================

    def mostrar_ferramentas(self):
        self.current_page = "ferramentas"
        self.limpar_conteudo()
        self.titulo_pagina(
            "Ferramentas", "Backup, exportação de dados e utilitários"
        )

        box = tk.Frame(self.conteudo, bg="#FFF8F0")
        box.pack(fill="both", expand=True, padx=30, pady=20)

        # Seção Backup
        f1 = tk.LabelFrame(
            box,
            text=" Backup do Banco de Dados ",
            bg="white",
            font=("Segoe UI", 11, "bold"),
            padx=15,
            pady=15,
        )
        f1.pack(fill="x", pady=10)

        tk.Button(
            f1,
            text="💾 Fazer Backup",
            command=self.fazer_backup,
            bg="#355C4D",
            fg="white",
            relief="flat",
            padx=15,
            pady=8,
        ).pack(side="left", padx=5)
        tk.Button(
            f1,
            text="📂 Restaurar Backup",
            command=self.restaurar_backup,
            bg="#A87855",
            fg="white",
            relief="flat",
            padx=15,
            pady=8,
        ).pack(side="left", padx=5)

        # Seção Exportar
        f2 = tk.LabelFrame(
            box,
            text=" Exportação de Dados ",
            bg="white",
            font=("Segoe UI", 11, "bold"),
            padx=15,
            pady=15,
        )
        f2.pack(fill="x", pady=10)

        tk.Button(
            f2,
            text="📄 Exportar Lançamentos (CSV)",
            command=self.exportar_csv,
            bg="#5D8B75",
            fg="white",
            relief="flat",
            padx=15,
            pady=8,
        ).pack(side="left", padx=5)

        # Seção Atualização
        f3 = tk.LabelFrame(
            box,
            text=" Atualização do Sistema (Versão 2) ",
            bg="white",
            font=("Segoe UI", 11, "bold"),
            padx=15,
            pady=15,
        )
        f3.pack(fill="x", pady=10)

        tk.Button(
            f3,
            text="⬆️ Upload de Pacote de Atualização (.py)",
            command=self.fazer_upload_atualizacao,
            bg="#6C9B73",
            fg="white",
            relief="flat",
            padx=15,
            pady=8,
        ).pack(side="left", padx=5)

    def fazer_backup(self):
        destino = filedialog.asksaveasfilename(
            defaultextension=".db",
            filetypes=[("Banco de Dados", "*.db")],
            initialfile="backup_financas.db",
        )
        if destino:
            try:
                shutil.copy(DB_NAME, destino)
                messagebox.showinfo(
                    "Sucesso", "Backup realizado com sucesso!"
                )
            except Exception as e:
                messagebox.showerror("Erro", f"Falha ao realizar backup:\n{e}")

    def restaurar_backup(self):
        origem = filedialog.askopenfilename(
            filetypes=[("Banco de Dados", "*.db")]
        )
        if origem:
            if messagebox.askyesno(
                "Atenção",
                "Restaurar o backup substituirá todos os dados atuais. Deseja continuar?",
            ):
                try:
                    shutil.copy(origem, DB_NAME)
                    messagebox.showinfo(
                        "Sucesso",
                        "Banco restaurado! Reiniciando a visualização.",
                    )
                    self.mostrar_dashboard()
                except Exception as e:
                    messagebox.showerror(
                        "Erro", f"Falha ao restaurar backup:\n{e}"
                    )

    def exportar_csv(self):
        destino = filedialog.asksaveasfilename(
            defaultextension=".csv",
            filetypes=[("Arquivo CSV", "*.csv")],
            initialfile="lancamentos.csv",
        )
        if destino:
            try:
                conn = conectar()
                cur = conn.cursor()
                cur.execute(
                    "SELECT id, tipo, descricao, categoria, valor, data FROM lancamentos"
                )
                rows = cur.fetchall()
                conn.close()

                with open(
                    destino, "w", newline="", encoding="utf-8-sig"
                ) as f:
                    writer = csv.writer(f, delimiter=";")
                    writer.writerow(
                        ["ID", "Tipo", "Descrição", "Categoria", "Valor", "Data"]
                    )
                    writer.writerows(rows)

                messagebox.showinfo(
                    "Sucesso", "Dados exportados com sucesso para CSV!"
                )
            except Exception as e:
                messagebox.showerror(
                    "Erro", f"Falha ao exportar para CSV:\n{e}"
                )


# ============================================================
# INICIALIZAÇÃO
# ============================================================

if __name__ == "__main__":
    criar_banco()
    root = tk.Tk()
    app = FinanceiroApp(root)
    root.mainloop()