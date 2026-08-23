"""Declaração de Residência — Seguro-Defeso (Defeso Fácil)."""

from __future__ import annotations

import html
import re
import uuid
from dataclasses import asdict, dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

from ui.formatters import display_nome, format_cpf, format_nome, only_digits


DEFESO_TAB = "Defeso"
DEFESO_HEADER = [
    "id",
    "personId",
    "nome",
    "cpf",
    "rg",
    "nacionalidade",
    "profissao",
    "cep",
    "endereco",
    "numero",
    "bairro",
    "municipio",
    "uf",
    "telefone",
    "email",
    "status",
    "temIdentidade",
    "temCarteiraPesca",
    "temCaf",
    "atualizadoEm",
    "criadoEm",
    "telefoneReap",
    "parcelasRecebidas",
    "entradaConfirmada",
]

MESES_PT = (
    "janeiro",
    "fevereiro",
    "março",
    "abril",
    "maio",
    "junho",
    "julho",
    "agosto",
    "setembro",
    "outubro",
    "novembro",
    "dezembro",
)


@dataclass
class FichaDefeso:
    id: str = ""
    person_id: str = ""
    nome: str = ""
    cpf: str = ""
    rg: str = ""
    nacionalidade: str = "Brasileira"
    profissao: str = "Pescador profissional"
    cep: str = ""
    endereco: str = ""
    numero: str = ""
    bairro: str = ""
    municipio: str = ""
    uf: str = ""
    telefone: str = ""
    email: str = ""
    status: str = "rascunho"
    tem_identidade: str = ""
    tem_carteira_pesca: str = ""
    tem_caf: str = ""
    atualizado_em: str = ""
    criado_em: str = ""
    telefone_reap: str = ""
    parcelas_recebidas: str = ""
    entrada_confirmada: str = ""

    def to_row(self) -> List[str]:
        return [
            self.id,
            self.person_id,
            self.nome,
            self.cpf,
            self.rg,
            self.nacionalidade,
            self.profissao,
            self.cep,
            self.endereco,
            self.numero,
            self.bairro,
            self.municipio,
            self.uf,
            self.telefone,
            self.email,
            self.status,
            self.tem_identidade,
            self.tem_carteira_pesca,
            self.tem_caf,
            self.atualizado_em,
            self.criado_em,
            self.telefone_reap,
            self.parcelas_recebidas,
            self.entrada_confirmada,
        ]

    def to_dict(self) -> Dict[str, Any]:
        d = asdict(self)
        d["nome_display"] = display_nome(self.nome)
        d["cpf_formatado"] = format_cpf(self.cpf)
        d["tem_ficha"] = bool(self.id)
        return d


def new_id() -> str:
    return uuid.uuid4().hex[:12]


def now_stamp() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def row_to_ficha(row: List[str] | None) -> Optional[FichaDefeso]:
    if not row or not str(row[0]).strip():
        return None
    cells = [str(c) if c is not None else "" for c in row]
    while len(cells) < len(DEFESO_HEADER):
        cells.append("")
    return FichaDefeso(
        id=cells[0].strip(),
        person_id=cells[1].strip(),
        nome=cells[2].strip(),
        cpf=only_digits(cells[3]),
        rg=cells[4].strip(),
        nacionalidade=cells[5].strip() or "Brasileira",
        profissao=cells[6].strip() or "Pescador profissional",
        cep=cells[7].strip(),
        endereco=cells[8].strip(),
        numero=cells[9].strip(),
        bairro=cells[10].strip(),
        municipio=cells[11].strip(),
        uf=cells[12].strip().upper()[:2],
        telefone=cells[13].strip(),
        email=cells[14].strip(),
        status=cells[15].strip() or "rascunho",
        tem_identidade=cells[16].strip(),
        tem_carteira_pesca=cells[17].strip(),
        tem_caf=cells[18].strip(),
        atualizado_em=cells[19].strip(),
        criado_em=cells[20].strip(),
        telefone_reap=cells[21].strip() if len(cells) > 21 else "",
        parcelas_recebidas=cells[22].strip() if len(cells) > 22 else "",
        entrada_confirmada=cells[23].strip() if len(cells) > 23 else "",
    )


