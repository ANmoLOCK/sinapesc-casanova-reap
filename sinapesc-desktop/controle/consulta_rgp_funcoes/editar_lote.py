"""Correção / edição em lote na Consulta RGP (nome, CPF, tel, mun, obs, senha Gov.br)."""

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
        row: Dict[str, str] = {
            "id": rid,
            "nome": format_nome(str(item.get("nome") or "").strip()),
            "cpf": normalize_cpf(item.get("cpf") or ""),
            "telefone": str(item.get("telefone") or item.get("numero") or "").strip(),
            "municipio": str(item.get("municipio") or "").strip(),
            "observacao": str(item.get("observacao") or item.get("obs") or "").strip(),
        }
        # senha individual por sócio (sempre envia a chave para gravar o valor digitado)
        if "govbr_senha" in item or "senha_govbr" in item or "senha" in item:
            row["govbr_senha"] = str(
                item.get("govbr_senha")
                if "govbr_senha" in item
                else item.get("senha_govbr")
                if "senha_govbr" in item
                else item.get("senha")
                or ""
            ).strip()
        out.append(row)
    return out
