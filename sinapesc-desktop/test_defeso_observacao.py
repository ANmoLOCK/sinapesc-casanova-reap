"""Testes: observação na ficha Defeso + relatório/filtros."""

from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parent


def test_observacao_modelo_e_planilha() -> None:
    from controle.defeso import DEFESO_HEADER, FichaDefeso, payload_to_ficha, row_to_ficha

    assert "observacao" in DEFESO_HEADER
    f = payload_to_ficha(
        {
            "nome": "Ana Souza",
            "cpf": "12345678901",
            "observacao": "Falta CAF — retornar amanhã",
            "entrada_confirmada": True,
        }
    )
    assert f.observacao == "Falta CAF — retornar amanhã"
    row = f.to_row()
    assert len(row) == len(DEFESO_HEADER)
    assert row[24] == "Falta CAF — retornar amanhã"
    back = row_to_ficha(row)
    assert back and back.observacao == "Falta CAF — retornar amanhã"


def test_observacao_filtros_e_html() -> None:
    from controle.defeso import FichaDefeso, format_parcelas
    from controle.defeso_relatorio import (
        COLUNAS_DEFESO_TODAS,
        itens_defeso_para_relatorio,
        montar_html_defeso,
        normalize_filtros_defeso,
    )

    assert "observacao" in COLUNAS_DEFESO_TODAS
    a = FichaDefeso(
        nome="Ana Souza",
        cpf="12345678901",
        endereco="Rua A",
        numero="1",
        bairro="Centro",
        uf="BA",
        cep="47300-000",
        status="salvo",
        entrada_confirmada="sim",
        observacao="Falta CAF",
        parcelas_recebidas=format_parcelas(["10/01/2026", "", "", ""]),
    )
    b = FichaDefeso(
        nome="Bruno Lima",
        cpf="10987654321",
        uf="BA",
        status="salvo",
        observacao="",
        parcelas_recebidas=format_parcelas(["", "", "", ""]),
    )
    base = dict(
        telefones_reap={"12345678901": "(74) 90000-0000", "10987654321": ""},
        municipios_reap={"12345678901": "Casa Nova", "10987654321": "Remanso"},
        nomes_reap={"12345678901": "Ana Souza", "10987654321": "Bruno Lima"},
        cpfs_reap=["12345678901", "10987654321"],
    )
    com = itens_defeso_para_relatorio([a, b], **base, filtros={"observacao": "com"})
    assert [x["nome"] for x in com] == ["Ana Souza"]
    sem = itens_defeso_para_relatorio([a, b], **base, filtros={"observacao": "sem"})
    assert [x["nome"] for x in sem] == ["Bruno Lima"]
    busca = itens_defeso_para_relatorio([a, b], **base, filtros={"busca": "caf"})
    assert [x["nome"] for x in busca] == ["Ana Souza"]
    assert normalize_filtros_defeso({"observacao": "com"})["observacao"] == "com"
    html = montar_html_defeso(
        org_short="Sinapesc",
        org_full="Sindicato",
        itens=com,
        titulo="Relatório",
        colunas=["nome", "observacao"],
    )
    assert "<th>Observação</th>" in html
    assert "Falta CAF" in html
    assert "MUNICÍPIO" in html.upper() or "Casa Nova" in html


def test_js_e_servico_observacao() -> None:
    js = (ROOT / "web" / "js" / "app.js").read_text(encoding="utf-8")
    assert 'id="df-obs"' in js
    assert "openDefesoRelatorioModal" in js
    assert "dr-observacao" in js
    assert "Obs.:" in js
    svc = (ROOT / "sheets" / "defeso_service.py").read_text(encoding="utf-8")
    assert '(24, "observacao")' in svc
    assert "A2:Y" in svc


def test_version() -> None:
    from ui.theme import APP_VERSION

    assert APP_VERSION == "1.7.54"


if __name__ == "__main__":
    test_observacao_modelo_e_planilha()
    test_observacao_filtros_e_html()
    test_js_e_servico_observacao()
    test_version()
    print("OK defeso_observacao")
