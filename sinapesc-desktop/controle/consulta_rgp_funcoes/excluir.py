"""Exclusão de registros na Consulta RGP (módulo próprio)."""

from __future__ import annotations

from typing import Any, Dict, List, Sequence


def ids_para_excluir(raw: Any) -> List[str]:
    if raw is None:
        return []
    if isinstance(raw, str):
        text = raw.strip()
        if not text:
            return []
        if text.startswith("["):
            import json

            try:
                raw = json.loads(text)
            except json.JSONDecodeError:
                return [x.strip() for x in text.split(",") if x.strip()]
        else:
            return [x.strip() for x in text.split(",") if x.strip()]
    if isinstance(raw, dict):
        raw = raw.get("ids") or raw.get("id") or []
        if isinstance(raw, str):
            return [raw.strip()] if raw.strip() else []
    if not isinstance(raw, (list, tuple)):
        return []
    return [str(x).strip() for x in raw if str(x).strip()]


def resumo_exclusao(*, ok: int, erros: Sequence[str], nomes: Sequence[str] = ()) -> Dict[str, Any]:
    nomes = [n for n in nomes if n]
    msg = f"Excluído(s) {ok} registro(s) da Consulta RGP."
    if nomes:
        sample = ", ".join(nomes[:5])
        if len(nomes) > 5:
            sample += f" … (+{len(nomes) - 5})"
        msg += f" ({sample})"
    if erros:
        msg += f" {len(erros)} aviso(s)."
    return {
        "ok_count": int(ok),
        "erros": list(erros)[:40],
        "nomes": list(nomes)[:40],
        "mensagem": msg,
    }
