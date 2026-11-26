# -*- coding: utf-8 -*-
"""Bateria: login online (aba Usuarios), PBKDF2, papéis, permissões e exclusões."""

from __future__ import annotations

import sys
import types
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))

if "tkinter" not in sys.modules:
    try:
        import tkinter as _tk  # noqa: F401
    except Exception:
        tk = types.ModuleType("tkinter")
        tk.TclError = Exception
        for _name in ("Canvas", "Tk", "Frame", "Label", "Button", "Toplevel", "Entry", "Text",
                      "Scrollbar", "Listbox", "Checkbutton", "Radiobutton", "Menu", "Widget",
                      "StringVar", "BooleanVar", "IntVar", "Misc", "Event", "PhotoImage"):
            setattr(tk, _name, type(_name, (), {"__init__": lambda self, *a, **k: None}))
        sys.modules["tkinter"] = tk
        for _sub in ("ttk", "messagebox", "filedialog", "font", "simpledialog"):
            mod = types.ModuleType(_sub)
            setattr(tk, _sub, mod)
            sys.modules[f"tkinter.{_sub}"] = mod
        sys.modules["tkinter.ttk"].Style = type("Style", (), {"__init__": lambda self, *a, **k: None})
        for _name in ("Frame", "Label", "Button", "Entry", "Combobox", "Treeview", "Scrollbar",
                      "Checkbutton", "Notebook", "Progressbar"):
            setattr(sys.modules["tkinter.ttk"], _name, type(_name, (), {"__init__": lambda self, *a, **k: None}))

from controle import exclusoes as ex  # noqa: E402
from controle import usuarios as u  # noqa: E402


def test_pbkdf2_hash_e_verify() -> None:
    h = u.hash_senha("segredo123")
    assert h.startswith("pbkdf2_sha256$")
    assert u.verificar_senha("segredo123", h)
    assert not u.verificar_senha("errada", h)
    # legado texto puro
    assert u.verificar_senha("plain", "plain")
    assert u.senha_precisa_rehash("plain")
    assert not u.senha_precisa_rehash(h)


def test_papeis_e_modulos() -> None:
    admin = u.novo_usuario(email="a@x.com", senha="123456", papel="admin")
    assert admin.pode_admin_usuarios and admin.pode_escrever
    assert admin.pode_cadastrar and admin.pode_editar and admin.pode_excluir_direto
    assert admin.permite_modulo("defeso")
    op = u.novo_usuario(
        email="o@x.com", senha="123456", papel="operador", modulos=["reap", "informe"]
    )
    assert op.pode_escrever and not op.pode_admin_usuarios
    assert op.pode_cadastrar and op.pode_editar and op.pode_pedir_exclusao
    assert not op.pode_excluir_direto
    assert op.permite_modulo("reap") and not op.permite_modulo("defeso")
    leit = u.novo_usuario(email="l@x.com", senha="123456", papel="leitura")
    assert not leit.pode_escrever
    assert not leit.pode_cadastrar and not leit.pode_editar
    assert leit.permite_modulo("reap")  # módulos vazios = todos


def test_permissoes_finas_e_celula() -> None:
    op = u.novo_usuario(
        email="p@x.com",
        senha="abcdef",
        papel="operador",
        permissoes=["cadastrar"],
    )
    assert op.pode_cadastrar and not op.pode_editar
    assert not op.pode_pedir_exclusao
    row = op.to_row()
    assert len(row) == len(u.USUARIOS_HEADER)
    assert "cadastrar" in row[10]
    back = u.row_to_usuario(row)
    assert back and back.permissoes == ["cadastrar"]
    # vazio na planilha = padrão do papel
    cells = list(row)
    cells[10] = ""
    back2 = u.row_to_usuario(cells)
    assert back2 and u.PERM_EDITAR in back2.permissoes
    # marcador nenhuma
    cells[10] = "nenhuma"
    back3 = u.row_to_usuario(cells)
    assert back3 and back3.permissoes == []


def test_pedido_exclusao_roundtrip() -> None:
    ped = ex.novo_pedido(
        person_id="pid-1",
        nome="Maria",
        cpf="12345678901",
        pedido_por="op@x.com",
        motivo="duplicado",
    )
    assert ped.status == ex.STATUS_PENDENTE
    back = ex.row_to_pedido(ped.to_row())
    assert back and back.person_id == "pid-1" and back.motivo == "duplicado"
    d = back.to_dict()
    assert d["pendente"] is True


def test_autenticar_bloqueado() -> None:
    ativo = u.novo_usuario(email="ok@x.com", senha="abcdef", ativo=True)
    bloqueado = u.novo_usuario(email="no@x.com", senha="abcdef", ativo=False)
    hit, err = u.autenticar([ativo, bloqueado], "ok@x.com", "abcdef")
    assert hit and not err
    hit2, err2 = u.autenticar([ativo, bloqueado], "no@x.com", "abcdef")
    assert hit2 is None and "bloqueado" in err2.lower()
    hit3, err3 = u.autenticar([ativo], "ok@x.com", "errada")
    assert hit3 is None and err3


def test_row_roundtrip() -> None:
    user = u.novo_usuario(
        email="Maria@Sinapesc.ORG",
        senha="abcdef",
        nome="Maria",
        papel="operador",
        modulos=["defeso"],
    )
    back = u.row_to_usuario(user.to_row())
    assert back and back.email == "maria@sinapesc.org"
    assert back.modulos == ["defeso"]
    assert u.verificar_senha("abcdef", back.senha_hash)
    pub = back.to_public_dict()
    assert "senha" not in pub and "senha_hash" not in pub
    assert "pode_pedir_exclusao" in pub


