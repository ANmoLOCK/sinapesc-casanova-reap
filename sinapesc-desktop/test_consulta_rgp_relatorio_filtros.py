"""Testes: filtros e colunas do relatório HTML Consulta RGP."""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))

from controle.consulta_rgp import RegistroConsultaRgp, SITUACAO_ATIVO  # noqa: E402
from controle.consulta_rgp_funcoes.exportar import (  # noqa: E402
    _html_export,
    exportar_consulta_rgp,
    filtrar_registros_export,
)


def _regs():
    return [
        RegistroConsultaRgp(
            id="1",
            nome="Maria",
            cpf="09545332590",
            municipio="Casa Nova",
            telefone="7499999",
            situacao_rgp=SITUACAO_ATIVO,
            govbr_senha="s1",
            ultima_consulta_em="2026-08-01 10:00",
        ),
        RegistroConsultaRgp(
            id="2",
            nome="Ana",
            cpf="05610690501",
            municipio="Juazeiro",
            situacao_rgp="Não consultado",
            govbr_senha="",
            ultima_consulta_em="",
        ),
        RegistroConsultaRgp(
            id="3",
            nome="Bruno",
            cpf="52998224725",
            municipio="Casa Nova",
            situacao_rgp="Suspenso",
            govbr_senha="s3",
            ultima_consulta_em="2026-09-01",
        ),
    ]


def test_filtro_ids_e_municipios():
    f = filtrar_registros_export(_regs(), ids=["1", "3"], municipios=["Casa Nova"])
    assert [r.id for r in f] == ["3", "1"] or [r.id for r in f] == ["1", "3"]
    # ordenado por nome: Bruno, Maria
    assert [r.nome for r in f] == ["Bruno", "Maria"]


def test_filtro_situacoes_multi_e_senha():
    f = filtrar_registros_export(_regs(), situacoes=["Ativo", "Suspenso"], com_senha="com")
    assert {r.id for r in f} == {"1", "3"}
    f2 = filtrar_registros_export(_regs(), com_senha="sem")
    assert [r.id for r in f2] == ["2"]


def test_filtro_busca_e_data():
    f = filtrar_registros_export(_regs(), busca="maria")
    assert [r.id for r in f] == ["1"]
    f2 = filtrar_registros_export(_regs(), ultima_de="2026-08-15")
    assert [r.id for r in f2] == ["3"]
    # Ana sem data não entra
    assert "2" not in {r.id for r in f2}


def test_html_colunas_e_sem_double_escape():
    regs = _regs()[:1]
    html = _html_export(
        regs,
        org_short="Sinapesc",
        org_full="Org & Test",
        filtros={"municipio": "Casa & Nova", "escopo": "selecionados"},
        modo_geral=True,
        colunas=["nome", "cpf", "govbr_senha"],
        auto_print=False,
    )
    assert "Org &amp; Test" in html
    assert "Casa &amp; Nova" in html
    assert "Casa &amp;amp; Nova" not in html  # sem double-escape
    assert "Senha Gov.br" in html
    assert "s1" in html
    assert "window.print" not in html
    assert "<th>Observação</th>" not in html


def test_export_com_selecao():
    out = exportar_consulta_rgp(
        _regs(),
        ids=["2"],
        modo_geral=True,
        colunas=["nome", "municipio"],
        auto_print=False,
        escopo="selecionados",
    )
    assert out["total"] == 1
    html = Path(out["html_path"]).read_text(encoding="utf-8")
    assert "Ana" in html
    assert "Juazeiro" in html
    assert "Senha Gov.br" not in html


def test_ui_abre_modal_filtros():
    js = (ROOT / "web" / "js" / "consulta_rgp_funcoes.js").read_text(encoding="utf-8")
    assert "openRelatorioHtmlModal" in js
    assert 'addEventListener("click", openRelatorioGeral)' in js
    assert "rgp-rel-escopo" in js
    assert "Prévia:" in js
    # não gera mais direto sem modal
    assert 'JSON.stringify({ abrir_html: true })' not in js
    css = (ROOT / "web" / "css" / "consulta_rgp_funcoes.css").read_text(encoding="utf-8")
    assert "rgp-relatorio-body" in css


def test_version():
    assert 'APP_VERSION = "1.7.50"' in (ROOT / "ui" / "theme.py").read_text(encoding="utf-8")


if __name__ == "__main__":
    test_filtro_ids_e_municipios()
    test_filtro_situacoes_multi_e_senha()
    test_filtro_busca_e_data()
    test_html_colunas_e_sem_double_escape()
    test_export_com_selecao()
    test_ui_abre_modal_filtros()
    test_version()
    print("ok")
