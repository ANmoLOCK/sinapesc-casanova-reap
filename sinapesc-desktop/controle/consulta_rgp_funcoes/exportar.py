"""Função 3 — Exportar Consulta RGP (CSV + HTML para imprimir/PDF)."""

from __future__ import annotations

import csv
import html
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence

from controle.auditoria import parse_em
from controle.backup import backup_root
from controle.consulta_rgp import normalize_situacao
from controle.relatorio import logo_data_uri
from ui.formatters import format_cpf, format_nome


def pasta_export_consulta() -> Path:
    dest = backup_root() / "consulta-rgp-export"
    dest.mkdir(parents=True, exist_ok=True)
    return dest


def filtrar_registros_export(
    registros: Sequence[Any],
    *,
    municipio: str = "",
    situacao: str = "",
    ultima_de: str = "",
    ultima_ate: str = "",
) -> List[Any]:
    mun_q = (municipio or "").strip().lower()
    sit_q = normalize_situacao(situacao) if (situacao or "").strip() else ""
    dt_de = parse_em(ultima_de) if (ultima_de or "").strip() else None
    dt_ate = parse_em(ultima_ate) if (ultima_ate or "").strip() else None
    # Se só data (sem hora), parse_em pode falhar — aceita YYYY-MM-DD
    if (ultima_de or "").strip() and dt_de is None:
        try:
            dt_de = datetime.strptime((ultima_de or "").strip()[:10], "%Y-%m-%d")
        except ValueError:
            dt_de = None
    if (ultima_ate or "").strip() and dt_ate is None:
        try:
            dt_ate = datetime.strptime((ultima_ate or "").strip()[:10], "%Y-%m-%d")
            dt_ate = dt_ate.replace(hour=23, minute=59, second=59)
        except ValueError:
            dt_ate = None

    out: List[Any] = []
    for r in registros:
        if mun_q:
            mun = str(getattr(r, "municipio", "") or "").strip().lower()
            if mun_q not in mun:
                continue
        if sit_q:
            if normalize_situacao(getattr(r, "situacao_rgp", "") or "") != sit_q:
                continue
        ultima = parse_em(str(getattr(r, "ultima_consulta_em", "") or ""))
        if dt_de and (ultima is None or ultima < dt_de):
            continue
        if dt_ate and (ultima is None or ultima > dt_ate):
            continue
        out.append(r)
    return out


def _rows_csv(regs: Sequence[Any]) -> List[List[str]]:
    header = [
        "nome",
        "cpf",
        "telefone",
        "municipio",
        "uf",
        "situacaoRgp",
        "ultimaConsultaEm",
        "observacao",
        "codigoRgp",
        "categoria",
        "email",
    ]
    rows: List[List[str]] = [header]
    for r in regs:
        rows.append(
            [
                format_nome(str(getattr(r, "nome", "") or "")),
                format_cpf(str(getattr(r, "cpf", "") or "")),
                str(getattr(r, "telefone", "") or ""),
                str(getattr(r, "municipio", "") or ""),
                str(getattr(r, "uf", "") or ""),
                normalize_situacao(getattr(r, "situacao_rgp", "") or ""),
                str(getattr(r, "ultima_consulta_em", "") or ""),
                str(getattr(r, "observacao", "") or ""),
                str(getattr(r, "codigo_rgp", "") or ""),
                str(getattr(r, "categoria", "") or ""),
                str(getattr(r, "email", "") or ""),
            ]
        )
    return rows