def test_client_tem_aba_usuarios_e_exclusoes() -> None:
    from sheets.client import (
        EXCLUSOES_HEADER,
        EXCLUSOES_TAB,
        USUARIOS_HEADER,
        USUARIOS_TAB,
    )

    assert USUARIOS_TAB == "Usuarios"
    assert "senhaHash" in USUARIOS_HEADER
    assert "papel" in USUARIOS_HEADER
    assert "permissoes" in USUARIOS_HEADER
    assert EXCLUSOES_TAB == "ExclusoesPendentes"
    assert "pedidoPor" in EXCLUSOES_HEADER


def test_js_ui_usuarios_e_filtro() -> None:
    js = (ROOT / "web" / "js" / "app.js").read_text(encoding="utf-8")
    assert 'id: "usuarios"' in js
    assert 'id: "aprovacoes"' in js
    assert "renderUsuarios" in js
    assert "renderAprovacoes" in js
    assert "aud-user" in js
    assert "podeAdminUsuarios" in js
    assert "podeCadastrar" in js
    assert "list_usuarios" in js
    assert "pedir_exclusao" in js
    assert "decidir_exclusao" in js
    assert "reset_usuario_senha" in js
    assert "Login online" in js or "aba Usuarios" in js
    im = (ROOT / "web" / "js" / "informe_mensal.js").read_text(encoding="utf-8")
    assert "im-aud-user" in im
    api = (ROOT / "webapp" / "api.py").read_text(encoding="utf-8")
    assert "def list_usuarios" in api
    assert "def create_usuario" in api
    assert "def pedir_exclusao" in api
    assert "def decidir_exclusao" in api
    assert "admin_password_set" in api
    assert "_gravar_usuario_silencioso" in (ROOT / "sheets" / "service.py").read_text(
        encoding="utf-8"
    )
    assert "garantir_admin_bootstrap" in api or "listar_usuarios" in api


def _api_leitura():
    from webapp import api as api_mod

    api = api_mod.SinapescApi()
    api._logged_in = True
    api._admin_user = "leitor@x.com"
    api._papel = "leitura"
    api._pode_escrever = False
    api._revalidar_sessao = lambda: None  # type: ignore[assignment]
    eventos = []

    def sync_run(op, work, busy=""):
        try:
            eventos.append((op, {"ok": True, "data": work()}))
        except Exception as exc:  # noqa: BLE001
            eventos.append((op, {"ok": False, "error": str(exc)}))
        return {"ok": True, "pending": True}

    api._run_async = sync_run  # type: ignore[assignment]
    return api, eventos


def test_leitura_nao_escreve_em_nenhum_modulo() -> None:
    api, eventos = _api_leitura()
    assert api.save_settings({"spreadsheet_id": "x"})["ok"] is False
    assert api.import_credentials_json("{}")["ok"] is False
    assert api.set_defeso_fonte("padrao")["ok"] is False
    assert api.set_defeso_atalhos_contato([], [])["ok"] is False
    seis = ["Tilápia", "Piau", "Pescada", "Tucunaré", "Tambaqui", "Piranha"]
    import json as _json
    assert api.salvar_informe_especies(_json.dumps({"especies": seis}))["ok"] is False
    assert api.delete_pessoa("p1")["ok"] is False
    assert api.toggle_mes("p1", 2026, "mar", True)["ok"] is False
    assert api.save_pessoa({"nome": "Ana Maria", "cpf": "52998224725"})["ok"] is False

    chamadas = [
        lambda: api.save_calendario(2026, ["mar"]),
        lambda: api.sync_planilhas_municipio(),
        lambda: api.save_defeso_ficha({"nome": "Ana", "cpf": "52998224725"}),
        lambda: api.excluir_consulta_rgp({"ids": ["1"]}),
        lambda: api.cadastrar_consulta_rgp({"nome": "Ana", "cpf": "52998224725"}),
        lambda: api.excluir_informe_mes('{"person_id": "p1", "ano": 2026, "mes": "mar"}'),
    ]
    for fn in chamadas:
        antes = len(eventos)
        res = fn()
        if len(eventos) > antes:
            assert eventos[-1][1]["ok"] is False, eventos[-1]
        else:
            assert res.get("ok") is False, res


def test_operador_nao_altera_config_local() -> None:
    api, _ = _api_leitura()
    api._papel = "operador"
    api._pode_escrever = True
    assert api.save_settings({"spreadsheet_id": "x"})["ok"] is False
    assert api.pick_defeso_anexos_dir()["ok"] is False


def test_proxy_consulta_sem_senha() -> None:
    from webapp.api import _ConsultaRgpSemSenha

    class Reg:
        def __init__(self) -> None:
            self.govbr_senha = "segredo"

    class Svc:
        def listar(self):
            return [Reg()]

        def get_govbr_senha(self):
            return "geral"

    p = _ConsultaRgpSemSenha(Svc())
    assert p.listar()[0].govbr_senha == ""
    assert p.get_govbr_senha() == ""


def test_version() -> None:
    theme = (ROOT / "ui" / "theme.py").read_text(encoding="utf-8")
    assert 'APP_VERSION = "2.0.0.0"' in theme


if __name__ == "__main__":
    test_pbkdf2_hash_e_verify()
    test_papeis_e_modulos()
    test_permissoes_finas_e_celula()
    test_pedido_exclusao_roundtrip()
    test_autenticar_bloqueado()
    test_row_roundtrip()
    test_client_tem_aba_usuarios_e_exclusoes()
    test_js_ui_usuarios_e_filtro()
    test_leitura_nao_escreve_em_nenhum_modulo()
    test_operador_nao_altera_config_local()
    test_proxy_consulta_sem_senha()
    test_version()
    print("OK usuarios_online")
