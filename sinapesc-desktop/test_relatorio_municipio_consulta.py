# -*- coding: utf-8 -*-
"""Testes: fila CPF inválido não aborta + relatório agrupado por município."""

from __future__ import annotations

import sys
import types
from datetime import datetime, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))

# stub tkinter (ambiente cloud) — só se ainda não houver módulo real/stub
if "tkinter" not in sys.modules:
    try:
        import tkinter as _tk  # noqa: F401
    except Exception:
        tk = types.ModuleType("tkinter")
        tk.TclError = Exception

        class _Canvas:  # mínimo para ui.widgets
            pass

        tk.Canvas = _Canvas
        tk.Tk = type("Tk", (), {})
        tk.Frame = type("Frame", (), {})
        tk.Label = type("Label", (), {})
        tk.Button = type("Button", (), {})
        sys.modules["tkinter"] = tk
        for name in ("ttk", "messagebox", "filedialog", "font"):
            sys.modules[f"tkinter.{name}"] = types.ModuleType(name)


from controle.consulta_rgp_funcoes.exportar import (  # noqa: E402
    filtrar_registros_export,
    _html_export,
)
from controle.consulta_rgp_funcoes.fila_inteligente import (  # noqa: E402
    rodar_fila_inteligente,
)
from controle.relatorio_municipio import agrupar_por_municipio  # noqa: E402


class _Reg:
    def __init__(self, **kw):
        self.id = kw.get("id", "")
        self.nome = kw.get("nome", "")
        self.cpf = kw.get("cpf", "")
        self.municipio = kw.get("municipio", "")
        self.telefone = kw.get("telefone", "")
        self.situacao_rgp = kw.get("situacao_rgp", "Ativo")
        self.ultima_consulta_em = kw.get("ultima_consulta_em", "")
        self.govbr_senha = kw.get("govbr_senha", "")
        self.observacao = kw.get("observacao", "")
        self.email = kw.get("email", "")
        self.uf = kw.get("uf", "")
        self.codigo_rgp = kw.get("codigo_rgp", "")


def test_fila_cpf_invalido_nao_pausa():
    """3 CPFs inválidos seguidos NÃO pausam a fila — continua até o fim."""
    regs = [
        _Reg(id="1", nome="A", cpf="111"),
        _Reg(id="2", nome="B", cpf="222"),
        _Reg(id="3", nome="C", cpf="333"),
        _Reg(id="4", nome="D", cpf="44444444444"),
    ]

    def consultar(reg):
        if len(str(reg.cpf)) != 11:
            return {"ok": False, "erro": "CPF inválido"}
        return {"ok": True, "situacao": "Ativo", "situacao_antes": "Não consultado"}

    res = rodar_fila_inteligente(
        regs,
        consultar_um=consultar,
        cancel_check=lambda: False,
        on_progress=lambda _p: None,
        max_falhas_seguidas=3,
        exportar_erros=False,
    )
    assert res.pausado_por_falhas is False
    assert res.fail_count == 3
    assert res.ok_count == 1
    assert res.total == 4


def test_fila_falhas_rede_ainda_pausa():
    """Falhas duras (rede/MPA) ainda pausam após N seguidas."""
    regs = [_Reg(id=str(i), nome=f"N{i}", cpf="09545332590") for i in range(5)]
    n = {"i": 0}

    def consultar(_reg):
        n["i"] += 1
        return {"ok": False, "erro": "timeout MPA"}

    res = rodar_fila_inteligente(
        regs,
        consultar_um=consultar,
        cancel_check=lambda: False,
        on_progress=lambda _p: None,
        max_falhas_seguidas=3,
        exportar_erros=False,
    )
    assert res.pausado_por_falhas is True
    assert res.fail_count == 3


def test_filtro_consultados_hoje_e_recentes():
    hoje = datetime.now().strftime("%d/%m/%Y %H:%M")
    ontem = (datetime.now() - timedelta(days=1)).strftime("%d/%m/%Y %H:%M")
    antigo = (datetime.now() - timedelta(days=20)).strftime("%d/%m/%Y %H:%M")
    regs = [
        _Reg(id="1", nome="Hoje", municipio="Remanso", ultima_consulta_em=hoje),
        _Reg(id="2", nome="Ontem", municipio="Casa Nova", ultima_consulta_em=ontem),
        _Reg(id="3", nome="Velho", municipio="Remanso", ultima_consulta_em=antigo),
        _Reg(id="4", nome="Nunca", municipio="Remanso", ultima_consulta_em=""),
    ]
    so_hoje = filtrar_registros_export(regs, consulta_periodo="hoje")
    assert [r.nome for r in so_hoje] == ["Hoje"]
    recentes = filtrar_registros_export(regs, consulta_periodo="recentes")
    nomes = {r.nome for r in recentes}
    assert "Hoje" in nomes and "Ontem" in nomes
    assert "Velho" not in nomes and "Nunca" not in nomes


def test_html_agrupa_municipio():
    regs = [
        _Reg(id="1", nome="Ana", cpf="09545332590", municipio="Remanso", telefone="1"),
        _Reg(id="2", nome="Bia", cpf="05610690501", municipio="Casa Nova", telefone="2"),
        _Reg(id="3", nome="Cia", cpf="09545332590", municipio="Remanso", telefone="3"),
    ]
    html_txt = _html_export(
        regs,
        org_short="Sinapesc",
        org_full="Teste",
        filtros={},
        modo_geral=True,
        colunas=["nome", "cpf", "telefone", "municipio"],
        auto_print=False,
    )
    assert "MUNICÍPIO — CASA NOVA" in html_txt
    assert "MUNICÍPIO — REMANSO" in html_txt
    # Casa Nova vem antes de Remanso (ordem alfabética)
    assert html_txt.index("MUNICÍPIO — CASA NOVA") < html_txt.index("MUNICÍPIO — REMANSO")


def test_agrupar_helper():
    itens = [
        {"nome": "Z", "municipio": "Remanso"},
        {"nome": "A", "municipio": "Casa Nova"},
        {"nome": "B", "municipio": "Remanso"},
        {"nome": "C", "municipio": ""},
    ]
    grupos = agrupar_por_municipio(
        itens,
        lambda x: x["municipio"],
        sort_nome=lambda x: x["nome"],
    )
    labels = [g[0] for g in grupos]
    assert labels[0] == "CASA NOVA"
    assert labels[1] == "REMANSO"
    assert labels[-1] == "SEM MUNICÍPIO"


def test_version():
    theme = (ROOT / "ui" / "theme.py").read_text(encoding="utf-8")
    assert 'APP_VERSION = "1.7.55"' in theme


def test_ui_has_periodo_filter():
    js = (ROOT / "web" / "js" / "consulta_rgp_funcoes.js").read_text(encoding="utf-8")
    assert 'id="rgp-rel-periodo"' in js
    assert "Consultados hoje" in js
    assert "consulta_periodo" in js
    assert "nao_consultados" in js
    app = (ROOT / "web" / "js" / "app.js").read_text(encoding="utf-8")
    assert "temErro" in app or "fail_count" in app
    assert "nao_consultados" in app


if __name__ == "__main__":
    test_fila_cpf_invalido_nao_pausa()
    test_fila_falhas_rede_ainda_pausa()
    test_filtro_consultados_hoje_e_recentes()
    test_html_agrupa_municipio()
    test_agrupar_helper()
    test_version()
    test_ui_has_periodo_filter()
    print("OK — relatórios município + fila CPF.")
