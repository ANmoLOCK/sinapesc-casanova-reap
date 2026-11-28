"""EmitirDec — declaração de endereço e declaração de filiação.

Preenche os modelos oficiais (PDF) com Times, Arial ou Calibri e abre no
navegador para imprimir. A letra maiúscula aperta na largura, sem encolher
o corpo até sumir e sem invadir o texto impresso do formulário.
"""

from __future__ import annotations

import re
import sys
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple

from controle.defeso import pasta_declaracoes
from controle.defeso_declaracao import PEN_BLUE, _encaixe
from ui.formatters import format_cpf, only_digits

MESES = (
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

# Times New Roman, Arial e Calibri (arquivos OFL com a mesma medida).
FONTES: Dict[str, Dict[str, str]] = {
    "times": {
        "id": "times",
        "label": "Times New Roman",
        "file": "LiberationSerif-Regular.ttf",
        "size": "13",
    },
    "arial": {
        "id": "arial",
        "label": "Arial",
        "file": "LiberationSans-Regular.ttf",
        "size": "13",
    },
    "calibri": {
        "id": "calibri",
        "label": "Calibri",
        "file": "Carlito-Regular.ttf",
        "size": "13",
    },
}
DEFAULT_FONTE = "times"

# (x0, palpite da linha, x1). A base é ajustada no traço real.
# Local, dia, mês e ano ficam em branco para preencher à mão.
CAMPOS_ENDERECO: Dict[str, Tuple[float, float, float]] = {
    "nome": (80.0, 146.4, 538.0),
    "nacionalidade": (170.0, 170.4, 308.0),
    "estado_civil": (396.0, 170.4, 530.0),
    "profissao": (148.0, 193.4, 300.0),
    "cpf": (142.0, 217.7, 340.0),
    "rg": (138.0, 242.6, 280.0),
    "endereco": (82.0, 265.9, 458.0),
    "numero": (536.0, 265.9, 555.0),
    "bairro": (128.0, 306.0, 350.0),
    "municipio": (430.0, 306.0, 548.0),
    "uf": (114.0, 329.8, 152.0),
    "cep": (204.0, 329.8, 318.0),
    "telefone": (438.0, 329.8, 548.0),
    "email": (136.0, 355.7, 545.0),
}

CAMPOS_FILIACAO: Dict[str, Tuple[float, float, float]] = {
    "nome": (54.0, 140.5, 408.0),
    "cpf": (452.0, 140.5, 568.0),
    "rg": (76.0, 168.0, 174.0),
    "residente": (230.0, 168.0, 560.0),
    "data_filiacao": (118.0, 447.0, 545.0),
}


def _app_root() -> Path:
    if getattr(sys, "frozen", False):
        return Path(sys._MEIPASS)  # type: ignore[attr-defined]
    return Path(__file__).resolve().parent.parent


def assets_dir() -> Path:
    return _app_root() / "assets" / "declaracoes"


def fontes_dir() -> Path:
    return assets_dir() / "fontes"


def listar_fontes() -> List[Dict[str, Any]]:
    out: List[Dict[str, Any]] = []
    for meta in FONTES.values():
        path = fontes_dir() / meta["file"]
        out.append(
            {
                "id": meta["id"],
                "label": meta["label"],
                "disponivel": path.is_file() and path.stat().st_size > 1000,
            }
        )
    return out


def normalize_fonte(fonte_id: str) -> str:
    key = (fonte_id or "").strip().lower()
    aliases = {
        "times new roman": "times",
        "times-roman": "times",
        "times": "times",
        "arial": "arial",
        "calibri": "calibri",
        "carlito": "calibri",
    }
    key = aliases.get(key, key)
    if key in FONTES and (fontes_dir() / FONTES[key]["file"]).is_file():
        return key
    return DEFAULT_FONTE


def _limpar(valor: Any) -> str:
    return " ".join(str(valor or "").split())


def _data_partes(raw: Any) -> Tuple[str, str, str]:
    texto = _limpar(raw)
    if not texto:
        hoje = datetime.now()
        return str(hoje.day), MESES[hoje.month - 1], str(hoje.year)
    m = re.match(r"^(\d{1,2})[/-](\d{1,2})[/-](\d{4})$", texto)
    if m:
        dia, mes, ano = int(m.group(1)), int(m.group(2)), m.group(3)
        nome_mes = MESES[mes - 1] if 1 <= mes <= 12 else m.group(2)
        return str(dia), nome_mes, ano
    return "", texto, ""


def valores_de_payload(payload: Dict[str, Any]) -> Dict[str, str]:
    """Campos das duas declarações. Data vazia vira a data de hoje."""
    data = payload or {}
    dia, mes, ano = _data_partes(data.get("data") or data.get("data_extenso"))
    if _limpar(data.get("dia")):
        dia = _limpar(data.get("dia"))
    if _limpar(data.get("mes")):
        mes = _limpar(data.get("mes"))
    if _limpar(data.get("ano")):
        ano = _limpar(data.get("ano"))
    cpf = format_cpf(only_digits(data.get("cpf"))) if only_digits(data.get("cpf")) else _limpar(data.get("cpf"))
    endereco = _limpar(data.get("endereco"))
    numero = _limpar(data.get("numero"))
    bairro = _limpar(data.get("bairro"))
    municipio = _limpar(data.get("municipio")) or "Casa Nova"
    uf = _limpar(data.get("uf") or "BA").upper()[:2]
    residente = _limpar(data.get("residente"))
    if not residente:
        pedacos = [p for p in (endereco, numero, bairro, f"{municipio}-{uf}" if municipio else "") if p]
        residente = ", ".join(pedacos)
    filiacao = _limpar(data.get("data_filiacao")) or (
        f"{dia} de {mes} de {ano}".strip(" de") if dia or mes or ano else ""
    )
    return {
        "nome": _limpar(data.get("nome")),
        "cpf": cpf,
        "rg": _limpar(data.get("rg")),
        "nacionalidade": _limpar(data.get("nacionalidade")) or "Brasileira",
        "estado_civil": _limpar(data.get("estado_civil")),
        "profissao": _limpar(data.get("profissao")) or "Pescador profissional",
        "endereco": endereco,
        "numero": numero,
        "bairro": bairro,
        "municipio": municipio,
        "uf": uf,
        "cep": _limpar(data.get("cep")),
        "telefone": _limpar(data.get("telefone")),
        "email": _limpar(data.get("email")),
        "local": _limpar(data.get("local")) or municipio or "Casa Nova",
        "residente": residente,
        "data_filiacao": filiacao,
        "dia": dia,
        "mes": mes,
        "ano": ano,
    }


def validar(valores: Dict[str, str], quais: Sequence[str]) -> Optional[str]:
    if not valores.get("nome"):
        return "Informe o nome completo."
    cpf = only_digits(valores.get("cpf"))
    if len(cpf) != 11:
        return "CPF deve ter 11 dígitos."
    if not quais:
        return "Marque a declaração de endereço, a de afiliação, ou as duas."
    return None


def _bind(page: Any, fitz: Any, fonte_id: str) -> Tuple[str, Any, float]:
    meta = FONTES[normalize_fonte(fonte_id)]
    path = fontes_dir() / meta["file"]
    if not path.is_file():
        raise ValueError(f"Fonte {meta['label']} não encontrada no programa.")
    page.insert_font(fontname="dec", fontfile=str(path))
    return "dec", fitz.Font(fontfile=str(path)), float(meta["size"])


def _baseline(page: Any, fitz: Any, x0: float, x1: float, guess: float) -> float:
    """Encosta a letra no traço de verdade, numa faixa estreita em volta do palpite."""
    if x1 - x0 < 8:
        return guess
    clip = fitz.Rect(x0, guess - 6, x1, guess + 6)
    pix = page.get_pixmap(matrix=fitz.Matrix(2, 2), clip=clip, alpha=False)
    w, h, n = pix.width, pix.height, pix.n
    if w < 4 or h < 2 or n < 3:
        return guess
    data = pix.samples
    scores = []
    step = 2
    cols = max(1, (w + step - 1) // step)
    for row in range(h):
        dark = 0
        base = row * w * n
        col = 0
        while col < w:
            i = base + col * n
            if data[i] < 110 and data[i + 1] < 110 and data[i + 2] < 110:
                dark += 1
            col += step
        scores.append(dark / cols)
    pico = max(range(h), key=scores.__getitem__)
    if scores[pico] < 0.35:
        return guess
    fundo = pico
    while fundo + 1 < h and scores[fundo + 1] >= scores[pico] * 0.55:
        fundo += 1
    return clip.y0 + (fundo + 0.5) / 2.0


def _draw(page: Any, fitz: Any, fontname: str, font: Any, text: str, box: Tuple[float, float, float], size: float) -> None:
    texto = (text or "").strip()
    if not texto:
        return
    x0, y, x1 = box
    max_w = max(8.0, x1 - x0 - 2)
    fs, escala = _encaixe(font, texto, max_w, size)
    ponto = (x0 + 1.0, y)
    if escala < 0.995:
        page.insert_text(
            ponto,
            texto,
            fontname=fontname,
            fontsize=fs,
            color=PEN_BLUE,
            morph=(fitz.Point(ponto[0], ponto[1]), fitz.Matrix(escala, 1)),
        )
        return
    page.insert_text(ponto, texto, fontname=fontname, fontsize=fs, color=PEN_BLUE)


def _preencher(page: Any, fitz: Any, fonte_id: str, campos: Dict[str, Tuple[float, float, float]], valores: Dict[str, str]) -> None:
    fontname, font, size = _bind(page, fitz, fonte_id)
    for chave, (x0, palpite, x1) in campos.items():
        y = _baseline(page, fitz, x0, x1, palpite)
        _draw(page, fitz, fontname, font, valores.get(chave) or "", (x0, y, x1), size)


def quais_de(raw: Any) -> List[str]:
    if isinstance(raw, str):
        itens = [p.strip().lower() for p in raw.split(",") if p.strip()]
    elif isinstance(raw, (list, tuple)):
        itens = [str(p).strip().lower() for p in raw if str(p).strip()]
    else:
        itens = ["endereco", "filiacao"]
    ordem = [k for k in ("endereco", "filiacao") if k in itens]
    return ordem


def gerar_pdf(
    payload: Dict[str, Any],
    *,
    fonte_id: str = DEFAULT_FONTE,
    quais: Optional[Iterable[str]] = None,
) -> Path:
    """Gera um PDF (1 ou 2 páginas) e devolve o caminho."""
    try:
        import pymupdf as fitz
    except ImportError as exc:  # pragma: no cover
        raise ValueError("Biblioteca pymupdf não instalada. Atualize o EXE.") from exc

    fonte_id = normalize_fonte(fonte_id)
    valores = valores_de_payload(payload)
    escolhidos = quais_de(list(quais) if quais is not None else payload.get("quais"))
    erro = validar(valores, escolhidos)
    if erro:
        raise ValueError(erro)

    modelos = {
        "endereco": (assets_dir() / "declaracao-endereco.pdf", CAMPOS_ENDERECO),
        "filiacao": (assets_dir() / "declaracao-filiacao.pdf", CAMPOS_FILIACAO),
    }
    saida = fitz.open()
    for chave in escolhidos:
        caminho, campos = modelos[chave]
        if not caminho.is_file():
            raise ValueError(f"Modelo da declaração não encontrado: {caminho.name}")
        doc = fitz.open(caminho)
        _preencher(doc[0], fitz, fonte_id, campos, valores)
        saida.insert_pdf(doc)
        doc.close()

    stamp = datetime.now().strftime("%Y%m%d_%H%M")
    slug = re.sub(r"[^a-zA-Z0-9]+", "-", valores["nome"])[:40].strip("-") or "pescador"
    cpf_d = only_digits(valores["cpf"]) or "semcpf"
    dest = pasta_declaracoes() / f"emitirdec-{cpf_d}-{slug}-{fonte_id}-{stamp}.pdf"
    dest.parent.mkdir(parents=True, exist_ok=True)
    for antigo in dest.parent.glob(f"emitirdec-{cpf_d}-*.pdf"):
        if antigo != dest:
            try:
                antigo.unlink()
            except OSError:
                pass
    saida.save(dest)
    saida.close()
    return dest
