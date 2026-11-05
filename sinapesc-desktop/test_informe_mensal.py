# -*- coding: utf-8 -*-
"""Bateria: módulo Informe Mensal (cérebro mês a mês + planilha + auditoria + UI)."""

from __future__ import annotations

import json
import random
import sys
import types
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))

if "tkinter" not in sys.modules:
    try:
        import tkinter as _tk  # noqa: F401
    except Exception:
        tk = types.ModuleType("tkinter")
        tk.TclError = Exception
        for _name in ("Canvas", "Tk", "Frame", "Label", "Button", "Toplevel", "Entry", "Text",
                      "Scrollbar", "Listbox", "Checkbutton", "Radiobutton", "Menu", "Widget",
                      "StringVar", "BooleanVar", "IntVar", "Misc", "Event", "PhotoImage"):
            setattr(tk, _name, type(_name, (), {"__init__": lambda self, *a, **k: None}))
        sys.modules["tkinter"] = tk
        for _sub in ("ttk", "messagebox", "filedialog", "font", "simpledialog"):
            mod = types.ModuleType(_sub)
            setattr(tk, _sub, mod)
            sys.modules[f"tkinter.{_sub}"] = mod
        sys.modules["tkinter.ttk"].Style = type("Style", (), {"__init__": lambda self, *a, **k: None})
        for _name in ("Frame", "Label", "Button", "Entry", "Combobox", "Treeview", "Scrollbar",
                      "Checkbutton", "Notebook", "Progressbar"):
            setattr(sys.modules["tkinter.ttk"], _name, type(_name, (), {"__init__": lambda self, *a, **k: None}))

from controle import informe_mensal as im  # noqa: E402


def _ano_completo(seed: int, globais: set | None = None, ordem: list | None = None,
                  planos: dict | None = None):
    salvos = {}
    meses = list(ordem or im.MESES_PESCA)
    for m in meses:
        r = im.gerar_mes(
            person_id=f"p{seed}",
            cpf=f"{seed:011d}",
            nome="Fulano",
            telefone="",
            ano=2026,
            mes=m,
            salvos=salvos,
            assinaturas_globais=globais,
            outros_planos=planos,
            seed=seed * 1000 + im.MESES_ORDEM.index(m),
        )
        assert not im.validar_mes(m, r.informe.dias, r.informe.especies)
        salvos[m] = r.informe
        if globais is not None:
            globais.add(r.informe.assinatura)
    if planos is not None:
        txt = im.plano_str([len(salvos[m].especies) for m in im.MESES_PESCA])
        planos[txt] = planos.get(txt, 0) + 1
    return salvos


def test_cerebro_ano_completo_qualquer_ordem() -> None:
    globais: set = set()
    planos: dict = {}
    com8 = 0
    for s in range(120):
        ordem = list(im.MESES_PESCA)
        random.Random(s).shuffle(ordem)
        salvos = _ano_completo(s, globais, ordem, planos)
        assert im.validar_ano(salvos) == [], (s, im.validar_ano(salvos))
        peso = im.peso_anual(salvos)
        assert im.KG_ANO_MIN <= peso <= im.KG_ANO_MAX
        contagens = [len(salvos[m].especies) for m in im.MESES_PESCA]
        assert {4, 5, 6} <= set(contagens)
        assert contagens.count(8) <= 1
        assert all(contagens.count(c) <= 3 for c in (4, 5, 6))
        assert all(a != b for a, b in zip(contagens, contagens[1:])), contagens
        com8 += 8 in contagens
        assert salvos["mar"].plano and im.plano_do_socio(salvos) == contagens
        conj = {im.assinatura_conjunto(r.especies) for r in salvos.values()}
        assert len(conj) == 8
        ordens = {im.assinatura_ordem(r.especies) for r in salvos.values()}
        assert len(ordens) == 8
        for r in salvos.values():
            for e in r.especies:
                assert e.valor == im.PRECOS_VAREJO[e.nome]
                assert isinstance(e.kg, int)
            assert im.DIAS_MIN <= r.dias <= im.DIAS_MAX
    # cada sócio com plano próprio; 8 espécies só para uma parte deles
    assert len(planos) == 120
    assert 0.2 <= com8 / 120 <= 0.5, com8


