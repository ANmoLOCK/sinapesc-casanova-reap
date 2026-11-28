"""Notificações (pedidos da diretoria), lotes REAP/Defeso e o programa que fechava sozinho."""

from __future__ import annotations

import re
import threading
import unittest
from pathlib import Path
from typing import Dict, List

ROOT = Path(__file__).resolve().parent


def _col_idx(letras: str) -> int:
    n = 0
    for ch in letras:
        n = n * 26 + (ord(ch) - 64)
    return n - 1


class PlanilhaMemoria:
    """Cliente falso com as abas em memória (A1 = linha 1)."""

    def __init__(self) -> None:
        self.abas: Dict[str, List[List[str]]] = {}

    def ensure_tabs(self) -> None:
        return None

    def _parse(self, rng: str):
        aba, cel = rng.split("!", 1)
        m = re.match(r"([A-Z]+)(\d*)(?::([A-Z]+)(\d*))?", cel)
        assert m, rng
        c0, r0, _c1, _r1 = m.groups()
        return aba, _col_idx(c0), int(r0) if r0 else 1

    def get_values(self, rng: str) -> List[List[str]]:
        aba, _c0, r0 = self._parse(rng)
        rows = self.abas.get(aba, [])
        return [list(r) for r in rows[r0 - 1 :]]

    def update_values(self, rng: str, values) -> None:
        aba, c0, r0 = self._parse(rng)
        rows = self.abas.setdefault(aba, [])
        for i, vals in enumerate(values):
            while len(rows) < r0 + i:
                rows.append([])
            row = rows[r0 - 1 + i]
            for j, v in enumerate(vals):
                while len(row) <= c0 + j:
                    row.append("")
                row[c0 + j] = v

    def append_values(self, rng: str, values) -> None:
        aba, _c0, _r0 = self._parse(rng)
        rows = self.abas.setdefault(aba, [["cabecalho"]])
        if not rows:
            rows.append(["cabecalho"])
        rows.extend([list(v) for v in values])

    def batch_update_values(self, data, chunk_size: int = 100) -> None:
        for item in data:
            self.update_values(item["range"], item["values"])


