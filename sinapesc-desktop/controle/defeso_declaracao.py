"""Declaração de Residência — PDF oficial MTE com letra de mão (azul)."""

from __future__ import annotations

import hashlib
import random
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


# Fontes manuscritas (id -> metadados). Padrão = Times limpo; demais = letra de mão.
FONTES: Dict[str, Dict[str, Any]] = {
    "allura": {
        "id": "allura",
        "label": "Manuscrita (Allura)",
        "descricao": "Cursiva de caneta — igual aos previews",
        "file": "Allura-Pura.ttf",
        "fallback": "Allura-Regular.ttf",
        "hand": True,
        "size_nome": 22.0,
        "size": 18.0,
    },
    "bairro": {
        "id": "bairro",
        "label": "Letra de bairro",
        "descricao": "Manuscrita informal (caneta)",
        "file": "SinapescLetraBairro.ttf",
        "hand": True,
        "size_nome": 20.0,
        "size": 18.0,
    },
    "mao": {
        "id": "mao",
        "label": "Mão suja",
        "descricao": "Letra irregular, mais “feita à mão”",
        "file": "SinapescMaoSuja.ttf",
        "hand": True,
        "size_nome": 18.0,
        "size": 17.0,
    },
    "architects": {
        "id": "architects",
        "label": "Caderno (Architects)",
        "descricao": "Letra de caderno / bloco",
        "file": "ArchitectsDaughter-Regular.ttf",
        "hand": True,
        "size_nome": 17.0,
        "size": 16.0,
    },
    "padrao": {
        "id": "padrao",
        "label": "Padrão (Times)",
        "descricao": "Times limpo no PDF (sem efeito de mão)",
        "file": "",
        "pdf_font": "times-roman",
        "hand": False,
        "size_nome": 16.0,
        "size": 16.0,
    },
}

DEFAULT_FONTE = "allura"

# Azul caneta (~#0d38ad) — igual aos PDFs de preview do chat
PEN_BLUE = (0.051, 0.220, 0.678)

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
            "descricao": str(meta.get("descricao") or ""),
            "disponivel": True,
        }
        if not meta.get("pdf_font"):
            item["disponivel"] = _resolve_font_file(meta["id"]) is not None
        out.append(item)
    return out


def normalize_fonte(fonte_id: str) -> str:
    key = (fonte_id or "").strip().lower()
    if key in FONTES:
        return key
    # aliases antigos
    aliases = {"manuscrita": "allura", "pura": "allura", "caderno": "architects"}
    if key in aliases:
        return aliases[key]
    return DEFAULT_FONTE


def _resolve_font_file(fonte_id: str) -> Optional[Path]:
    meta = FONTES.get(fonte_id) or {}
    primary = str(meta.get("file") or "")
    fallback = str(meta.get("fallback") or "")
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
    for size in (want, want - 1, want - 2, want - 3, 14, 12, 11, 10, 9, 8):
        if size < 8:
            break
        if font.text_length(text, fontsize=size) <= max_w:
            return float(size)
    return 8.0


def _bind_font(page: Any, fitz: Any, fonte_id: str) -> Tuple[str, Any]:
    """Retorna (fontname para insert_text, objeto Font para medir)."""
    meta = FONTES.get(fonte_id) or {}
    builtin = str(meta.get("pdf_font") or "")
    if builtin:
        return builtin, fitz.Font(builtin)

    font_path = _resolve_font_file(fonte_id)
    if not font_path:
        raise ValueError(f"Fonte '{fonte_id}' não encontrada nos assets.")
    page.insert_font(fontname="hand", fontfile=str(font_path))
    return "hand", fitz.Font(fontfile=str(font_path))


def _rng_for(fonte_id: str, field: str, text: str) -> random.Random:
    """Semente estável: mesma ficha + fonte = mesma “mão”."""
    raw = f"{fonte_id}|{field}|{text}".encode("utf-8")
    seed = int(hashlib.sha256(raw).hexdigest()[:16], 16)
    return random.Random(seed)


def _draw_plain(
    page: Any,
    *,
    fontname: str,
    font: Any,
    text: str,
    x0: float,
    yu: float,
    x1: float,
    size: float,
    center: bool,
) -> None:
    max_w = max(8.0, x1 - x0 - 2)
    fs = _fit_size(font, text, max_w, size)
    tw = font.text_length(text, fontsize=fs)
    x = x0 + max(0.0, (max_w - tw) / 2) if center else x0 + 1.2
    page.insert_text((x, yu - 3.4), text, fontname=fontname, fontsize=fs, color=PEN_BLUE)