def test_probabilidade_plano() -> None:
    p = im.probabilidades_plano()
    for m in im.MESES_PESCA:
        assert abs(sum(p["por_mes"][m].values()) - 1) < 0.01
        assert p["por_mes"][m]["8"] < p["por_mes"][m]["4"]
    assert 0.3 <= p["chance_ter_8"] <= 0.4
    # meio da safra tem mais chance de 8 que as pontas
    assert p["por_mes"]["jun"]["8"] > p["por_mes"]["mar"]["8"]
    regras = im.regras_probabilidade()
    assert regras["chance_socio_ter_8"] == im.CHANCE_SOCIO_TER_8
    # com Mar já salvo com 6, Abr nunca pode ser 6
    cond = im.probabilidades_plano({0: 6}, 800)
    assert cond["por_mes"]["mar"]["6"] == 1 and cond["por_mes"]["abr"]["6"] == 0
    assert im.plano_valido([4, 6, 5, 4, 8, 5, 6, 4])
    assert not im.plano_valido([4, 4, 5, 6, 5, 6, 4, 5])
    assert not im.plano_valido([4, 8, 5, 8, 6, 4, 5, 6])
    assert im.plano_parse(im.plano_str([4, 5, 6, 4, 5, 6, 4, 5])) == [4, 5, 6, 4, 5, 6, 4, 5]


def test_plano_evita_outros_e_repete_menos_usado() -> None:
    rng = random.Random(1)
    todos = {}
    for _ in range(150):
        pl = im.sortear_plano(rng, evitar=todos)
        txt = im.plano_str(pl)
        assert txt not in todos
        todos[txt] = 1


def test_padroes_iguais() -> None:
    a = _ano_completo(11)
    b = {m: im.row_to_informe(r.to_row()) for m, r in a.items()}
    for r in b.values():
        r.person_id = "outro"
    c = _ano_completo(12)
    grupos = im.padroes_iguais({"a": a, "b": b, "c": c})
    tipos = {g["tipo"] for g in grupos}
    assert {"plano", "kg", "mes_identico"} <= tipos
    assert all(g["socios"] == ["a", "b"] for g in grupos)
    assert im.padroes_iguais({"a": a, "c": c}) == []
    resumo = im.resumo_socio(a, "00000000011", 2026)
    assert resumo["plano_texto"] == "-".join(str(n) for n in resumo["contagens"])
    assert len(resumo["perfil"]["favoritas"]) == 3 and resumo["perfil"]["pico"] in im.MESES_PESCA


def test_humanizado_por_pessoa() -> None:
    p1, p2 = im.perfil_socio("11111111111", 2026), im.perfil_socio("22222222222", 2026)
    assert p1 == im.perfil_socio("11111111111", 2026)
    assert p1 != p2
    for nome, f in p1["pref"].items():
        assert 0.75 <= f <= 1.3, (nome, f)


def test_vizinhos_nao_repetem() -> None:
    for s in range(60):
        salvos = _ano_completo(500 + s)
        for a, b in zip(im.MESES_PESCA, im.MESES_PESCA[1:]):
            ra, rb = salvos[a], salvos[b]
            assert ra.dias != rb.dias
            assert ra.especies[0].nome != rb.especies[0].nome or len(rb.especies) == 1


def test_regerar_mes_mantem_regras() -> None:
    salvos = _ano_completo(77)
    antigo = salvos["jun"]
    r = im.gerar_mes(
        person_id="p77", cpf=f"{77:011d}", nome="Fulano", telefone="", ano=2026, mes="jun",
        salvos=salvos, assinaturas_globais={x.assinatura for x in salvos.values()}, seed=999,
    )
    assert r.informe.id == antigo.id
    novo = dict(salvos)
    novo["jun"] = r.informe
    assert im.validar_ano(novo) == []


def test_piracema_bloqueado() -> None:
    for m in ("jan", "fev", "nov", "dez", "Janeiro", "dezembro"):
        assert im.eh_piracema(m)
        try:
            im.gerar_mes(person_id="p", cpf="1", nome="", telefone="", ano=2026, mes=m, salvos={})
        except ValueError as exc:
            assert im.PIRACEMA_LABEL in str(exc)
        else:
            raise AssertionError("piracema deveria bloquear")
    assert im.validar_mes("nov", 18, [])
    assert im.normalizar_mes("Março") == "mar"
    assert im.normalizar_mes("marco") == "mar"


