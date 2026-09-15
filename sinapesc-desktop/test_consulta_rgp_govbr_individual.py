"""Senha Gov.br individual por sócio + edição em lote."""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))

from controle.consulta_rgp import (  # noqa: E402
    CONSULTA_RGP_HEADER,
    RegistroConsultaRgp,
    payload_to_registro,
    row_to_registro,
)
from controle.consulta_rgp_funcoes.editar_lote import normalizar_itens_edicao  # noqa: E402
from controle.consulta_rgp_funcoes.exportar import _html_export  # noqa: E402


def test_header_tem_govbr():
    assert "govbrSenha" in CONSULTA_RGP_HEADER
    assert CONSULTA_RGP_HEADER.index("govbrSenha") == 19


def test_row_roundtrip_senha():
    reg = RegistroConsultaRgp(
        id="x1",
        nome="Ana",
        cpf="52998224725",
        govbr_senha="SenhaAna1",
    )
    row = reg.to_row()
    assert row[19] == "SenhaAna1"
    back = row_to_registro(row)
    assert back is not None
    assert back.govbr_senha == "SenhaAna1"


def test_payload_preserva_e_atualiza_senha():
    base = RegistroConsultaRgp(id="a", nome="Bob", cpf="52998224725", govbr_senha="velha")
    r1 = payload_to_registro({"nome": "Bob", "cpf": "52998224725"}, existing=base)
    assert r1.govbr_senha == "velha"
    r2 = payload_to_registro(
        {"nome": "Bob", "cpf": "52998224725", "govbr_senha": "nova"},
        existing=base,
    )
    assert r2.govbr_senha == "nova"


def test_normalizar_itens_com_senha():
    itens = normalizar_itens_edicao(
        [
            {
                "id": "1",
                "nome": "maria silva",
                "cpf": "529.982.247-25",
                "telefone": "74999990000",
                "municipio": "Casa Nova",
                "observacao": "ok",
                "govbr_senha": "Segredo1",
            }
        ]
    )
    assert len(itens) == 1
    assert itens[0]["govbr_senha"] == "Segredo1"
    assert itens[0]["nome"] == "Maria Silva"


def test_html_relatorio_senha_por_pessoa():
    regs = [
        RegistroConsultaRgp(id="1", nome="A", cpf="52998224725", municipio="X", govbr_senha="s1"),
        RegistroConsultaRgp(id="2", nome="B", cpf="39053344705", municipio="Y", govbr_senha="s2"),
    ]
    html = _html_export(
        regs,
        org_short="SINAPESC",
        org_full="Sindicato",
        filtros={},
        modo_geral=True,
    )
    assert "s1" in html and "s2" in html
    assert "Senha Gov.br (módulo)" not in html


def test_ui_lote_tem_campo_por_linha():
    js = (ROOT / "web" / "js" / "consulta_rgp_funcoes.js").read_text(encoding="utf-8")
    assert "el-govbr" in js
    assert "Atualizar senha Gov.br do módulo" not in js
    app = (ROOT / "web" / "js" / "app.js").read_text(encoding="utf-8")
    assert "Senha Gov.br deste sócio" in app
    assert "Uma senha para o módulo" not in app


def test_version():
    theme = (ROOT / "ui" / "theme.py").read_text(encoding="utf-8")
    assert "APP_VERSION" in theme
    assert "govbrSenha" in (ROOT / "controle" / "consulta_rgp.py").read_text(encoding="utf-8")


if __name__ == "__main__":
    test_header_tem_govbr()
    test_row_roundtrip_senha()
    test_payload_preserva_e_atualiza_senha()
    test_normalizar_itens_com_senha()
    test_html_relatorio_senha_por_pessoa()
    test_ui_lote_tem_campo_por_linha()
    test_version()
    print("ok")
