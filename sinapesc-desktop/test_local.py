# -*- coding: utf-8 -*-
"""Testes locais sem chamar a API Google."""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))

from sheets.service import _row_to_pessoa, _row_to_reap  # noqa: E402
from sheets.models import meses_no_intervalo, meses_para_flags  # noqa: E402
from ui.formatters import format_cpf, format_cpf_masked, only_digits, parse_lote_lines  # noqa: E402


def test_meses_intervalo() -> None:
    assert meses_no_intervalo("mar", "out") == ["mar", "abr", "mai", "jun", "jul", "ago", "set", "out"]
    flags = meses_para_flags(["mar", "out"])
    assert flags[2] == "TRUE" and flags[9] == "TRUE" and flags[0] == "FALSE"



def test_formatters() -> None:
    assert only_digits("123.456.789-01") == "12345678901"
    assert format_cpf("12345678901") == "123.456.789-01"
    assert format_cpf("10520558545") == "105.205.585-45"
    assert format_cpf("105.205.585-45") == "105.205.585-45"
    assert format_cpf_masked("12345678901") == "***.***.789-**"


def test_display_nome() -> None:
    from ui.formatters import display_nome, format_nome

    assert format_nome("gabriel lourran da silva") == "Gabriel Lourran Da Silva"
    assert format_nome("GABRIEL LOURRAN DA SILVA") == "Gabriel Lourran Da Silva"
    assert format_nome("Gabriel Lourran Da Silva") == "Gabriel Lourran Da Silva"
    assert format_nome("  GABRIEL   lourran DA   silva ") == "Gabriel Lourran Da Silva"
    assert display_nome("JOAO SILVA") == "Joao Silva"
    assert display_nome("maria pereira") == "Maria Pereira"


def test_parse_lote() -> None:
    itens = parse_lote_lines("Maria Silva;12345678901\nJoao,98765432100\n")
    assert itens[0] == ("Maria Silva", "12345678901")
    assert itens[1][0] == "Joao"


def test_row_parsers() -> None:
    p = _row_to_pessoa(["id1", "Maria", "12345678901", "2024-01-01"])
    assert p.nome == "Maria"
    p2 = _row_to_pessoa(["id2", "Joao", "98765432100", "2024-01-02", "Casa Nova"])
    assert p2.municipio == "Casa Nova"
    p3 = _row_to_pessoa(["id3", "Ana", "11122233344", "2024-01-03", "Juazeiro", "(74) 98888-1111"])
    assert p3.telefone == "(74) 98888-1111"
    r = _row_to_reap(
        ["rid", "id1", "2024", "TRUE", "FALSE", "FALSE", "FALSE", "FALSE", "FALSE",
         "FALSE", "FALSE", "FALSE", "FALSE", "FALSE", "FALSE", "now"]
    )
    assert r.ano == 2024
    assert r.meses["jan"] is True
    assert r.meses["fev"] is False


def test_controle_pendencias() -> None:
    from sheets.models import PessoaComReap, ReapAno, meses_vazios
    from controle.calendario import CALENDARIO_PADRAO, parse_meses
    from controle.pendencias import classificar

    assert parse_meses("mar, out, XYZ") == ["mar", "out"]
    meses = meses_vazios()
    for m in ("mar", "abr", "mai", "jun", "jul", "ago", "set"):
        meses[m] = True
    maria = PessoaComReap(
        id="1",
        nome="Maria",
        cpf="12345678901",
        criado_em="",
        anos=[ReapAno(id="r", person_id="1", ano=2026, meses=meses, atualizado_em="")],
    )
    joao = PessoaComReap(id="2", nome="Joao", cpf="98765432100", criado_em="", anos=[])
    pend, reg = classificar([maria, joao], 2026, CALENDARIO_PADRAO)
    assert [p.pessoa.nome for p in pend] == ["Joao", "Maria"]
    assert pend[1].faltando == ["out"]
    assert not reg


def test_auditoria_parse() -> None:
    from datetime import datetime

    from controle.auditoria import (
        combina_busca,
        format_tempo_desde,
        row_to_evento,
        ultimo_toggle_por_pessoa,
    )

    assert row_to_evento(["id", "em", "usuario"]) is None
    evt = row_to_evento(
        ["abc", "2026-08-18 09:00:00", "admin@x", "toggle_mes", "marcou OUT/2026 em Maria", "pid", "Maria", "2026", "out"]
    )
    assert evt is not None and evt.nome == "Maria"
    assert combina_busca(evt, "maria")
    assert not combina_busca(evt, "inexistente")

    agora = datetime(2026, 8, 19, 12, 0, 0)
    assert format_tempo_desde("2026-08-19 11:59:30", agora=agora) == "agora"
    assert format_tempo_desde("2026-08-19 11:00:00", agora=agora) == "1h atrás"
    assert format_tempo_desde("2026-08-19 08:00:00", agora=agora) == "4h atrás"
    assert format_tempo_desde("2026-08-05 12:00:00", agora=agora) == "14d"
    assert format_tempo_desde("2025-08-04 12:00:00", agora=agora) == "1ano15d"

    e1 = row_to_evento(["1", "2026-08-19 10:00:00", "u", "toggle_mes", "", "p1", "A", "2026", "jan"])
    e2 = row_to_evento(["2", "2026-08-18 10:00:00", "u", "toggle_mes", "", "p1", "A", "2026", "fev"])
    e3 = row_to_evento(["3", "2026-08-17 10:00:00", "u", "save_pessoa", "", "p1", "A", "", ""])
    e4 = row_to_evento(["4", "2026-08-16 10:00:00", "u", "toggle_mes", "", "p2", "B", "2026", "mar"])
    assert e1 and e2 and e3 and e4
    ultimo = ultimo_toggle_por_pessoa([e1, e2, e3, e4])
    assert set(ultimo.keys()) == {"p1", "p2"}
    assert ultimo["p1"]["em"] == "2026-08-19 10:00:00"
    assert ultimo["p2"]["em"] == "2026-08-16 10:00:00"


