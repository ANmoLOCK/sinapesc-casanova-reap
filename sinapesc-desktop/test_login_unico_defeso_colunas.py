"""Bateria: login único + colunas do relatório Defeso."""

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
    # Nome sempre obrigatório mesmo se desligado no dict
    assert "nome" in normalize_colunas_defeso({"nome": False, "cpf": True})
    # Lixo ignorado
    assert normalize_colunas_defeso(["cpf", "foo", "entrada"]) == ["nome", "cpf", "entrada"]


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
    html_full = montar_html_defeso(
        org_short="Sinapesc",
        org_full="Sindicato",
        itens=itens,
        titulo="Relatório Defeso",
    )
    assert "<th>CPF</th>" in html_full
    assert "<th>Parcelas</th>" in html_full

    html_min = montar_html_defeso(
        org_short="Sinapesc",
        org_full="Sindicato",
        itens=itens,
        titulo="Relatório Defeso",
        colunas=["nome", "cpf"],
    )
    assert "<th>Nome</th>" in html_min
    assert "<th>CPF</th>" in html_min
    assert "<th>Telefone (REAP)</th>" not in html_min
    assert "<th>Parcelas</th>" not in html_min
    assert "<th>Endereço (Defeso)</th>" not in html_min
    assert "Maria Silva" in html_min
    assert "123.456.789-01" in html_min or "12345678901" in html_min


def test_js_login_unico_e_modal_relatorio() -> None:
    js = (ROOT / "web" / "js" / "app.js").read_text(encoding="utf-8")
    assert "Acesso unificado" in js
    assert "Uma entrada para REAP, Defeso Fácil e Consulta RGP" in js
    assert "goLoginUnico" in js
    assert "goReap" in js
    assert 'id="go-reap"' in js
    assert "← Módulos" in js
    assert "openDefesoRelatorioModal" in js
    assert "Colunas no relatório" in js
    assert "dr-gerar" in js
    assert "JSON.stringify(colunas)" in js
    assert 'afterLogin || "home"' in js
    assert "Login único ativo" in js
    # Não deve mais exigir login separado com texto antigo
    assert "Entrar como administrador" not in js
    assert "Acesso administrativo" not in js


def test_api_assinatura_colunas() -> None:
    import inspect

    from webapp.api import SinapescApi

    sig = inspect.signature(SinapescApi.generate_defeso_relatorio)
    assert "colunas" in sig.parameters


def test_version_bump() -> None:
    from ui.theme import APP_VERSION

    assert APP_VERSION == "1.7.27"


if __name__ == "__main__":
    test_normalize_colunas_defeso()
    test_montar_html_respeita_colunas()
    test_js_login_unico_e_modal_relatorio()
    test_api_assinatura_colunas()
    test_version_bump()
    print("OK login_unico_defeso_colunas")
