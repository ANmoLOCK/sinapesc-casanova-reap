"""Bateria: login único + filtros/colunas do relatório Defeso."""

from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parent


def test_normalize_colunas_defeso() -> None:
    from controle.defeso_relatorio import (
        COLUNAS_DEFESO_TODAS,
        normalize_colunas_defeso,
    )

    assert normalize_colunas_defeso(None) == list(COLUNAS_DEFESO_TODAS)
    assert normalize_colunas_defeso("") == list(COLUNAS_DEFESO_TODAS)
    assert normalize_colunas_defeso(["cpf", "telefone"]) == ["nome", "cpf", "telefone"]
    assert normalize_colunas_defeso("cpf,parcelas") == ["nome", "cpf", "parcelas"]
    assert normalize_colunas_defeso({"cpf": True, "telefone": False, "parcelas": True}) == [
        "nome",
        "cpf",
        "parcelas",
    ]
    assert "nome" in normalize_colunas_defeso({"nome": False, "cpf": True})
    assert normalize_colunas_defeso(["cpf", "foo", "entrada"]) == ["nome", "cpf", "entrada"]


def test_normalize_filtros_defeso() -> None:
    from controle.defeso_relatorio import normalize_filtros_defeso, resumo_filtros_defeso

    f = normalize_filtros_defeso(None, somente_entrada=True, somente_parcela=True)
    assert f["entrada"] == "sim"
    assert f["parcela"] == "com"

    f2 = normalize_filtros_defeso(
        {
            "localidade": "Casa Nova",
            "entrada": "nao",
            "parcela": "2",
            "telefone": "sem",
            "endereco": "incompleto",
            "uf": "ba",
            "doc_caf": True,
            "ordenar": "recente",
            "busca": "Maria",
        }
    )
    assert f2["entrada"] == "nao"
    assert f2["parcela"] == "2"
    assert f2["uf"] == "BA"
    assert f2["doc_caf"] is True
    assert f2["ordenar"] == "recente"
    resumo = resumo_filtros_defeso(f2)
    assert "Casa Nova" in resumo
    assert "2ª parcela" in resumo
    assert "entrada pendente" in resumo


def test_filtros_aplicam_nos_itens() -> None:
    from controle.defeso import FichaDefeso, format_parcelas
    from controle.defeso_relatorio import itens_defeso_para_relatorio

    a = FichaDefeso(
        nome="Ana Souza",
        cpf="12345678901",
        endereco="Rua A",
        numero="1",
        bairro="Centro",
        municipio="X",
        uf="BA",
        cep="47300-000",
        status="salvo",
        entrada_confirmada="sim",
        parcelas_recebidas=format_parcelas(["10/01/2026", "", "", ""]),
        tem_caf="sim",
        atualizado_em="2026-10-01T10:00:00",
    )
    b = FichaDefeso(
        nome="Bruno Lima",
        cpf="10987654321",
        endereco="",
        numero="",
        bairro="",
        municipio="Y",
        uf="PE",
        cep="",
        status="rascunho",
        entrada_confirmada="",
        parcelas_recebidas=format_parcelas(["", "", "", ""]),
        atualizado_em="2026-10-05T10:00:00",
    )
    base = dict(
        telefones_reap={"12345678901": "(74) 90000-0000", "10987654321": ""},
        municipios_reap={"12345678901": "Casa Nova", "10987654321": "Remanso"},
        nomes_reap={"12345678901": "Ana Souza", "10987654321": "Bruno Lima"},
        cpfs_reap=["12345678901", "10987654321"],
    )

    so_ent = itens_defeso_para_relatorio([a, b], **base, filtros={"entrada": "sim"})
    assert [x["nome"] for x in so_ent] == ["Ana Souza"]

    pend = itens_defeso_para_relatorio([a, b], **base, filtros={"entrada": "nao"})
    assert [x["nome"] for x in pend] == ["Bruno Lima"]

    p1 = itens_defeso_para_relatorio([a, b], **base, filtros={"parcela": "1"})
    assert [x["nome"] for x in p1] == ["Ana Souza"]

    sem_tel = itens_defeso_para_relatorio([a, b], **base, filtros={"telefone": "sem"})
    assert [x["nome"] for x in sem_tel] == ["Bruno Lima"]

    incompleto = itens_defeso_para_relatorio([a, b], **base, filtros={"endereco": "incompleto"})
    assert [x["nome"] for x in incompleto] == ["Bruno Lima"]

    uf = itens_defeso_para_relatorio([a, b], **base, filtros={"uf": "PE"})
    assert [x["nome"] for x in uf] == ["Bruno Lima"]

    caf = itens_defeso_para_relatorio([a, b], **base, filtros={"doc_caf": True})
    assert [x["nome"] for x in caf] == ["Ana Souza"]

    busca = itens_defeso_para_relatorio([a, b], **base, filtros={"busca": "109876"})
    assert [x["nome"] for x in busca] == ["Bruno Lima"]

    recente = itens_defeso_para_relatorio([a, b], **base, filtros={"ordenar": "recente"})
    assert recente[0]["nome"] == "Bruno Lima"