def test_relatorio_mostra_cpf_completo() -> None:
    from sheets.models import PessoaComReap, ReapAno, meses_vazios
    from controle.calendario import CALENDARIO_PADRAO
    from controle.pendencias import situacao_de
    from controle.relatorio import montar_html

    meses = meses_vazios()
    for m in CALENDARIO_PADRAO:
        meses[m] = True
    p = PessoaComReap(
        id="1", nome="Maria Silva", cpf="12345678901", criado_em="",
        anos=[ReapAno(id="r", person_id="1", ano=2026, meses=meses, atualizado_em="")],
    )
    item = situacao_de(p, 2026, CALENDARIO_PADRAO)
    html_txt = montar_html(
        org_short="Sinapesc",
        org_full="Sindicato",
        ano=2026,
        calendario=CALENDARIO_PADRAO,
        itens=[item],
        titulo="Teste",
        individual=True,
    )
    assert "123.456.789-01" in html_txt
    assert "***" not in html_txt
    assert "uso interno" in html_txt.lower()
    assert "não é comprovante de pagamento" in html_txt


def test_backup_rotacao() -> None:
    import tempfile
    from controle.backup import dias_desde, gravar_backup, listar_backups

    assert dias_desde("") is None
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        for i in range(14):
            gravar_backup(
                pessoas_rows=[["id", "nome"], ["1", "A"]],
                reap_rows=[["id"]],
                stamp=f"2026-01-{i + 1:02d}_1000",
                root=root,
            )
        assert len(listar_backups(root)) == 12


def test_chrome_routes() -> None:
    from ui.chrome import SCREEN_MODES, TAB_FOR_SCREEN

    assert SCREEN_MODES["admin"] == "secretaria"
    assert SCREEN_MODES["settings"] == "public"
    assert TAB_FOR_SCREEN["pendencias"] == "pendencias"


def test_brand_assets() -> None:
    from ui.brand import asset_path

    logo = asset_path("logo.png")
    icon = asset_path("icon.png")
    ico = asset_path("icon.ico")
    mark = asset_path("watermark.png")
    assert logo.exists() and logo.stat().st_size > 10_000
    assert icon.exists() and icon.stat().st_size > 10_000
    assert ico.exists() and ico.stat().st_size > 10_000
    assert mark.exists() and mark.stat().st_size > 10_000
    from PIL import Image

    im = Image.open(logo)
    assert im.size[0] >= 256 and im.size[1] >= 256
    assert Image.open(mark).mode == "RGBA"


def test_watermark_html_layer() -> None:
    html = (ROOT / "web" / "index.html").read_text(encoding="utf-8")
    css = (ROOT / "web" / "css" / "app.css").read_text(encoding="utf-8")
    assert 'class="app-watermark"' in html
    assert 'src="../assets/watermark.png"' in html
    assert 'id="content"' in html
    assert "background-image: url(" not in css
    assert ".app-watermark" in css
    from_html = (ROOT / "web" / "index.html").resolve().parent.parent / "assets" / "watermark.png"
    assert from_html.exists() and from_html.stat().st_size > 10_000


def test_layout_centered_default_scale() -> None:
    css = (ROOT / "web" / "css" / "app.css").read_text(encoding="utf-8")
    html = (ROOT / "web" / "index.html").read_text(encoding="utf-8")
    assert "--page-width:" in css
    assert "margin: 0 auto" in css
    assert "zoom: 1" in css
    assert "font-size: 14px" in css
    assert 'class="footer-inner"' in html
    launcher = (ROOT / "webapp" / "launcher.py").read_text(encoding="utf-8")
    assert "width=1280" in launcher


def test_run_async_enfileira_em_vez_de_rejeitar() -> None:
    from webapp.api import SinapescApi

    api = SinapescApi()
    api._busy = True
    r = api._run_async("op", lambda: 1, "ocupado")
    assert r.get("ok") is True
    assert r.get("queued") is True
    assert r.get("pending") is True
    assert len(api._queue) == 1
    api._queue.clear()
    api._busy = False


def test_js_tem_mes_instantaneo_e_cpf_formatado() -> None:
    js = (ROOT / "web" / "js" / "app.js").read_text(encoding="utf-8")
    assert "function paintPill(" in js
    assert "function formatCpf(" in js
    assert "function formatNome(" in js
    assert "function bindCpfMask(" in js
    assert 'api("print_qr"' in js
    assert "df-fonte-btn" in js
    assert "openDefesoFonteModal" in js
    assert "set_defeso_fonte" in js
    assert 'api("print_defeso_declaracao"' in js
    assert 'api("print_defeso_pacote"' in js
    assert 'AppEvents.on("defeso_print"' in js
    assert "df-pacote" in js
    assert "df-pacote-item" in js
    assert "defeso_declaracao_fonte" in js
    assert "window.open(\"\")" not in js
    assert "df-fonte-gear" not in js
    assert "btn-fonte" in js
    assert "id=\"df-fonte-btn\"" in js
    assert "qr-url" not in js
    assert "000.000.000-00" in js
    api_py = (ROOT / "webapp" / "api.py").read_text(encoding="utf-8")
    assert "self._queue" in api_py
    assert "queued" in api_py
    assert "def print_qr(" in api_py
    assert "def print_defeso_pacote(" in api_py
    assert "def _abrir_no_navegador(" in api_py
    assert "def _html_wrapper_pdf(" in api_py
    assert "def _windows_browsers(" in api_py
    assert "_abrir_no_navegador(path)" in api_py
    assert "limpar_declaracoes_anteriores" in (
        ROOT / "controle" / "defeso_declaracao.py"
    ).read_text(encoding="utf-8")
    assert '<p class="url">' not in api_py
    qrutil = (ROOT / "ui" / "qrutil.py").read_text(encoding="utf-8")
    assert "url_show" not in qrutil