def test_validar_mes_regras() -> None:
    ok = [im.Especie("Tilápia", 12, 16.0), im.Especie("Piau", 9, 14.0),
          im.Especie("Curimatã", 14, 15.0), im.Especie("Tucunaré", 10, 18.0)]
    assert im.validar_mes("mar", 18, ok) == []
    assert im.validar_mes("mar", 25, ok)
    assert im.validar_mes("mar", 18, ok[:3])
    assert im.validar_mes("mar", 18, ok[:3] + [im.Especie("Tilápia", 8, 16.0)])
    assert im.validar_mes("mar", 18, [im.Especie(e.nome, 10, e.valor) for e in ok])
    assert im.validar_mes("mar", 18, ok[:3] + [im.Especie("Bagre", 8, 10.0)])
    assert im.validar_mes("mar", 18, ok[:3] + [im.Especie("Piranha", 30, 15.0)])
    esp = im.especies_de_payload([{"nome": "Piau", "kg": "11"}, {"nome": "Tambaqui", "kg": 9.6}])
    assert [(e.nome, e.kg, e.valor) for e in esp] == [("Piau", 11, 14.0), ("Tambaqui", 10, 21.0)]


def test_row_roundtrip_e_texto() -> None:
    salvos = _ano_completo(3)
    r = salvos["ago"]
    row = r.to_row()
    assert len(row) == len(im.INFORME_HEADER)
    back = im.row_to_informe(row)
    assert back is not None
    assert back.to_dict() == r.to_dict()
    texto = im.texto_para_site(r)
    assert "Agosto/2026" in texto
    assert "Houve pesca: SIM" in texto
    assert "1. " in texto and "R$ " in texto and "," in texto
    assert im.row_to_informe(im.INFORME_HEADER) is None


def test_alvo_estavel_por_socio() -> None:
    a = im.alvo_peso_anual("12345678901", 2026)
    assert a == im.alvo_peso_anual("12345678901", 2026)
    assert im.KG_ANO_MIN <= a <= im.KG_ANO_MAX
    alvos = {im.alvo_peso_anual(f"{i:011d}", 2026) for i in range(50)}
    assert len(alvos) > 5


class FakeClient:
    def __init__(self) -> None:
        self.tabs: dict[str, list[list]] = {}
        self.spreadsheet_id = "fake"
        outer = self

        class _Req:
            def __init__(self, fn):
                self.fn = fn

            def execute(self):
                return self.fn()

        class _Sheets:
            def get(self, spreadsheetId):  # noqa: N803
                return _Req(lambda: {"sheets": [{"properties": {"title": t, "sheetId": i}}
                                                for i, t in enumerate(outer.tabs)]})

        class _Svc:
            def spreadsheets(self):
                return _Sheets()

        self._service = _Svc()

    @staticmethod
    def _split(range_a1: str):
        tab, cells = range_a1.split("!")
        start = cells.split(":")[0]
        row = int("".join(c for c in start if c.isdigit()) or 1)
        return tab, row

    def get_values(self, range_a1):
        tab, row = self._split(range_a1)
        rows = self.tabs.get(tab, [])
        if range_a1.endswith("1:I1") or range_a1.endswith("A1:X1"):
            return [list(rows[0])] if rows else []
        return [list(r) for r in rows[row - 1:]]

    def update_values(self, range_a1, values):
        tab, row = self._split(range_a1)
        rows = self.tabs.setdefault(tab, [])
        while len(rows) < row - 1 + len(values):
            rows.append([])
        for i, v in enumerate(values):
            rows[row - 1 + i] = list(v)

    def append_values(self, range_a1, values):
        tab, _ = self._split(range_a1)
        self.tabs.setdefault(tab, [[]]).extend(list(v) for v in values)

    def batch_update(self, requests):
        names = list(self.tabs)
        for req in requests:
            if "addSheet" in req:
                self.tabs.setdefault(req["addSheet"]["properties"]["title"], [])
            if "deleteDimension" in req:
                rng = req["deleteDimension"]["range"]
                tab = names[rng["sheetId"]]
                del self.tabs[tab][rng["startIndex"]:rng["endIndex"]]

    def get_sheet_ids_by_title(self):
        return {t: i for i, t in enumerate(self.tabs)}


