"""Função 1 — Fila inteligente de consulta (pausa após N falhas + CSV de erros)."""

from __future__ import annotations

import csv
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Sequence

from controle.backup import backup_root
from controle.consulta_rgp_funcoes.alertas import detectar_alerta_situacao, formatar_alerta

MAX_FALHAS_SEGUIDAS_PADRAO = 3


@dataclass
class ItemErro:
    id: str
    nome: str
    cpf: str
    erro: str
    indice: int


@dataclass
class ResultadoFila:
    ok_count: int = 0
    fail_count: int = 0
    total: int = 0
    cancelado: bool = False
    pausado_por_falhas: bool = False
    falhas_seguidas: int = 0
    erros: List[str] = field(default_factory=list)
    erros_detalhe: List[ItemErro] = field(default_factory=list)
    alertas: List[Dict[str, Any]] = field(default_factory=list)
    csv_erros_path: str = ""
    mensagem: str = ""


def pasta_erros_lote() -> Path:
    dest = backup_root() / "consulta-rgp-erros"
    dest.mkdir(parents=True, exist_ok=True)
    return dest


def exportar_erros_csv(erros: Sequence[ItemErro], *, stamp: Optional[str] = None) -> str:
    if not erros:
        return ""
    stamp = stamp or datetime.now().strftime("%Y-%m-%d_%H%M")
    path = pasta_erros_lote() / f"erros-lote-{stamp}.csv"
    with path.open("w", encoding="utf-8-sig", newline="") as fh:
        w = csv.writer(fh)
        w.writerow(["indice", "id", "nome", "cpf", "erro"])
        for e in erros:
            w.writerow([e.indice, e.id, e.nome, e.cpf, e.erro])
    return str(path)


def rodar_fila_inteligente(
    alvos: Sequence[Any],
    *,
    consultar_um: Callable[[Any], Dict[str, Any]],
    cancel_check: Callable[[], bool],
    on_progress: Callable[[Dict[str, Any]], None],
    max_falhas_seguidas: int = MAX_FALHAS_SEGUIDAS_PADRAO,
    exportar_erros: bool = True,
) -> ResultadoFila:
    """Consulta um a um; pausa se houver ``max_falhas_seguidas`` erros seguidos.

    ``consultar_um(reg)`` deve retornar:
      { ok, registro?, situacao_antes?, situacao?, erro? }
    """
    total = len(alvos)
    res = ResultadoFila(total=total)
    if total == 0:
        res.mensagem = "Nenhum registro para consultar."
        return res

    max_falhas = max(1, int(max_falhas_seguidas or MAX_FALHAS_SEGUIDAS_PADRAO))
    falhas_seguidas = 0

    on_progress(
        {
            "ok": True,
            "fase": "inicio",
            "atual": 0,
            "total": total,
            "mensagem": (
                f"Fila inteligente: {total} sócio(s). "
                f"Pausa automática após {max_falhas} falhas seguidas."
            ),
            "max_falhas_seguidas": max_falhas,
        }
    )

    for i, reg in enumerate(alvos, start=1):
        if cancel_check():
            res.cancelado = True
            break

        rid = str(getattr(reg, "id", "") or "")
        nome = str(getattr(reg, "nome", "") or "")
        cpf = str(getattr(reg, "cpf", "") or "")
        on_progress(
            {
                "ok": True,
                "fase": "item",
                "atual": i,
                "total": total,
                "id": rid,
                "nome": nome,
                "cpf": cpf,
                "mensagem": f"Consultando {i} de {total}: {nome or cpf}",
            }
        )

        try:
            out = consultar_um(reg) or {}
            if not out.get("ok"):
                raise ValueError(str(out.get("erro") or out.get("error") or "falha"))
            res.ok_count += 1
            falhas_seguidas = 0
            situacao_antes = str(out.get("situacao_antes") or "")
            situacao = str(out.get("situacao") or "")
            alerta = detectar_alerta_situacao(situacao_antes, situacao)
            alerta_payload = None
            if alerta:
                msg_alerta = formatar_alerta(reg, alerta)
                alerta_payload = {
                    **alerta,
                    "id": rid,
                    "nome": nome,
                    "cpf": cpf,
                    "mensagem": msg_alerta,
                }
                res.alertas.append(alerta_payload)
            on_progress(
                {
                    "ok": True,
                    "fase": "ok",
                    "atual": i,
                    "total": total,
                    "id": rid,
                    "registro": out.get("registro"),
                    "situacao": situacao,
                    "alerta": alerta_payload,
                    "mensagem": f"OK {i}/{total}: {situacao}",
                }
            )
        except Exception as exc:  # noqa: BLE001
            res.fail_count += 1
            falhas_seguidas += 1
            err_txt = str(exc)
            res.erros.append(f"{nome or cpf or rid}: {err_txt}")
            res.erros_detalhe.append(
                ItemErro(id=rid, nome=nome, cpf=cpf, erro=err_txt, indice=i)
            )
            on_progress(
                {
                    "ok": False,
                    "fase": "erro",
                    "atual": i,
                    "total": total,
                    "id": rid,
                    "error": err_txt,
                    "falhas_seguidas": falhas_seguidas,
                    "max_falhas_seguidas": max_falhas,
                    "mensagem": f"Erro {i}/{total}: {err_txt}",
                }
            )
            if falhas_seguidas >= max_falhas:
                res.pausado_por_falhas = True
                res.falhas_seguidas = falhas_seguidas
                on_progress(
                    {
                        "ok": False,
                        "fase": "pausa",
                        "atual": i,
                        "total": total,
                        "mensagem": (
                            f"Fila pausada: {falhas_seguidas} falhas seguidas. "
                            "Corrija o MPA/rede e retome do próximo."
                        ),
                    }
                )
                break

    if exportar_erros and res.erros_detalhe:
        res.csv_erros_path = exportar_erros_csv(res.erros_detalhe)

    if res.pausado_por_falhas:
        estado = "pausada por falhas seguidas"
    elif res.cancelado:
        estado = "cancelada"
    else:
        estado = "concluída"
    res.mensagem = (
        f"Consulta em lote {estado}: {res.ok_count} ok, "
        f"{res.fail_count} erro(s) de {res.total}."
    )
    if res.csv_erros_path:
        res.mensagem += f" Erros em CSV: {Path(res.csv_erros_path).name}"
    if res.alertas:
        res.mensagem += f" · {len(res.alertas)} alerta(s) de situação."
    return res