def payload_to_ficha(payload: Dict[str, Any], *, existing: Optional[FichaDefeso] = None) -> FichaDefeso:
    base = existing or FichaDefeso()
    nome = format_nome(str(payload.get("nome") or base.nome or ""))
    cpf = only_digits(str(payload.get("cpf") or base.cpf or ""))
    agora = now_stamp()
    return FichaDefeso(
        id=(str(payload.get("id") or base.id or "").strip() or new_id()),
        person_id=str(payload.get("person_id") or base.person_id or "").strip(),
        nome=nome,
        cpf=cpf,
        rg=str(payload.get("rg") or "").strip(),
        nacionalidade=str(payload.get("nacionalidade") or "Brasileira").strip() or "Brasileira",
        profissao=str(payload.get("profissao") or "Pescador profissional").strip()
        or "Pescador profissional",
        cep=_format_cep(str(payload.get("cep") or "")),
        endereco=str(payload.get("endereco") or "").strip(),
        numero=str(payload.get("numero") or "").strip(),
        bairro=str(payload.get("bairro") or "").strip(),
        municipio=str(payload.get("municipio") or "").strip(),
        uf=str(payload.get("uf") or "").strip().upper()[:2],
        telefone=str(payload.get("telefone") or "").strip(),
        email=str(payload.get("email") or "").strip(),
        status=str(payload.get("status") or base.status or "rascunho").strip() or "rascunho",
        tem_identidade=base.tem_identidade,
        tem_carteira_pesca=base.tem_carteira_pesca,
        tem_caf=base.tem_caf,
        atualizado_em=agora,
        criado_em=base.criado_em or agora,
        telefone_reap=str(payload.get("telefone_reap") or base.telefone_reap or "").strip(),
        parcelas_recebidas=str(payload.get("parcelas_recebidas") or base.parcelas_recebidas or "").strip(),
        entrada_confirmada=(
            _flag_sim(payload.get("entrada_confirmada"))
            if "entrada_confirmada" in payload
            else base.entrada_confirmada
        ),
    )


def validar_ficha(f: FichaDefeso) -> Optional[str]:
    if not f.nome.strip():
        return "Informe o nome completo."
    if len(f.cpf) != 11:
        return "CPF deve conter 11 dígitos."
    if f.uf and len(f.uf) != 2:
        return "UF deve ter 2 letras (ex.: BA)."
    cep_digits = only_digits(f.cep)
    if f.cep and len(cep_digits) not in (0, 8):
        return "CEP inválido."
    return None


def _flag_sim(valor: Any) -> str:
    if valor is True or str(valor or "").strip().lower() in ("sim", "true", "1", "yes", "on"):
        return "sim"
    return ""


def _format_cep(valor: str) -> str:
    d = only_digits(valor)
    if len(d) == 8:
        return f"{d[:5]}-{d[5:]}"
    return valor.strip()


def data_extenso(dt: Optional[datetime] = None) -> str:
    dt = dt or datetime.now()
    return f"{dt.day} de {MESES_PT[dt.month - 1]} de {dt.year}"


