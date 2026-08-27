"""Ponte Python ↔ JavaScript (pywebview) para o Sinapesc REAP."""

from __future__ import annotations

import base64
import json
import os
import subprocess
import threading
import webbrowser
from datetime import datetime
from io import BytesIO
from pathlib import Path
from typing import Any, Dict, List, Optional

from config import import_credentials_file, is_sheets_configured, load_config, save_config
from controle.auditoria import combina_busca
from controle.backup import backup_root, gravar_backup, listar_backups
from controle.calendario import meses_para_texto
from controle.defeso import FichaDefeso, entrada_confirmada_flag, endereco_completo, tem_parcela_preenchida
from controle.defeso_anexos import (
    anexos_mode,
    is_storage_quota_error,
    listar_anexos_local,
    pasta_anexos_root,
    salvar_anexo_local,
)
from controle.defeso_declaracao import (
    DEFAULT_FONTE,
    listar_fontes,
    normalize_fonte,
    preencher_pdf,
)
from controle.defeso_pacote import listar_opcoes_pacote, montar_pacote_pdf, normalize_selecao
from controle.pendencias import classificar
from controle.sync_planilhas import sync_municipios_bidirecional
from controle.defeso_relatorio import (
    itens_defeso_para_relatorio,
    montar_html_defeso,
    nome_arquivo_defeso_relatorio,
    salvar_html_defeso,
)
from controle.relatorio import itens_para_relatorio, montar_html, nome_arquivo_relatorio, salvar_html
from drive import DriveDefesoClient
from sheets import MESES, MESES_LABEL, MesKey, SheetsConfigError, SheetsService
from sheets.client import normalize_sheet_id
from sheets.defeso_service import DefesoService
from ui.formatters import display_nome, format_cpf, format_nome, only_digits, parse_lote_lines
from ui.public_link import ensure_site_qrs, urls_for
from ui.qr_vault import normalize_public_base, preferred_public_base, qr_dir
from ui.qrutil import make_qr_image
from ui.theme import APP_VERSION, ORG_FULL, ORG_SHORT
from webapp.serialize import err, ok, pessoa_to_dict

try:
    import webview
except ImportError:  # pragma: no cover
    webview = None  # type: ignore[assignment]


def _windows_browsers() -> List[Path]:
    """Caminhos absolutos do Edge/Chrome (não ficam no PATH na maioria dos PCs)."""
    import shutil

    local = os.environ.get("LOCALAPPDATA") or ""
    candidatos = [
        os.path.expandvars(r"%ProgramFiles(x86)%\Microsoft\Edge\Application\msedge.exe"),
        os.path.expandvars(r"%ProgramFiles%\Microsoft\Edge\Application\msedge.exe"),
        os.path.expandvars(r"%ProgramFiles%\Google\Chrome\Application\chrome.exe"),
        os.path.expandvars(r"%ProgramFiles(x86)%\Google\Chrome\Application\chrome.exe"),
        str(Path(local) / "Google" / "Chrome" / "Application" / "chrome.exe") if local else "",
        str(Path(local) / "Microsoft" / "Edge" / "Application" / "msedge.exe") if local else "",
        shutil.which("msedge") or "",
        shutil.which("chrome") or "",
        shutil.which("firefox") or "",
    ]
    out: List[Path] = []
    seen: set[str] = set()
    for raw in candidatos:
        if not raw:
            continue
        p = Path(raw)
        key = str(p).lower()
        if key in seen or not p.is_file():
            continue
        seen.add(key)
        out.append(p)
    return out


def _html_wrapper_pdf(pdf: Path) -> Path:
    """HTML ao lado do PDF — .html sempre abre no navegador (associação Windows)."""
    pdf = pdf.resolve()
    dest = pdf.with_name(pdf.stem + "-abrir.html")
    nome = (
        pdf.name.replace("&", "&amp;")
        .replace('"', "&quot;")
        .replace("<", "&lt;")
    )
    dest.write_text(
        f"""<!DOCTYPE html>
<html lang="pt-BR"><head>
<meta charset="utf-8">
<title>Sinapesc — {nome}</title>
<style>
  html,body{{margin:0;height:100%;overflow:hidden;background:#111}}
  embed{{border:0;width:100%;height:100vh;display:block}}
</style>
</head><body>
<embed src="{nome}" type="application/pdf" />
</body></html>
""",
        encoding="utf-8",
    )
    return dest


def _abrir_no_navegador(path: Path) -> None:
    """Abre PDF/HTML no navegador (Edge/Chrome). Nunca depende do Acrobat."""
    p = Path(path).resolve()
    if not p.exists():
        raise OSError(f"Arquivo não encontrado: {p}")

    # PDF → HTML wrapper (igual declaração antiga: startfile abre o navegador)
    alvo = _html_wrapper_pdf(p) if p.suffix.lower() == ".pdf" else p

    if os.name == "nt":
        flags = 0
        if hasattr(subprocess, "DETACHED_PROCESS"):
            flags |= subprocess.DETACHED_PROCESS  # type: ignore[attr-defined]
        if hasattr(subprocess, "CREATE_NEW_PROCESS_GROUP"):
            flags |= subprocess.CREATE_NEW_PROCESS_GROUP  # type: ignore[attr-defined]
        for exe in _windows_browsers():
            try:
                subprocess.Popen(
                    [str(exe), str(alvo)],
                    close_fds=True,
                    creationflags=flags,
                )
                return
            except OSError:
                continue
        # Associação .html = navegador (comportamento que já funcionava)
        os.startfile(str(alvo))  # type: ignore[attr-defined]
        return

    if not webbrowser.open(alvo.as_uri()):
        subprocess.Popen(["xdg-open", str(alvo)])


