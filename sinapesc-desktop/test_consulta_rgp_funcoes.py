# -*- coding: utf-8 -*-
"""Testes das 4 funções extras da Consulta RGP (módulos separados)."""

from __future__ import annotations

import sys
from datetime import datetime, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))

from controle.consulta_rgp import (  # noqa: E402
    RegistroConsultaRgp,
    SITUACAO_ATIVO,
    SITUACAO_CANCELADO,
    SITUACAO_NAO_CONSULTADO,
    SITUACAO_SUSPENSO,
)
from controle.consulta_rgp_funcoes.alertas import (  # noqa: E402
    detectar_alerta_situacao,
    formatar_alerta,
)
from controle.consulta_rgp_funcoes.exportar import (  # noqa: E402
    exportar_consulta_rgp,
    filtrar_registros_export,
)
from controle.consulta_rgp_funcoes.fila_inteligente import (  # noqa: E402
    rodar_fila_inteligente,
)
from controle.consulta_rgp_funcoes.vencidos import (  # noqa: E402
    ids_vencidos,
    listar_vencidos,
    registro_esta_vencido,
)


def _reg(**kw):
    base = dict(
        id="id1",
        nome="Maria",
        cpf="09545332590",
        municipio="Casa Nova",
        situacao_rgp=SITUACAO_ATIVO,
        ultima_consulta_em=datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
    )
    base.update(kw)
    return RegistroConsultaRgp(**base)


def test_vencidos():
    agora = datetime(2026, 9, 4, 12, 0, 0)
    r1 = _reg(id="a", situacao_rgp=SITUACAO_NAO_CONSULTADO, ultima_consulta_em="")
    r2 = _reg(
        id="b",
        situacao_rgp=SITUACAO_ATIVO,
        ultima_consulta_em=(agora - timedelta(days=40)).strftime("%Y-%m-%d %H:%M:%S"),
    )
    r3 = _reg(
        id="c",
        situacao_rgp=SITUACAO_ATIVO,
        ultima_consulta_em=(agora - timedelta(days=5)).strftime("%Y-%m-%d %H:%M:%S"),
    )
    assert registro_esta_vencido(r1, dias=30, agora=agora)
    assert registro_esta_vencido(r2, dias=30, agora=agora)
    assert not registro_esta_vencido(r3, dias=30, agora=agora)
    assert ids_vencidos([r1, r2, r3], dias=30, agora=agora) == ["a", "b"]
    assert len(listar_vencidos([r1, r2, r3], dias=30, agora=agora)) == 2


def test_alertas():
    assert detectar_alerta_situacao(SITUACAO_ATIVO, SITUACAO_SUSPENSO)
    assert detectar_alerta_situacao(SITUACAO_ATIVO, SITUACAO_CANCELADO)
    assert detectar_alerta_situacao(SITUACAO_ATIVO, SITUACAO_ATIVO) is None
    assert detectar_alerta_situacao(SITUACAO_NAO_CONSULTADO, SITUACAO_SUSPENSO) is None
    a = detectar_alerta_situacao(SITUACAO_ATIVO, SITUACAO_SUSPENSO)
    msg = formatar_alerta(_reg(nome="João"), a)
    assert "João" in msg and "Suspenso" in msg


def test_exportar(tmp_path=None):
    regs = [
        _reg(id="1", municipio="Casa Nova", situacao_rgp=SITUACAO_ATIVO),
        _reg(id="2", nome="Ana", cpf="05610690501", municipio="Juazeiro", situacao_rgp=SITUACAO_SUSPENSO),
    ]
    f = filtrar_registros_export(regs, municipio="casa")
    assert len(f) == 1 and f[0].id == "1"
    f2 = filtrar_registros_export(regs, situacao=SITUACAO_SUSPENSO)
    assert len(f2) == 1 and f2[0].id == "2"
    out = exportar_consulta_rgp(regs, municipio="Casa Nova", formatos=("csv", "html"))
    assert out["total"] == 1
    assert Path(out["csv_path"]).is_file()
    assert Path(out["html_path"]).is_file()
    assert "Casa Nova" in Path(out["html_path"]).read_text(encoding="utf-8")