def _draw_hand(
    page: Any,
    *,
    fontname: str,
    font: Any,
    text: str,
    field: str,
    fonte_id: str,
    x0: float,
    yu: float,
    x1: float,
    size: float,
    center: bool,
) -> None:
    """Desenha letra a letra com jitter de tamanho/Y — efeito caneta no formulário."""
    max_w = max(8.0, x1 - x0 - 2)
    base = _fit_size(font, text, max_w * 0.98, size)
    rng = _rng_for(fonte_id, field, text)

    # Mede largura total com jitter médio para decidir start X
    widths: List[float] = []
    sizes: List[float] = []
    for ch in text:
        fs = base * rng.uniform(0.93, 1.08)
        fs = max(11.0, min(fs, base + 2.8))
        sizes.append(fs)
        # espaço um pouco irregular
        if ch == " ":
            widths.append(font.text_length(" ", fontsize=base) * rng.uniform(0.8, 1.25))
        else:
            widths.append(font.text_length(ch, fontsize=fs) * rng.uniform(0.96, 1.04))

    total = sum(widths)
    # Se estourou, reduz proporcionalmente
    if total > max_w and total > 0:
        scale = max_w / total
        widths = [w * scale for w in widths]
        sizes = [max(10.0, s * scale) for s in sizes]
        total = sum(widths)

    x = x0 + max(0.0, (max_w - total) / 2) if center else x0 + 1.0
    # reinicia rng na mesma semente para Y/jitter alinhado às medidas
    rng = _rng_for(fonte_id, field, text)
    for i, ch in enumerate(text):
        fs = sizes[i]
        # vertical: senta na linha com leve “tremor” de mão
        y = yu - 3.2 + rng.uniform(-1.35, 1.05)
        if ch != " ":
            page.insert_text(
                (x, y),
                ch,
                fontname=fontname,
                fontsize=fs,
                color=PEN_BLUE,
            )
        x += widths[i]


def preencher_pdf(
    ficha: FichaDefeso,
    *,
    fonte_id: str = "allura",
    size: float = 0.0,
) -> Path:
    """Gera PDF do modelo oficial com texto azul (letra de mão quando aplicável)."""
    try:
        import pymupdf as fitz
    except ImportError as exc:  # pragma: no cover
        raise ValueError(
            "Biblioteca pymupdf não instalada. Atualize o EXE / requirements."
        ) from exc

    fonte_id = normalize_fonte(fonte_id)
    meta = FONTES[fonte_id]

    modelo = modelo_pdf_path()
    if not modelo.is_file():
        raise ValueError(f"Modelo PDF não encontrado: {modelo}")

    valores = valores_da_ficha(ficha)
    doc = fitz.open(modelo)
    page = doc[0]
    fontname, font = _bind_font(page, fitz, fonte_id)
    hand = bool(meta.get("hand"))
    size_nome = float(size or meta.get("size_nome") or 18)
    size_campo = float(size or meta.get("size") or 16)

    for key, (x0, yu, x1) in FIELDS.items():
        text = (valores.get(key) or "").strip()
        if not text:
            continue
        want = size_nome if key == "nome" else size_campo
        center = key in ("nome", "numero", "uf")
        if hand:
            _draw_hand(
                page,
                fontname=fontname,
                font=font,
                text=text,
                field=key,
                fonte_id=fonte_id,
                x0=x0,
                yu=yu,
                x1=x1,
                size=want,
                center=center,
            )
        else:
            _draw_plain(
                page,
                fontname=fontname,
                font=font,
                text=text,
                x0=x0,
                yu=yu,
                x1=x1,
                size=want,
                center=center,
            )

    stamp = datetime.now().strftime("%Y%m%d_%H%M")
    slug = re.sub(r"[^a-zA-Z0-9]+", "-", (ficha.nome or "pescador"))[:40].strip("-") or "pescador"
    cpf_d = only_digits(ficha.cpf) or "semcpf"
    dest = pasta_declaracoes() / f"declaracao-{cpf_d}-{slug}-{fonte_id}-{stamp}.pdf"
    dest.parent.mkdir(parents=True, exist_ok=True)
    doc.save(dest)
    doc.close()
    return dest
