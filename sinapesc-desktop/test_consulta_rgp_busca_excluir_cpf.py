"""Testes: máscara CPF (sem pad na digitação), busca RGP, exclusão."""

from __future__ import annotations

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))

from controle.consulta_rgp_funcoes.excluir import ids_para_excluir, resumo_exclusao  # noqa: E402


def test_ids_para_excluir():
    assert ids_para_excluir(["a", "b"]) == ["a", "b"]
    assert ids_para_excluir({"ids": ["x"]}) == ["x"]
    assert ids_para_excluir({"id": "z"}) == ["z"]
    assert ids_para_excluir('["p","q"]') == ["p", "q"]
    assert ids_para_excluir("") == []
    assert ids_para_excluir(None) == []


def test_resumo_exclusao():
    r = resumo_exclusao(ok=2, erros=[], nomes=["Ana", "Bia"])
    assert r["ok_count"] == 2
    assert "Ana" in r["mensagem"]
    assert "Excluído" in r["mensagem"] or "Excluído(s)" in r["mensagem"]


def test_masks_js_no_pad_while_typing():
    js = (ROOT / "web" / "js" / "masks.js").read_text(encoding="utf-8")
    assert "formatCpfInput" in js
    assert "padStart" in js  # normalize can pad
    # formatCpfInput must NOT call padStart
    m = re.search(
        r"function formatCpfInput\(value\) \{(.+?)\n  \}",
        js,
        re.S,
    )
    assert m, "formatCpfInput not found"
    body = m.group(1)
    assert "padStart" not in body
    assert "normalizeCpf" not in body
    assert "fixCpfDigits" not in body


def test_index_loads_masks_before_app():
    html = (ROOT / "web" / "index.html").read_text(encoding="utf-8")
    i_mask = html.index("js/masks.js")
    i_app = html.index("js/app.js")
    assert i_mask < i_app


def test_app_js_search_paint_and_excluir():
    js = (ROOT / "web" / "js" / "app.js").read_text(encoding="utf-8")
    assert "paintConsultaRgpTableBody" in js
    assert "scheduleConsultaRgpSearchRepaint" in js
    assert "excluirConsultaRgpIds" in js
    assert 'data-act="excluir"' in js
    assert 'AppEvents.on("consulta_rgp_excluir"' in js
    assert "excluir_consulta_rgp" in js
    # busca não deve chamar renderConsultaRgp a cada tecla
    m = re.search(
        r'\$\("#rgp-search"\)\?\.addEventListener\("input".+?\}\);',
        js,
        re.S,
    )
    assert m
    handler = m.group(0)
    assert "scheduleConsultaRgpSearchRepaint" in handler
    assert "renderConsultaRgp()" not in handler


def test_excluir_module_and_spec():
    assert (ROOT / "controle" / "consulta_rgp_funcoes" / "excluir.py").exists()
    spec = (ROOT / "build_exe.spec").read_text(encoding="utf-8")
    assert "controle.consulta_rgp_funcoes.excluir" in spec
    api = (ROOT / "webapp" / "api.py").read_text(encoding="utf-8")
    assert "def excluir_consulta_rgp" in api
    svc = (ROOT / "sheets" / "consulta_rgp_service.py").read_text(encoding="utf-8")
    assert "def excluir_varios" in svc


def test_version_mask_excluir():
    theme = (ROOT / "ui" / "theme.py").read_text(encoding="utf-8")
    assert "APP_VERSION" in theme
    assert (ROOT / "web" / "js" / "masks.js").exists()
    assert (ROOT / "controle" / "consulta_rgp_funcoes" / "excluir.py").exists()


if __name__ == "__main__":
    test_ids_para_excluir()
    test_resumo_exclusao()
    test_masks_js_no_pad_while_typing()
    test_index_loads_masks_before_app()
    test_app_js_search_paint_and_excluir()
    test_excluir_module_and_spec()
    test_version_mask_excluir()
    print("ok")
