"""Agrupamento de linhas de relatório por município (REAP / Defeso / Consulta RGP)."""

from __future__ import annotations

import html
from typing import Any, Callable, Iterable, List, Sequence, Tuple, TypeVar

T = TypeVar("T")

SEM_MUNICIPIO = "SEM MUNICÍPIO"


def municipio_rotulo(valor: Any) -> str:
    text = str(valor or "").strip()
    return text.upper() if text else SEM_MUNICIPIO


def agrupar_por_municipio(
    itens: Sequence[T],
    get_municipio: Callable[[T], Any],
    *,
    sort_nome: Callable[[T], str] | None = None,
) -> List[Tuple[str, List[T]]]:
    """Ordena por município e nome; devolve [(rótulo_município, [itens]), ...]."""
    keyed: List[Tuple[str, str, T]] = []
    for item in itens:
        mun = municipio_rotulo(get_municipio(item))
        nome = ""
        if sort_nome is not None:
            nome = str(sort_nome(item) or "").strip().lower()
        keyed.append((mun, nome, item))
    keyed.sort(key=lambda t: (t[0] == SEM_MUNICIPIO, t[0], t[1]))

    grupos: List[Tuple[str, List[T]]] = []
    atual_mun = ""
    bucket: List[T] = []
    for mun, _nome, item in keyed:
        if mun != atual_mun:
            if bucket:
                grupos.append((atual_mun, bucket))
            atual_mun = mun
            bucket = [item]
        else:
            bucket.append(item)
    if bucket:
        grupos.append((atual_mun, bucket))
    return grupos


def html_cabecalho_municipio(rotulo: str, *, colspan: int) -> str:
    """Linha de seção: MUNICIPIO - NOME."""
    label = html.escape(f"MUNICÍPIO — {rotulo}")
    span = max(1, int(colspan))
    return (
        f'<tr class="mun-group"><td colspan="{span}">'
        f"<strong>{label}</strong></td></tr>"
    )


def css_grupo_municipio() -> str:
    return """
    tr.mun-group td {
      background: #0A2F52;
      color: #EAF6FC;
      font-size: 13px;
      letter-spacing: 0.04em;
      padding: 10px 8px;
      border: 1px solid #0A2F52;
    }
    @media print {
      tr.mun-group td {
        -webkit-print-color-adjust: exact;
        print-color-adjust: exact;
      }
    }
    """