def test_service_upsert_excluir_auditoria() -> None:
    from sheets.informe_mensal_service import InformeMensalService

    cli = FakeClient()
    svc = InformeMensalService(cli)
    svc.actor = "op@sindicato"
    salvos = _ano_completo(11)
    for r in salvos.values():
        svc.salvar(r)
    assert cli.tabs[im.INFORME_TAB][0] == im.INFORME_HEADER
    assert len(svc.listar(2026)) == 8
    assert svc.listar(2025) == []
    r = salvos["mai"]
    r.dias = 21 if r.dias != 21 else 16
    svc.salvar(r)
    assert len(svc.listar(2026)) == 8
    assert svc.meses_do_socio("p11", 2026)["mai"].dias == r.dias
    removido = svc.excluir("p11", 2026, "mai")
    assert removido and removido.mes == "mai"
    assert "mai" not in svc.meses_do_socio("p11", 2026)
    assert svc.excluir("p11", 2026, "mai") is None
    svc.registrar_auditoria("gerar_informe", "Gerou REAP de Março/2026", person_id="p11",
                            nome="Fulano", ano="2026", meses="mar")
    svc.registrar_auditoria("editar_informe", "Alterou", person_id="p11", nome="Fulano",
                            ano="2026", meses="abr")
    evts = svc.listar_auditoria()
    assert [e.acao for e in evts] == ["editar_informe", "gerar_informe"]
    assert evts[0].usuario == "op@sindicato" and evts[0].meses == "abr"