def test_lote_50_socios_e_ponte_json() -> None:
    import json
    from sheets.service import SheetsService
    from webapp.api import _lote_itens_from_rows

    class FakeClient:
        def __init__(self) -> None:
            self.pessoas: list = []
            self.reap: list = []
            self.auditoria: list = []
            self._tabs_ready = True

        def ensure_tabs(self) -> None:
            return None

        def get_values(self, range_a1: str):
            if range_a1.startswith("Pessoas"):
                return list(self.pessoas)
            if range_a1.startswith("Reap"):
                return list(self.reap)
            return []

        def append_values(self, range_a1: str, values) -> None:
            rows = [list(v) for v in values]
            if range_a1.startswith("Pessoas"):
                self.pessoas.extend(rows)
            elif range_a1.startswith("Reap"):
                self.reap.extend(rows)
            else:
                self.auditoria.extend(rows)

    itens = [(f"Pessoa {i:02d}", f"{i:011d}") for i in range(1, 51)]
    payload = json.dumps([{"nome": n, "cpf": c} for n, c in itens], ensure_ascii=False)
    assert len(payload) > 722
    parsed = _lote_itens_from_rows(payload)
    assert len(parsed) == 50
    assert parsed[0] == ("Pessoa 01", "00000000001", "", "")
    assert parsed[49][0] == "Pessoa 50"

    svc = SheetsService(FakeClient())  # type: ignore[arg-type]
    svc._audit_silent = True
    result = svc.add_pessoas_lote(parsed, ano=2026, meses_on=["mar", "abr"])
    assert result["ok"] == 50
    assert result["erros"] == []
    assert len(svc.client.pessoas) == 50
    assert len(svc.client.reap) == 50
    assert svc.client.pessoas[0][2] == "000.000.000-01"
    assert len(svc.client.pessoas[0]) >= 6

    rich = _lote_itens_from_rows(
        [{"nome": "Ana", "cpf": "33333333333", "municipio": "Casa Nova", "telefone": "(74) 90000-0000"}]
    )
    assert rich[0] == ("Ana", "33333333333", "Casa Nova", "(74) 90000-0000")
    rich_ok = svc.add_pessoas_lote(rich, ano=2026)
    assert rich_ok["ok"] == 1
    assert svc.client.pessoas[-1][4] == "Casa Nova"
    assert svc.client.pessoas[-1][5] == "(74) 90000-0000"

    dup = svc.add_pessoas_lote([("Pessoa 01", "00000000001")], ano=2026)
    assert dup["ok"] == 0
    assert any("já cadastrado" in e for e in dup["erros"])

    caps = svc.add_pessoas_lote(
        [("GABRIEL LOURRAN DA SILVA", "11111111111"), ("gabriel lourran dos santos", "22222222222")],
        ano=2026,
    )
    assert caps["ok"] == 2
    gravados = [r[1] for r in svc.client.pessoas[-2:]]
    assert gravados == ["Gabriel Lourran Da Silva", "Gabriel Lourran Dos Santos"]

    js = (ROOT / "web" / "js" / "app.js").read_text(encoding="utf-8")
    assert "JSON.stringify(rows)" in js
    assert "sinapesc_lote_draft" in js
    assert "a janela só fecha se der certo" in js
    assert "backdrop._close(true);\n      const mesesOn" not in js


def test_licenca_proprietaria() -> None:
    repo = ROOT.parent
    lic = (repo / "LICENSE").read_text(encoding="utf-8")
    assert "Gabriel Lourran Da Silva Costa" in lic
    assert "105.825.755-24" not in lic
    assert "10582575524" not in lic
    assert "gabriel730costa@gmail.com" in lic
    assert "PROIBI" in lic.upper() or "proibid" in lic.lower()
    assert (repo / "COPYRIGHT").exists()
    html = (ROOT / "web" / "index.html").read_text(encoding="utf-8")
    assert "footer-legal" in html
    assert "Gabriel Lourran Da Silva Costa" in html
    assert "status-text" in html
    assert "footer-user" in html
    assert "footer-conn" in html
    assert "legal-bar" not in html
    consulta = (repo / "site-publico" / "consulta.html").read_text(encoding="utf-8")
    assert "footer-copy" in consulta
    assert "© todos os direitos reservados - 2026 - Gabriel" in consulta
    assert "legal.js" not in consulta
    assert (repo / "docs" / "DIREITOS-AUTORAIS.md").exists()
    assert "prazo indeterminado" in lic.lower() or "indeterminado" in lic.lower()
    assert "permanece de propriedade do autor" in lic.lower() or "propriedade do autor" in lic.lower()


def test_qr_selo_usa_logo() -> None:
    from ui.qrutil import make_qr_image

    img = make_qr_image("https://example.com/consulta")
    assert img.size[0] >= 200 and img.size[1] >= 200


