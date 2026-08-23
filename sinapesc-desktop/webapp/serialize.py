"""Conversão de modelos para JSON (API web)."""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from sheets.models import MESES, PessoaComReap
from ui.formatters import display_nome, format_cpf, format_cpf_masked, format_nome, only_digits


def pessoa_to_dict(
    p: PessoaComReap,
    *,
    mask_cpf: bool = False,
    ultimo_toggle: Optional[Dict[str, str]] = None,
) -> Dict[str, Any]:
    cpf_fmt = format_cpf_masked(p.cpf) if mask_cpf else format_cpf(p.cpf)
    out = {
        "id": p.id,
        "nome": format_nome(p.nome),
        "nome_display": display_nome(p.nome),
        "cpf": cpf_fmt,
        "cpf_raw": only_digits(p.cpf),
        "iniciais": _iniciais(p.nome),
        "criado_em": p.criado_em or "",
        "municipio": getattr(p, "municipio", "") or "",
        "anos": [
            {
                "ano": a.ano,
                "meses": {m: bool(a.meses.get(m)) for m in MESES},
            }
            for a in sorted(p.anos, key=lambda x: x.ano, reverse=True)
        ],
    }
    if ultimo_toggle:
        out["ultimo_toggle_em"] = ultimo_toggle.get("em") or ""
        out["ultimo_toggle_label"] = ultimo_toggle.get("label") or ""
    else:
        out["ultimo_toggle_em"] = ""
        out["ultimo_toggle_label"] = ""
    return out


def _iniciais(nome: str) -> str:
    parts = [p for p in (nome or "").strip().split() if p]
    if not parts:
        return "?"
    if len(parts) == 1:
        return parts[0][:2].upper()
    return (parts[0][0] + parts[-1][0]).upper()


def ok(data: Any = None, **extra) -> Dict[str, Any]:
    out: Dict[str, Any] = {"ok": True}
    if data is not None:
        out["data"] = data
    out.update(extra)
    return out


def err(msg: str, **extra) -> Dict[str, Any]:
    return {"ok": False, "error": msg, **extra}
