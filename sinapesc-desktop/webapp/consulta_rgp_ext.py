"""Ponte fina: API Consulta RGP ↔ módulos em controle/consulta_rgp_funcoes.

Mantém webapp/api.py sem virar bagunça — só orquestra.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Sequence

from controle.consulta_rgp import (
    SEGUNDOS_POR_CONSULTA_EST,
    aplicar_resultado_mpa,
    normalize_situacao,
    resumo_kpis,
)
from controle.consulta_rgp_funcoes import (
    DIAS_PADRAO_VENCIDOS,
    exportar_consulta_rgp,
    ids_vencidos,
    listar_vencidos,
    rodar_fila_inteligente,
)
from controle.consulta_rgp_mpa import consultar_cpf_isolado
from ui.formatters import cpf_digitos_validos, normalize_cpf
from ui.theme import ORG_FULL, ORG_SHORT
from webapp.serialize import ok


def _parse_ids(raw: Any) -> List[str]:
    if raw is None:
        return []
    if isinstance(raw, str):
        text = raw.strip()
        if not text:
            return []
        try:
            raw = json.loads(text)
        except json.JSONDecodeError:
            return [x.strip() for x in text.split(",") if x.strip()]
    if not isinstance(raw, (list, tuple)):
        return []
    return [str(x).strip() for x in raw if str(x).strip()]


def selecionar_alvos(regs: Sequence[Any], *, ids: List[str], todos: bool) -> List[Any]:
    if todos or not ids:
        return list(regs)
    idset = set(ids)
    return [r for r in regs if r.id in idset]


def consultar_um_registro(svc: Any, reg: Any) -> Dict[str, Any]:
    """Uma consulta MPA + gravação. Usado pela fila inteligente."""
    situacao_antes = normalize_situacao(reg.situacao_rgp or "")
    alvo = normalize_cpf(reg.cpf)
    if len(alvo) != 11 or not cpf_digitos_validos(alvo):
        # ainda tenta pad/recover
        alvo = normalize_cpf(reg.cpf)
    if len(alvo) != 11:
        return {"ok": False, "erro": "CPF inválido", "situacao_antes": situacao_antes}

    result = consultar_cpf_isolado(alvo)
    if not result.get("ok"):
        return {
            "ok": False,
            "erro": str(result.get("error") or "sem resultado"),
            "situacao_antes": situacao_antes,
        }
    data = result.get("data") if isinstance(result.get("data"), dict) else {}
    if not data and isinstance(result.get("situacao"), str):
        data = {"situacao": result.get("situacao")}
    if not data:
        return {"ok": False, "erro": "API MPA sem dados", "situacao_antes": situacao_antes}

    aplicar_resultado_mpa(reg, data, ator="Sistema")
    if result.get("situacao") and (
        not reg.situacao_rgp or reg.situacao_rgp == "Não consultado"
    ):
        reg.situacao_rgp = normalize_situacao(result.get("situacao"))
    reg.cpf = alvo
    salvo = svc.salvar(reg.to_dict())
    try:
        svc.registrar_auditoria(
            "consulta_rgp_consulta",
            f"Consultou MPA (lote): {salvo.nome} → {salvo.situacao_rgp}",
            person_id=salvo.id,
            nome=salvo.nome,
        )
    except Exception:  # noqa: BLE001
        pass
    return {
        "ok": True,
        "registro": salvo.to_dict(),
        "situacao": salvo.situacao_rgp,
        "situacao_antes": situacao_antes,
    }


def executar_lote(
    *,
    svc: Any,
    regs: Sequence[Any],
    ids: List[str],
    todos: bool,
    cancel_check: Callable[[], bool],
    on_progress: Callable[[Dict[str, Any]], None],
    on_status: Optional[Callable[[str], None]] = None,
    max_falhas_seguidas: int = 3,
) -> Dict[str, Any]:
    alvos = selecionar_alvos(regs, ids=ids, todos=todos)
    if not alvos:
        raise ValueError("Nenhum registro para consultar.")

    total = len(alvos)
    est_min = max(1, int(round(total * SEGUNDOS_POR_CONSULTA_EST / 60.0)))
    on_progress(
        {
            "ok": True,
            "fase": "inicio",
            "atual": 0,
            "total": total,
            "minutos_estimados": est_min,
            "mensagem": (
                f"Iniciando fila de {total} sócio(s). Estimativa: ~{est_min} min. "
                f"Pausa após {max_falhas_seguidas} falhas seguidas."
            ),
        }
    )
    try:
        svc.registrar_auditoria(
            "consulta_rgp_lote_inicio",
            f"Iniciou consulta em lote de {total} registro(s) (~{est_min} min).",
        )
    except Exception:  # noqa: BLE001
        pass

    def _consultar(reg: Any) -> Dict[str, Any]:
        if on_status:
            on_status(f"Consultando: {getattr(reg, 'nome', '') or getattr(reg, 'cpf', '')}…")
        return consultar_um_registro(svc, reg)

    resultado = rodar_fila_inteligente(
        alvos,
        consultar_um=_consultar,
        cancel_check=cancel_check,
        on_progress=on_progress,
        max_falhas_seguidas=max_falhas_seguidas,
        exportar_erros=True,
    )

    try:
        svc.registrar_auditoria("consulta_rgp_lote_fim", resultado.mensagem)
    except Exception:  # noqa: BLE001
        pass

    regs2 = svc.listar()
    return {
        "ok_count": resultado.ok_count,
        "fail_count": resultado.fail_count,
        "total": resultado.total,
        "cancelado": resultado.cancelado,
        "pausado_por_falhas": resultado.pausado_por_falhas,
        "falhas_seguidas": resultado.falhas_seguidas,
        "erros": resultado.erros[:40],
        "alertas": resultado.alertas,
        "csv_erros_path": resultado.csv_erros_path,
        "itens": [r.to_dict() for r in regs2],
        "kpis": resumo_kpis(regs2),
        "mensagem": resultado.mensagem,
    }


def listar_vencidos_payload(svc: Any, dias: int = DIAS_PADRAO_VENCIDOS) -> Dict[str, Any]:
    regs = svc.listar()
    venc = listar_vencidos(regs, dias=dias)
    return {
        "dias": int(dias),
        "total": len(venc),
        "ids": ids_vencidos(venc, dias=dias),
        "itens": [r.to_dict() for r in venc],
        "mensagem": (
            f"{len(venc)} sócio(s) vencidos "
            f"(Não consultado ou última consulta > {int(dias)} dia(s))."
        ),
        "minutos_estimados": max(
            1, int(round(len(venc) * SEGUNDOS_POR_CONSULTA_EST / 60.0))
        )
        if venc
        else 0,
    }


def exportar_payload(
    svc: Any,
    *,
    municipio: str = "",
    situacao: str = "",
    ultima_de: str = "",
    ultima_ate: str = "",
    abrir_html: bool = True,
) -> Dict[str, Any]:
    regs = svc.listar()
    out = exportar_consulta_rgp(
        regs,
        municipio=municipio,
        situacao=situacao,
        ultima_de=ultima_de,
        ultima_ate=ultima_ate,
        org_short=ORG_SHORT,
        org_full=ORG_FULL,
        formatos=("csv", "html"),
    )
    try:
        svc.registrar_auditoria(
            "consulta_rgp_export",
            out.get("mensagem") or f"Exportou {out.get('total', 0)} registro(s).",
        )
    except Exception:  # noqa: BLE001
        pass
    if abrir_html and out.get("html_path"):
        try:
            import webbrowser

            webbrowser.open(Path(out["html_path"]).resolve().as_uri())
        except Exception:  # noqa: BLE001
            pass
    return out