def test_defeso_relatorio_html() -> None:
    from controle.defeso import (
        FichaDefeso,
        endereco_defeso_relatorio,
        entrada_confirmada_flag,
        format_parcelas,
        parse_parcelas,
        parcelas_para_relatorio,
    )
    from controle.defeso_relatorio import (
        itens_defeso_para_relatorio,
        montar_html_defeso,
        telefone_relatorio,
    )

    f = FichaDefeso(
        nome="Maria Silva",
        cpf="12345678901",
        endereco="Rua B",
        numero="5",
        bairro="Centro",
        municipio="IgnoradoNoRelatorio",
        uf="BA",
        cep="47300-000",
        telefone="74999990000",
        telefone_reap="(74) 98888-1111",
        parcelas_recebidas=format_parcelas(["15/05/2026", "", "20/07/2026", ""]),
        entrada_confirmada="sim",
    )
    end = endereco_defeso_relatorio(f)
    assert "Rua B" in end and "BA" in end and "47300-000" in end
    assert "IgnoradoNoRelatorio" not in end
    assert telefone_relatorio(f, "") == "(74) 98888-1111"
    assert entrada_confirmada_flag(f)
    assert parse_parcelas(f.parcelas_recebidas)[0] == "15/05/2026"
    assert "1° parcela; 15/05/2026" in parcelas_para_relatorio(f.parcelas_recebidas)
    itens = itens_defeso_para_relatorio(
        [f],
        telefones_reap={"12345678901": "(74) 98888-1111"},
        municipios_reap={"12345678901": "Casa Nova"},
        nomes_reap={"12345678901": "Maria Silva"},
        cpfs_reap=["12345678901"],
    )
    assert len(itens) == 1
    assert itens[0]["telefone"] == "(74) 98888-1111"
    assert itens[0]["municipio"] == "Casa Nova"
    assert "IgnoradoNoRelatorio" not in itens[0]["endereco"]

    # Ficha órfã (não existe no REAP) NÃO entra no relatório
    fantasma = FichaDefeso(
        nome="Gabriel Lourran Da Silva Costa",
        cpf="99988877766",
        municipio="X",
        uf="BA",
        entrada_confirmada="sim",
    )
    sem_fantasma = itens_defeso_para_relatorio(
        [f, fantasma],
        telefones_reap={"12345678901": "(74) 98888-1111"},
        municipios_reap={"12345678901": "Casa Nova"},
        nomes_reap={"12345678901": "Maria Silva"},
        cpfs_reap=["12345678901"],
    )
    assert len(sem_fantasma) == 1
    assert all("Gabriel" not in str(x.get("nome")) for x in sem_fantasma)

    html = montar_html_defeso(
        org_short="Sinapesc",
        org_full="Sindicato",
        itens=itens,
        titulo="Relatório Defeso",
    )
    assert "Maria Silva" in html
    assert "(74) 98888-1111" in html
    assert "Casa Nova" in html
    assert "1° parcela" in html
    assert "15/05/2026" in html
    assert "Gabriel Lourran" not in html
    assert "df-parcela-1" in (ROOT / "web" / "js" / "app.js").read_text(encoding="utf-8")
    assert "entrada-check" in (ROOT / "web" / "js" / "app.js").read_text(encoding="utf-8")
    # Rodapé de crédito permanece na UI do app
    assert "footer-legal" in (ROOT / "web" / "index.html").read_text(encoding="utf-8")


def test_defeso_ficha_e_html() -> None:
    from controle.defeso import (
        FichaDefeso,
        montar_declaracao_html,
        payload_to_ficha,
        row_to_ficha,
        validar_ficha,
    )

    f = payload_to_ficha(
        {
            "nome": "joao da silva",
            "cpf": "10582575524",
            "endereco": "Rua A",
            "numero": "10",
            "bairro": "Centro",
            "municipio": "Casa Nova",
            "uf": "ba",
            "cep": "47300000",
        }
    )
    assert f.nome.startswith("Joao") or f.nome.startswith("João") or "Silva" in f.nome
    assert f.cpf == "10582575524"
    assert f.uf == "BA"
    assert f.cep == "47300-000"
    assert validar_ficha(f) is None
    html = montar_declaracao_html(f, org_full="Sinapesc")
    assert "Declaração de Residência" in html
    assert "105.825.755-24" in html or "10582575524" in html
    row = f.to_row()
    back = row_to_ficha(row)
    assert back and back.cpf == f.cpf
    assert validar_ficha(FichaDefeso(nome="", cpf="123")) == "Informe o nome completo."


def test_normalize_sheet_id() -> None:
    from sheets.client import normalize_sheet_id

    assert normalize_sheet_id("1UxDjb78h7tYUnKXPcLVniuqAfWwrbvyf") == "1UxDjb78h7tYUnKXPcLVniuqAfWwrbvyf"
    assert (
        normalize_sheet_id("1UxDjb78h7tYUnKXPcLVniuqAfWwrbvyf?hl=pt-br")
        == "1UxDjb78h7tYUnKXPcLVniuqAfWwrbvyf"
    )
    assert (
        normalize_sheet_id(
            "https://docs.google.com/spreadsheets/d/1UxDjb78h7tYUnKXPcLVniuqAfWwrbvyf/edit#gid=0"
        )
        == "1UxDjb78h7tYUnKXPcLVniuqAfWwrbvyf"
    )
    assert (
        normalize_sheet_id("https://drive.google.com/drive/folders/abc123XYZ/view")
        == "abc123XYZ"
    )


def test_drive_client_tem_upload() -> None:
    from drive.client import DriveDefesoClient, normalize_folder_id

    assert hasattr(DriveDefesoClient, "upload_base64")
    assert hasattr(DriveDefesoClient, "listar_anexos")
    assert hasattr(DriveDefesoClient, "ensure_cpf_folder")
    assert normalize_folder_id("abc?hl=pt-br") == "abc"


