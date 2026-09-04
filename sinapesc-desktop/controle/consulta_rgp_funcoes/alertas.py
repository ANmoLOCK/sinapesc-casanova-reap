"""Função 2 — Alerta quando situação piora (ex.: Ativo → Suspenso/Cancelado)."""

from __future__ import annotations

from typing import Any, Dict, Optional

from controle.consulta_rgp import (
    SITUACAO_ATIVO,
    SITUACAO_CANCELADO,
    SITUACAO_INATIVO,
    SITUACAO_SUSPENSO,
    normalize_situacao,
)

SITUACOES_ALERTA_NEGATIVA = frozenset(
    {
        SITUACAO_SUSPENSO,
        SITUACAO_CANCELADO,
        SITUACAO_INATIVO,
    }
)


def detectar_alerta_situacao(
    situacao_antes: str,
    situacao_depois: str,
) -> Optional[Dict[str, str]]:
    """Retorna dict de alerta se saiu de Ativo para situação negativa; senão None."""
    antes = normalize_situacao(situacao_antes)
    depois = normalize_situacao(situacao_depois)
    if antes != SITUACAO_ATIVO:
        return None
    if depois not in SITUACOES_ALERTA_NEGATIVA:
        return None
    if antes == depois:
        return None
    return {
        "tipo": "situacao_piorou",
        "de": antes,
        "para": depois,
        "severidade": "alta",
    }


def formatar_alerta(reg: Any, alerta: Dict[str, str]) -> str:
    nome = str(getattr(reg, "nome", "") or getattr(reg, "nome_display", "") or "").strip()
    cpf = str(getattr(reg, "cpf", "") or "").strip()
    de = alerta.get("de") or "?"
    para = alerta.get("para") or "?"
    quem = nome or cpf or "Sócio"
    return f"⚠ {quem}: {de} → {para}"