def _html_export(
    regs: Sequence[Any],
    *,
    org_short: str,
    org_full: str,
    filtros: Dict[str, str],
) -> str:
    logo = logo_data_uri()
    logo_tag = f'<img class="logo" src="{logo}" alt="">' if logo else ""
    filtro_bits = []
    for k, label in (
        ("municipio", "Município"),
        ("situacao", "Situação"),
        ("ultima_de", "Última consulta de"),
        ("ultima_ate", "até"),
    ):
        v = (filtros.get(k) or "").strip()
        if v:
            filtro_bits.append(f"{label}: {html.escape(v)}")
    filtro_txt = " · ".join(filtro_bits) if filtro_bits else "Sem filtros (lista completa)"
    trs = []
    for r in regs:
        trs.append(
            "<tr>"
            f"<td>{html.escape(format_nome(str(getattr(r, 'nome', '') or '')))}</td>"
            f"<td>{html.escape(format_cpf(str(getattr(r, 'cpf', '') or '')))}</td>"
            f"<td>{html.escape(str(getattr(r, 'telefone', '') or ''))}</td>"
            f"<td>{html.escape(str(getattr(r, 'municipio', '') or ''))}</td>"
            f"<td>{html.escape(normalize_situacao(getattr(r, 'situacao_rgp', '') or ''))}</td>"
            f"<td>{html.escape(str(getattr(r, 'ultima_consulta_em', '') or ''))}</td>"
            f"<td>{html.escape(str(getattr(r, 'observacao', '') or ''))}</td>"
            "</tr>"
        )
    body = "\n".join(trs) if trs else '<tr><td colspan="7">Nenhum registro.</td></tr>'
    gerado = datetime.now().strftime("%d/%m/%Y %H:%M")
    return f"""<!DOCTYPE html>
<html lang="pt-BR"><head><meta charset="utf-8">
<title>Consulta RGP — exportação</title>
<style>
  body {{ font-family: Segoe UI, system-ui, sans-serif; color: #0A2F52; margin: 24px; }}
  .head {{ display:flex; gap:16px; align-items:center; margin-bottom: 12px; }}
  .logo {{ height: 56px; }}
  h1 {{ margin: 0; font-size: 20px; }}
  .sub {{ color:#5A7388; font-size: 12px; margin: 4px 0 16px; }}
  table {{ width:100%; border-collapse: collapse; font-size: 12px; }}
  th, td {{ border: 1px solid #D5E4EE; padding: 6px 8px; text-align: left; }}
  th {{ background: #E7F1F7; }}
  @media print {{ body {{ margin: 12px; }} }}
</style></head><body>
<div class="head">{logo_tag}<div>
  <h1>{html.escape(org_short)} — Consulta RGP</h1>
  <div class="sub">{html.escape(org_full)}</div>
</div></div>
<p class="sub">{html.escape(filtro_txt)} · {len(regs)} registro(s) · gerado em {gerado}</p>
<table>
<thead><tr>
  <th>Nome</th><th>CPF</th><th>Telefone</th><th>Município</th>
  <th>Situação</th><th>Última consulta</th><th>Observação</th>
</tr></thead>
<tbody>
{body}
</tbody>
</table>
<script>window.addEventListener("load", () => setTimeout(() => window.print(), 400));</script>
</body></html>"""


def exportar_consulta_rgp(
    registros: Sequence[Any],
    *,
    municipio: str = "",
    situacao: str = "",
    ultima_de: str = "",
    ultima_ate: str = "",
    org_short: str = "Sinapesc",
    org_full: str = "",
    formatos: Optional[Sequence[str]] = None,
) -> Dict[str, Any]:
    """Gera CSV e/ou HTML. Retorna paths e contagem."""
    formatos = [str(f).lower() for f in (formatos or ("csv", "html"))]
    filtrados = filtrar_registros_export(
        registros,
        municipio=municipio,
        situacao=situacao,
        ultima_de=ultima_de,
        ultima_ate=ultima_ate,
    )
    stamp = datetime.now().strftime("%Y-%m-%d_%H%M")
    pasta = pasta_export_consulta()
    out: Dict[str, Any] = {
        "total": len(filtrados),
        "csv_path": "",
        "html_path": "",
        "filtros": {
            "municipio": municipio or "",
            "situacao": situacao or "",
            "ultima_de": ultima_de or "",
            "ultima_ate": ultima_ate or "",
        },
    }
    if "csv" in formatos:
        csv_path = pasta / f"consulta-rgp-{stamp}.csv"
        with csv_path.open("w", encoding="utf-8-sig", newline="") as fh:
            writer = csv.writer(fh)
            for row in _rows_csv(filtrados):
                writer.writerow(row)
        out["csv_path"] = str(csv_path)
    if "html" in formatos:
        html_path = pasta / f"consulta-rgp-{stamp}.html"
        html_path.write_text(
            _html_export(
                filtrados,
                org_short=org_short,
                org_full=org_full,
                filtros=out["filtros"],
            ),
            encoding="utf-8",
        )
        out["html_path"] = str(html_path)
    out["mensagem"] = (
        f"Exportados {len(filtrados)} registro(s)"
        + (f" · CSV: {Path(out['csv_path']).name}" if out["csv_path"] else "")
        + (f" · HTML: {Path(out['html_path']).name}" if out["html_path"] else "")
    )
    return out