def test_defeso_anexo_local() -> None:
    from controle.defeso_anexos import (
        anexos_mode,
        is_storage_quota_error,
        listar_anexos_local,
        pasta_anexos_root,
        salvar_anexo_local,
    )

    raw = b"%PDF-1.4 test"
    import base64
    import tempfile

    b64 = base64.b64encode(raw).decode("ascii")
    up = salvar_anexo_local(
        cpf="10582575524",
        kind="identidade",
        filename="rg.pdf",
        data_b64=b64,
        mime="application/pdf",
        cfg={"defeso_anexos_dir": ""},
    )
    assert up["where"] == "local"
    assert up["name"] == "identidade.pdf"
    assert Path(up["path"]).exists()
    listed = listar_anexos_local("10582575524", cfg={"defeso_anexos_dir": ""})
    assert any(x["name"] == "identidade.pdf" for x in listed)
    assert is_storage_quota_error(
        Exception("Service Accounts do not have storage quota. storageQuotaExceeded")
    )

    with tempfile.TemporaryDirectory() as tmp:
        cfg_sync = {"defeso_anexos_dir": tmp, "defeso_drive_folder_id": ""}
        assert anexos_mode(cfg_sync) == "sync"
        assert pasta_anexos_root(cfg_sync) == Path(tmp)
        up2 = salvar_anexo_local(
            cpf="52998224725",
            kind="caf",
            filename="caf.jpg",
            data_b64=b64,
            mime="image/jpeg",
            cfg=cfg_sync,
        )
        assert up2["where"] == "sync"
        assert up2["name"] == "caf.jpg"
        assert str(up2["path"]).startswith(str(Path(tmp)))
        listed2 = listar_anexos_local("52998224725", cfg=cfg_sync)
        assert any(x["name"] == "caf.jpg" and x["where"] == "sync" for x in listed2)

    assert anexos_mode({"defeso_anexos_dir": "", "defeso_drive_folder_id": "abc"}) == "drive"
    assert anexos_mode({"defeso_anexos_dir": "", "defeso_drive_folder_id": ""}) == "local"


def test_defeso_fontes_e_pdf() -> None:
    from controle.defeso import FichaDefeso, pasta_declaracoes
    from controle.defeso_declaracao import (
        DEFAULT_FONTE,
        listar_fontes,
        limpar_declaracoes_anteriores,
        modelo_pdf_path,
        normalize_fonte,
        preencher_pdf,
    )
    from ui.formatters import only_digits

    fontes = listar_fontes()
    ids = {f["id"] for f in fontes}
    assert {"padrao", "allura", "architects", "bairro", "mao"} <= ids
    assert normalize_fonte("") == DEFAULT_FONTE
    assert normalize_fonte("ALLURA") == "allura"
    assert modelo_pdf_path().is_file()
    ficha = FichaDefeso(
        nome="JOSE DA SILVA SANTOS",
        cpf="10582575524",
        rg="123",
        nacionalidade="Brasileira",
        profissao="Pescador",
        endereco="Rua A",
        numero="10",
        bairro="Centro",
        municipio="Casa Nova",
        uf="BA",
        cep="47300-000",
        telefone="74999998877",
        email="a@b.com",
    )
    cpf_d = only_digits(ficha.cpf)
    pasta = pasta_declaracoes()
    # limpa resíduos de runs anteriores neste CPF de teste
    limpar_declaracoes_anteriores(ficha.cpf)

    pdf0 = preencher_pdf(ficha, fonte_id="padrao")
    assert pdf0.exists() and pdf0.suffix == ".pdf"
    pdf = preencher_pdf(ficha, fonte_id="allura")
    assert pdf.exists() and pdf.suffix == ".pdf"
    # regenerar com outra fonte remove o PDF anterior do mesmo CPF
    assert not pdf0.exists()
    pdf_b = preencher_pdf(ficha, fonte_id="bairro")
    assert pdf_b.exists()
    assert not pdf.exists()
    pdf_m = preencher_pdf(ficha, fonte_id="mao")
    assert pdf_m.exists()
    assert not pdf_b.exists()
    pdf2 = preencher_pdf(ficha, fonte_id="architects")
    assert pdf2.exists()
    assert not pdf_m.exists()
    restantes = list(pasta.glob(f"declaracao-{cpf_d}-*.pdf"))
    assert restantes == [pdf2]
    # Confirma que o texto foi escrito por cima do modelo (não é HTML)
    import pymupdf as fitz

    doc = fitz.open(pdf2)
    page = doc[0]
    txt = page.get_text("text")
    # letra a letra → vários spans manuscritos
    spans = [
        s
        for b in page.get_text("dict")["blocks"]
        if b.get("type") == 0
        for line in b["lines"]
        for s in line["spans"]
        if s.get("color") and s["color"] != 0
    ]
    hand_spans = [s for s in spans if s["size"] >= 12 and len(s["text"]) <= 3]
    doc.close()
    assert "MINISTÉRIO DO TRABALHO" in txt or "MINISTERIO DO TRABALHO" in txt.upper()
    assert len(hand_spans) >= 10  # efeito mão: vários glifos separados


def test_abrir_pdf_cria_html_wrapper() -> None:
    """PDF vira HTML ao lado — no Windows .html abre no navegador, não no Acrobat."""
    import tempfile
    from pathlib import Path

    from webapp.api import _abrir_no_navegador, _html_wrapper_pdf

    with tempfile.TemporaryDirectory() as tmp:
        pdf = Path(tmp) / "declaracao-teste.pdf"
        pdf.write_bytes(b"%PDF-1.4 teste")
        html = _html_wrapper_pdf(pdf)
        assert html.exists()
        assert html.suffix == ".html"
        body = html.read_text(encoding="utf-8")
        assert 'src="declaracao-teste.pdf"' in body
        assert 'type="application/pdf"' in body
        # Em Linux xdg-open/webbrowser pode falhar sem display — só valida wrapper.
        try:
            _abrir_no_navegador(pdf)
        except OSError:
            pass
        assert html.exists()


