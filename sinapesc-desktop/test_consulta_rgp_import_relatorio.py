# -*- coding: utf-8 -*-
"""Testes: import arquivo (TXT/PDF/XLS) + relatório geral + batch anti-cota."""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Any, Dict, List
from unittest.mock import MagicMock

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))

from controle.consulta_rgp import (  # noqa: E402
    CONSULTA_RGP_TAB,
    RegistroConsultaRgp,
    SITUACAO_ATIVO,
    SITUACAO_NAO_CONSULTADO,
)
from controle.consulta_rgp_funcoes.exportar import exportar_consulta_rgp  # noqa: E402
from controle.consulta_rgp_funcoes.importar_arquivo import (  # noqa: E402
    parse_arquivo_lote,
    parse_texto_lote,
)
from sheets.consulta_rgp_service import ConsultaRgpService  # noqa: E402
from ui.formatters import normalize_cpf  # noqa: E402


def test_parse_texto_basico():
    raw = (
        "Nome;CPF;Município;Telefone\n"
        "Maria Silva;095.453.325-90;Casa Nova;(74) 99999-0001\n"
        "Joao Souza;05610690501;Juazeiro;74988881111\n"
    )
    itens, erros = parse_texto_lote(raw)
    assert len(itens) == 2
    assert itens[0][1] == "09545332590"
    assert "Casa Nova" in itens[0][2]
    assert itens[1][1] == "05610690501"
    assert not [e for e in erros if "sem nome" in e.lower()]


def test_parse_texto_sem_cabecalho():
    raw = "Ana Costa\t10520558545\tRemanso\n"
    itens, _ = parse_texto_lote(raw)
    assert len(itens) == 1
    assert itens[0][0].startswith("Ana")
    assert len(itens[0][1]) == 11


def test_parse_arquivo_txt(tmp_path: Path | None = None):
    pasta = Path(tmp_path) if tmp_path else Path("/tmp")
    pasta.mkdir(parents=True, exist_ok=True)
    f = pasta / "lote.txt"
    f.write_text(
        "Pedro Lima;12345678909;Casa Nova;74999990000\n"  # CPF fictício pode falhar DV — normalize still 11
        "Maria;09545332590;Casa Nova;\n",
        encoding="utf-8",
    )
    # Usa CPF com DV válido na 2ª linha
    f.write_text(
        "Pedro Lima;09545332590;Casa Nova;74999990000\n"
        "Ana Souza;05610690501;Juazeiro;\n",
        encoding="utf-8",
    )
    out = parse_arquivo_lote(f)
    assert out["total"] == 2
    assert out["origem"] == "texto"
    assert out["itens"][0][1] == "09545332590"


def test_parse_xlsx(tmp_path: Path | None = None):
    import openpyxl

    pasta = Path(tmp_path) if tmp_path else Path("/tmp")
    pasta.mkdir(parents=True, exist_ok=True)
    f = pasta / "lote.xlsx"
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.append(["Nome", "CPF", "Municipio", "Telefone"])
    ws.append(["Maria Silva", "09545332590", "Casa Nova", "74999990001"])
    ws.append(["Joao", "05610690501", "Juazeiro", ""])
    wb.save(f)
    wb.close()
    out = parse_arquivo_lote(f)
    assert out["total"] == 2
    assert out["origem"] == "xlsx"


def test_parse_pdf_simples(tmp_path: Path | None = None):
    import pymupdf as fitz

    pasta = Path(tmp_path) if tmp_path else Path("/tmp")
    pasta.mkdir(parents=True, exist_ok=True)
    f = pasta / "lote.pdf"
    doc = fitz.open()
    page = doc.new_page()
    page.insert_text(
        (72, 72),
        "Maria Silva;095.453.325-90;Casa Nova\nJoao Souza 056.106.905-01 Juazeiro",
    )
    doc.save(f)
    doc.close()
    out = parse_arquivo_lote(f)
    assert out["total"] >= 1
    cpfs = {it[1] for it in out["itens"]}
    assert "09545332590" in cpfs


def test_relatorio_geral_com_senha():
    regs = [
        RegistroConsultaRgp(
            id="1",
            nome="Maria",
            cpf="09545332590",
            municipio="Casa Nova",
            telefone="74999990000",
            situacao_rgp=SITUACAO_ATIVO,
        ),
        RegistroConsultaRgp(
            id="2",
            nome="Ana",
            cpf="05610690501",
            municipio="Juazeiro",
            telefone="",
            situacao_rgp=SITUACAO_NAO_CONSULTADO,
        ),
    ]
    out = exportar_consulta_rgp(
        regs,
        formatos=("html",),
        modo_geral=True,
        govbr_senha="SenhaGov123",
        org_short="Sinapesc",
    )
    assert out["modo_geral"] is True
    html = Path(out["html_path"]).read_text(encoding="utf-8")
    assert "SenhaGov123" in html
    assert "Casa Nova" in html
    assert "Situação RGP" in html or "Situação" in html
    assert "095.453.325-90" in html or "09545332590" in html
    assert "Relatório geral" in html or "geral" in html.lower()


