# -*- coding: utf-8 -*-
"""Bateria: scroll RGP + import nome+CPF (TXT/XLSX/PDF)."""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))

from controle.consulta_rgp_funcoes.importar_arquivo import (  # noqa: E402
    parse_arquivo_lote,
    parse_texto_lote,
)


def test_parse_nome_antes_cpf():
    raw = (
        "Maria Silva Santos 095.453.325-90\n"
        "Joao Souza;05610690501;Juazeiro\n"
        "Ana Costa\t10520558545\n"
    )
    itens, _ = parse_texto_lote(raw)
    by_cpf = {c: n for n, c, *_ in itens}
    assert by_cpf["09545332590"].lower().startswith("maria")
    assert by_cpf["05610690501"].lower().startswith("joao") or by_cpf[
        "05610690501"
    ].lower().startswith("joão")
    assert "ana" in by_cpf["10520558545"].lower()
    assert not any(n.lower().startswith("cpf ") for n, *_ in itens)


def test_parse_cpf_antes_nome():
    raw = "09545332590 Maria Silva Santos\n056.106.905-01;Joao da Silva;Casa Nova\n"
    itens, _ = parse_texto_lote(raw)
    assert len(itens) >= 2
    by_cpf = {c: n for n, c, *_ in itens}
    assert "maria" in by_cpf["09545332590"].lower()
    assert "joao" in by_cpf["05610690501"].lower() or "joão" in by_cpf["05610690501"].lower()


def test_parse_linhas_alternadas():
    raw = "Pedro Lima Oliveira\n09545332590\nAna Paula\n05610690501\n"
    itens, _ = parse_texto_lote(raw)
    assert len(itens) == 2
    by_cpf = {c: n for n, c, *_ in itens}
    assert "pedro" in by_cpf["09545332590"].lower()
    assert "ana" in by_cpf["05610690501"].lower()


def test_parse_nao_inventa_nome_cpf():
    raw = "09545332590\n05610690501\n"
    itens, erros = parse_texto_lote(raw)
    # sem nome na linha → não cadastra com «CPF …»
    assert all(not n.lower().startswith("cpf ") for n, *_ in itens)


def test_parse_arquivo_txt(tmp_path=None):
    pasta = Path(tmp_path) if tmp_path else Path("/tmp")
    pasta.mkdir(parents=True, exist_ok=True)
    f = pasta / "lote-nomes.txt"
    f.write_text(
        "MARIA APARECIDA DA SILVA 095.453.325-90\n"
        "JOSE CARLOS;05610690501;Casa Nova;(74) 99999-0000\n",
        encoding="utf-8",
    )
    out = parse_arquivo_lote(f)
    assert out["total"] == 2
    assert all(not it[0].lower().startswith("cpf ") for it in out["itens"])
    assert "maria" in out["itens"][0][0].lower()


def test_parse_xlsx_nome_cpf(tmp_path=None):
    import openpyxl

    pasta = Path(tmp_path) if tmp_path else Path("/tmp")
    pasta.mkdir(parents=True, exist_ok=True)
    f = pasta / "lote.xlsx"
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.append(["Nome", "CPF"])
    ws.append(["Maria Silva", "09545332590"])
    ws.append(["05610690501", "Joao Souza"])  # colunas invertidas sem cabeçalho certo
    wb.save(f)
    wb.close()
    # com cabeçalho Nome/CPF a 2ª linha invertida vira lixo — testamos a 1ª
    out = parse_arquivo_lote(f)
    assert out["total"] >= 1
    assert any("maria" in it[0].lower() for it in out["itens"])


def test_parse_pdf_nome_cpf(tmp_path=None):
    import pymupdf as fitz

    pasta = Path(tmp_path) if tmp_path else Path("/tmp")
    pasta.mkdir(parents=True, exist_ok=True)
    f = pasta / "lote.pdf"
    doc = fitz.open()
    page = doc.new_page()
    page.insert_text(
        (72, 72),
        "Maria Silva Santos 095.453.325-90\nJoao Souza 056.106.905-01",
    )
    doc.save(f)
    doc.close()
    out = parse_arquivo_lote(f)
    assert out["total"] >= 1
    assert any("maria" in it[0].lower() for it in out["itens"])
    assert all(not it[0].lower().startswith("cpf ") for it in out["itens"])


def test_scroll_css():
    css = (ROOT / "web" / "css" / "app.css").read_text(encoding="utf-8")
    assert ".rgp-shell {" in css
    # shell precisa de flex column + altura para o body-scroll funcionar
    block = css.split(".rgp-shell {")[1].split("}")[0]
    assert "display: flex" in block
    assert "flex-direction: column" in block
    assert "height: 100%" in block or "min-height: 0" in block
    assert "overflow-y: auto" in css.split(".rgp-body-scroll {")[1].split("}")[0]


if __name__ == "__main__":
    test_parse_nome_antes_cpf()
    test_parse_cpf_antes_nome()
    test_parse_linhas_alternadas()
    test_parse_nao_inventa_nome_cpf()
    test_parse_arquivo_txt()
    test_parse_xlsx_nome_cpf()
    test_parse_pdf_nome_cpf()
    test_scroll_css()
    print("OK — scroll + import nome+CPF.")
