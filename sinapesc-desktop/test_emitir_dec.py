"""EmitirDec e o encaixe de maiúsculas no Defeso Fácil."""

from __future__ import annotations

import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parent


class EmitirDecTest(unittest.TestCase):
    def test_maiuscula_nao_encolhe_o_corpo(self) -> None:
        import pymupdf as fitz

        from controle.defeso_declaracao import MIN_CORPO, _encaixe

        font = fitz.Font("times-roman")
        longo = "MARIA APARECIDA DOS SANTOS DE OLIVEIRA E SOUZA DA SILVA"
        tamanho, escala = _encaixe(font, longo, 90, 18)
        self.assertGreaterEqual(tamanho, MIN_CORPO)
        self.assertLessEqual(escala, 1.0)
        self.assertGreater(escala, 0.2)
        cabe = font.text_length(longo, fontsize=tamanho) * escala
        self.assertLessEqual(cabe, 90.5)

    def test_defeso_maiuscula_mantem_altura(self) -> None:
        from controle.defeso import FichaDefeso
        from controle.defeso_declaracao import preencher_pdf

        ficha = FichaDefeso(
            nome="JOSE APARECIDO DOS SANTOS DE OLIVEIRA E SOUZA",
            cpf="10582575524",
            rg="1234567",
            nacionalidade="BRASILEIRA",
            profissao="PESCADOR PROFISSIONAL",
            endereco="RUA PROJETADA DO LOTEAMENTO SANTO ANTONIO",
            numero="102",
            bairro="VILA SAO JOSE",
            municipio="CASA NOVA",
            uf="BA",
            cep="47300-000",
            telefone="74999990000",
            email="JOSE.OLIVEIRA@EMAIL.COM",
        )
        pdf = preencher_pdf(ficha, fonte_id="allura")
        self.assertTrue(pdf.is_file())
        import pymupdf as fitz

        doc = fitz.open(pdf)
        spans = [
            s
            for b in doc[0].get_text("dict")["blocks"]
            if b.get("type") == 0
            for line in b["lines"]
            for s in line["spans"]
            if s.get("color") == 866477 and s["text"].strip() and len(s["text"]) <= 3
        ]
        doc.close()
        self.assertGreaterEqual(len(spans), 10)
        self.assertTrue(all(s["size"] >= 12 for s in spans))

    def test_pdf_junta_as_duas_e_cabe_no_traco(self) -> None:
        import pymupdf as fitz

        from controle.emitir_dec import CAMPOS_ENDERECO, CAMPOS_FILIACAO, gerar_pdf

        nome = "MARIA APARECIDA DOS SANTOS DE OLIVEIRA E SOUZA"
        payload = {
            "nome": nome,
            "cpf": "105.825.755-24",
            "rg": "12.345.678-9",
            "nacionalidade": "BRASILEIRA",
            "estado_civil": "CASADA",
            "profissao": "PESCADORA PROFISSIONAL",
            "endereco": "RUA PROJETADA DO LOTEAMENTO SANTO ANTONIO",
            "numero": "102",
            "bairro": "VILA SAO JOSE",
            "municipio": "CASA NOVA",
            "uf": "BA",
            "cep": "47300-000",
            "telefone": "(74) 99999-0000",
            "email": "maria.oliveira@email.com",
            "local": "CASA NOVA",
            "data": "27/11/2026",
            "data_filiacao": "15 de março de 2019",
            "quais": ["endereco", "filiacao"],
            "fonte": "times",
        }
        path = gerar_pdf(payload, fonte_id="times")
        doc = fitz.open(path)
        self.assertEqual(doc.page_count, 2)
        self.assertIn(nome, doc[0].get_text("text"))
        self.assertIn(nome, doc[1].get_text("text"))
        self.assertIn("15 de março de 2019", doc[1].get_text("text"))
        self._cabe(doc[0], CAMPOS_ENDERECO)
        self._cabe(doc[1], CAMPOS_FILIACAO)
        doc.close()

    def _cabe(self, page, campos) -> None:
        linhas = []
        for b in page.get_text("dict")["blocks"]:
            if b.get("type") != 0:
                continue
            for line in b["lines"]:
                spans = [s for s in line["spans"] if s.get("color")]
                if not spans:
                    continue
                texto = "".join(s["text"] for s in spans)
                box = spans[0]["bbox"]
                linhas.append((texto, box[0], box[2], (box[1] + box[3]) / 2))
        for texto, x0, x1, ymid in linhas:
            donos = [
                (chave, cx0, cx1)
                for chave, (cx0, base, cx1) in campos.items()
                if abs(ymid - (base - 4)) < 16 and cx0 - 4 <= x0 <= cx1
            ]
            self.assertTrue(donos, texto)
            _chave, _cx0, cx1 = donos[0]
            self.assertLessEqual(x1, cx1 + 6, texto)

    def test_validar_nome_cpf_e_escolha(self) -> None:
        from controle.emitir_dec import validar, valores_de_payload

        v = valores_de_payload({"nome": "", "cpf": "1"})
        self.assertEqual(validar(v, ["endereco"]), "Informe o nome completo.")
        v = valores_de_payload({"nome": "Ana", "cpf": "123"})
        self.assertIn("11", validar(v, ["endereco"]) or "")
        v = valores_de_payload({"nome": "Ana", "cpf": "10582575524"})
        self.assertIn("Marque", validar(v, []) or "")

    def test_tela_tem_o_botao(self) -> None:
        app = (ROOT / "web" / "js" / "app.js").read_text(encoding="utf-8")
        js = (ROOT / "web" / "js" / "emitir_dec.js").read_text(encoding="utf-8")
        html = (ROOT / "web" / "index.html").read_text(encoding="utf-8")
        api = (ROOT / "webapp" / "api.py").read_text(encoding="utf-8")
        card = app.split('id="go-consulta-rgp"', 1)[1].split("</div>", 1)[0]
        self.assertIn('id="go-emitirdec">EmitirDec</button>', card)
        self.assertLess(app.index('id="go-consulta-rgp"'), app.index('id="go-emitirdec"'))
        self.assertIn("goEmitirDec", app)
        self.assertNotIn("rgp-emitirdec", app)
        self.assertIn("SinapescEmitirDec.open", app)
        self.assertIn("Gerar PDF", js)
        self.assertIn("Declaração de endereço", js)
        self.assertIn("Declaração de afiliação", js)
        self.assertIn("Times New Roman", js)
        self.assertIn("emitir_dec.js", html)
        self.assertIn("def emitir_declaracao", api)


if __name__ == "__main__":
    unittest.main()