def test_defeso_pacote_pdf() -> None:
    import tempfile
    from pathlib import Path

    import pymupdf as fitz

    from controle.defeso import FichaDefeso
    from controle.defeso_anexos import salvar_anexo_local
    from controle.defeso_pacote import (
        achar_anexo_arquivo,
        listar_opcoes_pacote,
        montar_pacote_pdf,
        normalize_selecao,
    )

    assert {x["id"] for x in listar_opcoes_pacote()} >= {
        "declaracao",
        "identidade",
        "pesca",
        "caf",
    }
    assert normalize_selecao([]) == ["declaracao", "identidade", "pesca", "caf"]
    assert normalize_selecao(["caf", "declaracao"]) == ["caf", "declaracao"]

    ficha = FichaDefeso(
        nome="JOSE PACOTE",
        cpf="52998224725",
        rg="1",
        nacionalidade="Brasileira",
        profissao="Pescador",
        endereco="Rua X",
        numero="1",
        bairro="Centro",
        municipio="Casa Nova",
        uf="BA",
        cep="47300-000",
        telefone="74",
        email="a@b.com",
    )
    with tempfile.TemporaryDirectory() as tmp:
        cfg = {"defeso_anexos_dir": tmp}
        # identidade PDF mínimo
        id_doc = fitz.open()
        id_doc.new_page()
        id_doc[0].insert_text((72, 72), "IDENTIDADE", fontsize=14)
        id_bytes = id_doc.tobytes()
        id_doc.close()
        import base64

        salvar_anexo_local(
            cpf=ficha.cpf,
            kind="identidade",
            filename="identidade.pdf",
            data_b64=base64.b64encode(id_bytes).decode("ascii"),
            cfg=cfg,
        )
        # CAF como PNG via pixmap
        img_doc = fitz.open()
        img_doc.new_page(width=200, height=200)
        img_doc[0].insert_text((20, 100), "CAF", fontsize=24)
        pix = img_doc[0].get_pixmap()
        # salvar via API anexos
        salvar_anexo_local(
            cpf=ficha.cpf,
            kind="caf",
            filename="caf.png",
            data_b64=base64.b64encode(pix.tobytes("png")).decode("ascii"),
            cfg=cfg,
        )
        img_doc.close()

        assert achar_anexo_arquivo(ficha.cpf, "identidade", cfg) is not None
        assert achar_anexo_arquivo(ficha.cpf, "caf", cfg) is not None
        assert achar_anexo_arquivo(ficha.cpf, "pesca", cfg) is None

        pack = montar_pacote_pdf(
            ficha,
            itens=["declaracao", "identidade", "caf", "pesca"],
            fonte_id="padrao",
            cfg=cfg,
        )
        assert Path(pack["path"]).is_file()
        assert pack["pages"] >= 3  # declaração + id + caf imagem
        assert any(x["id"] == "declaracao" for x in pack["incluidos"])
        assert "Carteira" in " ".join(pack["faltando"]) or pack["faltando"]

        # só declaração
        pack2 = montar_pacote_pdf(
            ficha, itens=["declaracao"], fonte_id="padrao", cfg=cfg
        )
        assert pack2["pages"] >= 1
        assert not pack2["faltando"]


def only_digits_cpf_helper(cpf: str) -> str:
    from ui.formatters import only_digits

    return only_digits(cpf)


def test_sync_municipios_bidirecional() -> None:
    from controle.defeso import DEFESO_TAB, FichaDefeso, payload_to_ficha
    from controle.sync_planilhas import sync_municipios_bidirecional
    from sheets.client import PESSOAS_TAB
    from sheets.models import Pessoa

    class FakeClient:
        def __init__(self, owner: str) -> None:
            self.owner = owner
            self.batch: list = []
            self.appends: list = []

        def ensure_tabs(self) -> None:
            return None

        def get_values(self, range_a1: str):
            if self.owner == "defeso":
                return [[f.id] for f in defeso.fichas]
            return [[p.id] for p in reap.pessoas]

        def batch_update_values(self, data, chunk_size: int = 80) -> None:
            self.batch.extend(data)
            for item in data:
                rng = str(item.get("range") or "")
                vals = item.get("values") or [[""]]
                val = vals[0][0] if vals and vals[0] else ""
                # Defeso!L{row} municipio / V telefoneReap / T stamp
                # Pessoas!E{row} municipio
                if "!" not in rng:
                    continue
                tab, cell = rng.split("!", 1)
                col = "".join(ch for ch in cell if ch.isalpha())
                row_s = "".join(ch for ch in cell if ch.isdigit())
                if not row_s:
                    continue
                row_idx = int(row_s)
                if tab == DEFESO_TAB:
                    f = defeso.fichas[row_idx - 2]
                    if col == "L":
                        f.municipio = str(val)
                    elif col == "V":
                        f.telefone_reap = str(val)
                elif tab == PESSOAS_TAB and col == "E":
                    p = reap.pessoas[row_idx - 2]
                    p.municipio = str(val)
                    reap.updates.append((p.id, str(val)))

        def append_values(self, range_a1: str, values) -> None:
            self.appends.extend(values)
            for row in values:
                # payload via to_row — reconstrói mínimo
                f = FichaDefeso(
                    id=str(row[0]),
                    person_id=str(row[1] if len(row) > 1 else ""),
                    nome=str(row[2] if len(row) > 2 else ""),
                    cpf=str(row[3] if len(row) > 3 else ""),
                    municipio=str(row[11] if len(row) > 11 else ""),
                    telefone_reap=str(row[21] if len(row) > 21 else ""),
                    status=str(row[15] if len(row) > 15 else "rascunho"),
                )
                defeso.fichas.append(f)
                defeso.salvos.append({"cpf": f.cpf, "municipio": f.municipio})

    class FakeReap:
        def __init__(self) -> None:
            self.pessoas = [
                Pessoa(id="p1", nome="Joao", cpf="12345678901", criado_em="", municipio="Salvador", telefone="74999990001"),
                Pessoa(id="p2", nome="Maria", cpf="98765432100", criado_em="", municipio=""),
                Pessoa(id="p3", nome="Novo", cpf="52998224725", criado_em="", municipio="Casa Nova", telefone="74"),
            ]
            self.updates: list = []
            self.client = FakeClient("reap")

        def get_all_pessoas(self):
            return list(self.pessoas)

    class FakeDefeso:
        def __init__(self) -> None:
            self.fichas = [
                FichaDefeso(
                    id="f1",
                    person_id="p1",
                    nome="Joao",
                    cpf="12345678901",
                    municipio="Camaçari",
                    status="salvo",
                ),
                FichaDefeso(
                    id="f2",
                    person_id="p2",
                    nome="Maria",
                    cpf="98765432100",
                    municipio="Feira de Santana",
                    status="confirmada",
                ),
            ]
            self.salvos: list = []
            self.client = FakeClient("defeso")

        def ensure(self) -> None:
            return None

        def listar(self):
            return list(self.fichas)

    reap = FakeReap()
    defeso = FakeDefeso()
    out = sync_municipios_bidirecional(reap, defeso)

    # REAP→Defeso: NÃO sobrescreve município da declaração
    assert defeso.fichas[0].municipio == "Camaçari"
    assert defeso.fichas[0].telefone_reap == "74999990001"
    assert out["reap_para_defeso"]["atualizados"] == 1  # só tel do Joao
    assert out["reap_para_defeso"]["criados"] == 1  # Novo (com tel)
    # Defeso NÃO altera planilha REAP
    assert out["defeso_para_reap"]["atualizados"] == 0
    assert reap.pessoas[1].municipio == ""