def test_api_gerar_editar_excluir() -> None:
    from sheets.informe_mensal_service import InformeMensalService
    from sheets.models import Pessoa
    import webapp.api as api_mod

    cli = FakeClient()
    pessoa = Pessoa(id="p1", nome="maria das dores", cpf="12345678901", criado_em="",
                    municipio="Remanso", telefone="(74) 99999-0000")

    class FakeSheets:
        client = cli
        actor = ""

        def get_all_pessoas(self):
            return [pessoa]

    api = api_mod.SinapescApi()
    api._logged_in = True
    api._admin_user = "operador@sinapesc"
    api._ensure_service = lambda require_login=True: FakeSheets()  # type: ignore[assignment]
    eventos = []
    api._dispatch = lambda ev, payload: eventos.append((ev, payload))  # type: ignore[assignment]

    def sync_run(op, work, busy=""):
        try:
            eventos.append((op, {"ok": True, "data": work()}))
        except Exception as exc:  # noqa: BLE001
            eventos.append((op, {"ok": False, "error": str(exc)}))
        return {"ok": True, "pending": True}

    api._run_async = sync_run  # type: ignore[assignment]

    r = api.gerar_informe_mes(json.dumps({"person_id": "p1", "ano": 2026, "mes": "jan"}))
    assert r["ok"] is False and "PIRACEMA" in r["error"]

    api.gerar_informe_mes(json.dumps({"person_id": "p1", "ano": 2026, "mes": "mar"}))
    ev, res = eventos[-1]
    assert ev == "informe_gerado" and res["ok"], res
    socio = res["data"]["socio"]
    assert socio["meses"]["mar"]["municipio"] == "Remanso"
    assert socio["meses"]["mar"]["gerado_por"] == "operador@sinapesc"
    assert socio["resumo"]["gerados"] == 1
    assert "Março/2026" in socio["textos"]["mar"]

    for m in ("abr", "mai", "jun", "jul", "ago", "set", "out"):
        api.gerar_informe_mes(json.dumps({"person_id": "p1", "ano": 2026, "mes": m}))
        assert eventos[-1][1]["ok"], eventos[-1]
    socio = eventos[-1][1]["data"]["socio"]
    assert socio["resumo"]["gerados"] == 8
    assert im.KG_ANO_MIN <= socio["resumo"]["peso_anual"] <= im.KG_ANO_MAX
    assert socio["resumo"]["avisos"] == []

    api.gerar_informe_mes(json.dumps({"person_id": "p1", "ano": 2026, "mes": "jul"}))
    assert eventos[-1][1]["data"]["regerado"] is True

    atual = socio["meses"]["abr"]
    esp = [{"nome": e["nome"], "kg": e["kg"]} for e in atual["especies"]]
    esp[0]["kg"] = esp[0]["kg"] + 1 if esp[0]["kg"] < im.KG_MAX else esp[0]["kg"] - 1
    novo_dias = 16 if atual["dias"] != 16 else 17
    api.salvar_informe_mes(json.dumps({"person_id": "p1", "ano": 2026, "mes": "abr",
                                       "dias": novo_dias, "especies": esp}))
    ev, res = eventos[-1]
    assert ev == "informe_salvo" and res["ok"], res
    abr = res["data"]["socio"]["meses"]["abr"]
    assert abr["dias"] == novo_dias
    assert abr["atualizado_por"] == "operador@sinapesc"
    assert abr["motor"].endswith("+manual")

    r = api.salvar_informe_mes(json.dumps({"person_id": "p1", "ano": 2026, "mes": "abr",
                                           "dias": 30, "especies": esp}))
    assert r["ok"] is False

    api.excluir_informe_mes(json.dumps({"person_id": "p1", "ano": 2026, "mes": "out"}))
    ev, res = eventos[-1]
    assert ev == "informe_excluido" and res["ok"]
    assert "out" not in res["data"]["socio"]["meses"]

    api.load_informe_auditoria()
    ev, res = eventos[-1]
    acoes = [e["acao"] for e in res["data"]["itens"]]
    assert acoes[0] == "excluir_informe"
    assert "editar_informe" in acoes and "regerar_informe" in acoes
    assert acoes.count("gerar_informe") == 8
    editar = next(e for e in res["data"]["itens"] if e["acao"] == "editar_informe")
    assert "dias" in editar["detalhe"] and editar["usuario"] == "operador@sinapesc"

    api.load_informe_mensal(2026)
    ev, res = eventos[-1]
    assert ev == "informe_lista" and res["ok"]
    assert res["data"]["meses_piracema"] == ["jan", "fev", "nov", "dez"]
    assert res["data"]["socios"][0]["resumo"]["gerados"] == 7
    assert res["data"]["probabilidades"]["por_mes"]["mar"]
    assert res["data"]["padroes_iguais"] == []
    assert res["data"]["socios"][0]["padrao_igual"] == []
    plano = res["data"]["socios"][0]["resumo"]["plano"]
    assert len(plano) == 8 and plano[:7] == res["data"]["socios"][0]["resumo"]["contagens"]
    assert abr["plano"], "edição manual mantém o plano"


def test_ui_botao_e_tela() -> None:
    js = (ROOT / "web" / "js" / "app.js").read_text(encoding="utf-8")
    home = js[js.index("function renderHome"):js.index("function renderLogin")]
    assert home.index('id="go-reap"') < home.index('id="go-informe"')
    assert ">Informe Mensal</button>" in home
    assert "informe_mensal: renderInformeMensal" in js
    assert '"consulta_rgp", "informe_mensal"' in js
    assert 'dest === "informe_mensal"' in js
    html = (ROOT / "web" / "index.html").read_text(encoding="utf-8")
    assert "js/informe_mensal.js" in html and "css/informe_mensal.css" in html
    im_js = (ROOT / "web" / "js" / "informe_mensal.js").read_text(encoding="utf-8")
    for token in ("ÉPOCA DE PIRACEMA", "im-mes-pir", "aria-disabled", "Auditoria",
                  "gerar_informe_mes", "salvar_informe_mes", "excluir_informe_mes",
                  "load_informe_auditoria", "Regerar", "Copiar texto",
                  "Plano de espécies", "Cálculo de probabilidade", "im-chip-8",
                  "padrao_igual", "Com padrão igual a outro sócio", "previsto",
                  "Abrir tabela no navegador", "abrir_informe_tabela", "informe_tabela",
                  "abrir_informe_tabela_socio", "im-card-tabela", "data-im-tabela"):
        assert token in im_js, token
    css = (ROOT / "web" / "css" / "informe_mensal.css").read_text(encoding="utf-8")
    assert ".im-mes-pir" in css and "not-allowed" in css
    spec = (ROOT / "build_exe.spec").read_text(encoding="utf-8")
    assert "controle.informe_mensal" in spec and "sheets.informe_mensal_service" in spec
    assert "controle.informe_mensal_relatorio" in spec
    # kg não re-renderiza no blur (senão o clique em Salvar se perde)
    assert 'inp.addEventListener("input"' in im_js



