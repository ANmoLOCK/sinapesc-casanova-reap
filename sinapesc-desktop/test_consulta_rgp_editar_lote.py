# -*- coding: utf-8 -*-
"""Testes: correção / edição em lote Consulta RGP."""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Any, Dict, List
from unittest.mock import MagicMock

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))

from controle.consulta_rgp import CONSULTA_RGP_TAB, RegistroConsultaRgp, SITUACAO_ATIVO  # noqa: E402
from controle.consulta_rgp_funcoes.editar_lote import normalizar_itens_edicao  # noqa: E402
from sheets.consulta_rgp_service import ConsultaRgpService  # noqa: E402


def test_normalizar_itens():
    itens = normalizar_itens_edicao(
        [
            {"id": "a", "nome": "maria silva", "cpf": "095.453.325-90", "numero": "7499999", "municipio": "Casa Nova", "obs": "ok"},
            {"nome": "sem id"},  # ignorado
        ]
    )
    assert len(itens) == 1
    assert itens[0]["id"] == "a"
    assert itens[0]["nome"].startswith("Maria")
    assert itens[0]["cpf"] == "09545332590"
    assert itens[0]["telefone"] == "7499999"
    assert itens[0]["observacao"] == "ok"


class _FakeClient:
    def __init__(self) -> None:
        self.spreadsheet_id = "fake"
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
        pass

    def batch_update_values(self, data: List[dict], *, chunk_size: int = 100) -> None:
        self.batch_updates.append(list(data))
        for item in data:
            rng = item["range"]
            row_n = int(rng.split("!")[-1].replace("A", "").split(":")[0])
            idx = row_n - 2
            vals = item["values"][0]
            if 0 <= idx < len(self._rows):
                self._rows[idx] = list(vals)


def test_editar_lote_batch():
    client = _FakeClient()
    client._rows = [
        RegistroConsultaRgp(
            id="id-a",
            nome="Antigo",
            cpf="09545332590",
            telefone="111",
            municipio="X",
            observacao="old",
            situacao_rgp=SITUACAO_ATIVO,
        ).to_row(),
        RegistroConsultaRgp(
            id="id-b",
            nome="Outro",
            cpf="05610690501",
            telefone="",
            municipio="",
            situacao_rgp=SITUACAO_ATIVO,
        ).to_row(),
    ]
    svc = ConsultaRgpService(client)
    svc._ready = True
    out = svc.editar_lote_batch(
        [
            {
                "id": "id-a",
                "nome": "Maria Nova",
                "cpf": "09545332590",
                "telefone": "74988887777",
                "municipio": "Casa Nova",
                "observacao": "corrigido",
                "govbr_senha": "SenhaMaria",
            },
            {
                "id": "id-b",
                "nome": "Joao Atualizado",
                "cpf": "05610690501",
                "telefone": "74",
                "municipio": "Juazeiro",
                "observacao": "",
                "govbr_senha": "SenhaJoao",
            },
        ]
    )
    assert out["atualizados"] == 2
    assert len(client.batch_updates) == 1
    # verifica células
    assert "Maria Nova" in client._rows[0][2]
    assert "Casa Nova" in client._rows[0][5]
    assert "corrigido" in client._rows[0][8]
    assert client._rows[0][19] == "SenhaMaria"
    assert client._rows[1][19] == "SenhaJoao"
    assert "Joao Atualizado" in client._rows[1][2] or "João" in client._rows[1][2]


def test_editar_lote_cpf_duplicado():
    client = _FakeClient()
    client._rows = [
        RegistroConsultaRgp(id="a", nome="A", cpf="09545332590").to_row(),
        RegistroConsultaRgp(id="b", nome="B", cpf="05610690501").to_row(),
    ]
    svc = ConsultaRgpService(client)
    svc._ready = True
    out = svc.editar_lote_batch(
        [
            {
                "id": "b",
                "nome": "B",
                "cpf": "09545332590",  # conflito com a
                "telefone": "",
                "municipio": "",
                "observacao": "",
            }
        ]
    )
    assert out["atualizados"] == 0
    assert any("já usado" in e for e in out["erros"])


def test_ui_hooks():
    js = (ROOT / "web" / "js" / "app.js").read_text(encoding="utf-8")
    fun = (ROOT / "web" / "js" / "consulta_rgp_funcoes.js").read_text(encoding="utf-8")
    api = (ROOT / "webapp" / "api.py").read_text(encoding="utf-8")
    assert "rgp-editar-lote" in js
    assert "openEditarLoteModal" in fun
    assert "editar_lote_consulta_rgp" in api
    assert "editar_lote_batch" in (ROOT / "sheets" / "consulta_rgp_service.py").read_text(encoding="utf-8")
    assert (ROOT / "controle" / "consulta_rgp_funcoes" / "editar_lote.py").exists()


if __name__ == "__main__":
    test_normalizar_itens()
    test_editar_lote_batch()
    test_editar_lote_cpf_duplicado()
    test_ui_hooks()
    print("OK — edição em lote Consulta RGP.")
