"""Declaração de Residência — sempre no PDF oficial do MTE + escolha de fonte."""

from __future__ import annotations

import re
import sys
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from controle.defeso import FichaDefeso, pasta_declaracoes
from ui.formatters import display_nome, format_cpf, only_digits


def _app_root() -> Path:
    if getattr(sys, "frozen", False):
        return Path(sys._MEIPASS)  # type: ignore[attr-defined]
    return Path(__file__).resolve().parent.parent


# Opções de fonte (id -> metadados)
# padrao = Times embutido do PDF; demais = TTF em assets/defeso/fonts
FONTES: Dict[str, Dict[str, str]] = {
    "padrao": {
        "id": "padrao",
        "label": "Padrão (Times)",
        "descricao": "Times azul nos espaços do PDF oficial",
        "file": "",
        "pdf_font": "times-roman",
    },
    "allura": {
        "id": "allura",
        "label": "Allura (manuscrita)",
        "descricao": "Cursiva manuscrita pura no PDF oficial",
        "file": "Allura-Pura.ttf",
        "fallback": "Allura-Regular.ttf",
    },
    "architects": {
        "id": "architects",
        "label": "Architects Daughter",
        "descricao": "Letra de caderno no PDF oficial",
        "file": "ArchitectsDaughter-Regular.ttf",
    },
}

DEFAULT_FONTE = "padrao"

# Azul caneta esferográfica
PEN_BLUE = (0.05, 0.22, 0.68)

# Espaços do PDF oficial (x0, y_underline, x1) — sem data/município embaixo
FIELDS = {
    "nome": (86.0, 166.0, 492.0),
    "nacionalidade": (160.0, 184.85, 312.0),
    "profissao": (366.0, 184.85, 498.0),
    "cpf": (214.0, 203.81, 350.0),
    "rg": (88.0, 222.79, 258.0),
    "endereco": (86.0, 241.69, 493.0),
    "numero": (131.0, 260.47, 186.0),
    "bairro": (227.0, 260.47, 341.0),
    "municipio": (400.0, 260.47, 504.0),
    "uf": (108.0, 279.67, 166.0),
    "cep": (200.0, 279.67, 296.0),
    "telefone": (349.0, 279.67, 506.0),
    "email": (122.0, 298.66, 500.0),
}


def assets_defeso_dir() -> Path:
    return _app_root() / "assets" / "defeso"


def fonts_dir() -> Path:
    return assets_defeso_dir() / "fonts"


def modelo_pdf_path() -> Path:
    return assets_defeso_dir() / "declaracao-modelo.pdf"


def listar_fontes() -> List[Dict[str, str]]:
    out: List[Dict[str, str]] = []
    for meta in FONTES.values():
        item = {
            "id": meta["id"],
            "label": meta["label"],
            "descricao": meta.get("descricao") or "",
            "disponivel": True,
        }
        if meta["id"] != "padrao":
            item["disponivel"] = _resolve_font_file(meta["id"]) is not None
        out.append(item)
    return out


def normalize_fonte(fonte_id: str) -> str:
    key = (fonte_id or "").strip().lower()
    if key in FONTES:
        return key
    return DEFAULT_FONTE


def _resolve_font_file(fonte_id: str) -> Optional[Path]:
    meta = FONTES.get(fonte_id) or {}
    primary = meta.get("file") or ""
    fallback = meta.get("fallback") or ""
    for name in (primary, fallback):
        if not name:
            continue
        path = fonts_dir() / name
        if path.is_file() and path.stat().st_size > 1000:
            return path
    return None


def valores_da_ficha(f: FichaDefeso) -> Dict[str, str]:
    return {
        "nome": display_nome(f.nome) or f.nome,
        "nacionalidade": f.nacionalidade or "Brasileira",
        "profissao": f.profissao or "Pescador profissional",
        "cpf": format_cpf(f.cpf),
        "rg": f.rg or "",
        "endereco": f.endereco or "",
        "numero": f.numero or "",
        "bairro": f.bairro or "",
        "municipio": f.municipio or "",
        "uf": (f.uf or "").upper()[:2],
        "cep": f.cep or "",
        "telefone": f.telefone or "",
        "email": f.email or "",
    }


def _fit_size(font: Any, text: str, max_w: float, want: float) -> float:
    for size in (want, want - 1, want - 2, 14, 12, 11, 10, 9, 8):
        if size < 8:
            break
        if font.text_length(text, fontsize=size) <= max_w:
            return size
    return 8.0


def _bind_font(page: Any, fitz: Any, fonte_id: str) -> Tuple[str, Any]:
    """Retorna (fontname para insert_text, objeto Font para medir)."""
    meta = FONTES.get(fonte_id) or {}
    builtin = meta.get("pdf_font") or ""
    if builtin:
        return builtin, fitz.Font(builtin)

    font_path = _resolve_font_file(fonte_id)
    if not font_path:
        raise ValueError(f"Fonte '{fonte_id}' não encontrada nos assets.")
    page.insert_font(fontname="hand", fontfile=str(font_path))
    return "hand", fitz.Font(fontfile=str(font_path))


def preencher_pdf(
    ficha: FichaDefeso,
    *,
    fonte_id: str = "padrao",
    size: float = 16.0,
) -> Path:
    """Gera PDF do modelo oficial com texto azul na fonte escolhida (sempre overlay)."""
    try:
        import pymupdf as fitz
    except ImportError as exc:  # pragma: no cover
        raise ValueError(
            "Biblioteca pymupdf não instalada. Atualize o EXE / requirements."
        ) from exc

    fonte_id = normalize_fonte(fonte_id)

    modelo = modelo_pdf_path()
    if not modelo.is_file():
        raise ValueError(f"Modelo PDF não encontrado: {modelo}")

    valores = valores_da_ficha(ficha)
    doc = fitz.open(modelo)
    page = doc[0]
    fontname, font = _bind_font(page, fitz, fonte_id)

    for key, (x0, yu, x1) in FIELDS.items():
        text = (valores.get(key) or "").strip()
        if not text:
            continue
        max_w = max(8.0, x1 - x0 - 2)
        fs = _fit_size(font, text, max_w, size)
        tw = font.text_length(text, fontsize=fs)
        if key in ("nome", "numero", "uf"):
            x = x0 + max(0.0, (max_w - tw) / 2)
        else:
            x = x0 + 1.2
        # senta na linha do formulário
        page.insert_text(
            (x, yu - 3.4),
            text,
            fontname=fontname,
            fontsize=fs,
            color=PEN_BLUE,
        )

    stamp = datetime.now().strftime("%Y%m%d_%H%M")
    slug = re.sub(r"[^a-zA-Z0-9]+", "-", (ficha.nome or "pescador"))[:40].strip("-") or "pescador"
    cpf_d = only_digits(ficha.cpf) or "semcpf"
    dest = pasta_declaracoes() / f"declaracao-{cpf_d}-{slug}-{fonte_id}-{stamp}.pdf"
    dest.parent.mkdir(parents=True, exist_ok=True)
    doc.save(dest)
    doc.close()
    return dest