class PedidosLotesTest(unittest.TestCase):
    def _svc(self):
        from sheets.service import SheetsService

        cli = PlanilhaMemoria()
        cli.abas["Pessoas"] = [["id"], ["p1", "Ana", "111.444.777-35", "", "Casa Nova", ""], ["p2", "Beto", "529.982.247-25", "", "", ""]]
        cli.abas["Reap"] = [["id"], ["r1", "p1", "2026", *["FALSE"] * 12, ""], ["r2", "p2", "2026", *["FALSE"] * 12, ""]]
        cli.abas["Config"] = [["chave", "valor"]]
        cli.abas["Pedidos"] = [["id"]]
        cli.abas["Auditoria"] = [["id"]]
        svc = SheetsService(cli)  # type: ignore[arg-type]
        svc.actor = "presidente@x.com"
        return svc, cli

    def test_pedido_criar_nao_duplica_e_marca_feito(self) -> None:
        from controle.pedidos import STATUS_FEITO, novo_pedido

        svc, _cli = self._svc()
        p = novo_pedido(tipo="reap", person_id="p1", nome="Ana", cpf="111.444.777-35", lote="Lote REAP 2026", pedido_por="presidente@x.com", pedido_por_nome="Presidente")
        svc.criar_pedido(p)
        with self.assertRaises(ValueError):
            svc.criar_pedido(novo_pedido(tipo="reap", person_id="p1", nome="Ana", cpf="", lote="Lote REAP 2026", pedido_por="vice@x.com"))
        svc.criar_pedido(novo_pedido(tipo="defeso", person_id="p1", nome="Ana", cpf="11144477735", lote="Defeso 2026", pedido_por="vice@x.com"))
        self.assertEqual(len(svc.listar_pedidos(tipo="reap")), 1)
        self.assertEqual(len(svc.listar_pedidos(tipo="defeso")), 1)
        alvo = svc.listar_pedidos(tipo="reap")[0]
        alvo.status = STATUS_FEITO
        svc.atualizar_pedido(alvo)
        self.assertEqual(svc.listar_pedidos(tipo="reap")[0].status, STATUS_FEITO)
        svc.criar_pedido(novo_pedido(tipo="reap", person_id="p1", nome="Ana", cpf="", lote="Lote REAP 2027", pedido_por="presidente@x.com"))
        self.assertEqual(svc.listar_pedidos(tipo="reap")[0].lote, "Lote REAP 2027")

    def test_abrir_lote_reap_2027_em_branco(self) -> None:
        svc, cli = self._svc()
        res = svc.abrir_lote_reap(2027, copiar_de=2026)
        self.assertEqual(res["criados"], 2)
        anos = [r for r in cli.abas["Reap"][1:] if r[2] == 2027]
        self.assertEqual(len(anos), 2)
        self.assertTrue(all(c == "FALSE" for r in anos for c in r[3:15]))
        self.assertEqual(svc.lotes_config()["reap_atual"], 2027)
        self.assertEqual(svc.abrir_lote_reap(2027)["criados"], 0)

    def test_lotes_defeso_varios_por_pescador(self) -> None:
        from controle.defeso import DEFESO_HEADER, FichaDefeso
        from controle.lotes import LOTE_DEFESO_PADRAO, com_lote, lotes_efetivos, sem_lote
        from sheets.defeso_service import DefesoService

        self.assertEqual(lotes_efetivos(""), [LOTE_DEFESO_PADRAO])
        self.assertEqual(com_lote("", "2027"), "Defeso 2026, Defeso 2027")
        self.assertEqual(sem_lote("Defeso 2026, Defeso 2027", "defeso 2026"), "Defeso 2027")
        with self.assertRaises(ValueError):
            sem_lote("Defeso 2026", "Defeso 2026")

        cli = PlanilhaMemoria()
        f1 = FichaDefeso(id="f1", nome="Ana", cpf="11144477735")
        f2 = FichaDefeso(id="f2", nome="Beto", cpf="52998224725", lotes="Defeso 2025")
        cli.abas["Defeso"] = [list(DEFESO_HEADER), f1.to_row(), f2.to_row()]
        svc = DefesoService(cli)  # type: ignore[arg-type]
        svc._ready = True
        res = svc.criar_lote("Defeso 2027", copiar_de="Defeso 2026")
        self.assertEqual(res["copiados"], 1)
        fichas = {f.id: f for f in svc.listar()}
        self.assertEqual(fichas["f1"].lotes, "Defeso 2026, Defeso 2027")
        self.assertEqual(fichas["f2"].lotes, "Defeso 2025")
        nomes = [d["nome"] for d in svc.listar_lotes()]
        self.assertEqual(nomes, ["Defeso 2027", "Defeso 2026", "Defeso 2025"])
        self.assertEqual(len(DEFESO_HEADER), 26)
        self.assertEqual(DEFESO_HEADER[25], "lotes")

    def test_diretoria_pode_pedir(self) -> None:
        from controle import usuarios as u

        user = u.Usuario(id="1", email="pres@x.com", nome="Presidente", senha_hash="", papel="presidenta")
        self.assertEqual(user.papel, u.PAPEL_DIRETORIA)
        self.assertTrue(user.pode_solicitar)
        self.assertTrue(user.pode_cadastrar)
        self.assertFalse(user.pode_editar)
        self.assertFalse(user.pode_admin_usuarios)
        op = u.Usuario(id="2", email="op@x.com", nome="Op", senha_hash="", papel="operador")
        self.assertFalse(op.pode_solicitar)
        self.assertIn("solicitar", u.PERMISSOES_TODAS)

    def test_cada_thread_tem_sua_conexao(self) -> None:
        import sheets  # noqa: F401  (instala o patch)
        from sheets import http_seguro

        class Cred:
            pass

        class Orig:
            credentials = Cred()

        orig = Orig()
        vistos = []

        def pega():
            vistos.append(http_seguro._http_da_thread(orig))
            vistos.append(http_seguro._http_da_thread(orig))

        t1 = threading.Thread(target=pega)
        t2 = threading.Thread(target=pega)
        t1.start(); t2.start(); t1.join(); t2.join()
        self.assertIs(vistos[0], vistos[1])
        self.assertIsNot(vistos[0], vistos[2])
        from googleapiclient.http import HttpRequest

        self.assertIn("http_seguro", HttpRequest.execute.__code__.co_filename)

    def test_log_de_erro_e_dispatch_seguro(self) -> None:
        launcher = (ROOT / "webapp" / "launcher.py").read_text(encoding="utf-8")
        api = (ROOT / "webapp" / "api.py").read_text(encoding="utf-8")
        self.assertIn("faulthandler.enable", launcher)
        self.assertIn("threading.excepthook", launcher)
        self.assertIn("sinapesc-erros.log", launcher)
        self.assertIn("with self._js_lock:", api)
        self.assertIn("default=str", api)

    def test_telas(self) -> None:
        app = (ROOT / "web" / "js" / "app.js").read_text(encoding="utf-8")
        self.assertIn('{ id: "notificacoes", label: "Notificações", screen: "notificacoes" }', app)
        self.assertIn("notificacoes: renderNotificacoesReap", app)
        self.assertIn("data-pedir-reap", app)
        self.assertIn("📨 Pedir entrada no seguro", app)
        self.assertIn('data-defeso-aba="notificacoes"', app)
        self.assertIn("+ Abrir novo lote", app)
        self.assertIn('api("criar_lote_defeso"', app.replace("callApi(", "api("))
        self.assertIn("lote_defeso_pessoas", app)


if __name__ == "__main__":
    unittest.main()
