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
from controle import usuarios as usuarios_mod
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
from controle.consulta_rgp import (
    SEGUNDOS_POR_CONSULTA_EST,
    aplicar_resultado_mpa,
    resumo_kpis,
    situacao_apta_import,
)
from controle.consulta_rgp_mpa import (
    MPA_CONSULTA_URL,
    abrir_site_mpa_no_navegador,
    consultar_cpf_isolado,
)
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
from sheets.consulta_rgp_service import ConsultaRgpService
from sheets.informe_mensal_service import InformeMensalService
from controle import informe_mensal as im
from ui.formatters import (
    display_nome,
    format_cpf,
    format_nome,
    normalize_cpf,
    only_digits,
    parse_lote_lines,
)
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
        self._js_lock = threading.Lock()
        self._fechando = False
        self._logged_in = False
        self._admin_user = ""
        self._admin_nome = ""
        self._papel = ""
        self._modulos: List[str] = []
        self._pode_escrever = False
        self._pode_admin_usuarios = False
        self._pode_cadastrar = False
        self._pode_editar = False
        self._pode_pedir_exclusao = False
        self._pode_excluir_direto = False
        self._pode_solicitar = False
        self._permissoes: List[str] = []
        self._usuario_id = ""
        self._service: Optional[SheetsService] = None
        self._defeso_service: Optional[DefesoService] = None
        self._consulta_rgp_service: Optional[ConsultaRgpService] = None
        self._informe_service: Optional[InformeMensalService] = None
        self._consulta_rgp_lote_cancel = False

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
                "admin_nome": self._admin_nome or self._admin_user,
                "papel": self._papel,
                "modulos": list(self._modulos),
                "pode_escrever": bool(self._pode_escrever),
                "pode_admin_usuarios": bool(self._pode_admin_usuarios),
                "pode_cadastrar": bool(self._pode_cadastrar),
                "pode_editar": bool(self._pode_editar),
                "pode_pedir_exclusao": bool(self._pode_pedir_exclusao),
                "pode_excluir_direto": bool(self._pode_excluir_direto),
                "pode_solicitar": bool(self._pode_solicitar),
                "permissoes": list(self._permissoes),
                "papeis": list(usuarios_mod.PAPEIS),
                "modulos_todos": list(usuarios_mod.MODULOS_TODOS),
                "permissoes_todas": list(usuarios_mod.PERMISSOES_TODAS),

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
                "consulta_rgp_spreadsheet_id": str(cfg.get("consulta_rgp_spreadsheet_id") or ""),
                "consulta_rgp_importar_auto": bool(cfg.get("consulta_rgp_importar_auto", True)),
                "consulta_rgp_govbr_opcional": bool(cfg.get("consulta_rgp_govbr_opcional", False)),
                "consulta_rgp_mpa_url": MPA_CONSULTA_URL,
                "public_site_url": site,
                "ultimo_backup_em": str(cfg.get("ultimo_backup_em") or "Nunca"),
                "credentials_label": cred_label,
                "backup_root": str(backup_root()),
                "qr_dir": str(qr_dir()),
                "meses": MESES,
                "meses_label": MESES_LABEL,
            }
        )

    def _set_sessao(self, user: Optional[usuarios_mod.Usuario] = None, *, email: str = "") -> None:
        if user is None:
            self._logged_in = False
            self._admin_user = ""
            self._admin_nome = ""
            self._papel = ""
            self._modulos = []
            self._permissoes = []
            self._usuario_id = ""
            self._pode_escrever = False
            self._pode_admin_usuarios = False
            self._pode_cadastrar = False
            self._pode_editar = False
            self._pode_pedir_exclusao = False
            self._pode_excluir_direto = False
            self._pode_solicitar = False
            return
        self._logged_in = True
        self._admin_user = user.email or email.strip()
        self._admin_nome = user.nome or user.email
        self._papel = user.papel
        self._modulos = list(user.modulos)
        self._permissoes = list(user.permissoes)
        self._usuario_id = user.id
        self._pode_escrever = user.pode_escrever
        self._pode_admin_usuarios = user.pode_admin_usuarios
        self._pode_cadastrar = user.pode_cadastrar
        self._pode_editar = user.pode_editar
        self._pode_pedir_exclusao = user.pode_pedir_exclusao
        self._pode_excluir_direto = user.pode_excluir_direto
        self._pode_solicitar = user.pode_solicitar

    def _sessao_payload(self) -> Dict[str, Any]:
        return {
            "admin_user": self._admin_user,
            "admin_nome": self._admin_nome or self._admin_user,
            "papel": self._papel,
            "modulos": list(self._modulos),
            "permissoes": list(self._permissoes),
            "pode_escrever": bool(self._pode_escrever),
            "pode_admin_usuarios": bool(self._pode_admin_usuarios),
            "pode_cadastrar": bool(self._pode_cadastrar),
            "pode_editar": bool(self._pode_editar),
            "pode_pedir_exclusao": bool(self._pode_pedir_exclusao),
            "pode_excluir_direto": bool(self._pode_excluir_direto),
            "pode_solicitar": bool(self._pode_solicitar),
        }

    def _revalidar_sessao(self) -> None:
        """Garante que o usuário ainda existe e está ativo (evita sessão fantasma)."""
        if not self._logged_in or not self._admin_user:
            raise SheetsConfigError("Faça login como administrador.")
        try:
            svc = self._ensure_service(require_login=False)
            atual = svc.obter_usuario_email(self._admin_user)
        except Exception as exc:  # noqa: BLE001
            raise SheetsConfigError(f"Não foi possível validar a sessão: {exc}") from exc
        if atual is None or not atual.ativo:
            self._set_sessao(None)
            raise SheetsConfigError("Sessão encerrada: usuário inativo ou removido.")
        self._set_sessao(atual)

    def _require_escrita(self) -> None:
        self._revalidar_sessao()
        if not self._pode_escrever:
            raise SheetsConfigError("Seu usuário é só leitura — não pode alterar dados.")

    def _require_perm(self, perm: str) -> None:
        self._revalidar_sessao()
        if self._papel == usuarios_mod.PAPEL_ADMIN:
            return
        if not self._logged_in:
            raise SheetsConfigError("Faça login como administrador.")
        flag = {
            usuarios_mod.PERM_CADASTRAR: self._pode_cadastrar,
            usuarios_mod.PERM_EDITAR: self._pode_editar,
            usuarios_mod.PERM_PEDIR_EXCLUSAO: self._pode_pedir_exclusao,
            usuarios_mod.PERM_EXCLUIR_DIRETO: self._pode_excluir_direto,
            usuarios_mod.PERM_SOLICITAR: self._pode_solicitar,
        }.get(perm, False)
        if not flag:
            raise SheetsConfigError(f"Sem permissão: {perm}.")

    def _erro_sem_escrita(self) -> Optional[Dict[str, Any]]:
        try:
            self._require_escrita()
        except SheetsConfigError as exc:
            return err(str(exc))
        return None

    def _require_admin_usuarios(self) -> None:
        self._revalidar_sessao()
        if not self._pode_admin_usuarios:
            raise SheetsConfigError("Só o papel admin gerencia usuários.")

    def login(self, email: str, password: str) -> Dict[str, Any]:
        cfg = load_config()
        if not is_sheets_configured(cfg):
            return err("Configure primeiro o Google Sheets.", redirect="settings")
        try:
            svc = SheetsService.from_config(cfg)
            svc.actor = usuarios_mod.normalizar_email(email) or "login"
            lista = svc.listar_usuarios()
        except Exception as exc:  # noqa: BLE001
            return err(f"Não foi possível ler a aba Usuarios: {exc}")

        # Bootstrap: aba vazia → cria admin a partir do config.json local
        if not lista:
            cfg_email = usuarios_mod.normalizar_email(cfg.get("admin_email"))
            cfg_pass = str(cfg.get("admin_password") or "")
            if (
                cfg_email
                and cfg_pass
                and usuarios_mod.normalizar_email(email) == cfg_email
                and password == cfg_pass
            ):
                try:
                    user = svc.garantir_admin_bootstrap(
                        cfg_email, cfg_pass, nome=str(cfg.get("admin_email") or "")
                    )
                except Exception as exc:  # noqa: BLE001
                    return err(f"Falha ao criar usuário inicial: {exc}")
            else:
                return err(
                    "Nenhum usuário na planilha ainda. Entre com o e-mail/senha "
                    "das Configurações locais para criar o 1º admin, ou cadastre "
                    "na aba Usuarios."
                )
        else:
            user, erro = usuarios_mod.autenticar(lista, email, password)
            if erro or user is None:
                return err(erro or "E-mail ou senha incorretos.")
            try:
                if usuarios_mod.senha_precisa_rehash(user.senha_hash):
                    svc.actor = user.email
                    user = svc.rehash_senha_se_preciso(user, password)
                svc.actor = user.email
                user = svc.marcar_ultimo_login(user)
            except Exception:
                pass

        self._service = None
        self._defeso_service = None
        self._consulta_rgp_service = None
        self._informe_service = None
        self._set_sessao(user)
        try:
            svc2 = self._ensure_service(require_login=False)
            svc2.actor = self._admin_user
            svc2.registrar_evento("login", f"Login de {self._admin_user} ({self._papel}).")
        except Exception:
            pass
        return ok(**self._sessao_payload())

    def logout(self) -> Dict[str, Any]:
        if self._logged_in and self._admin_user:
            try:
                svc = self._ensure_service(require_login=False)
                svc.actor = self._admin_user
                svc.registrar_evento("logout", f"Logout de {self._admin_user}.")
            except Exception:
                pass
        self._set_sessao(None)
        self._service = None
        self._defeso_service = None
        self._consulta_rgp_service = None
        self._informe_service = None
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
                "consulta_rgp_spreadsheet_id": str(cfg.get("consulta_rgp_spreadsheet_id") or ""),
                "consulta_rgp_importar_auto": bool(cfg.get("consulta_rgp_importar_auto", True)),
                "consulta_rgp_govbr_opcional": bool(cfg.get("consulta_rgp_govbr_opcional", False)),
                "public_site_url": normalize_public_base(
                    cfg.get("public_site_url") or cfg.get("public_base_url") or ""
                ),
                "admin_email": str(cfg.get("admin_email") or ""),
                # Nunca devolver a senha em claro — UI envia só se for alterar
                "admin_password": "",
                "admin_password_set": bool(str(cfg.get("admin_password") or "").strip()),
                "credentials_label": (
                    f"JSON: {cred.get('client_email')}"
                    if isinstance(cred, dict)
                    else "Nenhuma credencial carregada."
                ),
            }
        )

    def _bloqueio_config_local(self) -> Optional[Dict[str, Any]]:
        """Sem login a config fica aberta (instalação/conserto); logado, só admin altera."""
        if self._logged_in and self._papel != usuarios_mod.PAPEL_ADMIN:
            return err("Só o admin altera as Configurações deste computador.")
        return None

    def save_settings(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        bloqueio = self._bloqueio_config_local()
        if bloqueio:
            return bloqueio
        if not isinstance(payload, dict):
            return err("Payload inválido.")
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
        if "consulta_rgp_spreadsheet_id" in payload:
            cfg["consulta_rgp_spreadsheet_id"] = normalize_sheet_id(
                str(payload.get("consulta_rgp_spreadsheet_id") or "")
            )
        if "consulta_rgp_importar_auto" in payload:
            cfg["consulta_rgp_importar_auto"] = bool(payload.get("consulta_rgp_importar_auto"))
        if "consulta_rgp_govbr_opcional" in payload:
            cfg["consulta_rgp_govbr_opcional"] = bool(payload.get("consulta_rgp_govbr_opcional"))
        if "informe_especies" in payload:
            erros_esp = im.validar_especies_ativas(payload.get("informe_especies"))
            if erros_esp:
                return err(" ".join(erros_esp))
            cfg["informe_especies"] = im.normalizar_especies_ativas(payload.get("informe_especies"))
        if "public_site_url" in payload:
            base = normalize_public_base(str(payload.get("public_site_url") or ""))
            cfg["public_site_url"] = base
            cfg["public_base_url"] = base
        if "admin_email" in payload:
            cfg["admin_email"] = str(payload.get("admin_email") or "").strip()
        if "admin_password" in payload:
            nova = str(payload.get("admin_password") or "")
            # Vazio = manter senha atual (get_settings não devolve o valor)
            if nova.strip():
                cfg["admin_password"] = nova
        save_config(cfg)
        self._service = None
        self._defeso_service = None
        self._consulta_rgp_service = None
        self._sync_site_config_js(cfg.get("spreadsheet_id", ""))
        return ok()

    def import_credentials_json(self, raw_json: str) -> Dict[str, Any]:
        bloqueio = self._bloqueio_config_local()
        if bloqueio:
            return bloqueio
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

    # ---- pedidos da diretoria (Notificações) ------------------------------

    @staticmethod
    def _payload_dict(payload: Any) -> Dict[str, Any]:
        if isinstance(payload, dict):
            return payload
        if isinstance(payload, str) and payload.strip()[:1] in "{[":
            try:
                data = json.loads(payload)
            except json.JSONDecodeError as exc:
                raise ValueError("Payload inválido.") from exc
            return data if isinstance(data, dict) else {}
        return {}

    def _pode_decidir_pedidos(self) -> bool:
        return self._papel == usuarios_mod.PAPEL_ADMIN or bool(self._pode_editar)

    def list_pedidos(self, tipo: str = "") -> Dict[str, Any]:
        from controle.pedidos import normalizar_tipo, resumo

        if not self._logged_in:
            return err("Faça login.")
        t = normalizar_tipo(tipo)

        def work():
            svc = self._ensure_service()
            itens = svc.listar_pedidos(tipo=t)
            return {
                "tipo": t,
                "itens": [p.to_dict() for p in itens],
                "resumo": resumo(itens),
                "pode_decidir": self._pode_decidir_pedidos(),
                "pode_solicitar": bool(self._pode_solicitar or self._papel == usuarios_mod.PAPEL_ADMIN),
            }

        return self._run_async("pedidos", work, "Carregando notificações…")

    def criar_pedido(self, payload: Any = None) -> Dict[str, Any]:
        """Diretoria pede: fazer REAP (tipo reap) ou entrada no seguro (tipo defeso)."""
        from controle.pedidos import TIPO_DEFESO, TIPO_REAP, normalizar_tipo, novo_pedido

        try:
            data = self._payload_dict(payload)
            self._require_perm(usuarios_mod.PERM_SOLICITAR)
        except (ValueError, SheetsConfigError) as exc:
            return err(str(exc))
        tipo = normalizar_tipo(data.get("tipo"))
        if not tipo:
            return err("Tipo de pedido inválido.")

        def work():
            svc = self._ensure_service()
            person_id = str(data.get("person_id") or "").strip()
            nome = str(data.get("nome") or "").strip()
            cpf = only_digits(str(data.get("cpf") or ""))
            if person_id:
                pessoa = svc.get_pessoa_com_reap(person_id)
                if pessoa is None:
                    raise ValueError("Sócio não encontrado.")
                nome = pessoa.nome
                cpf = only_digits(getattr(pessoa, "cpf", "") or cpf)
            lote = str(data.get("lote") or "").strip()
            if not lote:
                cfg = svc.lotes_config()
                lote = (
                    f"Lote REAP {cfg['reap_atual']}" if tipo == TIPO_REAP else str(cfg["defeso_atual"])
                )
            elif tipo == TIPO_REAP and lote.isdigit():
                lote = f"Lote REAP {lote}"
            pedido = novo_pedido(
                tipo=tipo,
                person_id=person_id,
                nome=nome,
                cpf=format_cpf(cpf) if len(cpf) == 11 else cpf,
                lote=lote,
                pedido_por=self._admin_user,
                pedido_por_nome=self._admin_nome,
                obs=str(data.get("obs") or ""),
            )
            svc.actor = self._admin_user
            svc.criar_pedido(pedido)
            return {"pedido": pedido.to_dict(), "tipo": tipo, "acao": "criado"}

        return self._run_async("pedido_salvo", work, "Enviando pedido…")

    def decidir_pedido(self, payload: Any = None) -> Dict[str, Any]:
        """Secretaria marca o pedido como feito, recusado, ou reabre (pendente)."""
        from controle.pedidos import STATUS_PENDENTE, STATUS_VALIDOS, now_stamp

        try:
            data = self._payload_dict(payload)
            self._revalidar_sessao()
        except (ValueError, SheetsConfigError) as exc:
            return err(str(exc))
        if not self._pode_decidir_pedidos():
            return err("Só a secretaria (admin ou quem edita) marca pedidos como feitos.")
        pedido_id = str(data.get("id") or "").strip()
        status = str(data.get("status") or "").strip().lower()
        status = {"feita": "feito", "fazer": "feito", "recusar": "recusado", "reabrir": STATUS_PENDENTE}.get(status, status)
        if not pedido_id or status not in STATUS_VALIDOS:
            return err("Pedido ou situação inválida.")

        def work():
            svc = self._ensure_service()
            alvo = next((p for p in svc.listar_pedidos() if p.id == pedido_id), None)
            if alvo is None:
                raise ValueError("Pedido não encontrado.")
            alvo.status = status
            if status == STATUS_PENDENTE:
                alvo.decidido_em = ""
                alvo.decidido_por = ""
            else:
                alvo.decidido_em = now_stamp()
                alvo.decidido_por = self._admin_nome or self._admin_user
            if "obs" in data:
                alvo.obs = str(data.get("obs") or "").strip()
            svc.actor = self._admin_user
            svc.atualizar_pedido(alvo)
            return {"pedido": alvo.to_dict(), "tipo": alvo.tipo, "acao": status}

        return self._run_async("pedido_salvo", work, "Atualizando pedido…")

    # ---- lotes (REAP = ano; Defeso = nome livre) ---------------------------

    def _lotes_payload(self, *, com_defeso: bool = True) -> Dict[str, Any]:
        from controle.lotes import nome_lote_reap, ordenar_lotes

        svc = self._ensure_service()
        cfg = svc.lotes_config()
        anos: Dict[int, int] = {}
        for p in svc.get_all_pessoas_com_reap():
            for a in getattr(p, "anos", []) or []:
                if a.ano:
                    anos[int(a.ano)] = anos.get(int(a.ano), 0) + 1
        anos.setdefault(int(cfg["reap_atual"]), 0)
        reap = [
            {"ano": a, "nome": nome_lote_reap(a), "total": anos[a]}
            for a in sorted(anos, reverse=True)
        ]
        out: Dict[str, Any] = {"reap": reap, "reap_atual": int(cfg["reap_atual"])}
        if com_defeso:
            defeso_lotes: List[Dict[str, Any]] = []
            aviso = ""
            try:
                defeso_lotes = self._ensure_defeso().listar_lotes()
            except Exception as exc:  # noqa: BLE001
                aviso = f"Planilha Defeso indisponível: {exc}"
            vistos = {str(d["nome"]).lower() for d in defeso_lotes}
            for extra in [*cfg["defeso_extras"], cfg["defeso_atual"]]:
                if extra and extra.lower() not in vistos:
                    defeso_lotes.append({"nome": extra, "total": 0})
                    vistos.add(extra.lower())
            ordem = ordenar_lotes([str(d["nome"]) for d in defeso_lotes])
            por_nome = {str(d["nome"]).lower(): d for d in defeso_lotes}
            out["defeso"] = [por_nome[n.lower()] for n in ordem]
            out["defeso_atual"] = cfg["defeso_atual"]
            out["defeso_aviso"] = aviso
        return out

    def load_lotes(self) -> Dict[str, Any]:
        if not self._logged_in:
            return err("Faça login.")
        return self._run_async("lotes", lambda: self._lotes_payload(), "Carregando lotes…")

    def abrir_lote_reap(self, ano: Any = None, copiar_de: Any = None) -> Dict[str, Any]:
        """Lote REAP novo (ex.: 2027): linha do ano em branco para cada sócio."""
        from controle.lotes import ano_do_lote_reap

        try:
            self._require_perm(usuarios_mod.PERM_EDITAR)
            alvo = ano_do_lote_reap(ano)
            origem = ano_do_lote_reap(copiar_de) if str(copiar_de or "").strip() else None
        except (ValueError, SheetsConfigError) as exc:
            return err(str(exc))

        def work():
            svc = self._ensure_service()
            svc.actor = self._admin_user
            res = svc.abrir_lote_reap(alvo, copiar_de=origem)
            res["lotes"] = self._lotes_payload(com_defeso=False)
            return res

        return self._run_async("lote_reap", work, f"Abrindo o Lote REAP {alvo}…")

    def definir_lote_reap_atual(self, ano: Any = None) -> Dict[str, Any]:
        from controle.lotes import ano_do_lote_reap

        try:
            self._require_perm(usuarios_mod.PERM_EDITAR)
            alvo = ano_do_lote_reap(ano)
        except (ValueError, SheetsConfigError) as exc:
            return err(str(exc))

        def work():
            svc = self._ensure_service()
            svc.definir_lote_reap_atual(alvo)
            return self._lotes_payload(com_defeso=False)

        return self._run_async("lotes", work, "Salvando lote atual…")

    def criar_lote_defeso(self, nome: Any = None, copiar_de: Any = None) -> Dict[str, Any]:
        """Lote Defeso novo (ex.: Defeso 2027). Com copiar_de, traz todos daquele lote."""
        from controle.lotes import normalizar_nome_lote

        try:
            self._require_perm(usuarios_mod.PERM_EDITAR)
        except SheetsConfigError as exc:
            return err(str(exc))
        novo = normalizar_nome_lote(nome)
        if not novo:
            return err("Informe o nome do lote (ex.: Defeso 2027).")

        def work():
            svc = self._ensure_service()
            svc.actor = self._admin_user
            res = self._ensure_defeso().criar_lote(novo, copiar_de=str(copiar_de or ""))
            svc.definir_lote_defeso(novo, atual=True)
            svc._registrar_auditoria(
                "lote_defeso_criar",
                f"criou o lote {novo}" + (f" com {res['copiados']} ficha(s) de {copiar_de}" if copiar_de else ""),
            )
            res["lotes"] = self._lotes_payload()
            return res

        return self._run_async("lote_defeso", work, f"Criando {novo}…")

    def definir_lote_defeso_atual(self, nome: Any = None) -> Dict[str, Any]:
        from controle.lotes import normalizar_nome_lote

        try:
            self._require_perm(usuarios_mod.PERM_EDITAR)
        except SheetsConfigError as exc:
            return err(str(exc))
        alvo = normalizar_nome_lote(nome)
        if not alvo:
            return err("Lote inválido.")

        def work():
            self._ensure_service().definir_lote_defeso(alvo, atual=True)
            return self._lotes_payload()

        return self._run_async("lotes", work, "Salvando lote atual…")

    def lote_defeso_pessoas(self, payload: Any = None) -> Dict[str, Any]:
        """Coloca (ou tira) pescadores de um lote Defeso.

        payload: {lote, acao: "adicionar"|"remover", itens: [{ficha_id, person_id, nome, cpf}]}
        Quem ainda não tem ficha ganha uma ficha só com nome e CPF.
        """
        from controle.lotes import normalizar_nome_lote

        try:
            data = self._payload_dict(payload)
            self._require_perm(usuarios_mod.PERM_EDITAR)
        except (ValueError, SheetsConfigError) as exc:
            return err(str(exc))
        lote = normalizar_nome_lote(data.get("lote"))
        acao = str(data.get("acao") or "adicionar").strip().lower()
        itens = [i for i in (data.get("itens") or []) if isinstance(i, dict)]
        if not lote or not itens:
            return err("Escolha o lote e pelo menos um pescador.")

        def work():
            defeso = self._ensure_defeso()
            svc = self._ensure_service()
            svc.actor = self._admin_user
            if acao == "remover":
                total = 0
                for item in itens:
                    fid = str(item.get("ficha_id") or "").strip()
                    if fid:
                        total += defeso.remover_do_lote(fid, lote)
                svc._registrar_auditoria("lote_defeso_remover", f"tirou {total} ficha(s) do {lote}")
                return {"lote": lote, "acao": acao, "total": total, "lotes": self._lotes_payload()}
            ids: List[str] = []
            criadas = 0
            pessoas: Optional[Dict[str, Any]] = None
            for item in itens:
                fid = str(item.get("ficha_id") or "").strip()
                if fid:
                    ids.append(fid)
                    continue
                cpf = only_digits(str(item.get("cpf") or ""))
                pid = str(item.get("person_id") or "").strip()
                if len(cpf) != 11 and pid:
                    if pessoas is None:
                        pessoas = {p.id: p for p in svc.get_all_pessoas()}
                    p = pessoas.get(pid)
                    if p is not None:
                        cpf = only_digits(p.cpf)
                        item = {**item, "nome": item.get("nome") or p.nome}
                if len(cpf) != 11:
                    continue
                existente = defeso.por_cpf(cpf)
                if existente is not None:
                    ids.append(existente.id)
                    continue
                ficha = defeso.salvar(
                    {
                        "person_id": str(item.get("person_id") or ""),
                        "nome": str(item.get("nome") or ""),
                        "cpf": cpf,
                        "lote": lote,
                    }
                )
                ids.append(ficha.id)
                criadas += 1
            defeso.adicionar_ao_lote(ids, lote)
            svc._registrar_auditoria("lote_defeso_adicionar", f"colocou {len(ids)} pescador(es) no {lote}")
            return {"lote": lote, "acao": acao, "total": len(ids), "criadas": criadas, "lotes": self._lotes_payload()}

        return self._run_async("lote_defeso", work, f"Atualizando {lote}…")

    def on_closing(self) -> None:
        self._fechando = True

    def _dispatch(self, event: str, payload: Any) -> None:
        if not self._window or getattr(self, "_fechando", False):
            return
        try:
            body = json.dumps(payload, ensure_ascii=False, default=str)
        except (TypeError, ValueError) as exc:
            body = json.dumps(err(f"Resposta inválida: {exc}"), ensure_ascii=False)
        script = f"window.AppEvents && window.AppEvents.dispatch({json.dumps(event)}, {body})"
        # evaluate_js de várias threads ao mesmo tempo derruba o WebView2
        with self._js_lock:
            try:
                self._window.evaluate_js(script)
            except Exception as exc:  # noqa: BLE001
                try:
                    from webapp.launcher import registrar_erro

                    registrar_erro(f"Falha ao avisar a tela ({event})", repr(exc))
                except Exception:  # noqa: BLE001
                    pass

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

    def _ensure_service(
        self, *, require_login: bool = True, require_write: bool = False
    ) -> SheetsService:
        if require_login and not self._logged_in:
            raise SheetsConfigError("Faça login como administrador.")
        if require_write:
            self._require_escrita()
        cfg = load_config()
        if not is_sheets_configured(cfg):
            raise SheetsConfigError("Google Sheets ainda não configurado.")
        if self._service is None:
            self._service = SheetsService.from_config(cfg)
        actor = self._admin_user if self._logged_in else str(cfg.get("admin_email") or "")
        self._service.actor = actor
        return self._service

    def _ensure_defeso(self, *, require_write: bool = False) -> DefesoService:
        if not self._logged_in:
            raise SheetsConfigError("Faça login como administrador.")
        if require_write:
            self._require_escrita()
        cfg = load_config()
        if not is_sheets_configured(cfg):
            raise SheetsConfigError("Google Sheets ainda não configurado.")
        if self._defeso_service is None:
            self._defeso_service = DefesoService.from_config(cfg)
        return self._defeso_service

    def _ensure_consulta_rgp(self, *, require_write: bool = False) -> ConsultaRgpService:
        if not self._logged_in:
            raise SheetsConfigError("Faça login como administrador.")
        if require_write:
            self._require_escrita()
        cfg = load_config()
        if not is_sheets_configured(cfg):
            raise SheetsConfigError("Google Sheets ainda não configurado.")
        if self._consulta_rgp_service is None:
            self._consulta_rgp_service = ConsultaRgpService.from_config(cfg)
        self._consulta_rgp_service.actor = (
            self._admin_user if self._logged_in else str(cfg.get("admin_email") or "")
        )
        return self._consulta_rgp_service

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
            svc = self._ensure_service()
            ultimo = _ultimo_toggle_map(svc)
            pessoas = svc.get_all_pessoas_com_reap()
            # Só dados da planilha REAP — Defeso não altera o que aparece aqui
            return [
                pessoa_to_dict(p, ultimo_toggle=ultimo.get(p.id)) for p in pessoas
            ]

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
        try:
            if person_id:
                self._require_perm(usuarios_mod.PERM_EDITAR)
            else:
                self._require_perm(usuarios_mod.PERM_CADASTRAR)
        except SheetsConfigError as exc:
            return err(str(exc))

        def work():
            svc = self._ensure_service(require_write=True)
            pid = ""
            if person_id:
                svc.update_pessoa(person_id, nome, cpf, municipio, telefone)
                pid = person_id
            else:
                pid = svc.add_pessoa(nome, cpf, municipio, telefone).id
            if municipio or telefone:
                try:
                    defeso = self._ensure_defeso(require_write=True)
                    ficha = defeso.por_cpf(cpf)
                    if ficha:
                        # Município REAP NÃO sobrescreve o da declaração Defeso
                        if telefone:
                            defeso.atualizar_telefone_reap(ficha.id, telefone)
                    else:
                        defeso.salvar(
                            {
                                "person_id": pid,
                                "nome": nome,
                                "cpf": cpf,
                                # município da declaração fica vazio — usuário preenche no Defeso
                                "municipio": "",
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
            reap = self._ensure_service(require_write=True)
            defeso = self._ensure_defeso(require_write=True)
            return sync_municipios_bidirecional(reap, defeso)

        return self._run_async("sync_planilhas", work, "Sincronizando planilhas…")

    def delete_pessoa(self, person_id: str) -> Dict[str, Any]:
        if not person_id:
            return err("Sócio inválido.")
        try:
            self._revalidar_sessao()
        except SheetsConfigError as exc:
            return err(str(exc))
        # Exclusão direta só com permissão; senão vira pedido
        if self._pode_excluir_direto or self._papel == usuarios_mod.PAPEL_ADMIN:
            def work_del():
                self._ensure_service(require_write=True).delete_pessoa(person_id)
                return {"excluido": True}

            return self._run_async("pessoa_deleted", work_del, "Excluindo…")
        if not self._pode_pedir_exclusao:
            return err("Sem permissão para excluir ou pedir exclusão.")
        return self.pedir_exclusao({"person_id": person_id})

    def pedir_exclusao(self, payload: Any = None) -> Dict[str, Any]:
        data = payload if isinstance(payload, dict) else {}
        if isinstance(payload, str) and payload.strip()[:1] in "{[":
            try:
                data = json.loads(payload)
            except json.JSONDecodeError:
                return err("Payload inválido.")
        person_id = str(data.get("person_id") or "").strip()
        motivo = str(data.get("motivo") or "").strip()
        if not person_id:
            return err("Sócio inválido.")
        try:
            self._require_perm(usuarios_mod.PERM_PEDIR_EXCLUSAO)
        except SheetsConfigError as exc:
            return err(str(exc))

        def work():
            from controle.exclusoes import novo_pedido

            svc = self._ensure_service(require_write=True)
            pessoa = svc.get_pessoa_com_reap(person_id)
            if pessoa is None:
                raise ValueError("Sócio não encontrado.")
            pedido = novo_pedido(
                person_id=person_id,
                nome=pessoa.nome,
                cpf=getattr(pessoa, "cpf", "") or "",
                pedido_por=self._admin_user,
                motivo=motivo,
            )
            svc.criar_pedido_exclusao(pedido)
            return {"pedido": pedido.to_dict()}

        return self._run_async("exclusao_pedida", work, "Registrando pedido de exclusão…")

    def list_exclusoes_pendentes(self) -> Dict[str, Any]:
        try:
            self._require_admin_usuarios()
        except SheetsConfigError as exc:
            return err(str(exc))

        def work():
            svc = self._ensure_service()
            pendentes = [p.to_dict() for p in svc.listar_pedidos_exclusao(somente_pendentes=True)]
            recentes = [p.to_dict() for p in svc.listar_pedidos_exclusao()[:40]]
            return {"pendentes": pendentes, "recentes": recentes}

        return self._run_async("exclusoes", work, "Carregando pedidos de exclusão…")

    def decidir_exclusao(self, payload: Any = None) -> Dict[str, Any]:
        """Admin aprova (exclui sócio) ou recusa o pedido."""
        try:
            self._require_admin_usuarios()
        except SheetsConfigError as exc:
            return err(str(exc))
        data = payload if isinstance(payload, dict) else {}
        if isinstance(payload, str) and payload.strip()[:1] in "{[":
            try:
                data = json.loads(payload)
            except json.JSONDecodeError:
                return err("Payload inválido.")
        pedido_id = str(data.get("id") or "").strip()
        decisao = str(data.get("decisao") or data.get("status") or "").strip().lower()
        motivo = str(data.get("motivo") or "").strip()
        if not pedido_id:
            return err("Pedido inválido.")
        if decisao not in ("aprovado", "aprovar", "recusado", "recusar"):
            return err("Decisão deve ser aprovar ou recusar.")
        aprovar = decisao in ("aprovado", "aprovar")

        def work():
            from controle.exclusoes import (
                STATUS_APROVADO,
                STATUS_PENDENTE,
                STATUS_RECUSADO,
                now_stamp,
            )

            svc = self._ensure_service(require_write=True)
            pedido = next(
                (p for p in svc.listar_pedidos_exclusao() if p.id == pedido_id),
                None,
            )
            if pedido is None:
                raise ValueError("Pedido não encontrado.")
            if pedido.status != STATUS_PENDENTE:
                raise ValueError(f"Pedido já está {pedido.status}.")
            pedido.decidido_em = now_stamp()
            pedido.decidido_por = self._admin_user
            if motivo:
                pedido.motivo = (
                    f"{pedido.motivo} | decisão: {motivo}".strip(" |")
                    if pedido.motivo
                    else motivo
                )
            if aprovar:
                pedido.status = STATUS_APROVADO
                existe = svc.get_pessoa_com_reap(pedido.person_id) is not None
                svc.atualizar_pedido_exclusao(pedido)
                if existe:
                    svc.delete_pessoa(pedido.person_id)
                svc.registrar_evento(
                    "exclusao_aprovar",
                    f"Aprovou exclusão de {pedido.nome or pedido.person_id}"
                    + ("" if existe else " (sócio já não existia)"),
                    person_id=pedido.person_id,
                    nome=pedido.nome,
                )
                return {
                    "pedido": pedido.to_dict(),
                    "excluido": existe,
                    "aviso": "" if existe else "Sócio já tinha sido removido; pedido encerrado.",
                }
            pedido.status = STATUS_RECUSADO
            svc.atualizar_pedido_exclusao(pedido)
            svc.registrar_evento(
                "exclusao_recusar",
                f"Recusou exclusão de {pedido.nome or pedido.person_id}",
                person_id=pedido.person_id,
                nome=pedido.nome,
            )
            return {"pedido": pedido.to_dict(), "excluido": False}

        return self._run_async(
            "exclusao_decidida",
            work,
            "Aprovando exclusão…" if aprovar else "Recusando pedido…",
        )

    def toggle_mes(self, person_id: str, ano: int, mes: str, novo: bool) -> Dict[str, Any]:
        if mes not in MESES:
            return err("Mês inválido.")
        try:
            self._require_perm(usuarios_mod.PERM_EDITAR)
        except SheetsConfigError as exc:
            return err(str(exc))

        def work():
            svc = self._ensure_service(require_write=True)
            pessoa = svc.get_pessoa_com_reap(person_id)
            nome = pessoa.nome if pessoa else ""
            svc.toggle_mes(person_id, int(ano), mes, bool(novo), nome=nome)  # type: ignore[arg-type]
            return {"person_id": person_id, "ano": int(ano), "mes": mes, "on": bool(novo)}

        return self._run_async("mes_toggled", work, f"Atualizando {mes}/{ano}…")

    def add_ano(self, person_id: str, ano: int) -> Dict[str, Any]:
        try:
            self._require_perm(usuarios_mod.PERM_EDITAR)
        except SheetsConfigError as exc:
            return err(str(exc))

        def work():
            svc = self._ensure_service(require_write=True)
            pessoa = svc.get_pessoa_com_reap(person_id)
            nome = pessoa.nome if pessoa else ""
            svc.add_ano(person_id, int(ano), nome=nome)
            return True

        return self._run_async("ano_added", work, "Adicionando ano…")

    def save_lote(self, raw: str, ano: int, meses_on: List[str]) -> Dict[str, Any]:
        itens = parse_lote_lines(raw)
        if not itens:
            return err("Nenhuma linha válida (Nome + CPF).")
        try:
            self._require_perm(usuarios_mod.PERM_CADASTRAR)
        except SheetsConfigError as exc:
            return err(str(exc))

        def work():
            return self._ensure_service(require_write=True).add_pessoas_lote(
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
        try:
            self._require_perm(usuarios_mod.PERM_CADASTRAR)
        except SheetsConfigError as exc:
            return err(str(exc))

        def work():
            return self._ensure_service(require_write=True).add_pessoas_lote(
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
        try:
            self._require_perm(usuarios_mod.PERM_EDITAR)
        except SheetsConfigError as exc:
            return err(str(exc))

        def work():
            return self._ensure_service(require_write=True).copiar_reap_ano(
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
        try:
            self._require_perm(usuarios_mod.PERM_EDITAR)
        except SheetsConfigError as exc:
            return err(str(exc))

        def work():
            svc = self._ensure_service(require_write=True)
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
            cal = self._ensure_service(require_write=True).set_calendario(meses, ano=int(ano))
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
        colunas: Any = None,
        filtros: Any = None,
    ) -> Dict[str, Any]:
        """Relatório HTML Defeso com filtros, colunas e observação."""
        from controle.defeso_relatorio import (
            normalize_colunas_defeso,
            normalize_filtros_defeso,
            resumo_filtros_defeso,
        )

        raw_cols: Any = colunas
        if isinstance(colunas, str) and colunas.strip()[:1] in "{[":
            try:
                raw_cols = json.loads(colunas)
            except json.JSONDecodeError:
                raw_cols = colunas
        elif colunas is not None and not isinstance(colunas, (str, list, tuple, dict, bool)):
            try:
                raw_cols = _js_payload_to_dict(colunas)
            except ValueError:
                raw_cols = None
        cols = normalize_colunas_defeso(raw_cols)

        raw_filtros: Any = filtros
        if isinstance(filtros, str) and filtros.strip()[:1] in "{[":
            try:
                raw_filtros = json.loads(filtros)
            except json.JSONDecodeError:
                raw_filtros = {}
        elif filtros is not None and not isinstance(filtros, (str, dict)):
            try:
                raw_filtros = _js_payload_to_dict(filtros)
            except ValueError:
                raw_filtros = {}
        if isinstance(raw_filtros, dict) and raw_filtros.get("colunas") and not raw_cols:
            cols = normalize_colunas_defeso(raw_filtros.get("colunas"))
        fcfg = normalize_filtros_defeso(
            raw_filtros if isinstance(raw_filtros, dict) else None,
            localidade=str(localidade or ""),
            somente_entrada=bool(somente_entrada),
            somente_parcela=bool(somente_parcela),
        )

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
            loc = str(fcfg.get("localidade") or "").strip()
            itens = itens_defeso_para_relatorio(
                fichas,
                telefones_reap=telefones,
                municipios_reap=municipios,
                nomes_reap=nomes,
                cpfs_reap=cpfs,
                filtros=fcfg,
            )
            if not itens:
                raise ValueError("Nenhuma ficha encontrada com os filtros escolhidos.")
            resumo = resumo_filtros_defeso(fcfg)
            titulo = "Relatório Defeso Fácil"
            if resumo:
                titulo += f" — {resumo}"
            html_txt = montar_html_defeso(
                org_short=ORG_SHORT,
                org_full=ORG_FULL,
                itens=itens,
                titulo=titulo,
                localidade=loc,
                colunas=cols,
                filtros_resumo=resumo,
            )
            nome_arq = nome_arquivo_defeso_relatorio(localidade=loc)
            path = salvar_html_defeso(html_txt, nome_arquivo=nome_arq)
            reap.registrar_evento("relatorio_defeso", f"gerou {path.name}")
            return {
                "path": str(path),
                "html": html_txt,
                "total": len(itens),
                "colunas": cols,
                "filtros": fcfg,
            }

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

    def filter_auditoria_local(
        self,
        eventos: List[Dict[str, Any]],
        busca: str,
        usuario: str = "",
    ) -> Dict[str, Any]:
        from controle.auditoria import EventoAuditoria

        user_f = str(usuario or "").strip().lower()
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
            if user_f and evt.usuario.strip().lower() != user_f:
                continue
            if combina_busca(evt, busca):
                out.append(raw)
        return ok(data=out)

    # ---- Usuários online (aba Usuarios) ----------------------------------

    def list_usuarios(self) -> Dict[str, Any]:
        try:
            self._require_admin_usuarios()
        except SheetsConfigError as exc:
            return err(str(exc))

        def work():
            svc = self._ensure_service()
            itens = [u.to_public_dict() for u in svc.listar_usuarios()]
            return {
                "itens": itens,
                "papeis": list(usuarios_mod.PAPEIS),
                "modulos_todos": list(usuarios_mod.MODULOS_TODOS),
                "permissoes_todas": list(usuarios_mod.PERMISSOES_TODAS),
            }

        return self._run_async("usuarios", work, "Carregando usuários…")

    def create_usuario(self, payload: Any = None) -> Dict[str, Any]:
        try:
            self._require_admin_usuarios()
        except SheetsConfigError as exc:
            return err(str(exc))
        data = payload if isinstance(payload, dict) else {}
        if isinstance(payload, str) and payload.strip()[:1] in "{[":
            try:
                data = json.loads(payload)
            except json.JSONDecodeError:
                return err("Payload inválido.")

        def work():
            svc = self._ensure_service(require_write=True)
            emails = [u.email for u in svc.listar_usuarios()]
            erros = usuarios_mod.validar_payload_usuario(
                data, exige_senha=True, emails_ocupados=emails
            )
            if erros:
                raise ValueError(" ".join(erros))
            user = usuarios_mod.novo_usuario(
                email=str(data.get("email") or ""),
                senha=str(data.get("senha") or ""),
                nome=str(data.get("nome") or ""),
                papel=str(data.get("papel") or usuarios_mod.PAPEL_OPERADOR),
                ativo=usuarios_mod.normalizar_ativo(data.get("ativo", True)),
                modulos=data.get("modulos"),
                permissoes=data.get("permissoes") if "permissoes" in data else None,
            )
            svc.criar_usuario(user)
            return {"usuario": user.to_public_dict()}

        return self._run_async("usuario_salvo", work, "Cadastrando usuário…")

    def update_usuario(self, payload: Any = None) -> Dict[str, Any]:
        try:
            self._require_admin_usuarios()
        except SheetsConfigError as exc:
            return err(str(exc))
        data = payload if isinstance(payload, dict) else {}
        if isinstance(payload, str) and payload.strip()[:1] in "{[":
            try:
                data = json.loads(payload)
            except json.JSONDecodeError:
                return err("Payload inválido.")

        def work():
            svc = self._ensure_service(require_write=True)
            uid = str(data.get("id") or "").strip()
            atual = next((u for u in svc.listar_usuarios() if u.id == uid), None)
            if atual is None:
                raise ValueError("Usuário não encontrado.")
            emails = [u.email for u in svc.listar_usuarios()]
            erros = usuarios_mod.validar_payload_usuario(
                data, exige_senha=False, emails_ocupados=emails, email_atual=atual.email
            )
            if erros:
                raise ValueError(" ".join(erros))
            novo_papel = (
                usuarios_mod.normalizar_papel(data.get("papel"))
                if "papel" in data
                else atual.papel
            )
            novo_ativo = (
                usuarios_mod.normalizar_ativo(data.get("ativo"))
                if "ativo" in data
                else atual.ativo
            )
            if atual.papel == usuarios_mod.PAPEL_ADMIN and atual.ativo:
                if novo_papel != usuarios_mod.PAPEL_ADMIN or not novo_ativo:
                    outros_admin = [
                        u
                        for u in svc.listar_usuarios()
                        if u.id != atual.id
                        and u.papel == usuarios_mod.PAPEL_ADMIN
                        and u.ativo
                    ]
                    if not outros_admin:
                        raise ValueError(
                            "Não é possível desativar ou rebaixar o único admin ativo."
                        )
            if "email" in data:
                atual.email = usuarios_mod.normalizar_email(data.get("email"))
            if "nome" in data:
                atual.nome = str(data.get("nome") or "").strip() or atual.email
            atual.papel = novo_papel
            atual.ativo = novo_ativo
            if "modulos" in data:
                atual.modulos = usuarios_mod.normalizar_modulos(data.get("modulos"))
            if "permissoes" in data:
                atual.permissoes = usuarios_mod.normalizar_permissoes(
                    data.get("permissoes"), papel=novo_papel
                )
                atual._perms_explicit = True
            elif "papel" in data:
                # troca de papel sem permissões explícitas → padrão do novo papel
                atual.permissoes = usuarios_mod.normalizar_permissoes(None, papel=novo_papel)
                atual._perms_explicit = False
            svc.atualizar_usuario(atual)
            if atual.id == self._usuario_id:
                self._set_sessao(atual)
            return {"usuario": atual.to_public_dict(), "sessao": self._sessao_payload()}

        return self._run_async("usuario_salvo", work, "Salvando usuário…")

    def set_usuario_ativo(self, user_id: str, ativo: bool = True) -> Dict[str, Any]:
        return self.update_usuario({"id": user_id, "ativo": bool(ativo)})

    def reset_usuario_senha(self, payload: Any = None) -> Dict[str, Any]:
        try:
            self._require_admin_usuarios()
        except SheetsConfigError as exc:
            return err(str(exc))
        data = payload if isinstance(payload, dict) else {}
        if isinstance(payload, str) and payload.strip()[:1] in "{[":
            try:
                data = json.loads(payload)
            except json.JSONDecodeError:
                return err("Payload inválido.")

        def work():
            svc = self._ensure_service(require_write=True)
            uid = str(data.get("id") or "").strip()
            senha = str(data.get("senha") or "")
            erros = usuarios_mod.validar_senha_nova(senha)
            if erros:
                raise ValueError(" ".join(erros))
            atual = next((u for u in svc.listar_usuarios() if u.id == uid), None)
            if atual is None:
                raise ValueError("Usuário não encontrado.")
            atual.senha_hash = usuarios_mod.hash_senha(senha)
            svc.atualizar_usuario(atual)
            svc.registrar_evento(
                "usuario_reset_senha",
                f"Redefiniu a senha de {atual.email}.",
            )
            return {"usuario": atual.to_public_dict()}

        return self._run_async("usuario_salvo", work, "Redefinindo senha…")

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
                pessoa = self._ensure_service().get_pessoa_com_reap(person_id)
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
                pessoa = self._ensure_service().get_pessoa_com_reap(person_id)
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
        bloqueio = self._bloqueio_config_local()
        if bloqueio:
            return bloqueio
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
                # Lista/filtro: município exibido é só o REAP (declaração Defeso é separada)
                municipio = p_mun
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
                        "observacao": str(f.observacao or "").strip() if f else "",
                        "tem_observacao": bool(f and str(f.observacao or "").strip()),
                        "lotes": f.to_dict()["lotes_lista"] if f else [],
                    }
                )
            # Não lista fichas órfãs (existem só no Defeso, sem CPF no REAP) —
            # evita "sócio fantasma" no relatório / tela.
            rows.sort(key=lambda r: str(r.get("nome_display") or "").lower())
            localidades = sorted(
                {
                    str(r.get("municipio_reap") or "").strip()
                    for r in rows
                    if str(r.get("municipio_reap") or "").strip()
                },
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
                # Município REAP: só visualização / relatório — NÃO entra na declaração
                base["municipio_reap"] = p_mun
                # base["municipio"] continua sendo o da ficha Defeso (endereço da declaração)
                if str(base.get("municipio") or "").strip():
                    base["municipio_origem"] = "defeso"
                elif p_mun:
                    base["municipio_origem"] = "reap"
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
            p_mun = ""
            try:
                for p in self._ensure_service(require_write=True).get_all_pessoas():
                    if (pid and p.id == pid) or only_digits(p.cpf) == cpf:
                        if not str(local.get("telefone_reap") or "").strip():
                            tel = str(getattr(p, "telefone", "") or "").strip()
                            if tel:
                                local["telefone_reap"] = tel
                        p_mun = str(getattr(p, "municipio", "") or "").strip()
                        break
            except Exception:
                pass

            ficha = self._ensure_defeso(require_write=True).salvar(local)
            d = ficha.to_dict()
            d["municipio_reap"] = p_mun
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
            if data and self._pode_escrever:
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
            if data and self._pode_escrever:
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
        bloqueio = self._erro_sem_escrita()
        if bloqueio:
            return bloqueio
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
        bloqueio = self._erro_sem_escrita()
        if bloqueio:
            return bloqueio
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
            defeso = self._ensure_defeso(require_write=True)
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

    # ---- Consulta RGP ----------------------------------------------------

    def load_consulta_rgp(self) -> Dict[str, Any]:
        def work():
            cfg = load_config()
            svc = self._ensure_consulta_rgp()
            regs = svc.listar()
            # Preferências (senha Gov.br etc.) vêm da aba Config da planilha
            govbr_senha = ""
            try:
                govbr_senha = svc.get_govbr_senha()
            except Exception:  # noqa: BLE001
                govbr_senha = str(cfg.get("consulta_rgp_govbr_senha") or "")
            itens = [r.to_dict() for r in regs]
            if not self._pode_escrever:
                for it in itens:
                    it["govbr_senha_set"] = bool(str(it.get("govbr_senha") or "").strip())
                    it["govbr_senha"] = ""
                govbr_senha = ""
            return {
                "itens": itens,
                "kpis": resumo_kpis(regs),
                "importar_auto": bool(cfg.get("consulta_rgp_importar_auto", True)),
                "govbr_opcional": bool(govbr_senha) or bool(
                    cfg.get("consulta_rgp_govbr_opcional", False)
                ),
                "govbr_senha": govbr_senha,
                "spreadsheet_id": normalize_sheet_id(
                    str(cfg.get("consulta_rgp_spreadsheet_id") or cfg.get("spreadsheet_id") or "")
                ),
                "mpa_url": MPA_CONSULTA_URL,
            }

        return self._run_async("consulta_rgp", work, "Carregando Consulta RGP…")

    def save_consulta_rgp_prefs(self, payload: Any = None) -> Dict[str, Any]:
        """Grava preferências na planilha Consulta RGP (aba Config)."""
        data = _js_payload_to_dict(payload)

        def work():
            svc = self._ensure_consulta_rgp(require_write=True)
            govbr_senha = None
            if "govbr_senha" in data:
                govbr_senha = svc.set_govbr_senha(str(data.get("govbr_senha") or ""))
            else:
                govbr_senha = svc.get_govbr_senha()

            # Espelho local opcional (cache) — fonte da verdade é a planilha
            cfg = load_config()
            if "importar_auto" in data:
                cfg["consulta_rgp_importar_auto"] = bool(data.get("importar_auto"))
            cfg["consulta_rgp_govbr_senha"] = str(govbr_senha or "")
            cfg["consulta_rgp_govbr_opcional"] = bool(govbr_senha)
            if "govbr_opcional" in data and "govbr_senha" not in data:
                cfg["consulta_rgp_govbr_opcional"] = bool(data.get("govbr_opcional"))
            save_config(cfg)

            svc.registrar_auditoria(
                "consulta_rgp_prefs",
                "Alterou preferências/senha Gov.br na Consulta RGP.",
            )
            return {
                "importar_auto": bool(cfg.get("consulta_rgp_importar_auto", True)),
                "govbr_opcional": bool(govbr_senha) or bool(
                    cfg.get("consulta_rgp_govbr_opcional", False)
                ),
                "govbr_senha": str(govbr_senha or ""),
                "mensagem": "Senha Gov.br salva na planilha Consulta RGP.",
            }

        return self._run_async("consulta_rgp_prefs", work, "Salvando na planilha…")

    def sync_consulta_rgp_reap(self) -> Dict[str, Any]:
        """Desativado — Consulta RGP opera só na própria planilha nesta etapa."""
        return err(
            "Sincronização com REAP/Defeso desativada nesta etapa. "
            "Cadastre e consulte só na planilha Consulta RGP."
        )

    def importar_lote_consulta_rgp(self, rows: Any = None) -> Dict[str, Any]:
        """Importa nome/CPF/telefone/município na planilha Consulta (batch anti-cota)."""
        from webapp.consulta_rgp_ext import importar_lote_batch_payload

        itens = _lote_itens_from_rows(rows)

        def work():
            return importar_lote_batch_payload(self._ensure_consulta_rgp(require_write=True), itens)

        return self._run_async("consulta_rgp_lote", work, "Importando para Consulta RGP…")

    def importar_arquivo_consulta_rgp(self, path: Any = None) -> Dict[str, Any]:
        """Importa PDF/XLS/XLSX/TXT/CSV com batch (evita erro de cota 60/429 em ~500)."""
        from webapp.consulta_rgp_ext import importar_arquivo_payload

        arquivo = str(path or "").strip()
        if not arquivo:
            return err("Informe o caminho do arquivo.")

        def work():
            return importar_arquivo_payload(self._ensure_consulta_rgp(require_write=True), arquivo)

        return self._run_async(
            "consulta_rgp_lote",
            work,
            "Importando arquivo para Consulta RGP…",
        )

    def escolher_arquivo_import_consulta_rgp(self) -> Dict[str, Any]:
        """Abre seletor PDF/XLS/TXT e importa o lote de uma vez (anti-cota)."""
        try:
            import tkinter as tk
            from tkinter import filedialog
        except ImportError as exc:  # pragma: no cover
            return err(f"Seletor de arquivo indisponível: {exc}")

        root = tk.Tk()
        root.withdraw()
        try:
            root.attributes("-topmost", True)
        except tk.TclError:
            pass
        try:
            chosen = filedialog.askopenfilename(
                parent=root,
                title="Importar lote Consulta RGP (PDF / XLS / TXT)",
                filetypes=[
                    ("Listas nome+CPF", "*.pdf *.xls *.xlsx *.txt *.csv"),
                    ("PDF", "*.pdf"),
                    ("Excel", "*.xls *.xlsx"),
                    ("Texto/CSV", "*.txt *.csv"),
                    ("Todos", "*.*"),
                ],
            )
        finally:
            root.destroy()

        if not chosen:
            return err("Nenhum arquivo selecionado.")
        return self.importar_arquivo_consulta_rgp(chosen)

    def cadastrar_consulta_rgp(self, payload: Any = None) -> Dict[str, Any]:
        """Cadastra/atualiza sócio na Consulta (nome, CPF, município, telefone, obs)."""
        local = _js_payload_to_dict(payload)

        def work():
            nome = str(local.get("nome") or "").strip()
            cpf = normalize_cpf(local.get("cpf") or "")
            if not nome:
                raise ValueError("Informe o nome.")
            if len(cpf) != 11:
                raise ValueError("CPF inválido (11 dígitos).")
            svc = self._ensure_consulta_rgp(require_write=True)
            # Senha Gov.br individual do sócio (coluna na planilha ConsultaRGP)
            senha = None
            if "govbr_senha" in local:
                senha = str(local.get("govbr_senha") or "")
            reg = svc.upsert_manual(
                nome=nome,
                cpf=cpf,
                telefone=str(local.get("telefone") or "").strip(),
                municipio=str(local.get("municipio") or "").strip(),
                uf=str(local.get("uf") or "").strip(),
                email=str(local.get("email") or "").strip(),
                observacao=str(local.get("observacao") or "").strip(),
                govbr_senha=senha,
            )
            svc.registrar_auditoria(
                "consulta_rgp_cadastro",
                f"Cadastrou/atualizou sócio: {reg.nome} ({reg.cpf})",
                person_id=reg.id,
                nome=reg.nome,
            )
            regs = svc.listar()
            return {
                "registro": reg.to_dict(),
                "itens": [r.to_dict() for r in regs],
                "kpis": resumo_kpis(regs),
                "mensagem": "Sócio salvo na Consulta RGP.",
            }

        return self._run_async("consulta_rgp_cadastro", work, "Salvando sócio…")

    def save_consulta_rgp_registro(self, payload: Any = None) -> Dict[str, Any]:
        local = _js_payload_to_dict(payload)

        def work():
            svc = self._ensure_consulta_rgp(require_write=True)
            if not str(local.get("id") or "").strip():
                senha = None
                if "govbr_senha" in local:
                    senha = str(local.get("govbr_senha") or "")
                reg = svc.upsert_manual(
                    nome=str(local.get("nome") or "").strip(),
                    cpf=str(local.get("cpf") or ""),
                    telefone=str(local.get("telefone") or "").strip(),
                    municipio=str(local.get("municipio") or "").strip(),
                    uf=str(local.get("uf") or "").strip(),
                    email=str(local.get("email") or "").strip(),
                    observacao=str(local.get("observacao") or "").strip(),
                    govbr_senha=senha,
                )
            else:
                # preserva situação/consulta ao editar cadastro
                existing = svc.por_id(str(local.get("id")))
                if existing:
                    local.setdefault("situacao_rgp", existing.situacao_rgp)
                    local.setdefault("ultima_consulta_em", existing.ultima_consulta_em)
                    local.setdefault("codigo_rgp", existing.codigo_rgp)
                    local.setdefault("categoria", existing.categoria)
                    local.setdefault("timeline", existing.timeline)
                    local.setdefault("importado_reap_em", existing.importado_reap_em)
                    local.setdefault("importado_defeso_em", existing.importado_defeso_em)
                    local.setdefault("cadastro_reap_em", existing.cadastro_reap_em)
                    local.setdefault("person_id", existing.person_id)
                    if "govbr_senha" not in local:
                        local["govbr_senha"] = existing.govbr_senha
                # govbr_senha é coluna individual do registro (T)
                reg = svc.salvar(local)
            svc.registrar_auditoria(
                "consulta_rgp_salvar",
                f"Alterou cadastro: {reg.nome} ({reg.cpf})",
                person_id=reg.id,
                nome=reg.nome,
            )
            regs = svc.listar()
            return {
                "registro": reg.to_dict(),
                "itens": [r.to_dict() for r in regs],
                "kpis": resumo_kpis(regs),
            }

        return self._run_async("consulta_rgp_saved", work, "Salvando registro…")

    def consultar_rgp_pessoa(self, registro_id: Any = "", cpf: Any = "") -> Dict[str, Any]:
        """Consulta MPA em processo isolado; grava só na planilha Consulta (sem REAP).

        Prefira JSON string: ``JSON.stringify({id, cpf})`` — evita a ponte pywebview
        transformar CPF com zero à esquerda em número.
        Também aceita dict/JSObject ou ``(id, cpf)``.
        """
        rid, cpf_digits = _parse_consulta_rgp_args(registro_id, cpf)

        def work():
            svc = self._ensure_consulta_rgp(require_write=True)
            reg = svc.por_id(rid) if rid else None
            if reg is None and cpf_digits:
                reg = svc.por_cpf(cpf_digits)
            if reg is None:
                raise ValueError(
                    "Registro não encontrado. Cadastre o sócio na Consulta RGP primeiro."
                )

            # Planilha + arg JS (ambos normalizados; arg cobre planilha corrompida).
            # NÃO trocar CPF da planilha por outro só porque o arg tem zero à esquerda
            # e DV válido — isso inventava CPF diferente (ex. 10683919515 → 01068391952).
            sheet_cpf = normalize_cpf(reg.cpf)
            arg_cpf = normalize_cpf(cpf_digits) if cpf_digits else ""
            if len(sheet_cpf) == 11:
                alvo = sheet_cpf
            elif len(arg_cpf) == 11:
                alvo = arg_cpf
            else:
                alvo = sheet_cpf or arg_cpf
            if len(alvo) != 11:
                raise ValueError(
                    "CPF inválido para consulta. "
                    f"Planilha={reg.cpf!r} arg={cpf_digits!r}. "
                    "Edite o cadastro e salve o CPF completo (11 dígitos)."
                )
            # Regrava normalizado se a planilha tinha valor corrompido (float .0)
            if sheet_cpf != alvo or str(reg.cpf or "").strip() != alvo:
                reg.cpf = alvo
                try:
                    svc.salvar(reg.to_dict())
                except Exception:  # noqa: BLE001
                    pass

            try:
                result = consultar_cpf_isolado(alvo)
            except Exception as exc:  # noqa: BLE001
                raise ValueError(
                    f"Consulta automática falhou ({exc}). "
                    "Use «Abrir site MPA» se precisar consultar manualmente."
                ) from exc

            if not result.get("ok"):
                raise ValueError(
                    str(result.get("error") or "Consulta MPA sem resultado.")
                    + " Use «Abrir site MPA» se precisar consultar manualmente."
                )

            data = result.get("data") if isinstance(result.get("data"), dict) else {}
            if not data and isinstance(result.get("situacao"), str):
                data = {"situacao": result.get("situacao")}
            if not data:
                raise ValueError("API MPA não retornou dados.")

            aplicar_resultado_mpa(reg, data, ator="Sistema")
            # Robô: situação verdadeira do MPA (não limitada ao filtro da UI)
            if result.get("situacao"):
                from controle.consulta_rgp import normalize_situacao as _norm

                sit_mpa = _norm(result.get("situacao"))
                if sit_mpa and sit_mpa != "Não consultado":
                    reg.situacao_rgp = sit_mpa
                elif not reg.situacao_rgp or reg.situacao_rgp == "Não consultado":
                    reg.situacao_rgp = sit_mpa or reg.situacao_rgp
            reg.cpf = alvo
            # 1 write quando a linha já existe (anti-cota vs salvar→listar+_row_index)
            row_idx = 0
            try:
                row_idx = int(svc._row_index(reg.id) or 0)
            except Exception:  # noqa: BLE001
                row_idx = 0
            if row_idx >= 2 and hasattr(svc, "atualizar_linha"):
                salvo = svc.atualizar_linha(reg, row_idx)
            else:
                salvo = svc.salvar(reg.to_dict())
            svc.registrar_auditoria(
                "consulta_rgp_consulta",
                f"Consultou MPA: {salvo.nome} → {salvo.situacao_rgp}",
                person_id=salvo.id,
                nome=salvo.nome,
            )
            regs = svc.listar()
            return {
                "registro": salvo.to_dict(),
                "situacao": salvo.situacao_rgp,
                "itens": [r.to_dict() for r in regs],
                "kpis": resumo_kpis(regs),
                "imports": {},
                "mensagem": f"Situação RGP gravada: {salvo.situacao_rgp}",
            }

        return self._run_async("consulta_rgp_consulta", work, "Consultando RGP no MPA…")

    def estimar_consulta_rgp_lote(self, quantidade: Any = 0) -> Dict[str, Any]:
        """Estimativa de tempo (modelo: ~20 min para 500 sócios)."""
        try:
            n = max(0, int(quantidade or 0))
        except (TypeError, ValueError):
            n = 0
        secs = n * float(SEGUNDOS_POR_CONSULTA_EST)
        mins = max(1, int(round(secs / 60.0))) if n else 0
        return ok(
            quantidade=n,
            segundos_por_consulta=SEGUNDOS_POR_CONSULTA_EST,
            segundos_total=round(secs, 1),
            minutos_estimados=mins,
            mensagem=(
                f"Estimativa: ~{mins} min para {n} sócio(s) "
                f"(consulta automática uma a uma)."
                if n
                else "Selecione ao menos um registro."
            ),
        )

    def cancelar_consulta_rgp_lote(self) -> Dict[str, Any]:
        self._consulta_rgp_lote_cancel = True
        return ok(mensagem="Cancelamento solicitado — para após a consulta atual.")

    def consultar_rgp_lote(self, payload: Any = None) -> Dict[str, Any]:
        """Consulta MPA em série (fila inteligente: pausa após N falhas + CSV erros)."""
        from webapp.consulta_rgp_ext import executar_lote

        local = _js_payload_to_dict(payload)
        ids = []
        ids_raw = local.get("ids") or []
        if isinstance(ids_raw, str):
            try:
                ids_raw = json.loads(ids_raw)
            except json.JSONDecodeError:
                ids_raw = [x.strip() for x in ids_raw.split(",") if x.strip()]
        if isinstance(ids_raw, (list, tuple)):
            ids = [str(x).strip() for x in ids_raw if str(x).strip()]
        todos = bool(local.get("todos"))
        try:
            max_falhas = int(local.get("max_falhas_seguidas") or 3)
        except (TypeError, ValueError):
            max_falhas = 3

        def work():
            self._consulta_rgp_lote_cancel = False
            svc = self._ensure_consulta_rgp(require_write=True)
            return executar_lote(
                svc=svc,
                regs=svc.listar(),
                ids=ids,
                todos=todos,
                cancel_check=lambda: self._consulta_rgp_lote_cancel,
                on_progress=lambda p: self._dispatch("consulta_rgp_lote_progress", p),
                on_status=lambda msg: self._dispatch("status", {"msg": msg}),
                max_falhas_seguidas=max_falhas,
            )

        n_hint = len(ids) if ids and not todos else 0
        busy = (
            f"Consulta automática em lote ({n_hint or 'todos'})…"
            if n_hint
            else "Consulta automática em lote…"
        )
        return self._run_async("consulta_rgp_consulta_lote", work, busy)

    def listar_consulta_rgp_vencidos(self, dias: Any = 30) -> Dict[str, Any]:
        """Função 4 — sócios Não consultado ou última consulta > N dias."""
        from webapp.consulta_rgp_ext import listar_vencidos_payload

        try:
            n = int(dias or 30)
        except (TypeError, ValueError):
            n = 30

        def work():
            return listar_vencidos_payload(self._ensure_consulta_rgp(), dias=n)

        return self._run_async(
            "consulta_rgp_vencidos", work, "Listando vencidos…"
        )

    def _consulta_rgp_para_export(self):
        """Só-leitura exporta sem senhas Gov.br."""
        svc = self._ensure_consulta_rgp()
        if self._pode_escrever:
            return svc
        return _ConsultaRgpSemSenha(svc)

    def exportar_consulta_rgp(self, payload: Any = None) -> Dict[str, Any]:
        """Função 3 — exporta CSV + HTML (imprimir PDF) com filtros."""
        from webapp.consulta_rgp_ext import exportar_payload

        local = _js_payload_to_dict(payload)

        def work():
            return exportar_payload(
                self._consulta_rgp_para_export(),
                municipio=str(local.get("municipio") or ""),
                situacao=str(local.get("situacao") or ""),
                ultima_de=str(local.get("ultima_de") or ""),
                ultima_ate=str(local.get("ultima_ate") or ""),
                ids=local.get("ids") if isinstance(local.get("ids"), list) else None,
                busca=str(local.get("busca") or local.get("q") or ""),
                municipios=local.get("municipios") if isinstance(local.get("municipios"), list) else None,
                situacoes=local.get("situacoes") if isinstance(local.get("situacoes"), list) else None,
                com_senha=str(local.get("com_senha") or ""),
                consulta_periodo=str(local.get("consulta_periodo") or ""),
                colunas=local.get("colunas") if isinstance(local.get("colunas"), list) else None,
                auto_print=bool(local.get("auto_print", True)),
                escopo=str(local.get("escopo") or ""),
                abrir_html=bool(local.get("abrir_html", True)),
                modo_geral=bool(local.get("modo_geral") or local.get("relatorio_geral")),
            )

        return self._run_async("consulta_rgp_export", work, "Exportando Consulta RGP…")

    def relatorio_geral_consulta_rgp(self, payload: Any = None) -> Dict[str, Any]:
        """Relatório HTML com filtros/seleção e colunas configuráveis."""
        from webapp.consulta_rgp_ext import exportar_payload

        local = _js_payload_to_dict(payload)

        def work():
            return exportar_payload(
                self._consulta_rgp_para_export(),
                municipio=str(local.get("municipio") or ""),
                situacao=str(local.get("situacao") or ""),
                ultima_de=str(local.get("ultima_de") or ""),
                ultima_ate=str(local.get("ultima_ate") or ""),
                ids=local.get("ids") if isinstance(local.get("ids"), list) else None,
                busca=str(local.get("busca") or local.get("q") or ""),
                municipios=local.get("municipios") if isinstance(local.get("municipios"), list) else None,
                situacoes=local.get("situacoes") if isinstance(local.get("situacoes"), list) else None,
                com_senha=str(local.get("com_senha") or ""),
                consulta_periodo=str(local.get("consulta_periodo") or ""),
                colunas=local.get("colunas") if isinstance(local.get("colunas"), list) else None,
                auto_print=bool(local.get("auto_print", True)),
                escopo=str(local.get("escopo") or ""),
                abrir_html=bool(local.get("abrir_html", True)),
                modo_geral=True,
            )

        return self._run_async(
            "consulta_rgp_export", work, "Gerando relatório HTML…"
        )

    def editar_lote_consulta_rgp(self, payload: Any = None) -> Dict[str, Any]:
        """Corrige em lote: nome, CPF, telefone, município, observação (+ senha Gov.br)."""
        from webapp.consulta_rgp_ext import editar_lote_payload

        local = _js_payload_to_dict(payload)
        itens = local.get("itens") or local.get("rows") or []
        atualizar_govbr = bool(local.get("atualizar_govbr"))
        govbr = str(local.get("govbr_senha") or "") if atualizar_govbr else None

        def work():
            return editar_lote_payload(
                self._ensure_consulta_rgp(require_write=True),
                itens if isinstance(itens, list) else [],
                govbr_senha=govbr,
                atualizar_govbr=atualizar_govbr,
            )

        return self._run_async(
            "consulta_rgp_editar_lote",
            work,
            "Salvando correções em lote…",
        )

    def excluir_consulta_rgp(self, payload: Any = None) -> Dict[str, Any]:
        """Exclui um ou vários sócios da planilha Consulta RGP."""
        from webapp.consulta_rgp_ext import excluir_payload

        local = _js_payload_to_dict(payload)
        ids = local.get("ids") if isinstance(local, dict) else payload
        if isinstance(local, dict) and local.get("id") and not ids:
            ids = [local.get("id")]

        def work():
            return excluir_payload(self._ensure_consulta_rgp(require_write=True), ids)

        return self._run_async(
            "consulta_rgp_excluir",
            work,
            "Excluindo da Consulta RGP…",
        )

    def abrir_csv_erros_consulta_rgp(self, path: str = "") -> Dict[str, Any]:
        """Abre CSV de erros da fila inteligente."""
        p = Path(str(path or "")).expanduser()
        if not p.is_file():
            return err("Arquivo de erros não encontrado.")
        try:
            _abrir_no_navegador(p) if p.suffix.lower() in (".html", ".htm", ".pdf") else None
            if os.name == "nt":
                os.startfile(str(p))  # type: ignore[attr-defined]
            else:
                webbrowser.open(p.as_uri())
            return ok(path=str(p))
        except Exception as exc:  # noqa: BLE001
            return err(str(exc))

    def load_consulta_rgp_auditoria(self) -> Dict[str, Any]:
        def work():
            svc = self._ensure_consulta_rgp()
            evts = svc.listar_auditoria(500)
            return {
                "itens": [
                    {
                        "id": e.id,
                        "em": e.em,
                        "usuario": e.usuario,
                        "acao": e.acao,
                        "detalhe": e.detalhe,
                        "person_id": e.person_id,
                        "nome": e.nome,
                    }
                    for e in evts
                ]
            }

        return self._run_async(
            "consulta_rgp_auditoria", work, "Carregando auditoria Consulta RGP…"
        )

    # ---- Informe Mensal (REAP mês a mês, planilha REAP) ------------------

    def _ensure_informe(self, *, require_write: bool = False) -> InformeMensalService:
        svc = self._ensure_service(require_write=require_write)
        if self._informe_service is None or self._informe_service.client is not svc.client:
            self._informe_service = InformeMensalService(svc.client)
        self._informe_service.actor = self._admin_user
        return self._informe_service

    @staticmethod
    def _informe_especies_cfg() -> List[str]:
        return im.especies_ativas_de_config(load_config())

    @staticmethod
    def _carregar_peixes_informe(inf: InformeMensalService) -> None:
        """Peixes cadastrados na planilha entram no catálogo de todos os PCs."""
        try:
            extras = inf.listar_peixes()
        except Exception:  # noqa: BLE001
            extras = []
        im.definir_peixes_extras(extras)
        try:
            precos = inf.listar_precos()
        except Exception:  # noqa: BLE001
            precos = []
        im.aplicar_precos(precos)

    def _erro_nao_admin_informe(self) -> Optional[Dict[str, Any]]:
        try:
            self._revalidar_sessao()
        except Exception as exc:  # noqa: BLE001
            return err(str(exc))
        if not self._logged_in or self._papel != usuarios_mod.PAPEL_ADMIN:
            return err("Só o admin cadastra, precifica ou configura os peixes do Informe Mensal.")
        return None

    @classmethod
    def _informe_meta(cls) -> Dict[str, Any]:
        ativas = cls._informe_especies_cfg()
        n_pool = len(ativas)
        return {
            "catalogo": im.catalogo(ativas),
            "especies_ativas": ativas,
            "especies_todas": list(im.ESPECIES_TODAS),
            "especies_minimo": im.MIN_ESPECIES_ATIVAS,
            "meses_ordem": im.MESES_ORDEM,
            "meses_pesca": im.MESES_PESCA,
            "meses_piracema": im.MESES_PIRACEMA,
            "meses_titulo": im.MES_TITULO,
            "piracema_label": im.PIRACEMA_LABEL,
            "kg_min": im.KG_MIN,
            "kg_max": im.KG_MAX,
            "kg_ano_min": im.KG_ANO_MIN,
            "kg_ano_max": im.KG_ANO_MAX,
            "dias_min": im.DIAS_MIN,
            "dias_max": im.DIAS_MAX,
            "contagens": list(im.contagens_para_pool(n_pool)),
            "municipios": list(im.MUNICIPIOS),
            "probabilidades": im.probabilidades_plano(n_pool=n_pool),
            "regras_probabilidade": im.regras_probabilidade(),
            "permite_8": n_pool >= 8,
        }

    @staticmethod
    def _informe_socio_dict(p: Any, meses: Dict[str, "im.InformeMes"], ano: int) -> Dict[str, Any]:
        cpf = only_digits(p.cpf)
        return {
            "id": p.id,
            "nome": format_nome(p.nome),
            "cpf": format_cpf(p.cpf),
            "cpf_raw": cpf,
            "telefone": getattr(p, "telefone", "") or "",
            "municipio": getattr(p, "municipio", "") or "",
            "municipio_reap": im.normalizar_municipio(getattr(p, "municipio", "")),
            "meses": {m: r.to_dict() for m, r in meses.items()},
            "textos": {m: im.texto_para_site(r) for m, r in meses.items() if r.houve_pesca},
            "resumo": im.resumo_socio(meses, cpf or p.id, ano),
        }

    def _informe_pessoa(self, person_id: str) -> Any:
        pessoa = next(
            (p for p in self._ensure_service().get_all_pessoas() if p.id == person_id),
            None,
        )
        if not pessoa:
            raise ValueError("Sócio não encontrado na planilha REAP.")
        return pessoa

    def load_informe_mensal(self, ano: Any = None) -> Dict[str, Any]:
        ano_i = _informe_ano(ano)

        def work():
            svc = self._ensure_service()
            inf = self._ensure_informe()
            self._carregar_peixes_informe(inf)
            por_pessoa: Dict[str, Dict[str, im.InformeMes]] = {}
            for r in inf.listar(ano_i):
                por_pessoa.setdefault(r.person_id, {})[r.mes] = r
            socios = [
                self._informe_socio_dict(p, por_pessoa.get(p.id, {}), ano_i)
                for p in svc.get_all_pessoas()
            ]
            socios.sort(key=lambda s: s["nome"].casefold())
            iguais = _informe_iguais(por_pessoa, socios)
            return {"ano": ano_i, "socios": socios, "padroes_iguais": iguais, **self._informe_meta()}

        return self._run_async("informe_lista", work, "Carregando Informe Mensal…")

    def abrir_informe_tabela(self, ano: Any = None) -> Dict[str, Any]:
        """Gera HTML com tabela por sócio (meses preenchidos) e abre no navegador."""
        from controle.informe_mensal_relatorio import (
            montar_html_informe,
            nome_arquivo_informe,
            salvar_html_informe,
        )

        ano_i = _informe_ano(ano)

        def work():
            svc = self._ensure_service()
            inf = self._ensure_informe()
            self._carregar_peixes_informe(inf)
            por_pessoa: Dict[str, Dict[str, im.InformeMes]] = {}
            for r in inf.listar(ano_i):
                por_pessoa.setdefault(r.person_id, {})[r.mes] = r
            pessoas = svc.get_all_pessoas()
            socios = [
                self._informe_socio_dict(p, por_pessoa.get(p.id, {}), ano_i)
                for p in pessoas
            ]
            socios.sort(key=lambda s: s["nome"].casefold())
            html_txt = montar_html_informe(
                org_short=ORG_SHORT,
                org_full=ORG_FULL,
                ano=ano_i,
                socios=socios,
                por_pessoa=por_pessoa,
            )
            path = salvar_html_informe(html_txt, nome_arquivo=nome_arquivo_informe(ano_i))
            inf.registrar_auditoria(
                "abrir_tabela_informe",
                f"Abriu tabela HTML do Informe Mensal {ano_i} ({len(socios)} sócio(s)) — {path.name}",
                ano=str(ano_i),
            )
            return {
                "path": str(path),
                "total": len(socios),
                "com_meses": sum(1 for s in socios if (s.get("resumo") or {}).get("gerados")),
                "ano": ano_i,
            }

        return self._run_async("informe_tabela", work, "Gerando tabela do Informe Mensal…")

    def abrir_informe_tabela_socio(self, payload: Any = None) -> Dict[str, Any]:
        """HTML individual: só os meses preenchidos daquele sócio → abre no navegador."""
        from controle.informe_mensal_relatorio import (
            montar_html_informe_socio,
            nome_arquivo_informe_socio,
            salvar_html_informe,
        )

        data = _informe_args(payload)
        pid = str(data.get("person_id") or "").strip()
        ano_i = _informe_ano(data.get("ano"))
        if not pid:
            return err("Sócio não informado.")

        def work():
            inf = self._ensure_informe()
            pessoa = self._informe_pessoa(pid)
            meses = inf.meses_do_socio(pid, ano_i)
            socio = self._informe_socio_dict(pessoa, meses, ano_i)
            feitos = sum(1 for m in im.MESES_PESCA if m in meses and meses[m].houve_pesca)
            if feitos == 0:
                raise ValueError(
                    f"{socio['nome']} ainda não tem mês preenchido em {ano_i}. "
                    "Gere ao menos um REAP antes de abrir a tabela."
                )
            html_txt = montar_html_informe_socio(
                org_short=ORG_SHORT,
                org_full=ORG_FULL,
                ano=ano_i,
                socio=socio,
                meses=meses,
            )
            path = salvar_html_informe(
                html_txt, nome_arquivo=nome_arquivo_informe_socio(ano_i, socio["nome"])
            )
            inf.registrar_auditoria(
                "abrir_tabela_socio",
                f"Abriu tabela HTML individual de {socio['nome']} — {ano_i} "
                f"({feitos} mês(es)) — {path.name}",
                person_id=pid,
                nome=socio["nome"],
                ano=str(ano_i),
            )
            return {
                "path": str(path),
                "person_id": pid,
                "nome": socio["nome"],
                "meses": feitos,
                "ano": ano_i,
            }

        return self._run_async(
            "informe_tabela_socio", work, "Gerando tabela individual do sócio…"
        )

    def salvar_informe_especies(self, payload: Any = None) -> Dict[str, Any]:
        """Config exclusiva do Informe Mensal: peixes que entram no cérebro (universal)."""
        data = _informe_args(payload)
        erros = im.validar_especies_ativas(data.get("especies"))
        if erros:
            return err(" ".join(erros))
        ativas = im.normalizar_especies_ativas(data.get("especies"))
        bloqueio = self._erro_nao_admin_informe()
        if bloqueio:
            return bloqueio

        def work():
            cfg = load_config()
            cfg.update(im.config_especies(ativas))
            save_config(cfg)
            try:
                self._ensure_informe(require_write=True).registrar_auditoria(
                    "config_especies_informe",
                    f"Configurou peixes ({len(ativas)}): {', '.join(ativas)}",
                )
            except Exception:  # noqa: BLE001
                pass
            return {
                "especies_ativas": ativas,
                "catalogo": im.catalogo(ativas),
                "contagens": list(im.contagens_para_pool(len(ativas))),
                "permite_8": len(ativas) >= 8,
                "probabilidades": im.probabilidades_plano(n_pool=len(ativas)),
                "resumo": im.resumo_especies_ativas(ativas),
            }

        return self._run_async(
            "informe_especies_salvas", work, "Salvando peixes do Informe Mensal…"
        )

    def cadastrar_informe_peixe(self, payload: Any = None) -> Dict[str, Any]:
        """Admin cadastra um peixe novo (aba InformePeixes); aparece para todos."""
        data = _informe_args(payload)
        bloqueio = self._erro_nao_admin_informe()
        if bloqueio:
            return bloqueio

        def work():
            inf = self._ensure_informe(require_write=True)
            self._carregar_peixes_informe(inf)
            nome, preco = im.validar_novo_peixe(data.get("nome"), data.get("preco"))
            inf.cadastrar_peixe(nome, preco)
            self._carregar_peixes_informe(inf)
            inf.registrar_auditoria(
                "cadastrar_peixe_informe", f"Cadastrou peixe {nome} (R$ {preco:.0f}/kg)"
            )
            return {"nome": nome, "preco": preco, **self._informe_meta()}

        return self._run_async("informe_peixe_cadastrado", work, "Cadastrando peixe…")

    def salvar_informe_precos(self, payload: Any = None) -> Dict[str, Any]:
        """Admin grava o preço base (R$/kg). O gerador usa esse valor na hora."""
        data = _informe_args(payload)
        bloqueio = self._erro_nao_admin_informe()
        if bloqueio:
            return bloqueio

        def work():
            inf = self._ensure_informe(require_write=True)
            self._carregar_peixes_informe(inf)
            itens = im.validar_precos_informe(data.get("precos"))
            inf.salvar_precos(itens)
            self._carregar_peixes_informe(inf)
            texto = ", ".join(f"{n} R$ {p:.0f}" for n, p in itens)
            inf.registrar_auditoria("precificar_informe", f"Precificou: {texto}")
            return {"precos": [{"nome": n, "preco": p} for n, p in itens], **self._informe_meta()}

        return self._run_async("informe_precos_salvos", work, "Salvando preços dos peixes…")

    def gerar_informe_mes(self, payload: Any) -> Dict[str, Any]:
        data = _informe_args(payload)
        pid = str(data.get("person_id") or "").strip()
        ano_i = _informe_ano(data.get("ano"))
        try:
            mes = im.normalizar_mes(data.get("mes"))
        except ValueError as exc:
            return err(str(exc))
        if mes in im.MESES_PIRACEMA:
            return err(f"{im.MES_TITULO[mes]} é {im.PIRACEMA_LABEL} — não há REAP de pesca.")
        if not pid:
            return err("Sócio não informado.")
        municipio_req = str(data.get("municipio") or "").strip()

        def work():
            inf = self._ensure_informe(require_write=True)
            self._carregar_peixes_informe(inf)
            pessoa = self._informe_pessoa(pid)
            todos = inf.listar()
            do_ano = [r for r in todos if r.ano == ano_i]
            salvos = {r.mes: r for r in do_ano if r.person_id == pid}
            anterior = salvos.get(mes)
            globais = {r.assinatura for r in todos if r.assinatura}
            peixes_outros: Dict[str, int] = {}
            precos_outros: Dict[str, List[float]] = {}
            for r in do_ano:
                if r.person_id == pid or r.mes != mes or not r.houve_pesca:
                    continue
                for e in r.especies:
                    peixes_outros[e.nome] = peixes_outros.get(e.nome, 0) + 1
                    precos_outros.setdefault(e.nome, []).append(float(e.valor))
            nomes_outros = {
                im.assinatura_nomes(e.nome for e in r.especies)
                for r in do_ano
                if r.person_id != pid and r.mes == mes and r.houve_pesca
            }
            por_pessoa: Dict[str, Dict[str, im.InformeMes]] = {}
            for r in do_ano:
                por_pessoa.setdefault(r.person_id, {})[r.mes] = r
            outros_planos: Dict[str, int] = {}
            for outro, meses_outro in por_pessoa.items():
                if outro == pid:
                    continue
                pl = im.plano_do_socio(meses_outro)
                if pl:
                    txt = im.plano_str(pl)
                    outros_planos[txt] = outros_planos.get(txt, 0) + 1
            municipio = (
                municipio_req
                or (anterior.municipio if anterior else "")
                or pessoa.municipio
            )
            res = im.gerar_mes(
                person_id=pid,
                cpf=only_digits(pessoa.cpf),
                nome=format_nome(pessoa.nome),
                telefone=getattr(pessoa, "telefone", "") or "",
                ano=ano_i,
                mes=mes,
                salvos=salvos,
                assinaturas_globais=globais,
                nomes_outros_socios=nomes_outros,
                outros_planos=outros_planos,
                municipio=municipio,
                ator=self._admin_user,
                especies_ativas=self._informe_especies_cfg(),
                peixes_outros_socios=peixes_outros,
                precos_outros_socios=precos_outros,
            )
            reg = res.informe
            if anterior:
                reg.gerado_em = anterior.gerado_em or reg.gerado_em
                reg.gerado_por = anterior.gerado_por or reg.gerado_por
            inf.salvar(reg)
            salvos[mes] = reg
            por_pessoa[pid] = salvos
            titulo = f"{im.MES_TITULO[mes]}/{ano_i}"
            resumo_mes = f"{len(reg.especies)} espécies, {reg.dias} dias, {reg.peso_mes} kg"
            if anterior:
                acao = "regerar_informe"
                detalhe = (
                    f"Regerou REAP de {titulo} — {reg.nome}: {resumo_mes} "
                    f"(antes: {len(anterior.especies)} espécies, {anterior.dias} dias, "
                    f"{anterior.peso_mes} kg)"
                )
            else:
                acao = "gerar_informe"
                detalhe = f"Gerou REAP de {titulo} — {reg.nome}: {resumo_mes}"
            inf.registrar_auditoria(
                acao, detalhe, person_id=pid, nome=reg.nome, ano=str(ano_i), meses=mes
            )
            return {
                "ano": ano_i,
                "mes": mes,
                "regerado": bool(anterior),
                "avisos": res.avisos,
                "socio": self._informe_socio_dict(pessoa, salvos, ano_i),
                "padroes_iguais": [
                    g for g in im.padroes_iguais(por_pessoa) if pid in g["socios"]
                ],
            }

        return self._run_async("informe_gerado", work, "Gerando REAP do mês…")

    def salvar_informe_mes(self, payload: Any) -> Dict[str, Any]:
        data = _informe_args(payload)
        pid = str(data.get("person_id") or "").strip()
        ano_i = _informe_ano(data.get("ano"))
        try:
            mes = im.normalizar_mes(data.get("mes"))
        except ValueError as exc:
            return err(str(exc))
        especies = im.especies_de_payload(data.get("especies"), mes)
        dias = data.get("dias")
        erros = im.validar_mes(mes, dias, especies)
        if erros:
            return err(" ".join(erros))
        if not pid:
            return err("Sócio não informado.")
        municipio_req = str(data.get("municipio") or "").strip()

        def work():
            inf = self._ensure_informe(require_write=True)
            pessoa = self._informe_pessoa(pid)
            salvos = inf.meses_do_socio(pid, ano_i)
            anterior = salvos.get(mes)
            if not anterior:
                raise ValueError("Gere o REAP do mês antes de editar.")
            conj = im.assinatura_conjunto(especies)
            for m, r in salvos.items():
                if m != mes and r.houve_pesca and im.assinatura_conjunto(r.especies) == conj:
                    raise ValueError(
                        f"Mesmo conjunto de espécies/kg de {im.MES_TITULO[m]} — altere algum valor."
                    )
            agora = im.now_stamp()
            reg = im.InformeMes(
                id=anterior.id,
                person_id=pid,
                cpf=only_digits(pessoa.cpf),
                nome=format_nome(pessoa.nome),
                telefone=getattr(pessoa, "telefone", "") or "",
                ano=ano_i,
                mes=mes,
                houve_pesca=True,
                dias=int(dias),
                especies=especies,
                municipio=im.normalizar_municipio(municipio_req or anterior.municipio),
                assinatura=im.assinatura_mes(mes, especies, int(dias)),
                gerado_em=anterior.gerado_em,
                gerado_por=anterior.gerado_por,
                atualizado_em=agora,
                atualizado_por=self._admin_user,
                motor=f"{im.MOTOR}+manual",
                plano=anterior.plano,
            )
            mudancas = _informe_diff(anterior, reg)
            if not mudancas:
                return {
                    "ano": ano_i,
                    "mes": mes,
                    "sem_mudanca": True,
                    "avisos": im.validar_ano(salvos, n_pool=len(self._informe_especies_cfg())),
                    "socio": self._informe_socio_dict(pessoa, salvos, ano_i),
                }
            inf.salvar(reg)
            salvos[mes] = reg
            inf.registrar_auditoria(
                "editar_informe",
                f"Alterou REAP de {im.MES_TITULO[mes]}/{ano_i} — {reg.nome}: {'; '.join(mudancas)}",
                person_id=pid,
                nome=reg.nome,
                ano=str(ano_i),
                meses=mes,
            )
            return {
                "ano": ano_i,
                "mes": mes,
                "avisos": im.validar_ano(salvos, n_pool=len(self._informe_especies_cfg())),
                "socio": self._informe_socio_dict(pessoa, salvos, ano_i),
            }

        return self._run_async("informe_salvo", work, "Salvando REAP do mês…")

    def excluir_informe_mes(self, payload: Any) -> Dict[str, Any]:
        data = _informe_args(payload)
        pid = str(data.get("person_id") or "").strip()
        ano_i = _informe_ano(data.get("ano"))
        try:
            mes = im.normalizar_mes(data.get("mes"))
        except ValueError as exc:
            return err(str(exc))

        def work():
            inf = self._ensure_informe(require_write=True)
            pessoa = self._informe_pessoa(pid)
            removido = inf.excluir(pid, ano_i, mes)
            if not removido:
                raise ValueError("Esse mês ainda não foi gerado.")
            inf.registrar_auditoria(
                "excluir_informe",
                f"Excluiu REAP de {im.MES_TITULO[mes]}/{ano_i} — {removido.nome} "
                f"({len(removido.especies)} espécies, {removido.dias} dias, {removido.peso_mes} kg)",
                person_id=pid,
                nome=removido.nome,
                ano=str(ano_i),
                meses=mes,
            )
            salvos = inf.meses_do_socio(pid, ano_i)
            return {
                "ano": ano_i,
                "mes": mes,
                "socio": self._informe_socio_dict(pessoa, salvos, ano_i),
            }

        return self._run_async("informe_excluido", work, "Excluindo REAP do mês…")

    def load_informe_auditoria(self) -> Dict[str, Any]:
        def work():
            evts = self._ensure_informe().listar_auditoria(500)
            return {
                "itens": [
                    {
                        "id": e.id,
                        "em": e.em,
                        "usuario": e.usuario,
                        "acao": e.acao,
                        "detalhe": e.detalhe,
                        "person_id": e.person_id,
                        "nome": e.nome,
                        "ano": e.ano,
                        "mes": e.meses,
                    }
                    for e in evts
                ]
            }

        return self._run_async("informe_auditoria", work, "Carregando auditoria do Informe Mensal…")

    def importar_consulta_rgp(self, registro_id: str = "") -> Dict[str, Any]:
        return err(
            "Envio para REAP/Defeso desativado nesta etapa. "
            "Os dados ficam só na planilha Consulta RGP."
        )

    def abrir_consulta_rgp_mpa(self, cpf: Any = "") -> Dict[str, Any]:
        try:
            abrir_site_mpa_no_navegador(normalize_cpf(cpf) or str(cpf or ""))
            return ok(url=MPA_CONSULTA_URL)
        except Exception as exc:  # noqa: BLE001
            return err(str(exc))

    def get_emitir_dec_fontes(self) -> Dict[str, Any]:
        """Times, Arial e Calibri do EmitirDec. Exige login; não grava planilha."""
        try:
            self._revalidar_sessao()
        except Exception as exc:  # noqa: BLE001
            return err(str(exc))
        from controle.emitir_dec import DEFAULT_FONTE as fonte_padrao
        from controle.emitir_dec import listar_fontes as fontes_dec

        return ok(fontes=fontes_dec(), fonte=fonte_padrao)

    def emitir_declaracao(self, payload: Any = None, fonte_id: str = "") -> Dict[str, Any]:
        """Preenche endereço e/ou filiação e abre o PDF no navegador."""
        data = _informe_args(payload)
        fonte_arg = str(fonte_id or data.get("fonte") or "").strip()

        def work():
            self._revalidar_sessao()
            from controle.emitir_dec import gerar_pdf, normalize_fonte as fonte_dec

            fonte = fonte_dec(fonte_arg)
            path = gerar_pdf(data, fonte_id=fonte)
            try:
                _abrir_no_navegador(path)
            except OSError as exc:
                raise ValueError(f"Não foi possível abrir a declaração: {exc}") from exc
            return {"path": str(path), "fonte": fonte}

        return self._run_async("emitir_dec", work, "Gerando declarações…")

    def quit_app(self) -> Dict[str, Any]:
        if webview:
            webview.destroy_window()
        return ok()



def _informe_args(payload: Any) -> Dict[str, Any]:
    if isinstance(payload, str):
        text = payload.strip()
        if not text:
            return {}
        try:
            data = json.loads(text)
        except json.JSONDecodeError:
            return {}
        return data if isinstance(data, dict) else {}
    if payload is None:
        return {}
    return _js_payload_to_dict(payload)


def _informe_iguais(
    por_pessoa: Dict[str, Dict[str, "im.InformeMes"]], socios: List[Dict[str, Any]]
) -> List[Dict[str, Any]]:
    """Grupos de padrões iguais com nomes; marca ``padrao_igual`` em cada sócio."""
    nomes = {s["id"]: s["nome"] for s in socios}
    grupos = im.padroes_iguais(por_pessoa)
    marcados: Dict[str, List[str]] = {}
    for g in grupos:
        g["nomes"] = [nomes.get(pid, pid) for pid in g["socios"]]
        for pid in g["socios"]:
            marcados.setdefault(pid, []).append(g["descricao"])
    for s in socios:
        s["padrao_igual"] = marcados.get(s["id"], [])
    return grupos


def _informe_ano(valor: Any) -> int:
    try:
        ano = int(str(valor).strip())
    except (TypeError, ValueError):
        return datetime.now().year
    return ano if 2000 <= ano <= 2100 else datetime.now().year


def _informe_diff(antes: "im.InformeMes", depois: "im.InformeMes") -> List[str]:
    out: List[str] = []
    if int(antes.dias) != int(depois.dias):
        out.append(f"dias {antes.dias}→{depois.dias}")
    if antes.municipio != depois.municipio:
        out.append(f"município {antes.municipio}→{depois.municipio}")
    kg_antes = {e.nome: int(e.kg) for e in antes.especies}
    kg_depois = {e.nome: int(e.kg) for e in depois.especies}
    for nome, kg in kg_depois.items():
        if nome not in kg_antes:
            out.append(f"+{nome} {kg} kg")
        elif kg_antes[nome] != kg:
            out.append(f"{nome} {kg_antes[nome]}→{kg} kg")
    for nome in kg_antes:
        if nome not in kg_depois:
            out.append(f"−{nome}")
    if not out and [e.nome for e in antes.especies] != [e.nome for e in depois.especies]:
        out.append("ordem das espécies")
    return out


def _parse_consulta_rgp_args(registro_id: Any = "", cpf: Any = "") -> tuple[str, str]:
    """Extrai (id, cpf_normalizado) de JSON string, dict/JSObject ou args clássicos."""
    # 1) JSON string — forma preferida (sem coerção de zero à esquerda na ponte)
    if isinstance(registro_id, str):
        text = registro_id.strip()
        if text.startswith("{"):
            try:
                data = json.loads(text)
            except json.JSONDecodeError:
                data = {}
            if isinstance(data, dict):
                rid = str(data.get("id") or data.get("registro_id") or "").strip()
                digits = normalize_cpf(data.get("cpf") or cpf or "")
                return rid, digits
    # 2) dict / JSObject
    if _is_consulta_payload(registro_id):
        data = _js_payload_to_dict(registro_id)
        rid = str(data.get("id") or data.get("registro_id") or "").strip()
        digits = normalize_cpf(data.get("cpf") or cpf or "")
        return rid, digits
    # 3) (id, cpf) clássico
    return str(registro_id or "").strip(), normalize_cpf(cpf)


def _is_consulta_payload(obj: Any) -> bool:
    """True se o 1º arg de consultar_rgp_pessoa é dict/JSON/JSObject com id/cpf."""
    if isinstance(obj, dict):
        return True
    if isinstance(obj, str) and obj.strip().startswith("{"):
        return True
    try:
        keys = {str(k) for k in list(obj.keys())}  # type: ignore[attr-defined]
    except Exception:
        return False
    return bool(keys & {"id", "cpf", "registro_id"})


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


class _ConsultaRgpSemSenha:
    """Proxy de leitura do ConsultaRgpService que nunca expõe senhas Gov.br."""

    def __init__(self, svc: Any) -> None:
        self._svc = svc

    def listar(self, *args: Any, **kwargs: Any) -> List[Any]:
        import copy

        out = []
        for reg in self._svc.listar(*args, **kwargs):
            limpo = copy.copy(reg)
            if hasattr(limpo, "govbr_senha"):
                limpo.govbr_senha = ""
            out.append(limpo)
        return out

    def get_govbr_senha(self) -> str:
        return ""

    def __getattr__(self, name: str) -> Any:
        return getattr(self._svc, name)


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
