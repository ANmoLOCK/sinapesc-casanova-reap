"""Sincronização de município/telefone entre planilha REAP (Pessoas) e Defeso."""

from __future__ import annotations

import time
from typing import Any, Dict, List

from controle.defeso import DEFESO_TAB, FichaDefeso, now_stamp, payload_to_ficha
from sheets.client import PESSOAS_TAB
from sheets.defeso_service import DefesoService
from sheets.service import SheetsService
from ui.formatters import only_digits


def _mun_key(valor: str) -> str:
    return str(valor or "").strip()


def _tel_key(valor: str) -> str:
    return str(valor or "").strip()


def _mapa_id_linha(client: Any, tab: str) -> Dict[str, int]:
    """id → número de linha 1-based (uma única leitura da coluna A)."""
    rows = client.get_values(f"{tab}!A2:A")
    out: Dict[str, int] = {}
    for i, r in enumerate(rows):
        if r and str(r[0]).strip():
            out[str(r[0]).strip()] = i + 2
    return out


def sync_municipios_reap_para_defeso(
    reap: SheetsService, defeso: DefesoService
) -> Dict[str, Any]:
    """
    Copia telefone REAP → telefoneReap na planilha Defeso.

    Município do REAP NÃO é gravado na ficha Defeso (ele só aparece na tela
    para conferência e no relatório). O município da declaração é o que o
    usuário digita no Defeso.
    """
    atualizados = 0
    criados = 0
    ignorados = 0
    detalhes: List[str] = []

    pessoas = list(reap.get_all_pessoas())
    defeso.ensure()
    fichas = defeso.listar()
    by_cpf: Dict[str, FichaDefeso] = {}
    for f in fichas:
        cpf = only_digits(f.cpf)
        if len(cpf) == 11:
            by_cpf[cpf] = f

    id_linha = _mapa_id_linha(defeso.client, DEFESO_TAB)
    batch: List[dict] = []
    novos_rows: List[List[Any]] = []
    stamp = now_stamp()

    for p in pessoas:
        tel = _tel_key(getattr(p, "telefone", ""))
        if not tel:
            ignorados += 1
            continue
        cpf = only_digits(p.cpf)
        if len(cpf) != 11:
            ignorados += 1
            continue
        ficha = by_cpf.get(cpf)
        if ficha:
            if _tel_key(ficha.telefone_reap) == tel:
                ignorados += 1
                continue
            row_idx = id_linha.get(ficha.id, -1)
            if row_idx < 0:
                ignorados += 1
                continue
            batch.append({"range": f"{DEFESO_TAB}!V{row_idx}", "values": [[tel]]})
            batch.append({"range": f"{DEFESO_TAB}!T{row_idx}", "values": [[stamp]]})
            ficha.telefone_reap = tel
            atualizados += 1
            detalhes.append(f"tel REAP→Defeso: {p.nome} → {tel}")
        else:
            nova = payload_to_ficha(
                {
                    "person_id": p.id,
                    "nome": p.nome,
                    "cpf": cpf,
                    "municipio": "",
                    "telefone_reap": tel,
                    "status": "rascunho",
                }
            )
            novos_rows.append(nova.to_row())
            by_cpf[cpf] = nova
            criados += 1
            detalhes.append(f"criado (tel): {p.nome} → {tel}")

    if batch:
        defeso.client.batch_update_values(batch, chunk_size=80)

    for i in range(0, len(novos_rows), 40):
        chunk = novos_rows[i : i + 40]
        defeso.client.append_values(f"{DEFESO_TAB}!A2", chunk)
        if i + 40 < len(novos_rows):
            time.sleep(0.4)

    return {
        "atualizados": atualizados,
        "criados": criados,
        "ignorados": ignorados,
        "total_reap": len(pessoas),
        "detalhes": detalhes[:20],
        "api_writes_batch": len(batch),
        "api_creates": len(novos_rows),
    }


def sync_municipios_defeso_para_reap(
    reap: SheetsService, defeso: DefesoService
) -> Dict[str, Any]:
    """Preenche município vazio no REAP a partir da planilha Defeso (batch)."""
    atualizados = 0
    ignorados = 0
    detalhes: List[str] = []

    pessoas_list = list(reap.get_all_pessoas())
    pessoas = {p.id: p for p in pessoas_list}
    by_cpf = {only_digits(p.cpf): p for p in pessoas_list if len(only_digits(p.cpf)) == 11}

    reap.client.ensure_tabs()
    id_linha = _mapa_id_linha(reap.client, PESSOAS_TAB)
    batch: List[dict] = []

    for f in defeso.listar():
        mun = _mun_key(f.municipio)
        if not mun:
            ignorados += 1
            continue
        pid = (f.person_id or "").strip()
        pessoa = pessoas.get(pid) if pid else None
        if pessoa is None:
            cpf = only_digits(f.cpf)
            pessoa = by_cpf.get(cpf)
            if pessoa:
                pid = pessoa.id
        if pessoa is None:
            ignorados += 1
            continue
        if _mun_key(getattr(pessoa, "municipio", "")):
            ignorados += 1
            continue
        row_idx = id_linha.get(pid, -1)
        if row_idx < 0:
            ignorados += 1
            continue
        batch.append({"range": f"{PESSOAS_TAB}!E{row_idx}", "values": [[mun]]})
        pessoa.municipio = mun  # type: ignore[attr-defined]
        atualizados += 1
        detalhes.append(f"REAP ← Defeso: {pessoa.nome} → {mun}")

    if batch:
        reap.client.batch_update_values(batch, chunk_size=80)

    return {
        "atualizados": atualizados,
        "ignorados": ignorados,
        "detalhes": detalhes[:20],
        "api_writes_batch": len(batch),
    }


def sync_telefones_reap_para_defeso(
    reap: SheetsService, defeso: DefesoService
) -> Dict[str, Any]:
    """Copia telefone REAP → telefoneReap (já coberto por sync_municipios_reap_para_defeso)."""
    return sync_municipios_reap_para_defeso(reap, defeso)


def sync_municipios_bidirecional(
    reap: SheetsService, defeso: DefesoService
) -> Dict[str, Any]:
    """Telefone REAP→Defeso; município Defeso→REAP (só se REAP estiver vazio)."""
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
            f"Telefone REAP→Defeso: {para_defeso['atualizados']} atualizados, "
            f"{para_defeso['criados']} criados. "
            f"Município Defeso→REAP (vazios): {para_reap['atualizados']} preenchidos. "
            f"(Município REAP não entra na declaração — só relatório/conferência.)"
        ),
    }
