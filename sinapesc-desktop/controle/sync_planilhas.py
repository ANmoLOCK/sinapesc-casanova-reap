"""Sincronização de município/telefone entre planilha REAP (Pessoas) e Defeso."""

from __future__ import annotations

from typing import Any, Dict, List

from sheets.defeso_service import DefesoService
from sheets.service import SheetsService
from ui.formatters import only_digits


def _mun_key(valor: str) -> str:
    return str(valor or "").strip()


def _tel_key(valor: str) -> str:
    return str(valor or "").strip()


def sync_municipios_reap_para_defeso(
    reap: SheetsService, defeso: DefesoService
) -> Dict[str, Any]:
    """
    Copia município e telefone da aba Pessoas (REAP) para a planilha Defeso.
    Cria ficha mínima se ainda não existir.
    """
    atualizados = 0
    criados = 0
    ignorados = 0
    detalhes: List[str] = []

    for p in reap.get_all_pessoas():
        mun = _mun_key(getattr(p, "municipio", ""))
        tel = _tel_key(getattr(p, "telefone", ""))
        if not mun and not tel:
            ignorados += 1
            continue
        cpf = only_digits(p.cpf)
        if len(cpf) != 11:
            ignorados += 1
            continue
        ficha = defeso.por_cpf(cpf)
        same_mun = ficha and (not mun or _mun_key(ficha.municipio) == mun)
        same_tel = ficha and (not tel or _tel_key(ficha.telefone_reap) == tel)
        if ficha and same_mun and same_tel:
            ignorados += 1
            continue
        if ficha:
            if mun and _mun_key(ficha.municipio) != mun:
                defeso.atualizar_municipio(ficha.id, mun)
            if tel and _tel_key(ficha.telefone_reap) != tel:
                defeso.atualizar_telefone_reap(ficha.id, tel)
            atualizados += 1
            detalhes.append(f"atualizado: {p.nome} → mun={mun or '—'} tel={tel or '—'}")
        else:
            defeso.salvar(
                {
                    "person_id": p.id,
                    "nome": p.nome,
                    "cpf": cpf,
                    "municipio": mun,
                    "telefone_reap": tel,
                    "status": "rascunho",
                }
            )
            criados += 1
            detalhes.append(f"criado: {p.nome} → mun={mun or '—'} tel={tel or '—'}")

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


def sync_telefones_reap_para_defeso(
    reap: SheetsService, defeso: DefesoService
) -> Dict[str, Any]:
    """Copia telefone REAP → telefoneReap (já coberto por sync_municipios_reap_para_defeso)."""
    return sync_municipios_reap_para_defeso(reap, defeso)


def sync_municipios_bidirecional(
    reap: SheetsService, defeso: DefesoService
) -> Dict[str, Any]:
    """REAP → Defeso (município + telefone) e Defeso → REAP (município vazios)."""
    para_defeso = sync_municipios_reap_para_defeso(reap, defeso)
    para_reap = sync_municipios_defeso_para_reap(reap, defeso)
    return {
        "reap_para_defeso": para_defeso,
        "defeso_para_reap": para_reap,
        "telefones_reap_para_defeso": {
            "atualizados": para_defeso["atualizados"],
            "criados": para_defeso["criados"],
        },
        "mensagem": (
            f"REAP→Defeso: {para_defeso['atualizados']} atualizados, "
            f"{para_defeso['criados']} criados. "
            f"Defeso→REAP: {para_reap['atualizados']} municípios preenchidos."
        ),
    }
