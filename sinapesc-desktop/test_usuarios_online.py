# -*- coding: utf-8 -*-
"""Bateria: login online (aba Usuarios), PBKDF2, papéis e UI."""

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
    assert admin.permite_modulo("defeso")
    op = u.novo_usuario(
        email="o@x.com", senha="123456", papel="operador", modulos=["reap", "informe"]
    )
    assert op.pode_escrever and not op.pode_admin_usuarios
    assert op.permite_modulo("reap") and not op.permite_modulo("defeso")
    leit = u.novo_usuario(email="l@x.com", senha="123456", papel="leitura")
    assert not leit.pode_escrever
    assert leit.permite_modulo("reap")  # módulos vazios = todos


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


def test_client_tem_aba_usuarios() -> None:
    from sheets.client import USUARIOS_HEADER, USUARIOS_TAB

    assert USUARIOS_TAB == "Usuarios"
    assert "senhaHash" in USUARIOS_HEADER
    assert "papel" in USUARIOS_HEADER


def test_js_ui_usuarios_e_filtro() -> None:
    js = (ROOT / "web" / "js" / "app.js").read_text(encoding="utf-8")
    assert 'id: "usuarios"' in js
    assert "renderUsuarios" in js
    assert "aud-user" in js
    assert "podeAdminUsuarios" in js
    assert "list_usuarios" in js
    assert "reset_usuario_senha" in js
    assert "Login online" in js or "aba Usuarios" in js
    im = (ROOT / "web" / "js" / "informe_mensal.js").read_text(encoding="utf-8")
    assert "im-aud-user" in im
    api = (ROOT / "webapp" / "api.py").read_text(encoding="utf-8")
    assert "def list_usuarios" in api
    assert "def create_usuario" in api
    assert "garantir_admin_bootstrap" in api or "listar_usuarios" in api


def test_version() -> None:
    theme = (ROOT / "ui" / "theme.py").read_text(encoding="utf-8")
    assert 'APP_VERSION = "1.8.7"' in theme


if __name__ == "__main__":
    test_pbkdf2_hash_e_verify()
    test_papeis_e_modulos()
    test_autenticar_bloqueado()
    test_row_roundtrip()
    test_client_tem_aba_usuarios()
    test_js_ui_usuarios_e_filtro()
    test_version()
    print("OK usuarios_online")
