"""
Interface Sinapesc — Sindicato Dos Aquicultores E Pescadores De Casa Nova.
"""

from __future__ import annotations

import re
import threading
import tkinter as tk
from pathlib import Path
from tkinter import filedialog, messagebox, ttk
from typing import Callable, List, Optional, Set

from config import (
    app_data_dir,
    exe_dir,
    import_credentials_file,
    is_sheets_configured,
    load_config,
    save_config,
)
from sheets import MESES, MESES_LABEL, MesKey, PessoaComReap, SheetsConfigError, SheetsService
from sheets.models import meses_no_intervalo
from ui.brand import load_logo
from ui.chrome import build_shell, clear_body, go_back, navigate, page_wrap, sync_chrome
from ui.formatters import display_nome, format_cpf, format_cpf_input, format_cpf_masked, format_nome, get_initials, only_digits, parse_lote_lines
from ui.public_link import ensure_site_qrs, resolve_base, urls_for
from ui.public_web import start_public_server
from ui.qr_vault import (
    ensure_stable_qrs,
    normalize_public_base,
    path_for_consulta,
    path_for_lista,
    path_for_pessoa,
    preferred_public_base,
    qr_dir,
)
from ui.qrutil import make_qr_image, pil_to_tk, save_qr_png
from ui.scroll import ScrollableFrame
from ui.tela_auditoria import show_auditoria as open_auditoria
from ui.tela_backup import pedir_backup_agora, talvez_lembrar_backup
from ui.tela_pendencias import show_pendencias as open_pendencias
from ui.tela_relatorio import show_relatorio as open_relatorio
from ui.theme import COLORS, FONT_DISPLAY, FONT_FAMILY, ORG_FULL, ORG_SHORT, ORG_TITLE
from ui.tunnel import stop_tunnel
from ui.widgets import (
    card_shell,
    chevron_btn,
    circular_avatar,
    content_outline_btn,
    content_primary_btn,
    icon_btn,
    month_pill,
    search_field,
    setup_widget_styles,
)


