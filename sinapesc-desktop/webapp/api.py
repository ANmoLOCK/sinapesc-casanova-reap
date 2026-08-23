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
            # Município / telefone do Defeso quando REAP ainda não tem
            defeso_mun: Dict[str, str] = {}
            defeso_tel: Dict[str, str] = {}
            try:
                for f in self._ensure_defeso().listar():
                    cpf = only_digits(f.cpf)
                    if not cpf:
                        continue
                    if str(f.municipio or "").strip():
                        defeso_mun[cpf] = str(f.municipio).strip()
                    if str(f.telefone or "").strip():
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
            if person_id:
                svc.update_pessoa(person_id, nome, cpf, municipio, telefone)
                return person_id
            return svc.add_pessoa(nome, cpf, municipio, telefone).id

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

    def generate_relatorio(self, ano: int, modo: str, busca: str = "") -> Dict[str, Any]:
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
            return {"path": str(path), "html": html_txt}

        return self._run_async("relatorio", work, "Gerando relatório…")

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
            if os.name == "nt":
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
                f_mun = str(f.municipio).strip() if f else ""
                municipio = f_mun or p_mun
                confirmada = bool(
                    f
                    and str(f.status or "").strip().lower() in ("salvo", "confirmado", "confirmada")
                )
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
                        "status": f.status if f else "sem_ficha",
                        "confirmada": confirmada,
                        "atualizado_em": f.atualizado_em if f else "",
                        "tem_identidade": bool(f and f.tem_identidade),
                        "tem_carteira_pesca": bool(f and f.tem_carteira_pesca),
                        "tem_caf": bool(f and f.tem_caf),
                    }
                )
            for f in fichas.values():
                f_mun = str(f.municipio or "").strip()
                confirmada = str(f.status or "").strip().lower() in (
                    "salvo",
                    "confirmado",
                    "confirmada",
                )
                rows.append(
                    {
                        "person_id": f.person_id,
                        "nome": f.nome,
                        "nome_display": display_nome(f.nome),
                        "cpf": only_digits(f.cpf),
                        "cpf_formatado": format_cpf(f.cpf),
                        "tem_ficha": True,
                        "ficha_id": f.id,
                        "municipio": f_mun,
                        "municipio_reap": "",
                        "municipio_defeso": f_mun,
                        "status": f.status or "rascunho",
                        "confirmada": confirmada,
                        "atualizado_em": f.atualizado_em,
                        "tem_identidade": bool(f.tem_identidade),
                        "tem_carteira_pesca": bool(f.tem_carteira_pesca),
                        "tem_caf": bool(f.tem_caf),
                    }
                )
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
                }
            if pessoa:
                base["person_id"] = pessoa.id
                if not base.get("nome"):
                    base["nome"] = pessoa.nome
                base["nome_display"] = display_nome(str(base.get("nome") or pessoa.nome))
                base["cpf"] = only_digits(pessoa.cpf)
                base["cpf_formatado"] = format_cpf(pessoa.cpf)
                p_mun = str(getattr(pessoa, "municipio", "") or "").strip()
                f_mun = str(base.get("municipio") or "").strip()
                if not f_mun and p_mun:
                    base["municipio"] = p_mun
                    base["municipio_origem"] = "reap"
                elif f_mun and not p_mun:
                    base["municipio_origem"] = "defeso"
                p_tel = str(getattr(pessoa, "telefone", "") or "").strip()
                f_tel = str(base.get("telefone") or "").strip()
                if not f_tel and p_tel:
                    base["telefone"] = p_tel
                    base["telefone_origem"] = "reap"

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

    def save_defeso_ficha(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        def work():
            if not isinstance(payload, dict):
                raise ValueError("Dados inválidos.")
            ficha = self._ensure_defeso().salvar(payload)
            mun = str(ficha.municipio or "").strip()
            pid = str(ficha.person_id or payload.get("person_id") or "").strip()
            if mun and pid:
                try:
                    self._ensure_service().update_pessoa_municipio(pid, mun)
                except Exception:
                    pass
            return ficha.to_dict()

        return self._run_async("defeso_saved", work, "Salvando ficha Defeso…")

    def print_defeso_declaracao(
        self,
        ficha_id: str = "",
        payload: Optional[Dict[str, Any]] = None,
        fonte_id: str = "",
    ) -> Dict[str, Any]:
        def work():
            defeso = self._ensure_defeso()
            ficha = defeso.por_id(ficha_id) if ficha_id else None
            if ficha is None and isinstance(payload, dict) and payload:
                ficha = defeso.salvar(payload)
            if ficha is None:
                raise ValueError("Salve a ficha antes de imprimir.")

            cfg = load_config()
            # Preferência: fonte passada pela UI; senão a salva no config
            raw = (fonte_id or "").strip() or str(
                cfg.get("defeso_declaracao_fonte") or DEFAULT_FONTE
            )
            fonte = normalize_fonte(raw)
            # Sempre preenche o PDF oficial do MTE (texto azul por cima do modelo)
            path = preencher_pdf(ficha, fonte_id=fonte, size=0.0)

            try:
                if os.name == "nt":
                    os.startfile(str(path))  # type: ignore[attr-defined]
                else:
                    webbrowser.open(path.resolve().as_uri())
            except OSError as exc:
                raise ValueError(f"Não foi possível abrir a declaração: {exc}") from exc
            return {"path": str(path), "ficha_id": ficha.id, "fonte": fonte}

        return self._run_async("defeso_print", work, "Gerando declaração…")

    def print_defeso_pacote(
        self,
        ficha_id: str = "",
        payload: Optional[Dict[str, Any]] = None,
        itens: Optional[Any] = None,
        fonte_id: str = "",
    ) -> Dict[str, Any]:
        """Junta declaração + anexos escolhidos num único PDF e abre."""

        def work():
            defeso = self._ensure_defeso()
            ficha = defeso.por_id(ficha_id) if ficha_id else None
            if ficha is None and isinstance(payload, dict) and payload:
                ficha = defeso.salvar(payload)
            if ficha is None:
                raise ValueError("Salve a ficha antes de montar o pacote.")

            cfg = load_config()
            if isinstance(itens, str):
                # pywebview pode mandar CSV
                raw_itens = [x.strip() for x in itens.split(",") if x.strip()]
            elif isinstance(itens, list):
                raw_itens = itens
            else:
                raw_itens = normalize_selecao(None)

            fonte = (fonte_id or "").strip() or str(
                cfg.get("defeso_declaracao_fonte") or DEFAULT_FONTE
            )
            result = montar_pacote_pdf(
                ficha, itens=raw_itens, fonte_id=fonte, cfg=cfg
            )
            path = Path(result["path"])
            try:
                if os.name == "nt":
                    os.startfile(str(path))  # type: ignore[attr-defined]
                else:
                    webbrowser.open(path.resolve().as_uri())
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
