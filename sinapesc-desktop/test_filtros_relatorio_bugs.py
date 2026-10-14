"""Bateria: bugs de colunas/agrupamento nos relatórios HTML + filtros RGP."""

from __future__ import annotations

from datetime import datetime, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parent


def test_defeso_sem_municipio_nao_agrupa() -> None:
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
        parcelas_recebidas=format_parcelas(["15/05/2026", "", "", ""]),
        entrada_confirmada="sim",
        observacao="ok",
    )
    itens = itens_defeso_para_relatorio(
        [f],
        telefones_reap={"12345678901": "(74) 98888-1111"},
        municipios_reap={"12345678901": "Casa Nova"},
        nomes_reap={"12345678901": "Maria Silva"},
        cpfs_reap=["12345678901"],
    )
    html = montar_html_defeso(
        org_short="Sinapesc",
        org_full="Sindicato",
        itens=itens,
        titulo="Relatório",
        colunas=["nome", "cpf", "observacao"],
    )
    assert "<th>Município" not in html
    assert "MUNICÍPIO —" not in html
    assert "<th>Nome</th>" in html
    assert "<th>CPF</th>" in html
    assert "Maria Silva" in html

    html_com = montar_html_defeso(
        org_short="Sinapesc",
        org_full="Sindicato",
        itens=itens,
        titulo="Relatório",
        colunas=["nome", "municipio"],
    )
    assert "MUNICÍPIO —" in html_com
    assert "<th>Município" in html_com


def test_consulta_rgp_sem_municipio_nao_agrupa() -> None:
    from controle.consulta_rgp_funcoes.exportar import _html_export

    class _R:
        def __init__(self, **kw):
            self.__dict__.update(kw)

    regs = [
        _R(id="1", nome="Ana", cpf="09545332590", municipio="Remanso", telefone="1",
           situacao_rgp="Ativo", ultima_consulta_em="", observacao="", email="", uf="BA",
           codigo_rgp="", govbr_senha=""),
        _R(id="2", nome="Bia", cpf="05610690501", municipio="Casa Nova", telefone="2",
           situacao_rgp="Não consultado", ultima_consulta_em="", observacao="", email="", uf="BA",
           codigo_rgp="", govbr_senha=""),
    ]
    html = _html_export(
        regs,
        org_short="Sinapesc",
        org_full="Teste",
        filtros={},
        modo_geral=True,
        colunas=["nome", "cpf", "telefone"],
        auto_print=False,
    )
    assert "MUNICÍPIO —" not in html
    assert "<th>Município</th>" not in html
    assert "<th>Nome</th>" in html


def test_filtro_nao_consultados_e_recentes() -> None:
    from controle.consulta_rgp_funcoes.exportar import filtrar_registros_export

    class _R:
        def __init__(self, **kw):
            self.__dict__.update(kw)

    hoje = datetime.now().strftime("%d/%m/%Y %H:%M")
    ontem = (datetime.now() - timedelta(days=1)).strftime("%d/%m/%Y %H:%M")
    antigo = (datetime.now() - timedelta(days=20)).strftime("%d/%m/%Y %H:%M")
    regs = [
        _R(id="1", nome="Hoje", situacao_rgp="Ativo", ultima_consulta_em=hoje),
        _R(id="2", nome="Ontem", situacao_rgp="Ativo", ultima_consulta_em=ontem),
        _R(id="3", nome="Velho", situacao_rgp="Ativo", ultima_consulta_em=antigo),
        _R(id="4", nome="Nunca", situacao_rgp="Não consultado", ultima_consulta_em=""),
        _R(id="5", nome="Vazio", situacao_rgp="", ultima_consulta_em=""),
    ]
    nao = filtrar_registros_export(regs, consulta_periodo="nao_consultados")
    assert {r.nome for r in nao} == {"Nunca", "Vazio"}
    recentes = filtrar_registros_export(regs, consulta_periodo="recentes")
    assert {r.nome for r in recentes} == {"Hoje", "Ontem"}


def test_ui_tem_filtros_verificacao() -> None:
    js = (ROOT / "web" / "js" / "app.js").read_text(encoding="utf-8")
    assert 'id="rgp-periodo"' in js
    assert "nao_consultados" in js
    assert "Consultados recentes" in js
    assert "RGP_CHIP_PERIODOS" in js
    fun = (ROOT / "web" / "js" / "consulta_rgp_funcoes.js").read_text(encoding="utf-8")
    assert 'value="nao_consultados"' in fun
    assert "matchPeriodoLocal" in fun
    assert "CSV e HTML" in fun or "mesmas colunas" in fun


def test_aviso_defeso_respeita_colunas() -> None:
    from controle.defeso import FichaDefeso
    from controle.defeso_relatorio import itens_defeso_para_relatorio, montar_html_defeso

    f = FichaDefeso(nome="Ana", cpf="12345678901", observacao="x")
    itens = itens_defeso_para_relatorio(
        [f],
        telefones_reap={},
        municipios_reap={"12345678901": "Casa Nova"},
        nomes_reap={"12345678901": "Ana"},
        cpfs_reap=["12345678901"],
    )
    html = montar_html_defeso(
        org_short="S",
        org_full="T",
        itens=itens,
        titulo="R",
        colunas=["nome", "observacao"],
    )
    # texto do aviso não cita município/telefone quando colunas estão off
    start = html.find('class="disclaimer"')
    disc = html[start: start + 500].lower()
    assert "município" not in disc and "municipio" not in disc
    assert "telefone" not in disc
    assert "observa" in disc


def test_csv_respeita_colunas() -> None:
    from controle.consulta_rgp_funcoes.exportar import _resolver_colunas, _rows_csv

    assert _resolver_colunas(None, modo_geral=True)[0] == "nome"
    assert _resolver_colunas([], modo_geral=True) == ["nome"]
    assert _resolver_colunas(["foo", "bar"], modo_geral=False) == ["nome"]
    assert "municipio" not in _resolver_colunas(["nome", "cpf"], modo_geral=False)

    class _R:
        def __init__(self, **kw):
            self.__dict__.update(kw)

    regs = [_R(nome="Ana", cpf="09545332590", municipio="Remanso", telefone="1",
               situacao_rgp="Ativo", ultima_consulta_em="", observacao="", email="",
               uf="BA", codigo_rgp="", govbr_senha="")]
    rows = _rows_csv(regs, colunas=["nome", "cpf"])
    assert rows[0] == ["nome", "cpf"]
    assert "municipio" not in rows[0]
    assert len(rows[1]) == 2


def test_version() -> None:
    theme = (ROOT / "ui" / "theme.py").read_text(encoding="utf-8")
    assert 'APP_VERSION = "1.7.56"' in theme


if __name__ == "__main__":
    test_defeso_sem_municipio_nao_agrupa()
    test_consulta_rgp_sem_municipio_nao_agrupa()
    test_filtro_nao_consultados_e_recentes()
    test_ui_tem_filtros_verificacao()
    test_aviso_defeso_respeita_colunas()
    test_csv_respeita_colunas()
    test_version()
    print("OK filtros_relatorio_bugs")
