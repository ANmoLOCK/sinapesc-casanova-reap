"""Monta um único PDF: declaração + anexos Defeso escolhidos."""

from __future__ import annotations

import re
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence

from controle.defeso import FichaDefeso, pasta_declaracoes
from controle.defeso_anexos import pasta_anexos_root
from controle.defeso_declaracao import normalize_fonte, preencher_pdf
from drive.client import ANEXO_NOMES
from ui.formatters import only_digits

# Itens do pacote (UI checkboxes)
PACOTE_ITENS = (
    {"id": "declaracao", "label": "Declaração de residência"},
    {"id": "identidade", "label": "Identidade"},
    {"id": "pesca", "label": "Carteira de pescador"},
    {"id": "caf", "label": "CAF"},
)

_IMG_EXT = {".jpg", ".jpeg", ".png", ".webp", ".bmp", ".tif", ".tiff"}


def listar_opcoes_pacote() -> List[Dict[str, str]]:
    return [dict(x) for x in PACOTE_ITENS]


def normalize_selecao(itens: Optional[Sequence[str]]) -> List[str]:
    allowed = {x["id"] for x in PACOTE_ITENS}
    if not itens:
        return ["declaracao", "identidade", "pesca", "caf"]
    out: List[str] = []
    seen = set()
    for raw in itens:
        key = str(raw or "").strip().lower()
        if key == "carteira_pesca":
            key = "pesca"
        if key in allowed and key not in seen:
            seen.add(key)
            out.append(key)
    return out or ["declaracao"]


def achar_anexo_arquivo(cpf: str, kind: str, cfg: Optional[dict] = None) -> Optional[Path]:
    """Localiza identidade / carteira-pesca / caf na pasta do CPF."""
    if cfg is None:
        from config import load_config

        cfg = load_config()
    stem = ANEXO_NOMES.get((kind or "").strip().lower())
    if not stem:
        return None
    digits = only_digits(cpf)
    if len(digits) != 11:
        return None
    folder = pasta_anexos_root(cfg) / digits
    if not folder.is_dir():
        return None
    found: List[Path] = []
    for path in folder.iterdir():
        if not path.is_file():
            continue
        name = path.name.lower()
        if name.startswith(stem.lower() + ".") or name == stem.lower():
            found.append(path)
    if not found:
        return None

    def rank(p: Path) -> tuple:
        ext = p.suffix.lower()
        # PDF primeiro; depois imagens
        pref = 0 if ext == ".pdf" else (1 if ext in _IMG_EXT else 9)
        return (pref, -p.stat().st_mtime)

    found.sort(key=rank)
    return found[0]


def _append_pdf(dest: Any, src: Path) -> int:
    import pymupdf as fitz

    src_doc = fitz.open(src)
    try:
        dest.insert_pdf(src_doc)
        return src_doc.page_count
    finally:
        src_doc.close()


def _append_image(dest: Any, src: Path) -> int:
    import pymupdf as fitz

    # Página A4 com a imagem cabendo
    page = dest.new_page(width=595, height=842)
    rect = page.rect
    margin = 24
    box = fitz.Rect(margin, margin, rect.width - margin, rect.height - margin)
    page.insert_image(box, filename=str(src), keep_proportion=True)
    return 1


def _append_arquivo(dest: Any, src: Path) -> int:
    ext = src.suffix.lower()
    if ext == ".pdf":
        return _append_pdf(dest, src)
    if ext in _IMG_EXT:
        return _append_image(dest, src)
    raise ValueError(f"Formato não suportado no pacote: {src.name}")


def montar_pacote_pdf(
    ficha: FichaDefeso,
    *,
    itens: Optional[Sequence[str]] = None,
    fonte_id: str = "",
    cfg: Optional[dict] = None,
) -> Dict[str, Any]:
    """
    Gera um PDF único com os itens marcados.
    Retorna path, páginas, incluídos e avisos (faltantes).
    """
    try:
        import pymupdf as fitz
    except ImportError as exc:  # pragma: no cover
        raise ValueError("Biblioteca pymupdf não instalada.") from exc

    if cfg is None:
        from config import load_config

        cfg = load_config()

    selecao = normalize_selecao(itens)
    fonte = normalize_fonte(
        fonte_id or str(cfg.get("defeso_declaracao_fonte") or "")
    )

    incluidos: List[Dict[str, Any]] = []
    faltando: List[str] = []
    merged = fitz.open()

    try:
        for item in selecao:
            if item == "declaracao":
                decl = preencher_pdf(ficha, fonte_id=fonte)
                pages = _append_pdf(merged, decl)
                incluidos.append(
                    {"id": "declaracao", "label": "Declaração", "path": str(decl), "pages": pages}
                )
                continue

            path = achar_anexo_arquivo(ficha.cpf, item, cfg)
            label = next((x["label"] for x in PACOTE_ITENS if x["id"] == item), item)
            if path is None:
                faltando.append(label)
                continue
            try:
                pages = _append_arquivo(merged, path)
            except Exception as exc:  # noqa: BLE001
                faltando.append(f"{label} ({exc})")
                continue
            incluidos.append(
                {"id": item, "label": label, "path": str(path), "pages": pages}
            )

        if not incluidos:
            raise ValueError(
                "Nenhum documento disponível para juntar. "
                "Gere a declaração e anexe identidade / carteira / CAF."
            )

        stamp = datetime.now().strftime("%Y%m%d_%H%M")
        slug = re.sub(r"[^a-zA-Z0-9]+", "-", (ficha.nome or "pescador"))[:40].strip("-") or "pescador"
        cpf_d = only_digits(ficha.cpf) or "semcpf"
        dest = pasta_declaracoes() / f"pacote-{cpf_d}-{slug}-{stamp}.pdf"
        dest.parent.mkdir(parents=True, exist_ok=True)
        merged.save(dest)
    finally:
        merged.close()

    aviso = ""
    if faltando:
        aviso = "Não encontrados: " + ", ".join(faltando)

    return {
        "path": str(dest),
        "pages": sum(int(x.get("pages") or 0) for x in incluidos),
        "incluidos": incluidos,
        "faltando": faltando,
        "aviso": aviso,
        "fonte": fonte,
        "itens": selecao,
    }