def test_montar_html_respeita_colunas() -> None:
    from controle.defeso import FichaDefeso, format_parcelas
    from controle.defeso_relatorio import itens_defeso_para_relatorio, montar_html_defeso

    f = FichaDefeso(
        nome="Maria Silva",
        cpf="12345678901",
        endereco="Rua B",
        numero="5",
        bairro="Centro",
        municipio="Ignorado",
        uf="BA",
        cep="47300-000",
        telefone_reap="(74) 98888-1111",
        parcelas_recebidas=format_parcelas(["15/05/2026", "", "", ""]),
        entrada_confirmada="sim",
    )
    itens = itens_defeso_para_relatorio(
        [f],
        telefones_reap={"12345678901": "(74) 98888-1111"},
        municipios_reap={"12345678901": "Casa Nova"},
        nomes_reap={"12345678901": "Maria Silva"},
        cpfs_reap=["12345678901"],
    )
    html_min = montar_html_defeso(
        org_short="Sinapesc",
        org_full="Sindicato",
        itens=itens,
        titulo="Relatório Defeso",
        colunas=["nome", "cpf"],
        filtros_resumo="entrada confirmada",
    )
    assert "<th>Nome</th>" in html_min
    assert "<th>CPF</th>" in html_min
    assert "<th>Parcelas</th>" not in html_min
    assert "entrada confirmada" in html_min


def test_js_login_unico_e_modal_relatorio() -> None:
    js = (ROOT / "web" / "js" / "app.js").read_text(encoding="utf-8")
    assert "Acesso unificado" in js
    assert "goLoginUnico" in js
    assert "openDefesoRelatorioModal" in js
    assert "Colunas no relatório" in js
    assert "Documentos anexos" in js
    assert "dr-parcela" in js
    assert "dr-telefone" in js
    assert "dr-endereco" in js
    assert "dr-status" in js
    assert "dr-ordenar" in js
    assert "dr-busca" in js
    assert "doc_identidade" in js
    assert "JSON.stringify(filtros)" in js
    assert "Entrar como administrador" not in js


def test_api_assinatura_colunas() -> None:
    import inspect

    from webapp.api import SinapescApi

    sig = inspect.signature(SinapescApi.generate_defeso_relatorio)
    assert "colunas" in sig.parameters
    assert "filtros" in sig.parameters


def test_version_bump() -> None:
    from ui.theme import APP_VERSION

    assert APP_VERSION == "1.7.28"


if __name__ == "__main__":
    test_normalize_colunas_defeso()
    test_normalize_filtros_defeso()
    test_filtros_aplicam_nos_itens()
    test_montar_html_respeita_colunas()
    test_js_login_unico_e_modal_relatorio()
    test_api_assinatura_colunas()
    test_version_bump()
    print("OK login_unico_defeso_colunas")