def test_html_tabela_por_socio() -> None:
    from controle.informe_mensal_relatorio import montar_html_informe, nome_arquivo_informe
    salvos = _ano_completo(21)
    por = {"p21": salvos}
    socios = [{
        "id": "p21",
        "nome": "Fulano De Tal",
        "cpf": "000.000.000-21",
        "cpf_raw": f"{21:011d}",
        "telefone": "(74) 99999-0000",
        "municipio": "Casa Nova",
        "resumo": im.resumo_socio(salvos, f"{21:011d}", 2026),
    }, {
        "id": "p99",
        "nome": "Sem Meses",
        "cpf": "000.000.000-99",
        "cpf_raw": "00000000099",
        "telefone": "",
        "municipio": "Remanso",
        "resumo": im.resumo_socio({}, "00000000099", 2026),
    }]
    html_txt = montar_html_informe(
        org_short="Sinapesc", org_full="Sindicato", ano=2026, socios=socios, por_pessoa=por,
    )
    assert "Informe Mensal" in html_txt and "Fulano De Tal" in html_txt
    assert "Sem Meses" in html_txt
    assert "spp" in html_txt and "piracema" in html_txt
    assert "Detalhe dos meses preenchidos" in html_txt
    assert "Março/2026" in html_txt and "kg" in html_txt
    assert "nome_arquivo" or nome_arquivo_informe(2026).startswith("informe-mensal-2026-")
    assert "Abrir tabela" not in html_txt  # só no JS


def test_api_abrir_tabela(tmp_path=None) -> None:
    from pathlib import Path
    import tempfile
    from sheets.informe_mensal_service import InformeMensalService
    from sheets.models import Pessoa
    import webapp.api as api_mod
    import controle.informe_mensal_relatorio as rel

    cli = FakeClient()
    pessoa = Pessoa(id="p1", nome="maria das dores", cpf="12345678901", criado_em="",
                    municipio="Remanso", telefone="(74) 99999-0000")

    class FakeSheets:
        client = cli
        actor = ""
        def get_all_pessoas(self):
            return [pessoa]

    api = api_mod.SinapescApi()
    api._logged_in = True
    api._admin_user = "operador@sinapesc"
    api._ensure_service = lambda require_login=True: FakeSheets()  # type: ignore[assignment]
    eventos = []
    api._dispatch = lambda ev, payload: eventos.append((ev, payload))  # type: ignore[assignment]

    def sync_run(op, work, busy=""):
        try:
            eventos.append((op, {"ok": True, "data": work()}))
        except Exception as exc:  # noqa: BLE001
            eventos.append((op, {"ok": False, "error": str(exc)}))
        return {"ok": True, "pending": True}

    api._run_async = sync_run  # type: ignore[assignment]
    for m in im.MESES_PESCA:
        api.gerar_informe_mes(json.dumps({"person_id": "p1", "ano": 2026, "mes": m}))
        assert eventos[-1][1]["ok"], eventos[-1]

    pasta = Path(tempfile.mkdtemp())
    import controle.relatorio as relatorio_mod

    orig = relatorio_mod.pasta_relatorios
    relatorio_mod.pasta_relatorios = lambda: pasta  # type: ignore[assignment]
    try:
        api.abrir_informe_tabela(2026)
    finally:
        relatorio_mod.pasta_relatorios = orig  # type: ignore[assignment]
    ev, res = eventos[-1]
    assert ev == "informe_tabela" and res["ok"], res
    path = Path(res["data"]["path"])
    assert path.exists() and path.suffix == ".html"
    texto = path.read_text(encoding="utf-8")
    assert "Maria Das Dores" in texto or "maria das dores".title() in texto or "Maria" in texto
    assert res["data"]["com_meses"] == 1
    aud = [e.acao for e in api._ensure_informe().listar_auditoria(50)]
    assert "abrir_tabela_informe" in aud


