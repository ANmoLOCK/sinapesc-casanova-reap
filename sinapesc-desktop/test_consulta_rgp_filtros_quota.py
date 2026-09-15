# -*- coding: utf-8 -*-
"""Bateria: filtros RGP oficiais + anti-cota na consulta em lote."""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Any, Dict, List
from unittest.mock import MagicMock

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))

from controle.consulta_rgp import (  # noqa: E402
    SITUACAO_AGUARDANDO_ANALISE,
    SITUACAO_AGUARDANDO_ATUALIZACAO,
    SITUACAO_ATIVO,
    SITUACAO_FINALIZADA,
    SITUACAO_RASCUNHO,
    SITUACOES_FILTRO_UI,
    RegistroConsultaRgp,
    normalize_situacao,
    situacao_match_filtro,
)
from sheets.consulta_rgp_service import ConsultaRgpService  # noqa: E402
from webapp import consulta_rgp_ext as ext  # noqa: E402


def test_filtros_ui_oficiais():
    assert SITUACOES_FILTRO_UI == (
        "Ativo",
        "Aguardando análise",
        "Finalizada",
        "Rascunho",
        "Aguardando atualização",
    )
    assert "Suspenso" not in SITUACOES_FILTRO_UI
    assert "Não consultado" not in SITUACOES_FILTRO_UI


def test_normalize_aguardando_atualizacao_curta():
    assert normalize_situacao("Aguardando atualização do interessado") == (
        SITUACAO_AGUARDANDO_ATUALIZACAO
    )
    assert normalize_situacao("aguardando atualizacao") == SITUACAO_AGUARDANDO_ATUALIZACAO
    assert SITUACAO_AGUARDANDO_ATUALIZACAO == "Aguardando atualização"


def test_situacao_match_filtro():
    assert situacao_match_filtro("Ativo", "Ativo")
    assert situacao_match_filtro(
        "Aguardando atualização do interessado", "Aguardando atualização"
    )
    assert situacao_match_filtro(SITUACAO_AGUARDANDO_ATUALIZACAO, "Aguardando atualização")
    assert not situacao_match_filtro("Ativo", "Rascunho")
    assert situacao_match_filtro("Qualquer", "")


def test_js_filtros_oficiais():
    js = (ROOT / "web" / "js" / "app.js").read_text(encoding="utf-8")
    assert 'RGP_CHIP_SITUACOES = [' in js
    assert '"Finalizada"' in js
    assert '"Rascunho"' in js
    assert '"Aguardando atualização"' in js
    assert "situacaoMatchFiltro" in js
    # não deve mais listar Situações extras dinâmicas no filtro
    assert "situacoesExtra" not in js
    # chip antigo removido
    assert '"Pend. regularização"' not in js.split("RGP_CHIP_SITUACOES")[1].split("];")[0]


def test_lote_consulta_usa_atualizar_linha_sem_auditoria_por_item():
    """Simula fila: 1 mapa + N updates (sem N×listar + N×audit)."""
    writes: List[str] = []
    audits: List[str] = []

    class FakeSvc:
        def mapa_id_linha(self):
            return {"a": 2, "b": 3, "c": 4}

        def atualizar_linha(self, reg, row_idx):
            writes.append(f"upd:{reg.id}:{row_idx}")
            return reg

        def salvar(self, payload):
            writes.append(f"salvar:{payload.get('id')}")
            return RegistroConsultaRgp(**{**payload})

        def registrar_auditoria(self, acao, detalhe, **kw):
            audits.append(acao)

        def listar(self):
            return [
                RegistroConsultaRgp(id="a", nome="A", cpf="09545332590", situacao_rgp=SITUACAO_ATIVO),
                RegistroConsultaRgp(id="b", nome="B", cpf="05610690501", situacao_rgp=SITUACAO_RASCUNHO),
                RegistroConsultaRgp(id="c", nome="C", cpf="10520558545", situacao_rgp=SITUACAO_FINALIZADA),
            ]

    # stub MPA
    calls = {"n": 0}

    def fake_mpa(cpf):
        calls["n"] += 1
        sits = [SITUACAO_ATIVO, SITUACAO_AGUARDANDO_ANALISE, SITUACAO_FINALIZADA]
        sit = sits[(calls["n"] - 1) % 3]
        return {"ok": True, "situacao": sit, "data": {"situacao": sit, "cpf": cpf}}

    orig = ext.consultar_cpf_isolado
    ext.consultar_cpf_isolado = fake_mpa  # type: ignore
    try:
        svc = FakeSvc()
        regs = svc.listar()
        out = ext.executar_lote(
            svc=svc,
            regs=regs,
            ids=["a", "b", "c"],
            todos=False,
            cancel_check=lambda: False,
            on_progress=lambda _p: None,
            max_falhas_seguidas=3,
        )
        assert out["ok_count"] == 3
        assert all(w.startswith("upd:") for w in writes), writes
        assert len(writes) == 3
        # só auditoria inicio + fim (não por item)
        assert audits.count("consulta_rgp_lote_inicio") == 1
        assert audits.count("consulta_rgp_lote_fim") == 1
        assert "consulta_rgp_consulta" not in audits
    finally:
        ext.consultar_cpf_isolado = orig  # type: ignore


def test_robo_grava_situacao_mpa_nao_filtro():
    """Mesmo fora do filtro UI (ex. Suspenso), o robô deve gravar o valor do MPA."""
    class FakeSvc:
        def atualizar_linha(self, reg, row_idx):
            return reg

        def salvar(self, payload):
            return RegistroConsultaRgp(
                id=payload.get("id") or "x",
                nome=payload.get("nome") or "",
                cpf=payload.get("cpf") or "",
                situacao_rgp=payload.get("situacao_rgp") or "",
            )

        def registrar_auditoria(self, *a, **k):
            pass

    orig = ext.consultar_cpf_isolado
    ext.consultar_cpf_isolado = lambda cpf: {  # type: ignore
        "ok": True,
        "situacao": "Suspenso",
        "data": {"situacao": "Suspenso", "cpf": cpf},
    }
    try:
        reg = RegistroConsultaRgp(
            id="x", nome="Teste", cpf="09545332590", situacao_rgp=SITUACAO_ATIVO
        )
        out = ext.consultar_um_registro(FakeSvc(), reg, row_idx=2, auditar=False)
        assert out["ok"]
        assert out["situacao"] == "Suspenso"
        assert out["situacao"] not in SITUACOES_FILTRO_UI  # fora do filtro, mas gravado
    finally:
        ext.consultar_cpf_isolado = orig  # type: ignore


def test_api_hooks_anti_quota():
    api = (ROOT / "webapp" / "api.py").read_text(encoding="utf-8")
    svc = (ROOT / "sheets" / "consulta_rgp_service.py").read_text(encoding="utf-8")
    assert "mapa_id_linha" in svc
    assert "atualizar_linha" in svc
    assert "upsert_lote_batch" in svc
    assert "auditar=False" in (ROOT / "webapp" / "consulta_rgp_ext.py").read_text(encoding="utf-8")
    assert "mapa_id_linha" in (ROOT / "webapp" / "consulta_rgp_ext.py").read_text(encoding="utf-8")


if __name__ == "__main__":
    test_filtros_ui_oficiais()
    test_normalize_aguardando_atualizacao_curta()
    test_situacao_match_filtro()
    test_js_filtros_oficiais()
    test_lote_consulta_usa_atualizar_linha_sem_auditoria_por_item()
    test_robo_grava_situacao_mpa_nao_filtro()
    test_api_hooks_anti_quota()
    print("OK — filtros + anti-cota consulta lote.")
