"""Função 4 — Reconsultar vencidos (Não consultado ou última consulta antiga)."""

from __future__ import annotations

from datetime import datetime, timedelta
from typing import Any, Iterable, List, Optional, Sequence

from controle.auditoria import parse_em
from controle.consulta_rgp import SITUACAO_NAO_CONSULTADO, normalize_situacao

DIAS_PADRAO_VENCIDOS = 30


def _parse_ultima(valor: str) -> Optional[datetime]:
    return parse_em(valor)


def registro_esta_vencido(
    reg: Any,
    *,
    dias: int = DIAS_PADRAO_VENCIDOS,
    agora: Optional[datetime] = None,
) -> bool:
    """True se situação é «Não consultado» ou última consulta tem mais de ``dias``."""
    agora = agora or datetime.now()
    dias = max(1, int(dias or DIAS_PADRAO_VENCIDOS))
    sit = normalize_situacao(getattr(reg, "situacao_rgp", "") or "")
    if sit == SITUACAO_NAO_CONSULTADO or not sit:
        return True
    ultima = _parse_ultima(str(getattr(reg, "ultima_consulta_em", "") or ""))
    if ultima is None:
        return True
    return ultima < (agora - timedelta(days=dias))


def listar_vencidos(
    registros: Sequence[Any],
    *,
    dias: int = DIAS_PADRAO_VENCIDOS,
    agora: Optional[datetime] = None,
) -> List[Any]:
    return [r for r in registros if registro_esta_vencido(r, dias=dias, agora=agora)]


def ids_vencidos(
    registros: Iterable[Any],
    *,
    dias: int = DIAS_PADRAO_VENCIDOS,
    agora: Optional[datetime] = None,
) -> List[str]:
    out: List[str] = []
    for r in registros:
        if registro_esta_vencido(r, dias=dias, agora=agora):
            rid = str(getattr(r, "id", "") or "").strip()
            if rid:
                out.append(rid)
    return out