def test_js_filtros_defeso_e_sync_planilhas() -> None:
    js = (ROOT / "web" / "js" / "app.js").read_text(encoding="utf-8")
    assert "defeso-localidade" in js
    assert "defeso-confirmadas" in js
    assert "defeso-parcelas" in js
    assert "Com parcela disponível" in js
    assert "defeso-refresh" in js
    assert "Entradas confirmadas" in js
    assert "Sinc. Planilhas" in js
    assert 'api("sync_planilhas_municipio")' in js
    assert "refreshDefesoLocalidadeSelect" in js
    assert "defesoLocalidades" in js
    assert 'id="m-tel"' in js
    assert "Número (telefone)" in js
    assert "l-mun" in js
    assert "l-tel" in js
    assert "Nome;CPF;Município;Número" in js
    assert "defeso-relatorio" in js
    assert "generate_defeso_relatorio" in js
    assert "rel-localidade" in js
    assert "df-atalho-tel-0" in js
    assert "df-atalhos-gravar" in js
    assert "set_defeso_atalhos_contato" in js
    assert "admin-localidade" in js
    assert "card-contact" in js
    assert "df-parcela-1" in js
    assert "df-entrada" in js
    assert "entrada-check" in js
    assert "df-tel-reap" in js
    assert "df-mun-reap" in js
    assert 'municipio: ($("#df-mun")?.value || "").trim()' in js
    assert '$("#df-mun")?.value || $("#df-mun-reap")' not in js
    assert "municipio_reap ?? prev.municipio_reap" in js
    assert "municipio_origem === \"defeso\"" not in js
    assert "JSON.stringify(collectDefesoPayload())" in js
    api_py = (ROOT / "webapp" / "api.py").read_text(encoding="utf-8")
    assert 'base["municipio_reap"] = p_mun' in api_py
    assert "Município na ficha: prioriza REAP" not in api_py
    assert "defeso_mun" not in api_py
    assert "municipio = p_mun or f_mun" not in api_py
    assert 'd["municipio_reap"] = p_mun' in api_py
    assert "update_pessoa_municipio" not in api_py.split("def save_defeso_ficha")[1].split("def print_defeso")[0]
    assert "def generate_defeso_relatorio" in api_py
    assert "municipios_reap" in api_py
    assert "def _js_payload_to_dict" in api_py
    ser = (ROOT / "webapp" / "serialize.py").read_text(encoding="utf-8")
    assert '"municipio"' in ser
    assert '"telefone"' in ser


def test_js_payload_to_dict_aceita_json_e_dict() -> None:
    from webapp.api import _js_payload_to_dict, _prepare_defeso_payload

    d = _js_payload_to_dict(
        '{"nome":"Maria","cpf":"12345678901","parcelas":["15/05/2026","","",""],"entrada_confirmada":true}'
    )
    assert d["nome"] == "Maria"
    assert d["cpf"] == "12345678901"
    assert d["parcelas"][0] == "15/05/2026"
    assert d["entrada_confirmada"] is True
    assert _js_payload_to_dict({"a": 1, "b": [2, 3]}) == {"a": 1, "b": [2, 3]}
    assert _js_payload_to_dict(None) == {}
    assert _js_payload_to_dict("") == {}

    prep = _prepare_defeso_payload(
        {"nome": "Ana", "cpf": "111", "parcelas": ["15/05/2026", "20/06/2026", "", ""]}
    )
    assert "1° parcela;15/05/2026" in prep["parcelas_recebidas"]
    assert "2° parcela;20/06/2026" in prep["parcelas_recebidas"]


