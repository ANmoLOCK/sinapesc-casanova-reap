"""Correção / edição em lote na Consulta RGP (nome, CPF, tel, mun, obs)."""

from __future__ import annotations

from typing import Any, Dict, List, Sequence

from ui.formatters import format_nome, normalize_cpf


def normalizar_itens_edicao(raw: Sequence[Any]) -> List[Dict[str, str]]:
    """Aceita lista de dicts e devolve payload limpo para ``editar_lote_batch``."""
    out: List[Dict[str, str]] = []
    for item in raw or []:
        if not isinstance(item, dict):
            continue
        rid = str(item.get("id") or "").strip()
        if not rid:
            continue
        out.append(
            {
                "id": rid,
                "nome": format_nome(str(item.get("nome") or "").strip()),
                "cpf": normalize_cpf(item.get("cpf") or ""),
                "telefone": str(item.get("telefone") or item.get("numero") or "").strip(),
                "municipio": str(item.get("municipio") or "").strip(),
                "observacao": str(item.get("observacao") or item.get("obs") or "").strip(),
            }
        )
    return out
