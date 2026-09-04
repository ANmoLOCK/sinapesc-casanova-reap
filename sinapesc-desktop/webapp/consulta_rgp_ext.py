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


def consultar_um_registro(
    svc: Any,
    reg: Any,
    *,
    row_idx: int = 0,
    auditar: bool = True,
) -> Dict[str, Any]:
    """Uma consulta MPA + gravação.

    Com ``row_idx`` > 0 usa ``atualizar_linha`` (1 write) — anti-cota no lote.
    Sem ``row_idx`` cai no ``salvar`` completo (consulta individual).
    """
    situacao_antes = normalize_situacao(reg.situacao_rgp or "")
    alvo = normalize_cpf(reg.cpf)
    if len(alvo) != 11 or not cpf_digitos_validos(alvo):
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

    # Robô grava a situação verdadeira do MPA (não o filtro da UI)
    aplicar_resultado_mpa(reg, data, ator="Sistema")
    if result.get("situacao"):
        sit_mpa = normalize_situacao(result.get("situacao"))
        if sit_mpa and sit_mpa != "Não consultado":
            reg.situacao_rgp = sit_mpa
        elif not reg.situacao_rgp or reg.situacao_rgp == "Não consultado":
            reg.situacao_rgp = sit_mpa or reg.situacao_rgp
    reg.cpf = alvo

    if row_idx and row_idx >= 2 and hasattr(svc, "atualizar_linha"):
        salvo = svc.atualizar_linha(reg, int(row_idx))
    else:
        salvo = svc.salvar(reg.to_dict())

    if auditar:
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
                f"Pausa após {max_falhas_seguidas} falhas seguidas. "
                "Gravação leve (anti-cota Sheets)."
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

    # 1 GET de IDs → evita listar/por_id/_row_index a cada CPF (cota 60/429)
    try:
        id_to_row = svc.mapa_id_linha() if hasattr(svc, "mapa_id_linha") else {}
    except Exception:  # noqa: BLE001
        id_to_row = {}

    def _consultar(reg: Any) -> Dict[str, Any]:
        if on_status:
            on_status(f"Consultando: {getattr(reg, 'nome', '') or getattr(reg, 'cpf', '')}…")
        row = int(id_to_row.get(str(getattr(reg, "id", "") or ""), 0) or 0)
        return consultar_um_registro(svc, reg, row_idx=row, auditar=False)

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
    modo_geral: bool = False,
) -> Dict[str, Any]:
    regs = svc.listar()
    govbr = ""
    try:
        govbr = str(svc.get_govbr_senha() or "")
    except Exception:  # noqa: BLE001
        govbr = ""
    out = exportar_consulta_rgp(
        regs,
        municipio=municipio,
        situacao=situacao,
        ultima_de=ultima_de,
        ultima_ate=ultima_ate,
        org_short=ORG_SHORT,
        org_full=ORG_FULL,
        formatos=("html",) if modo_geral else ("csv", "html"),
        govbr_senha=govbr,
        modo_geral=bool(modo_geral),
    )
    try:
        acao = "consulta_rgp_relatorio_geral" if modo_geral else "consulta_rgp_export"
        svc.registrar_auditoria(
            acao,
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


def importar_lote_batch_payload(svc: Any, itens: Sequence[tuple]) -> Dict[str, Any]:
    """Grava lote com ``upsert_lote_batch`` (anti-cota) + 1 auditoria + listar."""
    if not itens:
        raise ValueError("Nenhuma linha para importar (nome + CPF).")
    result = svc.upsert_lote_batch(list(itens))
    criados = int(result.get("criados") or 0)
    atualizados = int(result.get("atualizados") or 0)
    erros = list(result.get("erros") or [])
    try:
        svc.registrar_auditoria(
            "consulta_rgp_lote",
            f"Lote Consulta RGP (batch): {criados} novos, {atualizados} atualizados"
            + (f", {len(erros)} aviso(s)" if erros else ""),
        )
    except Exception:  # noqa: BLE001
        pass
    regs = svc.listar()
    return {
        "criados": criados,
        "atualizados": atualizados,
        "erros": erros[:40],
        "total": len(regs),
        "itens": [r.to_dict() for r in regs],
        "kpis": resumo_kpis(regs),
        "mensagem": (
            f"Importados na Consulta: {criados} novos, {atualizados} atualizados"
            + (f" ({len(erros)} aviso(s))." if erros else ".")
            + " Gravação em lote (sem estourar cota do Sheets)."
        ),
    }


def importar_arquivo_payload(svc: Any, path: str) -> Dict[str, Any]:
    from controle.consulta_rgp_funcoes.importar_arquivo import parse_arquivo_lote

    parsed = parse_arquivo_lote(path)
    itens = parsed.get("itens") or []
    if not itens:
        raise ValueError(
            "Nenhum nome+CPF válido no arquivo. "
            "Use colunas Nome e CPF (TXT/CSV/XLS/PDF)."
        )
    out = importar_lote_batch_payload(svc, itens)
    out["arquivo"] = parsed.get("arquivo") or path
    out["nome_arquivo"] = parsed.get("nome_arquivo") or ""
    out["origem"] = parsed.get("origem") or ""
    out["parse_erros"] = parsed.get("erros") or []
    out["parse_total"] = int(parsed.get("total") or 0)
    avisos = out.get("erros") or []
    parse_erros = out["parse_erros"]
    if parse_erros:
        avisos = list(avisos) + [f"[arquivo] {e}" for e in parse_erros[:20]]
        out["erros"] = avisos[:40]
    out["mensagem"] = (
        f"Arquivo «{out['nome_arquivo']}»: {out['parse_total']} linha(s) lida(s). "
        + out["mensagem"]
    )
    return out


def editar_lote_payload(
    svc: Any,
    itens: Sequence[Any],
    *,
    govbr_senha: Optional[str] = None,
    atualizar_govbr: bool = False,
) -> Dict[str, Any]:
    """Aplica correções em lote (senha Gov.br individual por linha)."""
    from controle.consulta_rgp_funcoes.editar_lote import normalizar_itens_edicao

    limpos = normalizar_itens_edicao(itens)
    if not limpos:
        raise ValueError("Nenhuma linha para corrigir (selecione sócios ou carregue a lista).")

    # Compat: senha única antiga → aplica nas linhas sem senha própria
    if atualizar_govbr and govbr_senha is not None:
        comum = str(govbr_senha or "").strip()
        for row in limpos:
            if "govbr_senha" not in row:
                row["govbr_senha"] = comum

    result = svc.editar_lote_batch(limpos)
    atualizados = int(result.get("atualizados") or 0)
    erros = list(result.get("erros") or [])

    try:
        svc.registrar_auditoria(
            "consulta_rgp_editar_lote",
            f"Correção em lote: {atualizados} atualizado(s)"
            + (f", {len(erros)} aviso(s)" if erros else "")
            + (" · senhas Gov.br por sócio" if any("govbr_senha" in x for x in limpos) else ""),
        )
    except Exception:  # noqa: BLE001
        pass

    regs = svc.listar()
    return {
        "atualizados": atualizados,
        "erros": erros[:40],
        "total": len(regs),
        "itens": [r.to_dict() for r in regs],
        "kpis": resumo_kpis(regs),
        "mensagem": (
            f"Corrigidos {atualizados} registro(s) em lote"
            + (f" ({len(erros)} aviso(s))." if erros else ".")
        ),
    }


def excluir_payload(svc: Any, ids: Any) -> Dict[str, Any]:
    from controle.consulta_rgp_funcoes.excluir import ids_para_excluir, resumo_exclusao

    lista = ids_para_excluir(ids)
    if not lista:
        raise ValueError("Selecione ao menos um sócio para excluir.")
    result = svc.excluir_varios(lista)
    ok_n = int(result.get("ok") or 0)
    nomes = list(result.get("nomes") or [])
    try:
        svc.registrar_auditoria(
            "consulta_rgp_excluir",
            f"Excluiu {ok_n} registro(s) da Consulta RGP"
            + (f": {', '.join(nomes[:8])}" if nomes else ""),
        )
    except Exception:  # noqa: BLE001
        pass
    regs = svc.listar()
    out = resumo_exclusao(ok=ok_n, erros=[], nomes=nomes)
    out["ids"] = list(result.get("ids") or lista)
    out["itens"] = [r.to_dict() for r in regs]
    out["kpis"] = resumo_kpis(regs)
    out["total"] = len(regs)
    try:
        out["govbr_senha"] = str(svc.get_govbr_senha() or "")
    except Exception:  # noqa: BLE001
        out["govbr_senha"] = ""
    return out