def test_html_tabela_socio_individual() -> None:
    from controle.informe_mensal_relatorio import (
        montar_html_informe_socio,
        nome_arquivo_informe_socio,
    )

    salvos = _ano_completo(33)
    parcial = {m: salvos[m] for m in ("mar", "abr", "mai")}
    socio = {
        "id": "p33",
        "nome": "Antonio Individual",
        "cpf": "000.000.000-33",
        "cpf_raw": f"{33:011d}",
        "telefone": "(74) 90000-0000",
        "municipio": "Casa Nova",
        "resumo": im.resumo_socio(parcial, f"{33:011d}", 2026),
    }
    html_txt = montar_html_informe_socio(
        org_short="Sinapesc",
        org_full="Sindicato",
        ano=2026,
        socio=socio,
        meses=parcial,
    )
    assert "Antonio Individual" in html_txt
    assert "Março" in html_txt and "Abril" in html_txt and "Maio" in html_txt
    assert "Junho" not in html_txt
    assert "Somente os" in html_txt
    assert nome_arquivo_informe_socio(2026, "Antonio Individual").startswith(
        "informe-mensal-2026-"
    )


def test_api_abrir_tabela_socio() -> None:
    from pathlib import Path
    import tempfile
    from sheets.models import Pessoa
    import webapp.api as api_mod
    import controle.relatorio as relatorio_mod

    cli = FakeClient()
    pessoa = Pessoa(
        id="p1",
        nome="maria das dores",
        cpf="12345678901",
        criado_em="",
        municipio="Remanso",
        telefone="(74) 99999-0000",
    )

    class FakeSheets:
        client = cli
        actor = ""

        def get_all_pessoas(self):
            return [pessoa]

    api = api_mod.SinapescApi()
    api._logged_in = True
    api._admin_user = "operador@sinapesc"
    api._ensure_service = lambda require_login=True: FakeSheets()  # type: ignore[assignment]
    eventos = []
    api._dispatch = lambda ev, payload: eventos.append((ev, payload))  # type: ignore[assignment]

    def sync_run(op, work, busy=""):
        try:
            eventos.append((op, {"ok": True, "data": work()}))
        except Exception as exc:  # noqa: BLE001
            eventos.append((op, {"ok": False, "error": str(exc)}))
        return {"ok": True, "pending": True}

    api._run_async = sync_run  # type: ignore[assignment]

    api.abrir_informe_tabela_socio(json.dumps({"person_id": "p1", "ano": 2026}))
    ev, res = eventos[-1]
    assert ev == "informe_tabela_socio" and res["ok"] is False

    for m in ("mar", "abr"):
        api.gerar_informe_mes(json.dumps({"person_id": "p1", "ano": 2026, "mes": m}))
        assert eventos[-1][1]["ok"], eventos[-1]

    pasta = Path(tempfile.mkdtemp())
    orig = relatorio_mod.pasta_relatorios
    relatorio_mod.pasta_relatorios = lambda: pasta  # type: ignore[assignment]
    try:
        api.abrir_informe_tabela_socio(json.dumps({"person_id": "p1", "ano": 2026}))
    finally:
        relatorio_mod.pasta_relatorios = orig  # type: ignore[assignment]
    ev, res = eventos[-1]
    assert ev == "informe_tabela_socio" and res["ok"], res
    assert res["data"]["meses"] == 2
    path = Path(res["data"]["path"])
    assert path.exists()
    texto = path.read_text(encoding="utf-8")
    assert "Março" in texto and "Abril" in texto
    assert "Maio" not in texto
    aud = [e.acao for e in api._ensure_informe().listar_auditoria(50)]
    assert "abrir_tabela_socio" in aud


def test_version() -> None:
    theme = (ROOT / "ui" / "theme.py").read_text(encoding="utf-8")
    assert 'APP_VERSION = "1.8.3"' in theme


if __name__ == "__main__":
    for name, fn in list(globals().items()):
        if name.startswith("test_") and callable(fn):
            fn()
    print("OK informe_mensal")