class SinapescApi:
    """Métodos expostos ao JS via window.pywebview.api."""

    def __init__(self) -> None:
        self._window: Any = None
        self._busy = False
        self._queue: List[tuple] = []
        self._lock = threading.Lock()
        self._logged_in = False
        self._admin_user = ""
        self._service: Optional[SheetsService] = None
        self._defeso_service: Optional[DefesoService] = None

    def bind_window(self, window: Any) -> None:
        self._window = window

    # ---- sync / bootstrap ------------------------------------------------

    def get_bootstrap(self) -> Dict[str, Any]:
        cfg = load_config()
        cred = cfg.get("credentials_json")
        cred_label = (
            f"JSON: {cred.get('client_email')}"
            if isinstance(cred, dict)
            else "Nenhuma credencial carregada."
        )
        site = normalize_public_base(cfg.get("public_site_url") or cfg.get("public_base_url") or "")
        return ok(
            {
                "version": APP_VERSION,
                "org_short": ORG_SHORT,
                "org_full": ORG_FULL,
                "configured": is_sheets_configured(cfg),
                "logged_in": self._logged_in,
                "admin_email": str(cfg.get("admin_email") or ""),
                "admin_user": self._admin_user,
                "spreadsheet_id": str(cfg.get("spreadsheet_id") or ""),
                "defeso_spreadsheet_id": str(cfg.get("defeso_spreadsheet_id") or ""),
                "defeso_anexos_dir": str(cfg.get("defeso_anexos_dir") or ""),
                "defeso_drive_folder_id": str(cfg.get("defeso_drive_folder_id") or ""),
                "defeso_declaracao_fonte": normalize_fonte(
                    str(cfg.get("defeso_declaracao_fonte") or DEFAULT_FONTE)
                ),
                "defeso_atalhos_telefones": _normalize_atalhos_lista(
                    cfg.get("defeso_atalhos_telefones")
                ),
                "defeso_atalhos_emails": _normalize_atalhos_lista(
                    cfg.get("defeso_atalhos_emails")
                ),
                "public_site_url": site,
                "ultimo_backup_em": str(cfg.get("ultimo_backup_em") or "Nunca"),
                "credentials_label": cred_label,
                "backup_root": str(backup_root()),
                "qr_dir": str(qr_dir()),
                "meses": MESES,
                "meses_label": MESES_LABEL,
            }
        )

    def login(self, email: str, password: str) -> Dict[str, Any]:
        cfg = load_config()
        if email.strip().lower() != str(cfg.get("admin_email", "")).lower():
            return err("E-mail ou senha incorretos.")
        if password != str(cfg.get("admin_password", "")):
            return err("E-mail ou senha incorretos.")
        if not is_sheets_configured(cfg):
            return err("Configure primeiro o Google Sheets.", redirect="settings")
        self._logged_in = True
        self._admin_user = email.strip()
        self._service = None
        self._defeso_service = None
        return ok(admin_user=self._admin_user)

    def logout(self) -> Dict[str, Any]:
        self._logged_in = False
        self._admin_user = ""
        self._service = None
        self._defeso_service = None
        return ok()

    def get_settings(self) -> Dict[str, Any]:
        cfg = load_config()
        cred = cfg.get("credentials_json")
        return ok(
            {
                "spreadsheet_id": str(cfg.get("spreadsheet_id") or ""),
                "defeso_spreadsheet_id": str(cfg.get("defeso_spreadsheet_id") or ""),
                "defeso_anexos_dir": str(cfg.get("defeso_anexos_dir") or ""),
                "defeso_drive_folder_id": str(cfg.get("defeso_drive_folder_id") or ""),
                "defeso_declaracao_fonte": normalize_fonte(
                    str(cfg.get("defeso_declaracao_fonte") or DEFAULT_FONTE)
                ),
                "defeso_fontes": listar_fontes(),
                "public_site_url": normalize_public_base(
                    cfg.get("public_site_url") or cfg.get("public_base_url") or ""
                ),
                "admin_email": str(cfg.get("admin_email") or ""),
                "admin_password": str(cfg.get("admin_password") or ""),
                "credentials_label": (
                    f"JSON: {cred.get('client_email')}"
                    if isinstance(cred, dict)
                    else "Nenhuma credencial carregada."
                ),
            }
        )

    def save_settings(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        cfg = load_config()
        if "spreadsheet_id" in payload:
            cfg["spreadsheet_id"] = normalize_sheet_id(str(payload.get("spreadsheet_id") or ""))
        if "defeso_spreadsheet_id" in payload:
            cfg["defeso_spreadsheet_id"] = normalize_sheet_id(
                str(payload.get("defeso_spreadsheet_id") or "")
            )
        if "defeso_anexos_dir" in payload:
            raw_dir = str(payload.get("defeso_anexos_dir") or "").strip().strip('"')
            if raw_dir:
                try:
                    pasta_anexos_root({**cfg, "defeso_anexos_dir": raw_dir})
                except ValueError as exc:
                    return err(str(exc))
            cfg["defeso_anexos_dir"] = raw_dir
        if "defeso_drive_folder_id" in payload:
            cfg["defeso_drive_folder_id"] = normalize_sheet_id(
                str(payload.get("defeso_drive_folder_id") or "")
            )
        if "defeso_declaracao_fonte" in payload:
            cfg["defeso_declaracao_fonte"] = normalize_fonte(
                str(payload.get("defeso_declaracao_fonte") or DEFAULT_FONTE)
            )
        if "public_site_url" in payload:
            base = normalize_public_base(str(payload.get("public_site_url") or ""))
            cfg["public_site_url"] = base
            cfg["public_base_url"] = base
        if "admin_email" in payload:
            cfg["admin_email"] = str(payload.get("admin_email") or "").strip()
        if "admin_password" in payload:
            cfg["admin_password"] = str(payload.get("admin_password") or "")
        save_config(cfg)
        self._service = None
        self._defeso_service = None
        self._sync_site_config_js(cfg.get("spreadsheet_id", ""))
        return ok()

    def import_credentials_json(self, raw_json: str) -> Dict[str, Any]:
        try:
            data = json.loads(raw_json)
        except json.JSONDecodeError:
            return err("JSON inválido.")
        if not isinstance(data, dict) or data.get("type") != "service_account":
            return err("Arquivo inválido. Use o JSON da Conta de Serviço do Google Cloud.")
        if "client_email" not in data or "private_key" not in data:
            return err("JSON incompleto: faltam client_email ou private_key.")
        cfg = load_config()
        cfg["credentials_json"] = data
        cfg["service_account_email"] = data.get("client_email", "")
        cfg["private_key"] = data.get("private_key", "")
        save_config(cfg)
        self._service = None
        return ok(credentials_label=f"JSON: {data.get('client_email')}")

    def test_connection(self) -> Dict[str, Any]:
        try:
            svc = self._ensure_service(require_login=False)
            n = len(svc.get_all_pessoas())
            return ok(count=n)
        except Exception as exc:  # noqa: BLE001
            return err(str(exc))

    # ---- async helpers ---------------------------------------------------

    def _dispatch(self, event: str, payload: Any) -> None:
        if not self._window:
            return
        body = json.dumps(payload, ensure_ascii=False)
        self._window.evaluate_js(f"window.AppEvents.dispatch({json.dumps(event)}, {body})")

    def _run_async(self, op: str, work, busy: str = "Aguarde…") -> Dict[str, Any]:
        job = (op, work, busy)
        with self._lock:
            if self._busy:
                self._queue.append(job)
                queued = True
            else:
                self._busy = True
                queued = False
        if queued:
            self._dispatch("status", {"msg": busy})
            return ok(pending=True, op=op, queued=True)
        self._start_job(job)
        return ok(pending=True, op=op)

    def _start_job(self, job: tuple) -> None:
        op, work, busy = job
        self._dispatch("status", {"msg": busy})

        def target() -> None:
            try:
                payload = ok(work())
            except Exception as exc:  # noqa: BLE001
                payload = err(str(exc))
            nxt = None
            with self._lock:
                if self._queue:
                    nxt = self._queue.pop(0)
                else:
                    self._busy = False
            # Libera "ocupado" ANTES de avisar o JS, senão o recarregamento
            # da lista é recusado e a tela só muda com Atualizar.
            self._dispatch(op, payload)
            if nxt:
                self._start_job(nxt)
            else:
                self._dispatch("status", {"msg": "Pronto."})

        threading.Thread(target=target, daemon=True).start()

    def _ensure_service(self, *, require_login: bool = True) -> SheetsService:
        if require_login and not self._logged_in:
            raise SheetsConfigError("Faça login como administrador.")
        cfg = load_config()
        if not is_sheets_configured(cfg):
            raise SheetsConfigError("Google Sheets ainda não configurado.")
        if self._service is None:
            self._service = SheetsService.from_config(cfg)
        actor = self._admin_user if self._logged_in else str(cfg.get("admin_email") or "")
        self._service.actor = actor
        return self._service

    def _ensure_defeso(self) -> DefesoService:
        if not self._logged_in:
            raise SheetsConfigError("Faça login como administrador.")
        cfg = load_config()
        if not is_sheets_configured(cfg):
            raise SheetsConfigError("Google Sheets ainda não configurado.")
        if self._defeso_service is None:
            self._defeso_service = DefesoService.from_config(cfg)
        return self._defeso_service

    def _sync_site_config_js(self, spreadsheet_id: str) -> None:
        sid = (spreadsheet_id or "").strip()
        if not sid:
            return
        from config import app_data_dir, exe_dir

        candidates = [
            Path(__file__).resolve().parents[2] / "site-publico" / "config.js",
            exe_dir().parent / "site-publico" / "config.js",
            exe_dir() / "site-publico" / "config.js",
            app_data_dir() / "site-publico" / "config.js",
        ]
        import re

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
                return
            except OSError:
                continue

    # ---- sócios ----------------------------------------------------------

    def load_pessoas(self) -> Dict[str, Any]:
        def work():
            svc = self._ensure_service(require_login=False)
            ultimo = _ultimo_toggle_map(svc)
            pessoas = svc.get_all_pessoas_com_reap()
            # Município / UF / telefone do Defeso quando REAP ainda não tem
            defeso_mun: Dict[str, str] = {}
            defeso_uf: Dict[str, str] = {}
            defeso_tel: Dict[str, str] = {}
            try:
                for f in self._ensure_defeso().listar():
                    cpf = only_digits(f.cpf)
                    if not cpf:
                        continue
                    if str(f.municipio or "").strip():
                        defeso_mun[cpf] = str(f.municipio).strip()
                    if str(f.uf or "").strip():
                        defeso_uf[cpf] = str(f.uf).strip().upper()[:2]
                    if str(getattr(f, "telefone_reap", "") or "").strip():
                        defeso_tel[cpf] = str(f.telefone_reap).strip()
                    elif str(f.telefone or "").strip():
                        defeso_tel[cpf] = str(f.telefone).strip()
            except Exception:
                pass
            out = []
            for p in pessoas:
                d = pessoa_to_dict(p, ultimo_toggle=ultimo.get(p.id))
                if not (d.get("municipio") or "").strip():
                    alt = defeso_mun.get(d.get("cpf_raw") or "")
                    if alt:
                        d["municipio"] = alt
                        d["municipio_origem"] = "defeso"
                if not (d.get("uf") or "").strip():
                    alt_u = defeso_uf.get(d.get("cpf_raw") or "")
                    if alt_u:
                        d["uf"] = alt_u
                        d["uf_origem"] = "defeso"
                if not (d.get("telefone") or "").strip():
                    alt_t = defeso_tel.get(d.get("cpf_raw") or "")
                    if alt_t:
                        d["telefone"] = alt_t
                        d["telefone_origem"] = "defeso"
                out.append(d)
            return out

        return self._run_async("pessoas", work, "Carregando sócios…")

    def save_pessoa(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        nome = format_nome(str(payload.get("nome") or ""))
        cpf = only_digits(str(payload.get("cpf") or ""))
        municipio = str(payload.get("municipio") or "").strip()
        telefone = str(payload.get("telefone") or payload.get("numero") or "").strip()
        person_id = str(payload.get("id") or "").strip()
        if not nome:
            return err("Informe o nome completo.")
        if len(cpf) != 11:
            return err("CPF deve conter 11 dígitos.")

        def work():
            svc = self._ensure_service()
            pid = ""
            if person_id:
                svc.update_pessoa(person_id, nome, cpf, municipio, telefone)
                pid = person_id
            else:
                pid = svc.add_pessoa(nome, cpf, municipio, telefone).id
            if municipio or telefone:
                try:
                    defeso = self._ensure_defeso()
                    ficha = defeso.por_cpf(cpf)
                    if ficha:
                        if municipio:
                            defeso.atualizar_municipio(ficha.id, municipio)
                        if telefone:
                            defeso.atualizar_telefone_reap(ficha.id, telefone)
                    else:
                        defeso.salvar(
                            {
                                "person_id": pid,
                                "nome": nome,
                                "cpf": cpf,
                                "municipio": municipio,
                                "telefone_reap": telefone,
                                "status": "rascunho",
                            }
                        )
                except Exception:
                    pass
            return pid

        return self._run_async("pessoa_saved", work, "Salvando…")

    def sync_planilhas_municipio(self) -> Dict[str, Any]:
        """Sincroniza município REAP ↔ Defeso (botão no módulo Sócios/REAP)."""

        def work():
            reap = self._ensure_service()
            defeso = self._ensure_defeso()
            return sync_municipios_bidirecional(reap, defeso)

        return self._run_async("sync_planilhas", work, "Sincronizando planilhas…")

    def delete_pessoa(self, person_id: str) -> Dict[str, Any]:
        if not person_id:
            return err("Sócio inválido.")

        def work():
            self._ensure_service().delete_pessoa(person_id)
            return True

        return self._run_async("pessoa_deleted", work, "Excluindo…")

    def toggle_mes(self, person_id: str, ano: int, mes: str, novo: bool) -> Dict[str, Any]:
        if mes not in MESES:
            return err("Mês inválido.")

        def work():
            svc = self._ensure_service()
            pessoa = svc.get_pessoa_com_reap(person_id)
            nome = pessoa.nome if pessoa else ""
            svc.toggle_mes(person_id, int(ano), mes, bool(novo), nome=nome)  # type: ignore[arg-type]
            return {"person_id": person_id, "ano": int(ano), "mes": mes, "on": bool(novo)}

        return self._run_async("mes_toggled", work, f"Atualizando {mes}/{ano}…")

    def add_ano(self, person_id: str, ano: int) -> Dict[str, Any]:
        def work():
            svc = self._ensure_service()
            pessoa = svc.get_pessoa_com_reap(person_id)
            nome = pessoa.nome if pessoa else ""
            svc.add_ano(person_id, int(ano), nome=nome)
            return True

        return self._run_async("ano_added", work, "Adicionando ano…")

    def save_lote(self, raw: str, ano: int, meses_on: List[str]) -> Dict[str, Any]:
        itens = parse_lote_lines(raw)
        if not itens:
            return err("Nenhuma linha válida (Nome + CPF).")

        def work():
            return self._ensure_service().add_pessoas_lote(
                itens,
                ano=int(ano),
                meses_on=meses_on,
            )

        return self._run_async("lote_saved", work, "Importando lote…")

    def save_lote_rows(self, rows: Any, ano: int, meses_on: List[str]) -> Dict[str, Any]:
        try:
            itens = _lote_itens_from_rows(rows)
        except ValueError as exc:
            return err(str(exc))
        if not itens:
            return err("Nenhuma linha válida (Nome + CPF).")
        try:
            ano_i = int(ano)
        except (TypeError, ValueError):
            ano_i = datetime.now().year

        def work():
            return self._ensure_service().add_pessoas_lote(
                itens,
                ano=ano_i,
                meses_on=meses_on or [],
            )

        return self._run_async("lote_saved", work, f"Importando lote ({len(itens)} sócios)…")

    def copiar_ano(
        self,
        ano_origem: int,
        ano_destino: int,
        person_ids: Optional[List[str]] = None,
    ) -> Dict[str, Any]:
        def work():
            return self._ensure_service().copiar_reap_ano(
                int(ano_origem),
                int(ano_destino),
                person_ids=person_ids,
            )

        return self._run_async("copia_ok", work, "Copiando ano…")

    def marcar_meses_em_massa(
        self,
        ano: int,
        meses_on: List[str],
        person_ids: Optional[List[str]] = None,
        substituir: bool = False,
    ) -> Dict[str, Any]:
        """Alias JS (nome igual ao SheetsService)."""
        return self.marcar_meses_massa(ano, meses_on, person_ids, substituir)

    def marcar_meses_massa(
        self,
        ano: int,
        meses_on: List[str],
        person_ids: Optional[List[str]] = None,
        substituir: bool = False,
    ) -> Dict[str, Any]:
        if not meses_on:
            return err("Escolha pelo menos um mês.")

        def work():
            svc = self._ensure_service()
            if person_ids:
                return svc.marcar_meses_em_massa(
                    ano=int(ano),
                    meses_on=meses_on,
                    person_ids=person_ids,
                    substituir=bool(substituir),
                )
            return svc.marcar_meses_em_massa(
                ano=int(ano),
                meses_on=meses_on,
                substituir=bool(substituir),
            )

        return self._run_async("massa_ok", work, "Marcando meses…")

    # ---- pendências ------------------------------------------------------

    def load_pendencias(self, ano: int) -> Dict[str, Any]:
        def work():
            svc = self._ensure_service()
            ultimo = _ultimo_toggle_map(svc)
            pessoas = svc.get_all_pessoas_com_reap()
            cal = svc.get_calendario(int(ano))
            pend, reg = classificar(pessoas, int(ano), cal)
            return {
                "ano": int(ano),
                "calendario": cal,
                "calendario_texto": meses_para_texto(cal),
                "pendentes": [_situacao_dict(s, ultimo.get(s.pessoa.id)) for s in pend],
                "regulares_count": len(reg),
            }

        return self._run_async("pendencias", work, "Carregando pendências…")

    def save_calendario(self, ano: int, meses: List[str]) -> Dict[str, Any]:
        def work():
            cal = self._ensure_service().set_calendario(meses, ano=int(ano))
            return {"calendario": cal, "texto": meses_para_texto(cal)}

        return self._run_async("calendario_saved", work, "Salvando calendário…")

    # ---- relatório -------------------------------------------------------

    def generate_relatorio(
        self, ano: int, modo: str, busca: str = "", localidade: str = ""
    ) -> Dict[str, Any]:
        def work():
            svc = self._ensure_service()
            pessoas = svc.get_all_pessoas_com_reap()
            cal = svc.get_calendario(int(ano))
            pend, reg = classificar(pessoas, int(ano), cal)
            todos = itens_para_relatorio(pend, reg)
            escolhidos = todos
            titulo = f"Relatório de conformidade REAP {ano}"
            nome_arq = nome_arquivo_relatorio(int(ano))
            q = busca.strip().lower()
            digits = only_digits(q)
            loc = str(localidade or "").strip()
            if modo == "individual":
                if not q:
                    raise ValueError("Digite o nome ou CPF do sócio para o comprovante individual.")
                match = [
                    s
                    for s in todos
                    if q in s.pessoa.nome.lower() or (digits and digits in s.pessoa.cpf)
                ]
                if not match:
                    raise ValueError("Nenhum sócio encontrado com essa busca.")
                if len(match) > 1:
                    nomes = ", ".join(s.pessoa.nome for s in match[:8])
                    raise ValueError(f"Vários sócios ({len(match)}). Refine a busca.\n{nomes}")
                escolhidos = match
                titulo = f"Comprovante de situação REAP {ano}"
                nome_arq = nome_arquivo_relatorio(int(ano), individual_nome=match[0].pessoa.nome)
            elif loc:
                loc_l = loc.lower()
                escolhidos = [
                    s
                    for s in todos
                    if str(getattr(s.pessoa, "municipio", "") or "").strip().lower() == loc_l
                ]
                if not escolhidos:
                    raise ValueError(f"Nenhum sócio na localidade «{loc}».")
                titulo = f"Relatório de conformidade REAP {ano} — {loc}"
                slug = "".join(ch if ch.isalnum() else "-" for ch in loc)[:30].strip("-")
                nome_arq = f"reap-{int(ano)}-{slug}-{datetime.now().strftime('%Y%m%d_%H%M')}.html"
            html_txt = montar_html(
                org_short=ORG_SHORT,
                org_full=ORG_FULL,
                ano=int(ano),
                calendario=cal,
                itens=escolhidos,
                titulo=titulo,
                individual=modo == "individual",
            )
            path = salvar_html(html_txt, nome_arquivo=nome_arq)
            svc.registrar_evento("relatorio", f"gerou {path.name}")
            return {"path": str(path), "html": html_txt, "total": len(escolhidos)}

        return self._run_async("relatorio", work, "Gerando relatório…")

    def generate_defeso_relatorio(
        self,
        localidade: str = "",
        somente_entrada: bool = False,
        somente_parcela: bool = False,
    ) -> Dict[str, Any]:
        """Relatório HTML Defeso: nome, CPF, tel REAP, endereço Defeso, parcelas."""

        def work():
            reap = self._ensure_service()
            defeso = self._ensure_defeso()
            telefones: Dict[str, str] = {}
            municipios: Dict[str, str] = {}
            nomes: Dict[str, str] = {}
            cpfs: List[str] = []
            for p in reap.get_all_pessoas():
                cpf = only_digits(p.cpf)
                if len(cpf) != 11:
                    continue
                cpfs.append(cpf)
                nomes[cpf] = str(p.nome or "").strip()
                tel = str(getattr(p, "telefone", "") or "").strip()
                mun = str(getattr(p, "municipio", "") or "").strip()
                if tel:
                    telefones[cpf] = tel
                if mun:
                    municipios[cpf] = mun
            fichas = defeso.listar()
            loc = str(localidade or "").strip()
            itens = itens_defeso_para_relatorio(
                fichas,
                telefones_reap=telefones,
                municipios_reap=municipios,
                nomes_reap=nomes,
                cpfs_reap=cpfs,
                localidade=loc,
                somente_entrada=bool(somente_entrada),
                somente_parcela=bool(somente_parcela),
            )
            if not itens:
                raise ValueError("Nenhuma ficha encontrada com os filtros escolhidos.")
            titulo = "Relatório Defeso Fácil"
            if loc:
                titulo += f" — {loc}"
            if somente_entrada:
                titulo += " · entrada confirmada"
            if somente_parcela:
                titulo += " · com parcela"
            html_txt = montar_html_defeso(
                org_short=ORG_SHORT,
                org_full=ORG_FULL,
                itens=itens,
                titulo=titulo,
                localidade=loc,
            )
            nome_arq = nome_arquivo_defeso_relatorio(localidade=loc)
            path = salvar_html_defeso(html_txt, nome_arquivo=nome_arq)
            reap.registrar_evento("relatorio_defeso", f"gerou {path.name}")
            return {"path": str(path), "html": html_txt, "total": len(itens)}

        return self._run_async("defeso_relatorio", work, "Gerando relatório Defeso…")

    # ---- backup / auditoria ----------------------------------------------

    def run_backup(self) -> Dict[str, Any]:
        def work():
            svc = self._ensure_service()
            dados = svc.exportar_abas()
            pasta = gravar_backup(
                pessoas_rows=dados["pessoas"],
                reap_rows=dados["reap"],
                spreadsheet_id=str(svc.client.spreadsheet_id),
            )
            svc.registrar_evento("backup", f"gerou backup local {pasta.name}")
            cfg = load_config()
            cfg["ultimo_backup_em"] = datetime.now().isoformat(timespec="seconds")
            cfg["backup_adiado_em"] = ""
            save_config(cfg)
            return {"pasta": str(pasta), "ultimo_backup_em": cfg["ultimo_backup_em"]}

        return self._run_async("backup", work, "Gerando backup CSV…")

    def list_backups(self) -> Dict[str, Any]:
        return ok(data=[p.name for p in listar_backups()[:12]])

    def load_auditoria(self) -> Dict[str, Any]:
        def work():
            eventos = self._ensure_service().listar_auditoria(400)
            return [
                {
                    "em": e.em,
                    "usuario": e.usuario,
                    "acao": e.acao,
                    "detalhe": e.detalhe,
                    "nome": e.nome,
                    "ano": e.ano,
                    "meses": e.meses,
                }
                for e in eventos
            ]

        return self._run_async("auditoria", work, "Carregando auditoria…")

    def export_auditoria(self) -> Dict[str, Any]:
        import csv

        def work():
            eventos = self._ensure_service().listar_auditoria(400)
            path = backup_root() / "auditoria-reap.csv"
            with path.open("w", encoding="utf-8-sig", newline="") as fh:
                writer = csv.writer(fh)
                writer.writerow(["em", "usuario", "acao", "detalhe", "nome", "ano", "meses"])
                for e in eventos:
                    writer.writerow([e.em, e.usuario, e.acao, e.detalhe, e.nome, e.ano, e.meses])
            return {"path": str(path), "count": len(eventos)}

        return self._run_async("auditoria_export", work, "Exportando auditoria…")

    def filter_auditoria_local(self, eventos: List[Dict[str, Any]], busca: str) -> Dict[str, Any]:
        from controle.auditoria import EventoAuditoria

        out = []
        for raw in eventos:
            evt = EventoAuditoria(
                id="",
                em=str(raw.get("em") or ""),
                usuario=str(raw.get("usuario") or ""),
                acao=str(raw.get("acao") or ""),
                detalhe=str(raw.get("detalhe") or ""),
                nome=str(raw.get("nome") or ""),
                ano=str(raw.get("ano") or ""),
                meses=str(raw.get("meses") or ""),
            )
            if combina_busca(evt, busca):
                out.append(raw)
        return ok(data=out)

    # ---- site público / QR -----------------------------------------------

    def generate_site_qrs(self, force: bool = True) -> Dict[str, Any]:
        base = preferred_public_base()
        if not base:
            return err("Configure a URL do site público em Configurações.")

        def work():
            cfg = load_config()
            pessoas = []
            try:
                pessoas = self._ensure_service().get_all_pessoas_com_reap()
            except Exception:
                pass
            resolved = ensure_site_qrs(pessoas=pessoas or None, force=force)
            return {"base": resolved, "qr_dir": str(qr_dir())}

        return self._run_async("qrs", work, "Gerando QRs do site público…")

    def qr_preview(self, kind: str, person_id: str = "") -> Dict[str, Any]:
        base = preferred_public_base()
        if not base:
            return err("Site público não configurado.")
        try:
            if kind == "consulta":
                url = urls_for(base)["consulta"]
                subtitle = "Consulta por CPF"
            elif kind == "lista":
                url = urls_for(base)["lista"]
                subtitle = "Lista pública"
            elif kind == "pessoa" and person_id:
                pessoa = self._ensure_service(require_login=False).get_pessoa_com_reap(person_id)
                if not pessoa:
                    return err("Sócio não encontrado.")
                url = urls_for(base, pessoa)["pessoa"]
                subtitle = display_nome(pessoa.nome)
            else:
                return err("Tipo de QR inválido.")
            img = make_qr_image(url, subtitle=subtitle)
            buf = BytesIO()
            img.save(buf, format="PNG")
            b64 = base64.b64encode(buf.getvalue()).decode("ascii")
            return ok(data={"url": url, "image": f"data:image/png;base64,{b64}"})
        except Exception as exc:  # noqa: BLE001
            return err(str(exc))

    def print_qr(self, kind: str, person_id: str = "") -> Dict[str, Any]:
        """Gera HTML local de impressão e abre no navegador padrão."""
        base = preferred_public_base()
        if not base:
            return err("Site público não configurado.")
        try:
            if kind == "consulta":
                url = urls_for(base)["consulta"]
                subtitle = "Consulta por CPF"
                slug = "consulta"
            elif kind == "lista":
                url = urls_for(base)["lista"]
                subtitle = "Lista pública"
                slug = "lista"
            elif kind == "pessoa" and person_id:
                pessoa = self._ensure_service(require_login=False).get_pessoa_com_reap(person_id)
                if not pessoa:
                    return err("Sócio não encontrado.")
                url = urls_for(base, pessoa)["pessoa"]
                subtitle = display_nome(pessoa.nome)
                slug = f"pessoa-{person_id[:8]}"
            else:
                return err("Tipo de QR inválido.")

            stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            out_dir = Path(qr_dir())
            out_dir.mkdir(parents=True, exist_ok=True)
            img_path = out_dir / f"qr-{slug}-{stamp}.png"
            html_path = out_dir / f"qr-{slug}-{stamp}.html"
            make_qr_image(url, subtitle=subtitle).save(img_path, format="PNG")
            html_txt = f"""<!DOCTYPE html>
<html lang="pt-BR"><head><meta charset="utf-8"><title>QR Sinapesc</title>
<style>
  body {{ font-family: Segoe UI, Arial, sans-serif; text-align: center; color: #0A2F52; margin: 20px; }}
  img.qr {{ max-width: 420px; margin: 12px 0; }}
  h1 {{ font-size: 18px; margin: 8px 0 4px; }}
</style></head><body onload="setTimeout(function(){{window.print();}},250)">
  <h1>SINAPESC</h1>
  <p>Sindicato Dos Aquicultores E Pescadores De Casa Nova</p>
  <img class="qr" src="{img_path.name}" alt="QR" />
</body></html>"""
            html_path.write_text(html_txt, encoding="utf-8")
            opened = self.open_path(str(html_path))
            if not opened.get("ok"):
                return opened
            return ok(data={"path": str(html_path), "image_path": str(img_path), "url": url})
        except Exception as exc:  # noqa: BLE001
            return err(str(exc))

    def open_path(self, path: str) -> Dict[str, Any]:
        p = Path(path)
        if not p.exists():
            return err("Caminho não encontrado.")
        try:
            # PDF/HTML: forçar navegador (igual relatório / declaração antiga).
            if p.is_file() and p.suffix.lower() in {".pdf", ".html", ".htm"}:
                _abrir_no_navegador(p)
            elif os.name == "nt":
                os.startfile(str(p))  # type: ignore[attr-defined]
            else:
                subprocess.Popen(["xdg-open", str(p)])
            return ok()
        except OSError as exc:
            return err(str(exc))

    def open_url(self, url: str) -> Dict[str, Any]:
        try:
            webbrowser.open(url)
            return ok()
        except Exception as exc:  # noqa: BLE001
            return err(str(exc))

    def pick_defeso_anexos_dir(self) -> Dict[str, Any]:
        """Abre diálogo para escolher pasta sincronizada (ex.: D:\\Meu Drive\\Sinapesc-Defeso)."""
        try:
            import tkinter as tk
            from tkinter import filedialog
        except ImportError as exc:  # pragma: no cover
            return err(f"Seletor de pasta indisponível: {exc}")

        cfg = load_config()
        initial = str(cfg.get("defeso_anexos_dir") or "").strip()
        root = tk.Tk()
        root.withdraw()
        try:
            root.attributes("-topmost", True)
        except tk.TclError:
            pass
        try:
            chosen = filedialog.askdirectory(
                parent=root,
                title="Pasta Defeso — Google Drive no PC (sincronizada)",
                initialdir=initial or None,
                mustexist=True,
            )
        finally:
            root.destroy()

        if not chosen:
            return err("Nenhuma pasta selecionada.")
        path = str(Path(chosen).expanduser().resolve())
        try:
            pasta_anexos_root({**cfg, "defeso_anexos_dir": path})
        except ValueError as exc:
            return err(str(exc))
        cfg["defeso_anexos_dir"] = path
        save_config(cfg)
        return ok(defeso_anexos_dir=path, anexos_mode="sync")

    def open_defeso_anexos_dir(self) -> Dict[str, Any]:
        try:
            root = pasta_anexos_root()
        except ValueError as exc:
            return err(str(exc))
        return self.open_path(str(root))

    # ---- Defeso Fácil ----------------------------------------------------

    def load_defeso_lista(self) -> Dict[str, Any]:
        def work():
            # 1) REAP (CPFs) — obrigatório e isolado
            try:
                reap = self._ensure_service()
                pessoas = reap.get_all_pessoas()
            except Exception as exc:  # noqa: BLE001
                raise ValueError(
                    "Não foi possível ler a planilha REAP (sócios/CPF). "
                    f"Confira spreadsheet_id e o compartilhamento com o client_email. Detalhe: {exc}"
                ) from exc

            # 2) Planilha Defeso — opcional para montar a lista (não bloqueia os CPFs)
            fichas: Dict[str, Any] = {}
            defeso_aviso = ""
            try:
                defeso = self._ensure_defeso()
                fichas = {only_digits(f.cpf): f for f in defeso.listar() if only_digits(f.cpf)}
            except Exception as exc:  # noqa: BLE001
                defeso_aviso = (
                    "Lista de CPFs do REAP ok, mas a planilha Defeso falhou. "
                    "Compartilhe a planilha Defeso com o client_email (Editor) e confira "
                    f"defeso_spreadsheet_id. Detalhe: {exc}"
                )

            rows = []
            for p in pessoas:
                cpf = only_digits(p.cpf)
                f = fichas.pop(cpf, None) if fichas else None
                p_mun = str(getattr(p, "municipio", "") or "").strip()
                p_tel = str(getattr(p, "telefone", "") or "").strip()
                f_mun = str(f.municipio).strip() if f else ""
                # Lista/relatório: município e telefone do REAP têm prioridade
                municipio = p_mun or f_mun
                tel_reap = p_tel or (str(f.telefone_reap).strip() if f else "")
                entrada = entrada_confirmada_flag(f) if f else False
                tem_parc = tem_parcela_preenchida(f) if f else False
                rows.append(
                    {
                        "person_id": p.id,
                        "nome": p.nome,
                        "nome_display": display_nome(p.nome),
                        "cpf": cpf,
                        "cpf_formatado": format_cpf(cpf),
                        "tem_ficha": bool(f),
                        "ficha_id": f.id if f else "",
                        "municipio": municipio,
                        "municipio_reap": p_mun,
                        "municipio_defeso": f_mun,
                        "telefone_reap": tel_reap,
                        "status": f.status if f else "sem_ficha",
                        "confirmada": entrada,
                        "entrada_confirmada": entrada,
                        "tem_parcela": tem_parc,
                        "parcelas_recebidas": f.parcelas_recebidas if f else "",
                        "endereco_completo": endereco_completo(f) if f else "",
                        "atualizado_em": f.atualizado_em if f else "",
                        "tem_identidade": bool(f and f.tem_identidade),
                        "tem_carteira_pesca": bool(f and f.tem_carteira_pesca),
                        "tem_caf": bool(f and f.tem_caf),
                    }
                )
            # Não lista fichas órfãs (existem só no Defeso, sem CPF no REAP) —
            # evita "sócio fantasma" no relatório / tela.
            rows.sort(key=lambda r: str(r.get("nome_display") or "").lower())
            localidades = sorted(
                {str(r.get("municipio") or "").strip() for r in rows if str(r.get("municipio") or "").strip()},
                key=lambda s: s.lower(),
            )
            cfg = load_config()
            mode = anexos_mode(cfg)
            return {
                "itens": rows,
                "localidades": localidades,
                "defeso_spreadsheet_id": normalize_sheet_id(
                    str(cfg.get("defeso_spreadsheet_id") or "")
                ),
                "defeso_anexos_dir": str(cfg.get("defeso_anexos_dir") or ""),
                "anexos_mode": mode,
                "drive_ok": mode in ("sync", "drive"),
                "aviso": defeso_aviso,
            }

        return self._run_async("defeso_lista", work, "Carregando Defeso Fácil…")

    def load_defeso_ficha(self, person_id: str = "", cpf: str = "", ficha_id: str = "") -> Dict[str, Any]:
        def work():
            reap = self._ensure_service()
            defeso = self._ensure_defeso()
            ficha = defeso.por_id(ficha_id) if ficha_id else None
            cpf_d = only_digits(cpf)
            if ficha is None and cpf_d:
                ficha = defeso.por_cpf(cpf_d)
            pessoa = None
            if person_id:
                for p in reap.get_all_pessoas():
                    if p.id == person_id:
                        pessoa = p
                        break
            if pessoa is None and cpf_d:
                for p in reap.get_all_pessoas():
                    if only_digits(p.cpf) == cpf_d:
                        pessoa = p
                        break
            if ficha is None and pessoa is None:
                raise ValueError("Sócio/ficha não encontrado.")

            if ficha:
                base = ficha.to_dict()
            else:
                assert pessoa is not None
                base = {
                    "id": "",
                    "person_id": pessoa.id,
                    "nome": pessoa.nome,
                    "nome_display": display_nome(pessoa.nome),
                    "cpf": only_digits(pessoa.cpf),
                    "cpf_formatado": format_cpf(pessoa.cpf),
                    "rg": "",
                    "nacionalidade": "Brasileira",
                    "profissao": "Pescador profissional",
                    "cep": "",
                    "endereco": "",
                    "numero": "",
                    "bairro": "",
                    "municipio": "",
                    "uf": "",
                    "telefone": "",
                    "email": "",
                    "status": "rascunho",
                    "tem_identidade": "",
                    "tem_carteira_pesca": "",
                    "tem_caf": "",
                    "atualizado_em": "",
                    "criado_em": "",
                    "tem_ficha": False,
                    "telefone_reap": "",
                    "parcelas_recebidas": "",
                    "entrada_confirmada": "",
                }
            if pessoa:
                base["person_id"] = pessoa.id
                if not base.get("nome"):
                    base["nome"] = pessoa.nome
                base["nome_display"] = display_nome(str(base.get("nome") or pessoa.nome))
                base["cpf"] = only_digits(pessoa.cpf)
                base["cpf_formatado"] = format_cpf(pessoa.cpf)
                p_mun = str(getattr(pessoa, "municipio", "") or "").strip()
                # Município na ficha: prioriza REAP (mesmo do relatório)
                if p_mun:
                    base["municipio"] = p_mun
                    base["municipio_origem"] = "reap"
                elif str(base.get("municipio") or "").strip():
                    base["municipio_origem"] = "defeso"
                p_tel = str(getattr(pessoa, "telefone", "") or "").strip()
                if p_tel:
                    base["telefone_reap"] = p_tel
                elif not str(base.get("telefone_reap") or "").strip():
                    base["telefone_reap"] = ""
            base["entrada_confirmada"] = bool(
                entrada_confirmada_flag(ficha) if ficha else False
            )
            # Parcelas como lista de 4 datas para a UI
            try:
                from controle.defeso import parse_parcelas

                base["parcelas"] = parse_parcelas(str(base.get("parcelas_recebidas") or ""))
            except Exception:
                base["parcelas"] = ["", "", "", ""]

            anexos: List[Dict[str, str]] = []
            cfg = load_config()
            mode = anexos_mode(cfg)
            # Sempre lista anexos da pasta configurada (sync ou AppData)
            try:
                anexos.extend(listar_anexos_local(str(base["cpf"]), cfg))
            except Exception:
                pass
            # API Drive só se não houver pasta sync (evita 403 e duplicata)
            if mode == "drive":
                try:
                    anexos.extend(
                        DriveDefesoClient.from_config(cfg).listar_anexos(str(base["cpf"]))
                    )
                except Exception:
                    pass
            # dedupe by name (pasta local/sync primeiro)
            seen = set()
            uniq = []
            for a in anexos:
                key = str(a.get("name") or "")
                if key in seen:
                    continue
                seen.add(key)
                uniq.append(a)
            base["anexos"] = uniq
            base["anexos_mode"] = mode
            base["drive_ok"] = mode in ("sync", "drive")
            base["defeso_anexos_dir"] = str(cfg.get("defeso_anexos_dir") or "")
            try:
                base["anexos_local_root"] = str(pasta_anexos_root(cfg))
            except ValueError:
                base["anexos_local_root"] = ""
            return base

        return self._run_async("defeso_ficha", work, "Abrindo ficha Defeso…")

    def save_defeso_ficha(self, payload: Any = None) -> Dict[str, Any]:
        # pywebview: o objeto JS só existe na thread da API — copiar ANTES do async
        try:
            data = _prepare_defeso_payload(payload)
        except ValueError as exc:
            return err(str(exc))

        def work():
            local = dict(data)
            cpf = only_digits(str(local.get("cpf") or ""))
            pid = str(local.get("person_id") or "").strip()
            if not str(local.get("telefone_reap") or "").strip():
                try:
                    for p in self._ensure_service().get_all_pessoas():
                        if (pid and p.id == pid) or only_digits(p.cpf) == cpf:
                            tel = str(getattr(p, "telefone", "") or "").strip()
                            mun = str(getattr(p, "municipio", "") or "").strip()
                            if tel:
                                local["telefone_reap"] = tel
                            if mun and not str(local.get("municipio") or "").strip():
                                local["municipio"] = mun
                            break
                except Exception:
                    pass

            ficha = self._ensure_defeso().salvar(local)
            mun = str(ficha.municipio or "").strip()
            pid2 = str(ficha.person_id or local.get("person_id") or "").strip()
            if mun and pid2:
                try:
                    self._ensure_service().update_pessoa_municipio(pid2, mun)
                except Exception:
                    pass
            d = ficha.to_dict()
            d["entrada_confirmada"] = entrada_confirmada_flag(ficha)
            from controle.defeso import parse_parcelas

            d["parcelas"] = parse_parcelas(ficha.parcelas_recebidas or "")
            return d

        return self._run_async("defeso_saved", work, "Salvando ficha Defeso…")

    def print_defeso_declaracao(
        self,
        ficha_id: str = "",
        payload: Any = None,
        fonte_id: str = "",
    ) -> Dict[str, Any]:
        data = _prepare_defeso_payload(payload) if payload not in (None, "", {}) else {}
        fid = str(ficha_id or data.get("id") or "").strip()
        fonte_arg = str(fonte_id or "").strip()

        def work():
            defeso = self._ensure_defeso()
            if data:
                local = dict(data)
                if fid and not local.get("id"):
                    local["id"] = fid
                ficha = defeso.salvar(local)
            else:
                ficha = defeso.por_id(fid) if fid else None
            if ficha is None:
                raise ValueError("Salve a ficha antes de imprimir.")

            cfg = load_config()
            raw = fonte_arg or str(cfg.get("defeso_declaracao_fonte") or DEFAULT_FONTE)
            fonte = normalize_fonte(raw)
            path = preencher_pdf(ficha, fonte_id=fonte, size=0.0)
            try:
                _abrir_no_navegador(path)
            except OSError as exc:
                raise ValueError(f"Não foi possível abrir a declaração: {exc}") from exc
            return {"path": str(path), "ficha_id": ficha.id, "fonte": fonte}

        return self._run_async("defeso_print", work, "Gerando declaração…")

    def print_defeso_pacote(
        self,
        ficha_id: str = "",
        payload: Any = None,
        itens: Optional[Any] = None,
        fonte_id: str = "",
    ) -> Dict[str, Any]:
        """Junta declaração + anexos escolhidos num único PDF e abre."""
        data = _prepare_defeso_payload(payload) if payload not in (None, "", {}) else {}
        fid = str(ficha_id or data.get("id") or "").strip()
        fonte_arg = str(fonte_id or "").strip()
        if isinstance(itens, str):
            raw_itens = [x.strip() for x in itens.split(",") if x.strip()]
        elif isinstance(itens, list):
            raw_itens = [str(x).strip() for x in itens if str(x).strip()]
        else:
            raw_itens = normalize_selecao(None)

        def work():
            defeso = self._ensure_defeso()
            if data:
                local = dict(data)
                if fid and not local.get("id"):
                    local["id"] = fid
                ficha = defeso.salvar(local)
            else:
                ficha = defeso.por_id(fid) if fid else None
            if ficha is None:
                raise ValueError("Salve a ficha antes de montar o pacote.")

            cfg = load_config()
            fonte = fonte_arg or str(cfg.get("defeso_declaracao_fonte") or DEFAULT_FONTE)
            result = montar_pacote_pdf(
                ficha, itens=raw_itens, fonte_id=fonte, cfg=cfg
            )
            path = Path(result["path"])
            try:
                _abrir_no_navegador(path)
            except OSError as exc:
                raise ValueError(f"Não foi possível abrir o pacote PDF: {exc}") from exc
            result["ficha_id"] = ficha.id
            return result

        return self._run_async("defeso_pacote", work, "Montando pacote PDF…")

    def get_defeso_pacote_opcoes(self) -> Dict[str, Any]:
        return ok({"itens": listar_opcoes_pacote()})

    def get_defeso_fontes(self) -> Dict[str, Any]:
        cfg = load_config()
        return ok(
            {
                "fonte": normalize_fonte(
                    str(cfg.get("defeso_declaracao_fonte") or DEFAULT_FONTE)
                ),
                "fontes": listar_fontes(),
            }
        )

    def set_defeso_fonte(self, fonte_id: str = "") -> Dict[str, Any]:
        cfg = load_config()
        fonte = normalize_fonte(fonte_id)
        from controle.defeso_declaracao import FONTES, _resolve_font_file

        meta = FONTES.get(fonte) or {}
        if not meta.get("pdf_font") and _resolve_font_file(fonte) is None:
            return err(f"Fonte '{fonte}' indisponível neste EXE.")
        cfg["defeso_declaracao_fonte"] = fonte
        save_config(cfg)
        return ok(fonte=fonte, fontes=listar_fontes())

    def get_defeso_atalhos_contato(self) -> Dict[str, Any]:
        cfg = load_config()
        return ok(
            {
                "telefones": _normalize_atalhos_lista(cfg.get("defeso_atalhos_telefones")),
                "emails": _normalize_atalhos_lista(cfg.get("defeso_atalhos_emails")),
            }
        )

    def set_defeso_atalhos_contato(
        self, telefones: Any = None, emails: Any = None
    ) -> Dict[str, Any]:
        """Grava até 3 telefones e 3 e-mails rápidos para a declaração Defeso."""
        cfg = load_config()
        tels = _normalize_atalhos_lista(telefones)
        mails = _normalize_atalhos_lista(emails)
        cfg["defeso_atalhos_telefones"] = tels
        cfg["defeso_atalhos_emails"] = mails
        save_config(cfg)
        return ok(telefones=tels, emails=mails)

    def upload_defeso_anexo(
        self,
        ficha_id: str,
        kind: str,
        filename: str,
        data_b64: str,
        mime: str = "",
    ) -> Dict[str, Any]:
        def work():
            cfg = load_config()
            defeso = self._ensure_defeso()
            ficha = defeso.por_id(ficha_id)
            if not ficha:
                raise ValueError("Salve a ficha antes de anexar documentos.")

            mode = anexos_mode(cfg)
            aviso = ""
            up: Dict[str, Any]

            # Preferência: pasta sincronizada (Google Drive no PC) — usa a cota do usuário.
            if mode == "sync":
                up = salvar_anexo_local(
                    cpf=ficha.cpf,
                    kind=kind,
                    filename=filename,
                    data_b64=data_b64,
                    mime=mime,
                    cfg=cfg,
                )
                aviso = (
                    f"Anexo gravado em:\n{up.get('path')}\n"
                    "O Google Drive no PC sobe para a nuvem (sua cota)."
                )
            elif mode == "drive":
                # Conta de serviço NÃO tem cota no "Meu Drive".
                # Tentamos Drive API; se der storageQuotaExceeded, salvamos local.
                try:
                    drive = DriveDefesoClient.from_config(cfg)
                    up = drive.upload_base64(
                        cpf=ficha.cpf,
                        kind=kind,
                        filename=filename,
                        data_b64=data_b64,
                        mime=mime,
                    )
                    up["where"] = "drive"
                except Exception as exc:  # noqa: BLE001
                    up = salvar_anexo_local(
                        cpf=ficha.cpf,
                        kind=kind,
                        filename=filename,
                        data_b64=data_b64,
                        mime=mime,
                        cfg=cfg,
                    )
                    if is_storage_quota_error(exc):
                        aviso = (
                            "O Google bloqueou o upload pela API (conta de serviço sem cota). "
                            "Arquivo salvo na pasta local. "
                            "Melhor: em Configurações, escolha a pasta do Google Drive no PC "
                            "(ex.: D:\\Meu Drive\\Sinapesc-Defeso)."
                        )
                    else:
                        aviso = f"Drive falhou ({exc}). Anexo guardado localmente."
            else:
                up = salvar_anexo_local(
                    cpf=ficha.cpf,
                    kind=kind,
                    filename=filename,
                    data_b64=data_b64,
                    mime=mime,
                    cfg=cfg,
                )
                aviso = (
                    "Anexo salvo na pasta local do EXE. "
                    "Em Configurações → escolha a pasta do Google Drive (D:) para sincronizar."
                )

            defeso.marcar_anexo(ficha.id, kind, True)
            up["aviso"] = aviso
            up["anexos_mode"] = mode
            return up

        return self._run_async("defeso_anexo", work, "Enviando anexo…")

    def quit_app(self) -> Dict[str, Any]:
        if webview:
            webview.destroy_window()
        return ok()


def _normalize_atalhos_lista(raw: Any) -> List[str]:
    """Até 3 strings não vazias (telefone/e-mail rápidos)."""
    if isinstance(raw, str):
        text = raw.strip()
        if text.startswith("["):
            try:
                raw = json.loads(text)
            except json.JSONDecodeError:
                raw = [x.strip() for x in text.split(",") if x.strip()]
        else:
            raw = [x.strip() for x in text.split(",") if x.strip()]
    if not isinstance(raw, (list, tuple)):
        raw = []
    out: List[str] = []
    for item in raw:
        s = str(item or "").strip()
        if s:
            out.append(s)
        if len(out) >= 3:
            break
    while len(out) < 3:
        out.append("")
    return out[:3]


def _js_payload_to_dict(payload: Any) -> Dict[str, Any]:
    """
    Converte o objeto vindo do pywebview em dict Python puro.

    Objetos JS da ponte NÃO podem ser lidos depois, nem em outra thread —
    por isso copiamos tudo na chamada da API (thread principal).
    """
    if payload is None or payload == "":
        return {}
    if isinstance(payload, str):
        text = payload.strip()
        if not text:
            return {}
        try:
            payload = json.loads(text)
        except json.JSONDecodeError as exc:
            raise ValueError("Dados da ficha inválidos (JSON).") from exc
    if not isinstance(payload, dict):
        # JSObject / mapeamento: tenta keys()
        try:
            keys = list(payload.keys())  # type: ignore[attr-defined]
        except Exception as exc:
            raise ValueError("Dados da ficha inválidos.") from exc
        out: Dict[str, Any] = {}
        for k in keys:
            out[str(k)] = _js_value_plain(payload[k])
        return out
    return {str(k): _js_value_plain(v) for k, v in payload.items()}


def _prepare_defeso_payload(payload: Any) -> Dict[str, Any]:
    """Dict puro + normaliza lista de parcelas → parcelas_recebidas."""
    from controle.defeso import format_parcelas

    data = _js_payload_to_dict(payload)
    raw_parc = data.get("parcelas")
    if isinstance(raw_parc, list):
        data["parcelas_recebidas"] = format_parcelas(raw_parc)
    elif not str(data.get("parcelas_recebidas") or "").strip() and raw_parc:
        data["parcelas_recebidas"] = str(raw_parc)
    return data


def _js_value_plain(value: Any) -> Any:
    if value is None or isinstance(value, (bool, int, float, str)):
        return value
    if isinstance(value, list):
        return [_js_value_plain(v) for v in value]
    if isinstance(value, tuple):
        return [_js_value_plain(v) for v in value]
    if isinstance(value, dict):
        return {str(k): _js_value_plain(v) for k, v in value.items()}
    # JSObject array-like
    try:
        if hasattr(value, "keys"):
            return {str(k): _js_value_plain(value[k]) for k in list(value.keys())}
    except Exception:
        pass
    try:
        return [_js_value_plain(v) for v in list(value)]
    except Exception:
        return str(value)


def _lote_itens_from_rows(rows: Any) -> List[tuple]:
    """Aceita lista de dicts OU JSON string (ponte JS do pywebview).
    Retorna [(nome, cpf, municipio, telefone), ...].
    """
    if isinstance(rows, str):
        text = rows.strip()
        if not text:
            return []
        try:
            rows = json.loads(text)
        except json.JSONDecodeError as exc:
            raise ValueError("Lista do lote inválida.") from exc
    itens: List[tuple] = []
    for row in rows or []:
        if isinstance(row, (list, tuple)) and len(row) >= 2:
            nome = str(row[0] or "").strip()
            cpf = only_digits(str(row[1] or ""))
            mun = str(row[2] if len(row) > 2 else "").strip()
            tel = str(row[3] if len(row) > 3 else "").strip()
        elif isinstance(row, dict):
            nome = str(row.get("nome") or "").strip()
            cpf = only_digits(str(row.get("cpf") or ""))
            mun = str(row.get("municipio") or "").strip()
            tel = str(row.get("telefone") or row.get("numero") or "").strip()
        else:
            continue
        if nome or cpf:
            itens.append((nome, cpf, mun, tel))
    return itens


AUDIT_ULTIMO_LIMITE = 2000


def _ultimo_toggle_map(svc: SheetsService) -> Dict[str, Dict[str, str]]:
    """Última marca/desmarca de mês por sócio — lido da aba Auditoria (visível a todos)."""
    try:
        from controle.auditoria import ultimo_toggle_por_pessoa

        return ultimo_toggle_por_pessoa(svc.listar_auditoria(AUDIT_ULTIMO_LIMITE))
    except Exception:
        return {}


def _situacao_dict(item, ultimo_toggle: Optional[Dict[str, str]] = None) -> Dict[str, Any]:
    p = item.pessoa
    out: Dict[str, Any] = {
        "person_id": p.id,
        "nome": p.nome,
        "nome_display": display_nome(p.nome),
        "cpf": format_cpf(p.cpf),
        "faltando": list(item.faltando),
        "regular": item.regular,
        "rotulo": item.rotulo_faltando,
        "tem_ano": item.tem_ano,
        "ano": item.ano,
    }
    if ultimo_toggle:
        out["ultimo_toggle_em"] = ultimo_toggle.get("em") or ""
        out["ultimo_toggle_label"] = ultimo_toggle.get("label") or ""
    else:
        out["ultimo_toggle_em"] = ""
        out["ultimo_toggle_label"] = ""
    return out