def montar_declaracao_html(f: FichaDefeso, *, org_full: str = "") -> str:
    nome = html.escape(display_nome(f.nome))
    cpf = html.escape(format_cpf(f.cpf))
    rg = html.escape(f.rg or "_______________")
    nac = html.escape(f.nacionalidade or "Brasileira")
    prof = html.escape(f.profissao or "Pescador profissional")
    end = html.escape(f.endereco or "_______________")
    num = html.escape(f.numero or "____")
    bairro = html.escape(f.bairro or "_______________")
    mun = html.escape(f.municipio or "_______________")
    uf = html.escape(f.uf or "__")
    cep = html.escape(f.cep or "________")
    tel = html.escape(f.telefone or "_______________")
    email = html.escape(f.email or "_______________")
    local = html.escape(f.municipio or "_______________")
    data = html.escape(data_extenso())
    org = html.escape(org_full or "Sinapesc")

    return f"""<!DOCTYPE html>
<html lang="pt-BR">
<head>
<meta charset="UTF-8" />
<title>Declaração de Residência — {nome}</title>
<style>
  @page {{ size: A4; margin: 18mm; }}
  body {{ font-family: "Times New Roman", Times, serif; font-size: 12.5pt; color: #111; line-height: 1.45; }}
  h1 {{ text-align: center; font-size: 14pt; margin: 0 0 4px; text-transform: uppercase; }}
  h2 {{ text-align: center; font-size: 13pt; margin: 0 0 22px; text-transform: uppercase; letter-spacing: .4px; }}
  .org {{ text-align: center; font-size: 10pt; color: #444; margin-bottom: 18px; }}
  p {{ margin: 0 0 12px; text-align: justify; }}
  .linha {{ margin: 10px 0; }}
  .assinatura {{ margin-top: 42px; text-align: center; }}
  .assinatura .traco {{ border-top: 1px solid #111; width: 320px; margin: 48px auto 6px; }}
  .bloco {{ margin-top: 36px; font-size: 11pt; }}
  .bloco h3 {{ font-size: 11pt; margin: 0 0 10px; text-transform: uppercase; }}
  .muted {{ color: #333; font-size: 10.5pt; }}
  .artigo {{ font-size: 10pt; margin: 14px 0; }}
  @media print {{ .no-print {{ display: none !important; }} }}
</style>
</head>
<body>
  <button class="no-print" onclick="window.print()" style="margin-bottom:16px;padding:8px 14px;cursor:pointer">Imprimir</button>
  <h1>Ministério do Trabalho e Emprego — MTE</h1>
  <h2>Declaração de Residência</h2>
  <div class="org">{org}</div>

  <p>Na falta de documentos próprios, aptos a comprovarem a minha residência e domicílio, eu,</p>
  <p><strong>{nome}</strong></p>
  <p class="linha">Nacionalidade: <strong>{nac}</strong> &nbsp;&nbsp; Profissão: <strong>{prof}</strong></p>
  <p class="linha">Inscrito no (CPF) sob o nº <strong>{cpf}</strong>, portador(a) da carteira de RG/CIN: <strong>{rg}</strong>,</p>
  <p>declaro ser residente e domiciliado(a) no endereço:</p>
  <p class="linha"><strong>{end}</strong></p>
  <p class="linha">Número: <strong>{num}</strong> &nbsp;&nbsp; Bairro: <strong>{bairro}</strong> &nbsp;&nbsp; Município: <strong>{mun}</strong></p>
  <p class="linha">UF: <strong>{uf}</strong> &nbsp;&nbsp; CEP: <strong>{cep}</strong> &nbsp;&nbsp; Telefone: <strong>{tel}</strong></p>
  <p class="linha">E-mail: <strong>{email}</strong></p>

  <p>Declaro sob responsabilidade civil e penal, que as informações declaradas acima são
  verdadeiras e que estou ciente que as informações não verídicas declaradas implicarão em
  penalidades previstas no Artigo 299 do Código Penal (Falsidade Ideológica), além de sanções
  civis e administrativas cabíveis, conforme dispõe a Lei nº 7.115, de 29 de agosto de 1983.</p>

  <p class="artigo">“Art. 299 - Omitir, em documento público ou particular, declaração que dele devia constar,
  ou nele inserir ou fazer inserir declaração falsa ou diversa da que devia ser escrita, com o fim
  de prejudicar direito, criar obrigação ou alterar a verdade sobre fato juridicamente relevante:
  Pena - reclusão, de um a cinco anos, e multa, se o documento é público, e reclusão de um a
  três anos, e multa, se o documento é particular.”</p>

  <p>Por ser verdade, assino esta declaração:</p>
  <p>{local}, {data}.</p>

  <div class="assinatura">
    <div class="traco"></div>
    Assinatura do Pescador Profissional
  </div>

  <div class="bloco">
    <h3>Assinatura a rogo (interessado analfabeto) e testemunhas</h3>
    <p class="muted">NOME: _______________________________________________</p>
    <p class="muted">RG nº _____________________ CPF _____________________</p>
    <p class="muted">ASSINATURA: _______________________________________</p>
    <br/>
    <p class="muted">NOME: _______________________________________________</p>
    <p class="muted">RG nº _____________________ CPF _____________________</p>
    <p class="muted">ASSINATURA: _______________________________________</p>
    <p class="muted" style="margin-top:18px">POLEGAR DIREITO</p>
  </div>
  <script>setTimeout(function(){{ window.print(); }}, 400);</script>
</body>
</html>
"""


def pasta_declaracoes() -> Path:
    from controle.backup import backup_root

    dest = backup_root() / "defeso"
    dest.mkdir(parents=True, exist_ok=True)
    return dest


def endereco_completo(f: FichaDefeso) -> str:
    """Monta endereço completo só com dados da ficha Defeso."""
    partes: List[str] = []
    if f.endereco:
        linha = f.endereco.strip()
        if f.numero:
            linha = f"{linha}, nº {f.numero.strip()}"
        partes.append(linha)
    elif f.numero:
        partes.append(f"nº {f.numero.strip()}")
    if f.bairro:
        partes.append(f.bairro.strip())
    cidade = f.municipio.strip()
    if f.uf:
        cidade = f"{cidade}/{f.uf}" if cidade else f.uf
    if cidade:
        partes.append(cidade)
    if f.cep:
        partes.append(f"CEP {f.cep.strip()}")
    return " — ".join(partes)


def entrada_confirmada_flag(f: FichaDefeso) -> bool:
    return str(f.entrada_confirmada or "").strip().lower() in ("sim", "true", "1", "yes")


def salvar_declaracao_html(html_text: str, *, cpf: str, nome: str) -> Path:
    stamp = datetime.now().strftime("%Y%m%d_%H%M")
    slug = re.sub(r"[^a-zA-Z0-9]+", "-", (nome or "pescador"))[:40].strip("-") or "pescador"
    cpf_d = only_digits(cpf) or "semcpf"
    path = pasta_declaracoes() / f"declaracao-{cpf_d}-{slug}-{stamp}.html"
    path.write_text(html_text, encoding="utf-8")
    return path