class SinapescApp(tk.Tk):
    def __init__(self) -> None:
        super().__init__()
        self.title(ORG_TITLE)
        self.geometry("1100x740")
        self.minsize(960, 640)
        self.configure(bg=COLORS["content"])

        self.cfg = load_config()
        self.service: Optional[SheetsService] = None
        self._logged_in = False
        self._admin_user = ""
        self._bg_busy = False
        self._lista_mode = False
        self._pessoas: List[PessoaComReap] = []
        self._expanded_ids: Set[str] = set()
        self._scroll: Optional[ScrollableFrame] = None
        self._qr_photo = None
        self._public_url_var = tk.StringVar(value=str(self.cfg.get("public_base_url") or ""))

        self._setup_style()
        build_shell(self)
        navigate(self, "home", push=False)
        self.protocol("WM_DELETE_WINDOW", self._on_close)

        try:
            self.iconphoto(True, tk.PhotoImage(file=_asset("icon.png")))
        except Exception:
            pass

    def _on_close(self) -> None:
        cfg = load_config()
        if not cfg.get("keep_tunnel_alive", True):
            stop_tunnel()
        if self._scroll is not None:
            try:
                self._scroll.destroy()
            except tk.TclError:
                pass
        self.destroy()

    def _setup_style(self) -> None:
        style = ttk.Style(self)
        try:
            style.theme_use("clam")
        except tk.TclError:
            pass
        style.configure(".", font=(FONT_FAMILY, 10), background=COLORS["content"])
        style.configure("TFrame", background=COLORS["content"])
        style.configure("Header.TFrame", background=COLORS["primary"])
        style.configure("Header.TLabel", background=COLORS["primary"], foreground=COLORS["primary_fg"], font=(FONT_DISPLAY, 15, "bold"))
        style.configure("HeaderSub.TLabel", background=COLORS["primary"], foreground="#A9C0D4", font=(FONT_FAMILY, 9))
        style.configure("Title.TLabel", background=COLORS["content"], foreground=COLORS["primary"], font=(FONT_DISPLAY, 20, "bold"))
        style.configure("Muted.TLabel", background=COLORS["content"], foreground=COLORS["muted"], font=(FONT_FAMILY, 10))
        setup_widget_styles(self)

    def _clear_body(self) -> None:
        clear_body(self)

    def go_back(self) -> None:
        go_back(self)

    def _btn(self, parent, text, command, *, kind="accent", padx=12, pady=7, font_size=10, bold=True):
        styles = {
            "accent": (COLORS["accent"], COLORS["accent_fg"], COLORS["accent_hover"]),
            "primary": (COLORS["primary"], COLORS["primary_fg"], COLORS["primary_mid"]),
            "ghost": (COLORS["surface"], COLORS["primary"], COLORS["border_soft"]),
            "outline": (COLORS["content"], COLORS["primary"], COLORS["surface_soft"]),
            "danger": (COLORS["danger_bg"], COLORS["danger"], "#EFD0CC"),
            "nav": (COLORS["accent"], COLORS["accent_fg"], COLORS["accent_hover"]),
        }
        bg, fg, hover = styles.get(kind, styles["accent"])
        btn = tk.Button(
            parent, text=text, command=command, bg=bg, fg=fg, activebackground=hover,
            activeforeground=fg, relief="solid" if kind == "outline" else "flat",
            highlightbackground=COLORS["primary"] if kind == "outline" else bg,
            highlightthickness=1 if kind == "outline" else 0,
            bd=1 if kind == "outline" else 0,
            padx=padx, pady=pady,
            font=(FONT_FAMILY, font_size, "bold" if bold else "normal"), cursor="hand2",
        )
        return btn

    def _set_busy(self, message: str) -> None:
        self.status.set(message)
        self.configure(cursor="watch")
        self.update_idletasks()

    def _set_idle(self, message: str = "Pronto.") -> None:
        self.status.set(message)
        self.configure(cursor="")

    def _run_bg(self, work: Callable, on_ok: Callable, on_err: Callable, busy_msg: str) -> bool:
        if getattr(self, "_bg_busy", False):
            messagebox.showwarning("Aguarde", "Outra operação na planilha ainda está em andamento.")
            return False
        self._bg_busy = True
        self._set_busy(busy_msg)

        def finish_ok(result) -> None:
            try:
                self._set_idle()
                on_ok(result)
            finally:
                self._bg_busy = False

        def finish_err(exc: Exception) -> None:
            try:
                self._set_idle("Erro.")
                on_err(exc)
            finally:
                self._bg_busy = False

        def target() -> None:
            try:
                result = work()
            except Exception as exc:  # noqa: BLE001
                self.after(0, lambda e=exc: finish_err(e))
                return
            self.after(0, lambda r=result: finish_ok(r))

        threading.Thread(target=target, daemon=True).start()
        return True

    def _ensure_service(self) -> SheetsService:
        self.cfg = load_config()
        if not is_sheets_configured(self.cfg):
            raise SheetsConfigError("Google Sheets ainda não configurado. Abra Configurações.")
        self.service = SheetsService.from_config(self.cfg)
        self.service.actor = (
            getattr(self, "_admin_user", "") or str(self.cfg.get("admin_email") or "")
        ).strip()
        return self.service

    def _ensure_public_server(self) -> str:
        """Servidor local só como fallback; site público é o canal principal."""
        self.cfg = load_config()
        if self.cfg.get("public_site_url"):
            return resolve_base()
        svc = self._ensure_service()

        def fetch():
            return svc.get_all_pessoas_com_reap()

        port = int(self.cfg.get("public_port") or 8765)
        start_public_server(fetch, port=port)
        return resolve_base()

    def _activate_link(self, *, force_new: bool = False, on_done=None) -> None:
        """Gera QRs para o site público configurado (URL fixa)."""
        if not preferred_public_base():
            messagebox.showwarning(
                "Site público",
                "Configure a URL do site público em Configurações "
                "(GitHub Pages / Cloudflare / Netlify).",
            )
            navigate(self, "settings")
            return

        def work():
            pessoas = []
            try:
                svc = self._ensure_service()
                pessoas = svc.get_all_pessoas_com_reap()
            except Exception:
                pass
            base = ensure_site_qrs(pessoas=pessoas or None, force=force_new)
            return base, force_new, pessoas

        def ok(result):
            base, mudou, _pessoas = result
            self.cfg = load_config()
            if on_done:
                on_done(base, mudou)
            else:
                messagebox.showinfo(
                    "QRs do site público",
                    f"QRs apontando para:\n{base}\n\n"
                    f"Pasta:\n{qr_dir()}\n\n"
                    "Este endereço é fixo — não precisa gerar QR novo depois.",
                )

        self._run_bg(
            work,
            ok,
            lambda e: messagebox.showerror("Site público", str(e)),
            "Gerando QRs do site público…",
        )

    def _sync_site_config_js(self, spreadsheet_id: str) -> None:
        """Atualiza spreadsheetId em site-publico/config.js quando existir no disco."""
        sid = (spreadsheet_id or "").strip()
        if not sid:
            return
        candidates = [
            Path(__file__).resolve().parents[2] / "site-publico" / "config.js",
            exe_dir().parent / "site-publico" / "config.js",
            exe_dir() / "site-publico" / "config.js",
            app_data_dir() / "site-publico" / "config.js",
        ]
        for path in candidates:
            if not path.exists():
                continue
            try:
                text = path.read_text(encoding="utf-8")
                updated = re.sub(
                    r'spreadsheetId:\s*"[^"]*"',
                    f'spreadsheetId: "{sid}"',
                    text,
                    count=1,
                )
                if updated != text:
                    path.write_text(updated, encoding="utf-8")
                    self.status.set(f"config.js atualizado: {path}")
                return
            except OSError:
                continue

    # ------------------------------------------------------------------
    # Home / Login
    # ------------------------------------------------------------------
    def show_home(self) -> None:
        navigate(self, "home")

    def _render_home(self) -> None:
        self._lista_mode = False
        wrap = page_wrap(self, padx=40, pady=28)

        hero = tk.Frame(wrap, bg=COLORS["primary"], padx=22, pady=18)
        hero.pack(fill="x", pady=(0, 18))
        row = tk.Frame(hero, bg=COLORS["primary"])
        row.pack(fill="x")
        if getattr(self, "_logo_img", None) is not None:
            tk.Label(row, image=self._logo_img, bg=COLORS["primary"]).pack(side="left", padx=(0, 14))
        col = tk.Frame(row, bg=COLORS["primary"])
        col.pack(side="left", fill="x", expand=True)
        tk.Label(col, text=ORG_SHORT, bg=COLORS["primary"], fg=COLORS["foam"], font=(FONT_DISPLAY, 22, "bold")).pack(anchor="w")
        tk.Label(col, text=ORG_FULL, bg=COLORS["primary"], fg="#B7D3E8", font=(FONT_FAMILY, 10)).pack(anchor="w", pady=(2, 6))
        tk.Label(
            col,
            text="Controle REAP · consulta online · QR permanente",
            bg=COLORS["primary"], fg="#8EB0C9", font=(FONT_FAMILY, 9),
        ).pack(anchor="w")

        cards = tk.Frame(wrap, bg=COLORS["content"])
        cards.pack(fill="x")
        self._home_card(
            cards,
            "Secretaria",
            "Cadastre sócios, marque REAPs e importe lotes na planilha Google.",
            "Entrar como administrador",
            self.show_login,
        ).pack(side="left", fill="both", expand=True, padx=(0, 10))
        self._home_card(
            cards,
            "Consulta & QR",
            "Site público online (CPF) e QRs permanentes para imprimir na sede.",
            "Abrir lista e QRs",
            self.show_lista,
        ).pack(side="left", fill="both", expand=True, padx=(10, 0))

        tip = tk.Frame(wrap, bg=COLORS["surface_soft"], padx=16, pady=12)
        tip.pack(fill="x", pady=(18, 0))
        tip.configure(highlightbackground=COLORS["border"], highlightthickness=1)
        tk.Label(
            tip,
            text="Site gratuito: compartilhe a planilha como Leitor, publique site-publico/, "
            "cole a URL em Configurações e gere o QR Consulta.",
            bg=COLORS["surface_soft"],
            fg=COLORS["muted"],
            font=(FONT_FAMILY, 9),
            wraplength=880,
            justify="left",
        ).pack(anchor="w")

    def _home_card(self, parent, title, desc, btn_text, command) -> tk.Frame:
        outer = tk.Frame(parent, bg=COLORS["border"], padx=1, pady=1)
        inner = tk.Frame(outer, bg=COLORS["surface"], padx=22, pady=22)
        inner.pack(fill="both", expand=True)
        tk.Label(inner, text=title, bg=COLORS["surface"], fg=COLORS["primary"], font=(FONT_DISPLAY, 14, "bold"), anchor="w").pack(fill="x")
        tk.Label(inner, text=desc, bg=COLORS["surface"], fg=COLORS["muted"], font=(FONT_FAMILY, 10), wraplength=340, justify="left", anchor="w").pack(fill="x", pady=(8, 18))
        self._btn(inner, btn_text, command, kind="primary").pack(anchor="w")
        return outer

    def show_login(self) -> None:
        navigate(self, "login")

    def _render_login(self) -> None:
        wrap = page_wrap(self)
        box = tk.Frame(wrap, bg=COLORS["surface"], padx=32, pady=28, highlightbackground=COLORS["border"], highlightthickness=1)
        box.pack(anchor="n", pady=40)
        tk.Label(box, text="Acesso administrativo", bg=COLORS["surface"], fg=COLORS["primary"], font=(FONT_DISPLAY, 15, "bold")).pack(anchor="w")
        tk.Label(box, text=ORG_FULL, bg=COLORS["surface"], fg=COLORS["muted"], font=(FONT_FAMILY, 9)).pack(anchor="w", pady=(2, 16))

        tk.Label(box, text="E-mail", bg=COLORS["surface"], fg=COLORS["muted"]).pack(anchor="w")
        email = ttk.Entry(box, width=42)
        email.pack(anchor="w", pady=(2, 10))
        email.insert(0, self.cfg.get("admin_email", ""))

        tk.Label(box, text="Senha", bg=COLORS["surface"], fg=COLORS["muted"]).pack(anchor="w")
        password = ttk.Entry(box, width=42, show="•")
        password.pack(anchor="w", pady=(2, 16))

        def do_login() -> None:
            cfg = load_config()
            if email.get().strip().lower() != str(cfg.get("admin_email", "")).lower() or password.get() != str(cfg.get("admin_password", "")):
                messagebox.showerror("Login", "E-mail ou senha incorretos.")
                return
            if not is_sheets_configured(cfg):
                messagebox.showwarning("Configuração", "Configure primeiro o Google Sheets.")
                navigate(self, "settings")
                return
            self._logged_in = True
            self._admin_user = email.get().strip()
            sync_chrome(self, "secretaria", active_tab="socies")
            navigate(self, "admin")

        self._btn(box, "Entrar", do_login).pack(anchor="e")
        password.bind("<Return>", lambda _e: do_login())

    # ------------------------------------------------------------------
    # Configurações + site público
    # ------------------------------------------------------------------
    def show_settings(self) -> None:
        navigate(self, "settings")

    def _render_settings(self) -> None:
        outer = page_wrap(self)
        tk.Label(outer, text="Configurações", bg=COLORS["content"], fg=COLORS["primary"], font=(FONT_DISPLAY, 20, "bold")).pack(anchor="w")

        scroll = ScrollableFrame(outer, bg=COLORS["content"])
        scroll.pack(fill="both", expand=True, pady=(8, 0))
        self._scroll = scroll
        wrap = scroll.inner
        cfg = load_config()

        form = tk.Frame(wrap, bg=COLORS["surface"], padx=18, pady=18, highlightbackground=COLORS["border"], highlightthickness=1)
        form.pack(fill="x", padx=2, pady=(0, 16))

        def labeled(row, label, width=72, show=None, value=""):
            tk.Label(form, text=label, bg=COLORS["surface"], fg=COLORS["muted"]).grid(row=row, column=0, sticky="w")
            ent = ttk.Entry(form, width=width, show=show)
            ent.grid(row=row + 1, column=0, sticky="we", pady=(2, 10))
            ent.insert(0, value)
            return ent

        sheet_id = labeled(0, "ID da planilha Google (admin / API)", value=cfg.get("spreadsheet_id", ""))
        site_url = labeled(
            2,
            "URL do site público (cole SEM /consulta.html) — ex.: https://anmolock.github.io/sinapesc-casanova-reap",
            value=normalize_public_base(cfg.get("public_site_url", "") or cfg.get("public_base_url", "")),
        )
        admin_email = labeled(4, "E-mail do administrador", width=40, value=cfg.get("admin_email", "admin@sinapesc.local"))
        admin_password = labeled(6, "Senha do administrador", width=40, show="•", value=cfg.get("admin_password", "sinapesc"))

        cred_label = tk.StringVar(
            value=(
                f"JSON: {cfg['credentials_json'].get('client_email')}"
                if isinstance(cfg.get("credentials_json"), dict)
                else "Nenhuma credencial carregada."
            )
        )
        tk.Label(form, textvariable=cred_label, bg=COLORS["surface"], fg=COLORS["accent"], font=(FONT_FAMILY, 9, "bold")).grid(row=8, column=0, sticky="w", pady=(0, 8))
        credentials_holder = {"json": cfg.get("credentials_json")}

        def pick_json() -> None:
            path = filedialog.askopenfilename(title="JSON da Conta de Serviço", filetypes=[("JSON", "*.json"), ("Todos", "*.*")])
            if not path:
                return
            try:
                data = import_credentials_file(path)
            except Exception as exc:  # noqa: BLE001
                messagebox.showerror("Credenciais", str(exc))
                return
            credentials_holder["json"] = data
            cred_label.set(f"JSON: {data.get('client_email')}")

        self._btn(form, "Importar JSON da Conta de Serviço…", pick_json, kind="primary").grid(row=9, column=0, sticky="w", pady=(0, 12))

        site_box = tk.Frame(form, bg=COLORS["surface_soft"], padx=14, pady=14)
        site_box.grid(row=10, column=0, sticky="we", pady=(0, 14))
        tk.Label(site_box, text="Site público online (Opção A — gratuito)", bg=COLORS["surface_soft"], fg=COLORS["primary"], font=(FONT_DISPLAY, 11, "bold")).pack(anchor="w")
        tk.Label(
            site_box,
            text=(
                "1) Compartilhe a planilha como Leitor (qualquer pessoa com o link)\n"
                "2) Publique a pasta site-publico/ (GitHub Pages)\n"
                "3) Cole a URL do site acima · 4) Gere os QRs permanentes\n"
                "O notebook NÃO precisa ficar ligado para a consulta no celular."
            ),
            bg=COLORS["surface_soft"], fg=COLORS["muted"], font=(FONT_FAMILY, 9), justify="left",
        ).pack(anchor="w", pady=(4, 10))
        site_status = tk.StringVar(
            value=(f"Site: {cfg.get('public_site_url')}" if cfg.get("public_site_url") else "Site ainda não configurado.")
        )
        tk.Label(site_box, textvariable=site_status, bg=COLORS["surface_soft"], fg=COLORS["accent"], font=(FONT_FAMILY, 9, "bold")).pack(anchor="w", pady=(0, 8))

        def persist_site_url() -> str:
            """Salva a URL do site (normalizada) sem exigir login Google."""
            base = normalize_public_base(site_url.get())
            if not base:
                return ""
            new_cfg = load_config()
            new_cfg["public_site_url"] = base
            new_cfg["public_base_url"] = base
            save_config(new_cfg)
            self.cfg = new_cfg
            site_url.delete(0, "end")
            site_url.insert(0, base)
            site_status.set(f"Site: {base}")
            return base

        def gerar_qrs_site() -> None:
            base = persist_site_url()
            if not base:
                messagebox.showwarning(
                    "Site público",
                    "Cole a URL do site, por exemplo:\n"
                    "https://anmolock.github.io/sinapesc-casanova-reap\n\n"
                    "(sem /consulta.html no final)",
                )
                return
            if sheet_id.get().strip():
                new_cfg = load_config()
                new_cfg["spreadsheet_id"] = sheet_id.get().strip()
                save_config(new_cfg)
                self.cfg = new_cfg
                self._sync_site_config_js(new_cfg.get("spreadsheet_id", ""))

            def done(b, _mudou):
                site_status.set(f"QRs prontos → {b}")

            self._activate_link(force_new=True, on_done=done)

        def abrir_pasta_qr() -> None:
            import os
            import subprocess

            path = str(qr_dir())
            if os.name == "nt":
                os.startfile(path)  # type: ignore[attr-defined]
            else:
                subprocess.Popen(["xdg-open", path])

        def qr_consulta_agora() -> None:
            persist_site_url()
            self._show_qr_consulta()

        row = tk.Frame(site_box, bg=COLORS["surface_soft"])
        row.pack(anchor="w")
        self._btn(row, "Gerar QRs do site", gerar_qrs_site).pack(side="left", padx=(0, 6))
        self._btn(row, "QR Consulta CPF", qr_consulta_agora, kind="primary").pack(side="left", padx=(0, 6))
        self._btn(row, "Pasta dos QRs", abrir_pasta_qr, kind="ghost").pack(side="left")

        def save() -> None:
            new_cfg = load_config()
            new_cfg["spreadsheet_id"] = sheet_id.get().strip()
            site = normalize_public_base(site_url.get())
            new_cfg["public_site_url"] = site
            if site:
                new_cfg["public_base_url"] = site
            new_cfg["admin_email"] = admin_email.get().strip()
            new_cfg["admin_password"] = admin_password.get()
            if credentials_holder["json"]:
                new_cfg["credentials_json"] = credentials_holder["json"]
                new_cfg["service_account_email"] = credentials_holder["json"].get("client_email", "")
                new_cfg["private_key"] = credentials_holder["json"].get("private_key", "")
            # Sempre pode salvar a URL do site; Sheets só é obrigatório se for usar admin
            if site:
                save_config(new_cfg)
                self.cfg = new_cfg
                site_url.delete(0, "end")
                site_url.insert(0, site)
                site_status.set(f"Site: {site}")
            if new_cfg["spreadsheet_id"] and not is_sheets_configured(new_cfg):
                messagebox.showwarning(
                    "Configuração",
                    "URL do site salva.\nPara o admin, importe também o JSON da Conta de Serviço.",
                )
                return
            if not new_cfg["spreadsheet_id"]:
                if site:
                    messagebox.showinfo("Configuração", f"URL do site salva:\n{site}")
                else:
                    messagebox.showerror("Configuração", "Informe o ID da planilha ou a URL do site.")
                return
            save_config(new_cfg)
            self.cfg = new_cfg
            self.service = None
            self._sync_site_config_js(new_cfg.get("spreadsheet_id", ""))
            site_status.set(f"Site: {site}" if site else "Site ainda não configurado.")
            messagebox.showinfo("Configuração", "Salvo com sucesso.")

        def test_connection() -> None:
            save()
            try:
                svc = self._ensure_service()
            except Exception as exc:  # noqa: BLE001
                messagebox.showerror("Teste", str(exc))
                return

            def work():
                svc.client.ensure_tabs()
                return len(svc.get_all_pessoas())

            self._run_bg(
                work,
                lambda n: messagebox.showinfo("Teste", f"Conexão OK!\nAssociados: {n}"),
                lambda e: messagebox.showerror("Teste", str(e)),
                "Testando…",
            )

        actions = tk.Frame(form, bg=COLORS["surface"])
        actions.grid(row=13, column=0, sticky="w")
        self._btn(actions, "Salvar", save).pack(side="left", padx=(0, 8))
        self._btn(actions, "Testar conexão", test_connection, kind="primary").pack(side="left")
        form.columnconfigure(0, weight=1)

    # ------------------------------------------------------------------
    # Admin
    # ------------------------------------------------------------------
    def show_admin(self) -> None:
        navigate(self, "admin")

    def _render_admin(self) -> None:
        self._lista_mode = False
        wrap = page_wrap(self)

        title_block = tk.Frame(wrap, bg=COLORS["content"])
        title_block.pack(fill="x", pady=(0, 12))
        title_line = tk.Frame(title_block, bg=COLORS["content"])
        title_line.pack(anchor="w")
        tk.Label(
            title_line, text="Sócios", bg=COLORS["content"], fg=COLORS["primary"],
            font=(FONT_DISPLAY, 22, "bold"),
        ).pack(side="left")
        self.admin_count = tk.StringVar(value="")
        tk.Label(
            title_line, textvariable=self.admin_count, bg=COLORS["content"], fg=COLORS["muted"],
            font=(FONT_FAMILY, 10),
        ).pack(side="left", padx=(12, 0))
        tk.Label(
            title_block, text="Clique no nome para abrir o REAP", bg=COLORS["content"], fg=COLORS["muted"],
            font=(FONT_FAMILY, 9),
        ).pack(anchor="w", pady=(4, 0))

        toolbar = tk.Frame(wrap, bg=COLORS["content"])
        toolbar.pack(fill="x", pady=(0, 14))
        self.search_var = tk.StringVar()
        search_field(toolbar, self.search_var, width=36).pack(side="left", fill="x", expand=True, padx=(0, 12))
        self.search_var.trace_add("write", lambda *_: self._render_admin_list())

        btn_row = tk.Frame(toolbar, bg=COLORS["content"])
        btn_row.pack(side="right")
        content_outline_btn(btn_row, "↻ Atualizar", self._load_admin_data).pack(side="left", padx=(0, 6))
        content_outline_btn(btn_row, "⇪ Cadastro em lote", self._dialog_lote).pack(side="left", padx=(0, 6))
        content_primary_btn(btn_row, "+ Novo sócio", lambda: self._dialog_pessoa()).pack(side="left")

        self._scroll = ScrollableFrame(wrap, bg=COLORS["content"])
        self._scroll.pack(fill="both", expand=True)
        self.admin_list = self._scroll.inner
        self._load_admin_data()
        self.after(1400, lambda: talvez_lembrar_backup(self))

    def show_pendencias(self) -> None:
        navigate(self, "pendencias")

    def _render_pendencias(self) -> None:
        open_pendencias(self)

    def show_relatorio(self) -> None:
        navigate(self, "relatorio")

    def _render_relatorio(self) -> None:
        open_relatorio(self)

    def show_backup(self) -> None:
        navigate(self, "backup")

    def _render_backup(self) -> None:
        from ui.tela_backup import render_backup

        render_backup(self)

    def show_auditoria(self) -> None:
        navigate(self, "auditoria")

    def _render_auditoria(self) -> None:
        open_auditoria(self)

    def _open_atalhos_tab(self) -> None:
        self._dialog_atalhos()

    def _logout(self) -> None:
        self._logged_in = False
        self._admin_user = ""
        self._expanded_ids.clear()
        self._nav_history.clear()
        navigate(self, "home", push=False)

    def _load_admin_data(self) -> None:
        try:
            svc = self._ensure_service()
        except Exception as exc:  # noqa: BLE001
            messagebox.showerror("Sheets", str(exc))
            navigate(self, "settings")
            return

        def work():
            return svc.get_all_pessoas_com_reap()

        def ok(pessoas: List[PessoaComReap]) -> None:
            self._pessoas = pessoas
            if hasattr(self, "admin_count"):
                self.admin_count.set(f"{len(pessoas)} cadastrados")
            self._render_admin_list()

        self._run_bg(work, ok, lambda e: messagebox.showerror("Erro", str(e)), "Carregando sócios…")

    def _filtered_pessoas(self) -> List[PessoaComReap]:
        pessoas = list(self._pessoas)
        if hasattr(self, "search_var"):
            q = self.search_var.get().strip().lower()
            digits = only_digits(q)
            if q:
                pessoas = [p for p in pessoas if q in p.nome.lower() or (digits and digits in p.cpf)]
        mode = getattr(self, "_sort_mode", "recent")
        if mode == "az":
            pessoas.sort(key=lambda p: (p.nome or "").lower())
        else:
            pessoas.sort(key=lambda p: p.criado_em or "", reverse=True)
        return pessoas

    def _render_admin_list(self) -> None:
        if not hasattr(self, "admin_list") or not self.admin_list.winfo_exists():
            return
        for child in self.admin_list.winfo_children():
            child.destroy()
        pessoas = self._filtered_pessoas()
        if not pessoas:
            tk.Label(
                self.admin_list,
                text="Nenhum sócio encontrado." if self._pessoas else "Nenhum sócio cadastrado.",
                bg=COLORS["content"], fg=COLORS["muted"],
            ).pack(anchor="w", pady=20)
            return
        for pessoa in pessoas:
            self._pessoa_row(self.admin_list, pessoa, editable=True)

    def _toggle_expand(self, person_id: str) -> None:
        if person_id in self._expanded_ids:
            self._expanded_ids.discard(person_id)
        else:
            self._expanded_ids.add(person_id)
        y = 0.0
        if self._scroll is not None:
            try:
                y = self._scroll.canvas.yview()[0]
            except tk.TclError:
                y = 0.0
        if self._lista_mode:
            self._render_lista_rows()
        else:
            self._render_admin_list()
        if self._scroll is not None:
            self.after(10, lambda: self._scroll.canvas.yview_moveto(y))

    def _pessoa_row(self, parent, pessoa: PessoaComReap, *, editable: bool, mask_cpf: bool = False) -> None:
        expanded = pessoa.id in self._expanded_ids
        card = card_shell(parent)
        card.pack(fill="x", pady=6, padx=1)

        head = tk.Frame(card, bg=COLORS["surface"])
        head.pack(fill="x")

        avatar = circular_avatar(head, get_initials(pessoa.nome))
        avatar.pack(side="left", padx=(0, 14))

        info = tk.Frame(head, bg=COLORS["surface"], cursor="hand2")
        info.pack(side="left", fill="x", expand=True)

        name_lbl = tk.Label(
            info, text=display_nome(pessoa.nome), bg=COLORS["surface"], fg=COLORS["primary"],
            font=(FONT_DISPLAY, 11, "bold"), anchor="w", cursor="hand2",
        )
        name_lbl.pack(anchor="w")
        cpf_txt = format_cpf_masked(pessoa.cpf) if mask_cpf else format_cpf(pessoa.cpf)
        sub = tk.Label(
            info, text=f"CPF: {cpf_txt}", bg=COLORS["surface"], fg=COLORS["muted"],
            font=(FONT_FAMILY, 9), anchor="w", cursor="hand2",
        )
        sub.pack(anchor="w", pady=(2, 0))

        def toggle(_e=None, pid=pessoa.id):
            self._toggle_expand(pid)

        for w in (info, name_lbl, sub, avatar):
            w.bind("<Button-1>", toggle)

        if editable:
            actions = tk.Frame(head, bg=COLORS["surface"])
            actions.pack(side="right")
            icon_btn(actions, "▦ QR", lambda p=pessoa: self._show_qr_pessoa(p)).pack(side="left", padx=(0, 2))
            icon_btn(actions, "✎ Editar", lambda p=pessoa: self._dialog_pessoa(p)).pack(side="left", padx=2)
            icon_btn(actions, "🗑 Excluir", lambda p=pessoa: self._delete_pessoa(p), danger=True).pack(side="left", padx=2)
            chevron_btn(actions, expanded, lambda pid=pessoa.id: self._toggle_expand(pid)).pack(side="left", padx=(6, 0))
        else:
            chevron_btn(head, expanded, lambda pid=pessoa.id: self._toggle_expand(pid)).pack(side="right")

        if not expanded:
            return

        detail = tk.Frame(card, bg=COLORS["surface"])
        detail.pack(fill="x", pady=(14, 0))
        tk.Frame(detail, bg=COLORS["border_soft"], height=1).pack(fill="x", pady=(0, 12))

        if not pessoa.anos:
            tk.Label(detail, text="Nenhum ano registrado.", bg=COLORS["surface"], fg=COLORS["muted"]).pack(anchor="w")
        for ano in pessoa.anos:
            ano_frame = tk.Frame(detail, bg=COLORS["surface"])
            ano_frame.pack(fill="x", pady=(4, 0))
            tk.Label(
                ano_frame, text=f"Ano {ano.ano}", bg=COLORS["surface"], fg=COLORS["primary"],
                font=(FONT_DISPLAY, 10, "bold"),
            ).pack(anchor="w", pady=(0, 6))
            self._month_grid(ano_frame, pessoa.id, ano.ano, ano.meses, editable=editable)

        if editable:
            add_row = tk.Frame(detail, bg=COLORS["surface"])
            add_row.pack(fill="x", pady=(14, 0))
            year_var = tk.StringVar(value=str(__import__("datetime").datetime.now().year + 1))
            ttk.Entry(add_row, textvariable=year_var, width=8).pack(side="left")
            content_outline_btn(
                add_row, "Adicionar ano", lambda p=pessoa, y=year_var: self._add_ano(p, y.get()), padx=10, pady=4,
            ).pack(side="left", padx=8)

    def _month_grid(self, parent, person_id: str, ano: int, meses: dict, *, editable: bool) -> None:
        row = tk.Frame(parent, bg=COLORS["surface"])
        row.pack(fill="x", pady=2)
        for mes in MESES:
            pago = bool(meses.get(mes))
            cmd = None
            if editable:
                cmd = lambda m=mes, p=pago: self._toggle_mes(person_id, ano, m, not p)
            pill = month_pill(row, mes, pago=pago, editable=editable, command=cmd)
            pill.pack(side="left", padx=3)
            pill.bind("<Enter>", lambda _e, t=MESES_LABEL[mes]: self.status.set(t))
            pill.bind("<Leave>", lambda _e: self.status.set("Pronto."))

    def _toggle_mes(self, person_id: str, ano: int, mes: MesKey, novo: bool) -> None:
        try:
            svc = self._ensure_service()
        except Exception as exc:  # noqa: BLE001
            messagebox.showerror("Sheets", str(exc))
            return
        self._expanded_ids.add(person_id)
        nome = next((p.nome for p in self._pessoas if p.id == person_id), "")

        def work():
            svc.toggle_mes(person_id, ano, mes, novo, nome=nome)
            return True

        self._run_bg(work, lambda _: self._load_admin_data(), lambda e: messagebox.showerror("Erro", str(e)), f"Atualizando {mes}/{ano}…")

    def _dialog_pessoa(self, pessoa: Optional[PessoaComReap] = None) -> None:
        win = tk.Toplevel(self)
        win.title("Editar sócio" if pessoa else "Novo sócio")
        win.configure(bg=COLORS["surface"])
        win.transient(self)
        win.grab_set()

        tk.Label(win, text="Nome completo", bg=COLORS["surface"], fg=COLORS["muted"]).pack(anchor="w", padx=16, pady=(16, 2))
        nome = ttk.Entry(win, width=44)
        nome.pack(padx=16)
        if pessoa:
            nome.insert(0, format_nome(pessoa.nome))

        tk.Label(win, text="CPF (11 dígitos)", bg=COLORS["surface"], fg=COLORS["muted"]).pack(anchor="w", padx=16, pady=(10, 2))
        cpf = ttk.Entry(win, width=44)
        cpf.pack(padx=16)
        if pessoa:
            cpf.insert(0, format_cpf_input(pessoa.cpf))

        def _mask_cpf(_evt=None) -> None:
            digits = only_digits(cpf.get())
            shown = format_cpf_input(digits)
            if cpf.get() != shown:
                pos = cpf.index("insert")
                cpf.delete(0, "end")
                cpf.insert(0, shown)
                try:
                    cpf.icursor(min(pos, len(shown)))
                except tk.TclError:
                    cpf.icursor("end")

        cpf.bind("<KeyRelease>", _mask_cpf)

        def save() -> None:
            n = format_nome(nome.get())
            c = only_digits(cpf.get())
            if not n:
                messagebox.showerror("Validação", "Informe o nome completo.", parent=win)
                return
            if len(c) != 11:
                messagebox.showerror("Validação", "CPF deve conter 11 dígitos.", parent=win)
                return
            try:
                svc = self._ensure_service()
            except Exception as exc:  # noqa: BLE001
                messagebox.showerror("Sheets", str(exc), parent=win)
                return

            def work():
                if pessoa:
                    svc.update_pessoa(pessoa.id, n, c)
                    return pessoa.id
                return svc.add_pessoa(n, c).id

            def ok(pid: str) -> None:
                win.destroy()
                self._expanded_ids.add(pid)
                self._load_admin_data()

            self._run_bg(work, ok, lambda e: messagebox.showerror("Erro", str(e), parent=win), "Salvando…")

        self._btn(win, "Salvar", save).pack(pady=16)

    def _atalhos_month_vars(self, parent) -> dict:
        box = tk.Frame(parent, bg=COLORS["surface"])
        box.pack(fill="x", pady=(4, 8))
        vars_mes = {m: tk.BooleanVar(value=False) for m in MESES}

        def aplicar(meses):
            ligados = set(meses)
            for m, var in vars_mes.items():
                var.set(m in ligados)

        presets = tk.Frame(box, bg=COLORS["surface"])
        presets.pack(fill="x", pady=(0, 6))
        self._btn(presets, "Mar → Out", lambda: aplicar(meses_no_intervalo("mar", "out")), kind="ghost", padx=8, pady=3, font_size=9).pack(side="left", padx=(0, 4))
        self._btn(presets, "Ano inteiro", lambda: aplicar(list(MESES)), kind="ghost", padx=8, pady=3, font_size=9).pack(side="left", padx=4)
        self._btn(presets, "Limpar", lambda: aplicar([]), kind="ghost", padx=8, pady=3, font_size=9).pack(side="left", padx=4)

        grid = tk.Frame(box, bg=COLORS["surface"])
        grid.pack(fill="x")
        for i, mes in enumerate(MESES):
            tk.Checkbutton(
                grid,
                text=MESES_LABEL[mes][:3],
                variable=vars_mes[mes],
                bg=COLORS["surface"],
                fg=COLORS["primary"],
                selectcolor=COLORS["surface_soft"],
                activebackground=COLORS["surface"],
                font=(FONT_FAMILY, 9),
            ).grid(row=i // 6, column=i % 6, sticky="w", padx=4, pady=2)
        return vars_mes

    def _meses_escolhidos(self, vars_mes: dict) -> List[str]:
        return [m for m, var in vars_mes.items() if var.get()]

    def _dialog_atalhos(self) -> None:
        win = tk.Toplevel(self)
        win.title("Config.Atalhos")
        win.configure(bg=COLORS["bg"])
        win.geometry("760x640")
        win.transient(self)
        win.grab_set()

        tk.Frame(win, bg=COLORS["gold"], height=3).pack(fill="x")
        head = tk.Frame(win, bg=COLORS["primary"], padx=16, pady=12)
        head.pack(fill="x")
        tk.Label(head, text="Config.Atalhos", bg=COLORS["primary"], fg=COLORS["foam"], font=(FONT_DISPLAY, 16, "bold")).pack(anchor="w")
        tk.Label(
            head,
            text="Automações estáveis: poucas chamadas à planilha, sem marcar mês a mês na API.",
            bg=COLORS["primary"],
            fg="#B7D3E8",
            font=(FONT_FAMILY, 9),
        ).pack(anchor="w", pady=(4, 0))

        scroll = ScrollableFrame(win, bg=COLORS["bg"])
        scroll.pack(fill="both", expand=True, padx=16, pady=12)
        body = scroll.inner

        def card(title, desc):
            outer = tk.Frame(body, bg=COLORS["border"], padx=1, pady=1)
            outer.pack(fill="x", pady=(0, 12))
            inner = tk.Frame(outer, bg=COLORS["surface"], padx=14, pady=12)
            inner.pack(fill="both", expand=True)
            tk.Label(inner, text=title, bg=COLORS["surface"], fg=COLORS["primary"], font=(FONT_DISPLAY, 12, "bold")).pack(anchor="w")
            tk.Label(inner, text=desc, bg=COLORS["surface"], fg=COLORS["muted"], font=(FONT_FAMILY, 9), wraplength=680, justify="left").pack(anchor="w", pady=(2, 8))
            return inner

        from datetime import datetime as _dt

        # ---- 1 lote com meses ----
        c1 = card(
            "1) Lote com REAP já marcado",
            "Cadastra vários sócios de uma vez e já deixa os meses pagos no ano escolhido "
            "(ex.: março a outubro, ou só um mês). Uma escrita na aba Pessoas e outra na Reap.",
        )
        r1 = tk.Frame(c1, bg=COLORS["surface"])
        r1.pack(fill="x")
        tk.Label(r1, text="Ano", bg=COLORS["surface"], fg=COLORS["muted"]).pack(side="left")
        ano1 = ttk.Entry(r1, width=8)
        ano1.insert(0, str(_dt.now().year))
        ano1.pack(side="left", padx=8)
        vars1 = self._atalhos_month_vars(c1)
        self._btn(
            c1,
            "Abrir lote com meses marcados…",
            lambda: self._abrir_lote_atalho(win, vars1, ano1.get()),
            kind="accent",
        ).pack(anchor="w")

        # ---- 2 marcar existentes ----
        c2 = card(
            "2) Marcar meses nos sócios já cadastrados",
            "Liga o intervalo (ex.: mar–out) no ano para todos os sócios, ou só os da busca atual. "
            "Não apaga meses já pagos, a menos que você marque “substituir o ano”.",
        )
        r2 = tk.Frame(c2, bg=COLORS["surface"])
        r2.pack(fill="x")
        tk.Label(r2, text="Ano", bg=COLORS["surface"], fg=COLORS["muted"]).pack(side="left")
        ano2 = ttk.Entry(r2, width=8)
        ano2.insert(0, str(_dt.now().year))
        ano2.pack(side="left", padx=8)
        so_busca = tk.BooleanVar(value=False)
        tk.Checkbutton(r2, text="Só quem aparece na busca da lista", variable=so_busca, bg=COLORS["surface"], fg=COLORS["primary"], selectcolor=COLORS["surface_soft"]).pack(side="left", padx=12)
        substituir = tk.BooleanVar(value=False)
        tk.Checkbutton(c2, text="Substituir o ano (desmarca os meses não escolhidos)", variable=substituir, bg=COLORS["surface"], fg=COLORS["muted"], selectcolor=COLORS["surface_soft"]).pack(anchor="w")
        vars2 = self._atalhos_month_vars(c2)

        def run_marcar() -> None:
            meses = self._meses_escolhidos(vars2)
            if not meses:
                messagebox.showwarning("Atalhos", "Escolha pelo menos um mês (ex.: Mar → Out).", parent=win)
                return
            try:
                ano = int(ano2.get().strip())
            except ValueError:
                messagebox.showerror("Atalhos", "Ano inválido.", parent=win)
                return
            alvo = self._filtered_pessoas() if so_busca.get() else list(self._pessoas)
            if not alvo:
                messagebox.showwarning("Atalhos", "Nenhum sócio para aplicar.", parent=win)
                return
            nomes = ", ".join(m.upper() for m in meses)
            if not messagebox.askyesno(
                "Confirmar",
                f"Marcar {nomes} em {ano} para {len(alvo)} sócio(s)?\n\n"
                "Isso grava na planilha em lote (não quebra a API).",
                parent=win,
            ):
                return
            try:
                svc = self._ensure_service()
            except Exception as extra:  # noqa: BLE001
                messagebox.showerror("Sheets", str(extra), parent=win)
                return

            def work():
                return svc.marcar_meses_em_massa(
                    ano=ano,
                    meses_on=meses,
                    person_ids=[p.id for p in alvo],
                    substituir=substituir.get(),
                )

            def ok(res: dict) -> None:
                messagebox.showinfo(
                    "Atalhos",
                    f"Atualizados: {res.get('atualizados', 0)}\n"
                    f"Anos criados: {res.get('criados', 0)}",
                    parent=win,
                )
                self._load_admin_data()

            if not self._run_bg(work, ok, lambda e: messagebox.showerror("Erro", str(e), parent=win), "Marcando meses em lote…"):
                return

        self._btn(c2, "Aplicar marcação em massa", run_marcar).pack(anchor="w", pady=(4, 0))

        # ---- 3 copiar ano ----
        c3 = card(
            "3) Copiar REAP de um ano para outro",
            "Leva os 12 meses já marcados (ex.: 2025 → 2026). Cria o ano novo se ainda não existir. "
            "Útil no virar do ano, sem clicar sócio por sócio.",
        )
        r3 = tk.Frame(c3, bg=COLORS["surface"])
        r3.pack(fill="x")
        tk.Label(r3, text="De", bg=COLORS["surface"], fg=COLORS["muted"]).pack(side="left")
        ano_de = ttk.Entry(r3, width=8)
        ano_de.insert(0, str(_dt.now().year - 1))
        ano_de.pack(side="left", padx=6)
        tk.Label(r3, text="para", bg=COLORS["surface"], fg=COLORS["muted"]).pack(side="left")
        ano_para = ttk.Entry(r3, width=8)
        ano_para.insert(0, str(_dt.now().year))
        ano_para.pack(side="left", padx=6)
        so_busca3 = tk.BooleanVar(value=False)
        tk.Checkbutton(r3, text="Só a busca da lista", variable=so_busca3, bg=COLORS["surface"], fg=COLORS["primary"], selectcolor=COLORS["surface_soft"]).pack(side="left", padx=12)

        def run_copiar() -> None:
            try:
                a = int(ano_de.get().strip())
                b = int(ano_para.get().strip())
            except ValueError:
                messagebox.showerror("Atalhos", "Anos inválidos.", parent=win)
                return
            alvo = self._filtered_pessoas() if so_busca3.get() else list(self._pessoas)
            if not alvo:
                messagebox.showwarning("Atalhos", "Nenhum sócio para copiar.", parent=win)
                return
            if not messagebox.askyesno("Confirmar", f"Copiar meses de {a} para {b} em {len(alvo)} sócio(s)?", parent=win):
                return
            try:
                svc = self._ensure_service()
            except Exception as extra:  # noqa: BLE001
                messagebox.showerror("Sheets", str(extra), parent=win)
                return

            def work():
                return svc.copiar_reap_ano(a, b, person_ids=[p.id for p in alvo])

            def ok(res: dict) -> None:
                messagebox.showinfo(
                    "Atalhos",
                    f"Copiados: {res.get('ok', 0)}\n"
                    f"Sem ano {a} (pulados): {res.get('pulados', 0)}",
                    parent=win,
                )
                self._load_admin_data()

            if not self._run_bg(work, ok, lambda e: messagebox.showerror("Erro", str(e), parent=win), "Copiando ano…"):
                return

        self._btn(c3, "Copiar ano", run_copiar, kind="accent").pack(anchor="w", pady=(8, 0))

        tk.Label(
            body,
            text="As três ações usam escrita em lote. Evite clicar várias vezes seguidas enquanto a barra de status disser “Marcando…” / “Copiando…”.",
            bg=COLORS["bg"],
            fg=COLORS["muted"],
            font=(FONT_FAMILY, 8),
            wraplength=680,
            justify="left",
        ).pack(anchor="w", pady=(0, 16))

        self._btn(win, "Fechar", win.destroy, kind="ghost").pack(pady=(0, 12))

    def _abrir_lote_atalho(self, atalhos_win, vars_mes: dict, ano: str) -> None:
        meses = self._meses_escolhidos(vars_mes)
        if not meses:
            messagebox.showwarning(
                "Atalhos",
                "Escolha os meses (ex.: Mar → Out) ou um mês específico antes de abrir o lote.",
                parent=atalhos_win,
            )
            return
        ano_txt = (ano or "").strip()
        if not ano_txt.isdigit():
            messagebox.showerror("Atalhos", "Informe um ano válido (ex.: 2026).", parent=atalhos_win)
            return
        ano_int = int(ano_txt)
        if ano_int < 2000 or ano_int > 2100:
            messagebox.showerror("Atalhos", "Informe um ano entre 2000 e 2100.", parent=atalhos_win)
            return
        try:
            atalhos_win.grab_release()
        except tk.TclError:
            pass

        def restore_modal() -> None:
            if atalhos_win.winfo_exists():
                try:
                    atalhos_win.grab_set()
                except tk.TclError:
                    pass

        self._dialog_lote(meses_on=meses, ano=ano_txt, on_close=restore_modal)

    def _dialog_lote(
        self,
        meses_on: Optional[List[str]] = None,
        ano: Optional[str] = None,
        *,
        on_close: Optional[Callable[[], None]] = None,
    ) -> None:
        win = tk.Toplevel(self)
        win.title("Cadastro em lote")
        win.configure(bg=COLORS["surface"])
        win.geometry("720x560")
        win.transient(self)
        win.grab_set()

        def close_lote() -> None:
            if on_close:
                on_close()
            win.destroy()

        win.protocol("WM_DELETE_WINDOW", close_lote)

        tk.Frame(win, bg=COLORS["gold"], height=3).pack(fill="x")
        tk.Label(
            win,
            text="Cadastro de sócios em lote",
            bg=COLORS["surface"],
            fg=COLORS["primary"],
            font=(FONT_DISPLAY, 14, "bold"),
        ).pack(anchor="w", padx=16, pady=(14, 2))
        tk.Label(
            win,
            text="Uma linha = um sócio. Preencha Nome e CPF lado a lado. A lixeira remove a linha.",
            bg=COLORS["surface"],
            fg=COLORS["muted"],
            font=(FONT_FAMILY, 9),
        ).pack(anchor="w", padx=16)
        meses_escolhidos = [str(m).lower()[:3] for m in (meses_on or []) if str(m).lower()[:3] in MESES]
        ano_lote: Optional[int] = None
        if ano and str(ano).strip().isdigit():
            ano_lote = int(str(ano).strip())
        if meses_escolhidos:
            tk.Label(
                win,
                text=(
                    f"Atalho: no ano {ano_lote or 'atual'} já entram marcados: "
                    + ", ".join(m.upper() for m in meses_escolhidos)
                ),
                bg=COLORS["success_bg"],
                fg=COLORS["success"],
                font=(FONT_FAMILY, 9, "bold"),
            ).pack(fill="x", padx=16, pady=(8, 0))

        header = tk.Frame(win, bg=COLORS["surface_soft"])
        header.pack(fill="x", padx=16, pady=(12, 0))
        tk.Label(header, text="Nome completo", bg=COLORS["surface_soft"], fg=COLORS["primary"], font=(FONT_FAMILY, 9, "bold"), width=36, anchor="w").pack(side="left", padx=(8, 8))
        tk.Label(header, text="CPF", bg=COLORS["surface_soft"], fg=COLORS["primary"], font=(FONT_FAMILY, 9, "bold"), width=18, anchor="w").pack(side="left")
        tk.Label(header, text="", bg=COLORS["surface_soft"], width=4).pack(side="left")

        scroll = ScrollableFrame(win, bg=COLORS["bg"])
        scroll.pack(fill="both", expand=True, padx=16, pady=8)
        rows_host = scroll.inner
        rows_host.configure(bg=COLORS["bg"])
        linhas: List[dict] = []

        def bind_cpf_mask(entry: ttk.Entry) -> None:
            def on_key(_evt=None):
                digits = only_digits(entry.get())
                # format_cpf_input: sem pad/recover (format_cpf quebrava no 9º/10º dígito)
                shown = format_cpf_input(digits)
                if entry.get() != shown:
                    entry.delete(0, "end")
                    entry.insert(0, shown)
                    entry.icursor("end")

            entry.bind("<KeyRelease>", on_key)

        def remover_linha(item: dict) -> None:
            if len(linhas) <= 1:
                item["nome"].delete(0, "end")
                item["cpf"].delete(0, "end")
                return
            linhas.remove(item)
            item["frame"].destroy()

        def add_linha(nome: str = "", cpf: str = "") -> None:
            frame = tk.Frame(rows_host, bg=COLORS["surface"], highlightbackground=COLORS["border_soft"], highlightthickness=1)
            frame.pack(fill="x", pady=4)
            inner = tk.Frame(frame, bg=COLORS["surface"])
            inner.pack(fill="x", padx=6, pady=6)
            nome_ent = ttk.Entry(inner, width=38)
            nome_ent.pack(side="left", padx=(0, 8))
            if nome:
                nome_ent.insert(0, nome)
            cpf_ent = ttk.Entry(inner, width=18)
            cpf_ent.pack(side="left")
            if cpf:
                cpf_ent.insert(0, format_cpf_input(cpf))
            bind_cpf_mask(cpf_ent)
            item = {"frame": frame, "nome": nome_ent, "cpf": cpf_ent}
            self._btn(
                inner,
                "🗑",
                lambda: remover_linha(item),
                kind="ghost",
                padx=8,
                pady=3,
                font_size=10,
                bold=False,
            ).pack(side="left", padx=(8, 0))
            linhas.append(item)

        for _ in range(5):
            add_linha()

        def coletar() -> List[tuple[str, str]]:
            itens: List[tuple[str, str]] = []
            for item in linhas:
                nome = item["nome"].get().strip()
                cpf = only_digits(item["cpf"].get())
                if not nome and not cpf:
                    continue
                itens.append((nome, cpf))
            return itens

        def load_file() -> None:
            path = filedialog.askopenfilename(
                parent=win,
                title="Importar CSV/TXT",
                filetypes=[("Texto/CSV", "*.csv *.txt"), ("Todos", "*.*")],
            )
            if not path:
                return
            raw = open(path, encoding="utf-8-sig", errors="replace").read()
            parsed = parse_lote_lines(raw)
            if not parsed:
                messagebox.showerror("Lote", "Nenhuma linha válida no arquivo.\nUse Nome;CPF", parent=win)
                return
            for item in list(linhas):
                linhas.remove(item)
                item["frame"].destroy()
            for nome, cpf in parsed:
                add_linha(nome, cpf)
            add_linha()

        def salvar() -> None:
            itens = coletar()
            if not itens:
                messagebox.showerror("Lote", "Preencha pelo menos um Nome e CPF.", parent=win)
                return
            try:
                svc = self._ensure_service()
            except Exception as extra:  # noqa: BLE001
                messagebox.showerror("Sheets", str(extra), parent=win)
                return

            def work():
                return svc.add_pessoas_lote(itens, ano=ano_lote, meses_on=meses_escolhidos or None)

            def ok(result: dict) -> None:
                for pid in result.get("ids", []):
                    self._expanded_ids.add(pid)
                msg = f"Cadastrados: {result.get('ok', 0)}"
                if result.get("meses"):
                    msg += f"\nAno {result.get('ano')}: {', '.join(str(m).upper() for m in result['meses'])} já marcados."
                erros = result.get("erros") or []
                if erros:
                    msg += "\n\nAvisos:\n" + "\n".join(erros[:12])
                    if len(erros) > 12:
                        msg += f"\n… e mais {len(erros) - 12}."
                messagebox.showinfo("Lote", msg, parent=win)
                close_lote()
                self._load_admin_data()

            if not self._run_bg(work, ok, lambda e: messagebox.showerror("Erro", str(e), parent=win), "Cadastrando lote…"):
                return

        extra = tk.Frame(win, bg=COLORS["surface"])
        extra.pack(fill="x", padx=16, pady=(0, 4))
        self._btn(extra, "+ Adicionar linha", lambda: add_linha(), kind="ghost").pack(side="left")

        bar = tk.Frame(win, bg=COLORS["surface"])
        bar.pack(fill="x", padx=16, pady=(0, 16))
        self._btn(bar, "Importar arquivo…", load_file, kind="ghost").pack(side="left")
        self._btn(bar, "Cadastrar lote", salvar).pack(side="right")

    def _delete_pessoa(self, pessoa: PessoaComReap) -> None:
        if not messagebox.askyesno("Remover", f"Remover {pessoa.nome} e todo o histórico de REAP?"):
            return
        try:
            svc = self._ensure_service()
        except Exception as exc:  # noqa: BLE001
            messagebox.showerror("Sheets", str(exc))
            return

        def work():
            svc.delete_pessoa(pessoa.id)
            return True

        def ok(_: bool) -> None:
            self._expanded_ids.discard(pessoa.id)
            self._load_admin_data()

        self._run_bg(work, ok, lambda e: messagebox.showerror("Erro", str(e)), "Removendo…")

    def _add_ano(self, pessoa: PessoaComReap, ano_txt: str) -> None:
        try:
            ano = int(ano_txt)
        except ValueError:
            messagebox.showerror("Ano", "Informe um ano válido.")
            return
        if ano < 2000 or ano > 2100:
            messagebox.showerror("Ano", "Informe um ano entre 2000 e 2100.")
            return
        try:
            svc = self._ensure_service()
        except Exception as exc:  # noqa: BLE001
            messagebox.showerror("Sheets", str(exc))
            return
        self._expanded_ids.add(pessoa.id)

        def work():
            svc.add_ano(pessoa.id, ano, nome=pessoa.nome)
            return True

        self._run_bg(work, lambda _: self._load_admin_data(), lambda e: messagebox.showerror("Erro", str(e)), f"Adicionando {ano}…")

    # ------------------------------------------------------------------
    # Lista + QR
    # ------------------------------------------------------------------
    def show_lista(self) -> None:
        navigate(self, "lista")

    def _render_lista(self) -> None:
        self._lista_mode = True
        wrap = page_wrap(self)

        top = tk.Frame(wrap, bg=COLORS["content"])
        top.pack(fill="x", pady=(0, 8))
        tk.Label(
            top, text="Lista pública de REAP", bg=COLORS["content"], fg=COLORS["primary"],
            font=(FONT_DISPLAY, 20, "bold"),
        ).pack(side="left")
        self._btn(top, "QR Consulta CPF", self._show_qr_consulta, kind="outline", padx=10, pady=6, font_size=9).pack(side="right", padx=(6, 0))
        self._btn(top, "QR Lista", self._show_qr_lista, kind="primary", padx=10, pady=6, font_size=9).pack(side="right")

        tk.Label(
            wrap,
            text="Clique no nome para ver os meses. O QR de Consulta por CPF é o ideal para imprimir na sede.",
            bg=COLORS["content"], fg=COLORS["muted"], font=(FONT_FAMILY, 10),
        ).pack(anchor="w", pady=(4, 10))

        self._scroll = ScrollableFrame(wrap, bg=COLORS["content"])
        self._scroll.pack(fill="both", expand=True)
        self.lista_frame = self._scroll.inner

        try:
            self._ensure_public_server()
        except Exception:
            pass

        try:
            svc = self._ensure_service()
        except Exception as exc:  # noqa: BLE001
            tk.Label(self.lista_frame, text=str(exc), bg=COLORS["content"], fg=COLORS["muted"]).pack(anchor="w")
            return

        def work():
            return svc.get_all_pessoas_com_reap()

        def ok(pessoas: List[PessoaComReap]) -> None:
            self._pessoas = pessoas
            self._render_lista_rows()

        self._run_bg(work, ok, lambda e: messagebox.showerror("Erro", str(e)), "Carregando lista…")

    def _render_lista_rows(self) -> None:
        if not hasattr(self, "lista_frame") or not self.lista_frame.winfo_exists():
            return
        for child in self.lista_frame.winfo_children():
            child.destroy()
        if not self._pessoas:
            tk.Label(self.lista_frame, text="Nenhum sócio cadastrado.", bg=COLORS["content"], fg=COLORS["muted"]).pack(anchor="w")
            return
        for p in self._pessoas:
            self._pessoa_row(self.lista_frame, p, editable=False, mask_cpf=True)

    def _show_qr_consulta(self) -> None:
        base = preferred_public_base()
        if not base:
            messagebox.showwarning(
                "Site público",
                "Cole esta URL em Configurações e clique Salvar:\n\n"
                "https://anmolock.github.io/sinapesc-casanova-reap\n\n"
                "(sem /consulta.html no final)",
            )
            navigate(self, "settings")
            return
        ensure_stable_qrs(base, force=False)
        self._qr_dialog(
            urls_for(base)["consulta"],
            title=f"{ORG_SHORT} — Consulta por CPF",
            subtitle="QR permanente do site público. O associado digita o CPF e vê só os próprios REAPs.",
            kind="consulta",
        )

    def _show_qr_lista(self) -> None:
        base = preferred_public_base()
        if not base:
            messagebox.showwarning(
                "Site público",
                "Configure a URL do site público em Configurações antes de gerar o QR.",
            )
            navigate(self, "settings")
            return
        ensure_stable_qrs(base, force=False)
        self._qr_dialog(
            urls_for(base)["lista"],
            title=f"{ORG_SHORT} — Lista pública",
            subtitle="Lista geral no site público. Mesmo QR enquanto a URL do site não mudar.",
            kind="lista",
        )

    def _show_qr_pessoa(self, pessoa: PessoaComReap) -> None:
        base = preferred_public_base()
        if not base:
            messagebox.showwarning(
                "Site público",
                "Configure a URL do site público em Configurações antes de gerar o QR.",
            )
            navigate(self, "settings")
            return
        ensure_stable_qrs(base, pessoas=[pessoa], force=False)
        self._qr_dialog(
            urls_for(base, pessoa)["pessoa"],
            title=f"{ORG_SHORT} — {pessoa.nome}",
            subtitle="Comprovante individual no site público · QR permanente.",
            kind="pessoa",
            person_id=pessoa.id,
        )

    def _qr_dialog(
        self,
        url: str,
        *,
        title: str,
        subtitle: str,
        kind: str = "lista",
        person_id: str = "",
    ) -> None:
        win = tk.Toplevel(self)
        win.title(title)
        win.configure(bg=COLORS["surface"])
        win.transient(self)
        win.grab_set()

        state = {"url": url}

        tk.Frame(win, bg=COLORS["gold"], height=3).pack(fill="x")
        head = tk.Frame(win, bg=COLORS["primary"], padx=16, pady=12)
        head.pack(fill="x")
        fish = load_fish(win, size=56)
        if fish is not None:
            win._fish = fish  # keep ref
            tk.Label(head, image=fish, bg=COLORS["primary"]).pack(side="right")
        tk.Label(head, text=title, bg=COLORS["primary"], fg=COLORS["foam"], font=(FONT_DISPLAY, 13, "bold")).pack(anchor="w")
        tk.Label(win, text=subtitle, bg=COLORS["surface"], fg=COLORS["muted"], font=(FONT_FAMILY, 9), wraplength=400).pack(padx=16, pady=(12, 0))
        qr_label = tk.Label(win, bg=COLORS["surface"])
        qr_label.pack(pady=12)
        url_lbl = tk.Label(win, text=url, bg=COLORS["surface"], fg=COLORS["accent"], font=(FONT_FAMILY, 8), wraplength=420)
        url_lbl.pack(padx=16)
        tk.Label(
            win,
            text=f"Arquivos permanentes em: {qr_dir()}",
            bg=COLORS["surface"],
            fg=COLORS["muted"],
            font=(FONT_FAMILY, 8),
            wraplength=420,
        ).pack(padx=16, pady=(4, 0))

        def render(u: str) -> None:
            state["url"] = u
            url_lbl.configure(text=u)
            try:
                poster = make_qr_image(u, title=title, subtitle=subtitle)
                photo = pil_to_tk(poster, max_size=(300, 340))
                self._qr_photo = photo
                qr_label.configure(image=photo)
            except Exception as exc:  # noqa: BLE001
                qr_label.configure(text=f"Falha ao gerar QR: {exc}", image="")

        render(url)

        def save() -> None:
            default = {
                "consulta": "sinapesc-consulta-cpf-qr.png",
                "lista": "sinapesc-lista-qr.png",
                "pessoa": f"sinapesc-pessoa-{person_id[:8] or 'socio'}-qr.png",
            }.get(kind, "sinapesc-qr.png")
            vault_map = {
                "consulta": path_for_consulta(),
                "lista": path_for_lista(),
                "pessoa": path_for_pessoa(person_id) if person_id else None,
            }
            suggested = vault_map.get(kind)
            path = filedialog.asksaveasfilename(
                parent=win,
                title="Salvar QR permanente",
                defaultextension=".png",
                filetypes=[("PNG", "*.png")],
                initialfile=default,
            )
            if not path:
                return
            if suggested and suggested.exists():
                from shutil import copyfile

                copyfile(suggested, path)
            else:
                save_qr_png(state["url"], path, title=title, subtitle=subtitle)
            messagebox.showinfo("QR", f"Salvo em:\n{path}\n\nEste QR permanece válido com a URL do site público.", parent=win)

        def copy_url() -> None:
            win.clipboard_clear()
            win.clipboard_append(state["url"])
            self.status.set("URL copiada.")

        btns = tk.Frame(win, bg=COLORS["surface"])
        btns.pack(pady=14)
        self._btn(btns, "Salvar PNG", save).pack(side="left", padx=5)
        self._btn(btns, "Copiar link", copy_url, kind="primary").pack(side="left", padx=5)
        self._btn(btns, "Fechar", win.destroy, kind="ghost").pack(side="left", padx=5)


def _asset(name: str) -> str:
    from pathlib import Path
    import sys

    if getattr(sys, "frozen", False):
        base = Path(sys._MEIPASS)  # type: ignore[attr-defined]
    else:
        base = Path(__file__).resolve().parent.parent
    return str(base / "assets" / name)