def test_fila_inteligente_pausa():
    regs = [_reg(id=str(i), nome=f"P{i}") for i in range(5)]
    calls = {"n": 0}

    def consultar(reg):
        calls["n"] += 1
        if calls["n"] <= 3:
            raise ValueError("MPA fora")
        return {"ok": True, "situacao": SITUACAO_ATIVO, "situacao_antes": SITUACAO_ATIVO, "registro": reg.to_dict()}

    progress = []
    res = rodar_fila_inteligente(
        regs,
        consultar_um=consultar,
        cancel_check=lambda: False,
        on_progress=progress.append,
        max_falhas_seguidas=3,
        exportar_erros=True,
    )
    assert res.pausado_por_falhas
    assert res.fail_count == 3
    assert res.ok_count == 0
    assert res.csv_erros_path and Path(res.csv_erros_path).is_file()
    assert any(p.get("fase") == "pausa" for p in progress)


def test_fila_com_alerta():
    reg = _reg(situacao_rgp=SITUACAO_ATIVO)

    def consultar(_item):
        return {
            "ok": True,
            "situacao_antes": SITUACAO_ATIVO,
            "situacao": SITUACAO_CANCELADO,
            "registro": _reg(situacao_rgp=SITUACAO_CANCELADO).to_dict(),
        }

    res = rodar_fila_inteligente(
        [reg],
        consultar_um=consultar,
        cancel_check=lambda: False,
        on_progress=lambda _p: None,
        max_falhas_seguidas=3,
        exportar_erros=False,
    )
    assert res.ok_count == 1
    assert len(res.alertas) == 1
    assert res.alertas[0]["para"] == SITUACAO_CANCELADO


def test_arquivos_separados():
    assert (ROOT / "controle" / "consulta_rgp_funcoes" / "vencidos.py").exists()
    assert (ROOT / "controle" / "consulta_rgp_funcoes" / "exportar.py").exists()
    assert (ROOT / "controle" / "consulta_rgp_funcoes" / "alertas.py").exists()
    assert (ROOT / "controle" / "consulta_rgp_funcoes" / "fila_inteligente.py").exists()
    assert (ROOT / "controle" / "consulta_rgp_funcoes" / "importar_arquivo.py").exists()
    assert (ROOT / "web" / "js" / "consulta_rgp_funcoes.js").exists()
    assert (ROOT / "web" / "css" / "consulta_rgp_funcoes.css").exists()
    assert (ROOT / "webapp" / "consulta_rgp_ext.py").exists()
    html = (ROOT / "web" / "index.html").read_text(encoding="utf-8")
    assert "consulta_rgp_funcoes.js" in html
    assert "consulta_rgp_funcoes.css" in html
    js = (ROOT / "web" / "js" / "app.js").read_text(encoding="utf-8")
    assert "SinapescRgpFuncoes" in js
    assert "rgp-vencidos" in (ROOT / "web" / "js" / "consulta_rgp_funcoes.js").read_text(encoding="utf-8")
    assert "rgp-relatorio-geral" in (ROOT / "web" / "js" / "consulta_rgp_funcoes.js").read_text(encoding="utf-8")
    api = (ROOT / "webapp" / "api.py").read_text(encoding="utf-8")
    assert "listar_consulta_rgp_vencidos" in api
    assert "exportar_consulta_rgp" in api
    assert "relatorio_geral_consulta_rgp" in api
    assert "escolher_arquivo_import_consulta_rgp" in api


if __name__ == "__main__":
    test_vencidos()
    test_alertas()
    test_exportar()
    test_fila_inteligente_pausa()
    test_fila_com_alerta()
    test_arquivos_separados()
    print("OK — funções Consulta RGP (4/3/2/1) passaram.")
