"""Sincronização de município entre planilha REAP (Pessoas) e Defeso."""

from __future__ import annotations

from typing import Any, Dict, List

from controle.defeso import FichaDefeso, payload_to_ficha
from sheets.defeso_service import DefesoService
from sheets.service import SheetsService
from ui.formatters import only_digits


def _mun_key(valor: str) -> str:
    return str(valor or "").strip()


def sync_municipios_reap_para_defeso(
    reap: SheetsService, defeso: DefesoService
) -> Dict[str, Any]:
    """
    Copia município da aba Pessoas (REAP) para a planilha Defeso (só o campo municipio).
    Cria ficha mínima se ainda não existir.
    """
    atualizados = 0
    criados = 0
    ignorados = 0
    detalhes: List[str] = []

    for p in reap.get_all_pessoas():
        mun = _mun_key(getattr(p, "municipio", ""))
        if not mun:
            ignorados += 1
            continue
        cpf = only_digits(p.cpf)
        if len(cpf) != 11:
            ignorados += 1
            continue
        ficha = defeso.por_cpf(cpf)
        if ficha and _mun_key(ficha.municipio) == mun:
            ignorados += 1
            continue
        if ficha:
            defeso.atualizar_municipio(ficha.id, mun)
            atualizados += 1
            detalhes.append(f"atualizado: {p.nome} → {mun}")
        else:
            payload = {
                "person_id": p.id,
                "nome": p.nome,
                "cpf": cpf,
                "municipio": mun,
                "status": "rascunho",
            }
            defeso.salvar(payload)
            criados += 1
            detalhes.append(f"criado: {p.nome} → {mun}")

    return {
        "atualizados": atualizados,
        "criados": criados,
        "ignorados": ignorados,
        "total_reap": len(reap.get_all_pessoas()),
        "detalhes": detalhes[:20],
    }


def sync_municipios_defeso_para_reap(
    reap: SheetsService, defeso: DefesoService
) -> Dict[str, Any]:
    """Preenche município vazio no REAP a partir da planilha Defeso."""
    atualizados = 0
    ignorados = 0
    detalhes: List[str] = []

    pessoas = {p.id: p for p in reap.get_all_pessoas()}
    for f in defeso.listar():
        mun = _mun_key(f.municipio)
        if not mun:
            ignorados += 1
            continue
        pid = (f.person_id or "").strip()
        pessoa = pessoas.get(pid) if pid else None
        if pessoa is None:
            cpf = only_digits(f.cpf)
            for p in pessoas.values():
                if only_digits(p.cpf) == cpf:
                    pessoa = p
                    pid = p.id
                    break
        if pessoa is None:
            ignorados += 1
            continue
        if _mun_key(getattr(pessoa, "municipio", "")):
            ignorados += 1
            continue
        reap.update_pessoa_municipio(pid, mun)
        atualizados += 1
        detalhes.append(f"REAP ← Defeso: {pessoa.nome} → {mun}")

    return {
        "atualizados": atualizados,
        "ignorados": ignorados,
        "detalhes": detalhes[:20],
    }


def sync_municipios_bidirecional(
    reap: SheetsService, defeso: DefesoService
) -> Dict[str, Any]:
    """REAP → Defeso (sobrescreve municipio) e Defeso → REAP (só vazios)."""
    para_defeso = sync_municipios_reap_para_defeso(reap, defeso)
    para_reap = sync_municipios_defeso_para_reap(reap, defeso)
    return {
        "reap_para_defeso": para_defeso,
        "defeso_para_reap": para_reap,
        "mensagem": (
            f"REAP→Defeso: {para_defeso['atualizados']} atualizados, "
            f"{para_defeso['criados']} criados. "
            f"Defeso→REAP: {para_reap['atualizados']} preenchidos."
        ),
    }