class _FakeClient:
    def __init__(self) -> None:
        self.spreadsheet_id = "fake"
        self.appends: List[Any] = []
        self.batch_updates: List[Any] = []
        self._rows: List[List[str]] = []
        self._service = MagicMock()

    def get_values(self, range_a1: str) -> List[List[str]]:
        if "A1" in range_a1 or "Config" in range_a1 or "Auditoria" in range_a1:
            return []
        return list(self._rows)

    def update_values(self, range_a1: str, values: Any) -> None:
        pass

    def append_values(self, range_a1: str, values: Any) -> None:
        self.appends.append((range_a1, list(values)))
        if CONSULTA_RGP_TAB in range_a1:
            self._rows.extend(list(values))

    def batch_update_values(self, data: List[dict], *, chunk_size: int = 100) -> None:
        self.batch_updates.append(list(data))
        for item in data:
            rng = item["range"]
            # ConsultaRGP!A12 → row 12
            row_n = int(rng.split("!")[-1].replace("A", "").split(":")[0])
            idx = row_n - 2
            vals = item["values"][0]
            if 0 <= idx < len(self._rows):
                self._rows[idx] = list(vals)


def test_upsert_lote_batch_anti_quota():
    """500 linhas → poucas escritas (não 1 por linha)."""
    client = _FakeClient()
    # seed 2 existentes
    client._rows = [
        RegistroConsultaRgp(
            id="exist-1",
            nome="Antigo",
            cpf="09545332590",
            municipio="X",
            situacao_rgp=SITUACAO_ATIVO,
        ).to_row(),
    ]
    svc = ConsultaRgpService(client)
    svc._ready = True  # evita ensure() com API real

    itens = []
    # 1 update + 499 creates (CPFs sintéticos 11 dígitos — normalize aceita)
    itens.append(("Maria Atualizada", "09545332590", "Casa Nova", "74999990000"))
    for i in range(499):
        # gera 11 dígitos distintos (não precisa DV válido para upsert_lote_batch —
        # só checa len==11 via normalize_cpf; valores curtos zfill)
        base = f"{i + 1:09d}00"  # 11 chars
        cpf = normalize_cpf(base)
        if len(cpf) != 11:
            cpf = f"{i + 1:011d}"
        itens.append((f"Pessoa {i}", cpf, "Mun", ""))

    # Evita colisão com o CPF já existente
    itens = [itens[0]] + [it for it in itens[1:] if it[1] != "09545332590"]

    result = svc.upsert_lote_batch(itens)
    assert result["atualizados"] == 1
    assert result["criados"] >= 400
    # anti-cota: appends <= 2 (chunk 400) e batch_updates <= 1
    appends_data = [a for a in client.appends if CONSULTA_RGP_TAB in a[0]]
    assert len(appends_data) <= 2
    assert len(client.batch_updates) <= 2
    # NÃO pode ser ~500 appends
    assert len(appends_data) < 10


def test_api_hooks():
    api = (ROOT / "webapp" / "api.py").read_text(encoding="utf-8")
    assert "escolher_arquivo_import_consulta_rgp" in api
    assert "importar_arquivo_consulta_rgp" in api
    assert "relatorio_geral_consulta_rgp" in api
    assert "upsert_lote_batch" in (
        ROOT / "sheets" / "consulta_rgp_service.py"
    ).read_text(encoding="utf-8")
    js = (ROOT / "web" / "js" / "consulta_rgp_funcoes.js").read_text(encoding="utf-8")
    assert "rgp-relatorio-geral" in js
    assert "relatorio_geral_consulta_rgp" in js
    assert "rgp-l-file" in (ROOT / "web" / "js" / "app.js").read_text(encoding="utf-8")
    assert (ROOT / "controle" / "consulta_rgp_funcoes" / "importar_arquivo.py").exists()


if __name__ == "__main__":
    test_parse_texto_basico()
    test_parse_texto_sem_cabecalho()
    test_parse_arquivo_txt()
    test_parse_xlsx()
    test_parse_pdf_simples()
    test_relatorio_geral_com_senha()
    test_upsert_lote_batch_anti_quota()
    test_api_hooks()
    print("OK — import arquivo + relatório geral + batch anti-cota.")