def test_config_appdata_sobrescreve_exe() -> None:
    """UI salva em AppData; deve vencer o config.json ao lado do EXE."""
    import json
    import tempfile
    from pathlib import Path

    import config as cfgmod

    root = Path(tempfile.mkdtemp())
    exe = root / "exe"
    app = root / "appdata"
    exe.mkdir()
    app.mkdir()
    (exe / "config.json").write_text(
        json.dumps({"spreadsheet_id": "SHEET", "defeso_declaracao_fonte": "padrao"}),
        encoding="utf-8",
    )

    old_exe, old_app = cfgmod.exe_dir, cfgmod.app_data_dir
    cfgmod.exe_dir = lambda: exe  # type: ignore[assignment]
    cfgmod.app_data_dir = lambda: app  # type: ignore[assignment]
    try:
        assert cfgmod.load_config()["defeso_declaracao_fonte"] == "padrao"
        c = cfgmod.load_config()
        c["defeso_declaracao_fonte"] = "allura"
        cfgmod.save_config(c)
        assert (app / "config.json").is_file()
        assert cfgmod.load_config()["defeso_declaracao_fonte"] == "allura"
        assert cfgmod.load_config()["spreadsheet_id"] == "SHEET"
    finally:
        cfgmod.exe_dir = old_exe  # type: ignore[assignment]
        cfgmod.app_data_dir = old_app  # type: ignore[assignment]


def test_consulta_rgp_dominio_e_ui() -> None:
    from controle.consulta_rgp import (
        SITUACAO_ATIVO,
        aplicar_resultado_mpa,
        extract_situacao_from_mpa,
        normalize_situacao,
        resumo_kpis,
        row_to_registro,
        situacao_apta_import,
        RegistroConsultaRgp,
    )
    from controle.consulta_rgp_mpa import MPA_CONSULTA_URL, WORKER_FLAG, _js_consultar

    assert normalize_situacao("rascunho") == "Rascunho"
    assert normalize_situacao("Finalizado") == "Finalizada"
    assert normalize_situacao(4) == "Ativo"
    assert extract_situacao_from_mpa({"situacaoRgp": "Ativo"}) == "Ativo"
    assert situacao_apta_import("Ativo")
    assert not situacao_apta_import("Aguardando análise")
    assert not situacao_apta_import("Finalizada")
    assert not situacao_apta_import("Finalizado")

    reg = RegistroConsultaRgp(id="abc", nome="Teste", cpf="10582575524")
    aplicar_resultado_mpa(
        reg,
        {
            "situacao": "Aguardando análise",
            "cpf": "10582575524",
            "municipio": "Casa Nova",
            "uf": "BA",
            "telefone": "74999990000",
            "codigoRGP": "RGP1",
        },
    )
    assert reg.situacao_rgp == "Aguardando análise"
    assert reg.municipio == "Casa Nova"
    assert reg.ultima_consulta_em
    assert any("Consulta realizada" in t["evento"] for t in reg.timeline_items())

    row = reg.to_row()
    back = row_to_registro(row)
    assert back and back.cpf == "10582575524"
    assert resumo_kpis([reg])["aguardando_analise"] == 1

    aplicar_resultado_mpa(reg, {"situacao": "Ativo"})
    assert reg.situacao_rgp == SITUACAO_ATIVO
    assert situacao_apta_import(reg.situacao_rgp)

    js = (ROOT / "web" / "js" / "app.js").read_text(encoding="utf-8")
    assert "renderConsultaRgp" in js
    assert "go-consulta-rgp" in js
    assert "consultar_rgp_pessoa" in js
    assert "cadastrar_consulta_rgp" in js
    assert "Cadastrar sócio" in js
    assert "consultaRgpLoading" in js
    css = (ROOT / "web" / "css" / "app.css").read_text(encoding="utf-8")
    assert "rgp-shell" in css
    assert "rgp-topbar" in css
    main = (ROOT / "main.py").read_text(encoding="utf-8")
    assert WORKER_FLAG in main
    assert "pesqbrasil-pescadorprofissional.mpa.gov.br" in MPA_CONSULTA_URL
    assert "10582575524" in _js_consultar("105.825.755-24")
    assert "grecaptcha.execute" in _js_consultar("10582575524")
    api_src = (ROOT / "webapp" / "api.py").read_text(encoding="utf-8")
    assert "def consultar_rgp_pessoa" in api_src
    assert "def cadastrar_consulta_rgp" in api_src
    assert "desativada nesta etapa" in api_src
    assert "upsert_manual" in (ROOT / "sheets" / "consulta_rgp_service.py").read_text(encoding="utf-8")
    assert "upsert_from_reap" not in (ROOT / "sheets" / "consulta_rgp_service.py").read_text(encoding="utf-8")



if __name__ == "__main__":
    test_formatters()
    test_display_nome()
    test_row_parsers()
    test_parse_lote()
    test_meses_intervalo()
    test_controle_pendencias()
    test_auditoria_parse()
    test_relatorio_mostra_cpf_completo()
    test_defeso_ficha_e_html()
    test_defeso_relatorio_html()
    test_normalize_sheet_id()
    test_drive_client_tem_upload()
    test_defeso_anexo_local()
    test_defeso_fontes_e_pdf()
    test_defeso_pacote_pdf()
    test_sync_municipios_bidirecional()
    test_js_filtros_defeso_e_sync_planilhas()
    test_js_payload_to_dict_aceita_json_e_dict()
    test_config_appdata_sobrescreve_exe()
    test_consulta_rgp_dominio_e_ui()
    test_backup_rotacao()
    test_chrome_routes()
    test_brand_assets()
    test_watermark_html_layer()
    test_layout_centered_default_scale()
    test_run_async_enfileira_em_vez_de_rejeitar()
    test_js_tem_mes_instantaneo_e_cpf_formatado()
    test_lote_50_socios_e_ponte_json()
    test_licenca_proprietaria()
    test_qr_selo_usa_logo()
    print("OK — testes locais passaram.")
