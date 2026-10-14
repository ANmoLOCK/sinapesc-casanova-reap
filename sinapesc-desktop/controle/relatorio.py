"""HTML de conformidade REAP (imprimir / salvar PDF pelo navegador). Sem R$."""

from __future__ import annotations

import base64
import html
from datetime import datetime
from pathlib import Path
from typing import Iterable, List, Sequence

from controle.relatorio_municipio import (
    agrupar_por_municipio,
    css_grupo_municipio,
    html_cabecalho_municipio,
    municipio_rotulo,
)
from sheets.models import MESES
from ui.brand import asset_path
from ui.formatters import format_cpf, format_nome

from .calendario import meses_para_texto
from .pendencias import SituacaoReap, meses_marcados


def logo_data_uri() -> str:
    for name in ("logo.png", "icon.png"):
        path = asset_path(name)
        if path.exists():
            raw = path.read_bytes()
            return "data:image/png;base64," + base64.b64encode(raw).decode("ascii")
    return ""


def pasta_relatorios() -> Path:
    from .backup import backup_root

    dest = backup_root() / "relatorios"
    dest.mkdir(parents=True, exist_ok=True)
    return dest


def _grid(meses: dict) -> str:
    cells = []
    for m in MESES:
        on = bool(meses.get(m))
        cls = "on" if on else "off"
        mark = "✓" if on else "·"
        cells.append(f'<div class="m {cls}">{html.escape(m.upper())}<br>{mark}</div>')
    return '<div class="months">' + "".join(cells) + "</div>"


def montar_html(
    *,
    org_short: str,
    org_full: str,
    ano: int,
    calendario: Sequence[str],
    itens: Sequence[SituacaoReap],
    titulo: str,
    gerado_em: datetime | None = None,
    individual: bool = False,
) -> str:
    gerado_em = gerado_em or datetime.now()
    logo = logo_data_uri()
    logo_tag = f'<img class="logo" src="{logo}" alt="{html.escape(org_short)}">' if logo else ""
    cal = meses_para_texto(calendario)
    n = len(itens)
    n_reg = sum(1 for i in itens if i.regular)
    n_pen = n - n_reg

    rows_html: List[str] = []
    if individual and itens:
        s = itens[0]
        sit = "REGULAR" if s.regular else "PENDENTE"
        sit_cls = "ok" if s.regular else "warn"
        extra = "" if s.regular else f"<p class='faltando'>{html.escape(s.rotulo_faltando)}</p>"
        rows_html.append(
            f"""
            <section class="card">
              <h2>{html.escape(format_nome(s.pessoa.nome))}</h2>
              <p>CPF: {html.escape(format_cpf(s.pessoa.cpf))}</p>
              <p>Ano {int(ano)} · Situação REAP: <strong class="{sit_cls}">{sit}</strong></p>
              {extra}
              {_grid(meses_marcados(s.pessoa, ano))}
            </section>
            """
        )
    else:
        body_rows: List[str] = []
        grupos = agrupar_por_municipio(
            list(itens),
            lambda s: getattr(s.pessoa, "municipio", "") or "",
            sort_nome=lambda s: format_nome(s.pessoa.nome),
        )
        # Sócio | CPF | Telefone | Município | Situação | meses…
        colspan = 5 + len(MESES)
        for mun_label, grupo in grupos:
            body_rows.append(html_cabecalho_municipio(mun_label, colspan=colspan))
            for s in grupo:
                sit = "Regular" if s.regular else "Pendente"
                sit_cls = "ok" if s.regular else "warn"
                marks = meses_marcados(s.pessoa, ano)
                tds = "".join(
                    f'<td class="{"on" if marks[m] else "off"}">{"✓" if marks[m] else "·"}</td>'
                    for m in MESES
                )
                tel = str(getattr(s.pessoa, "telefone", "") or "") or "—"
                mun = str(getattr(s.pessoa, "municipio", "") or "") or "—"
                body_rows.append(
                    "<tr>"
                    f"<td>{html.escape(format_nome(s.pessoa.nome))}</td>"
                    f"<td>{html.escape(format_cpf(s.pessoa.cpf))}</td>"
                    f"<td>{html.escape(tel)}</td>"
                    f"<td>{html.escape(mun)}</td>"
                    f'<td class="{sit_cls}">{html.escape(sit)}</td>'
                    f"{tds}"
                    "</tr>"
                )
        thead = (
            "<tr><th>Sócio</th><th>CPF</th><th>Telefone</th><th>Município</th><th>Situação</th>"
            + "".join(f"<th>{m.upper()}</th>" for m in MESES)
            + "</tr>"
        )
        rows_html.append(
            f"<table><thead>{thead}</thead><tbody>{''.join(body_rows)}</tbody></table>"
        )

    aviso = (
        "Uso interno da secretaria (somente administrador). "
        "Este documento não é comprovante de pagamento. "
        "É o registro de REAP constante na base do sindicato na data da emissão."
    )

    return f"""<!DOCTYPE html>
<html lang="pt-BR">
<head>
  <meta charset="utf-8">
  <title>{html.escape(titulo)}</title>
  <style>
    body {{ font-family: Segoe UI, Arial, sans-serif; color: #0A2F52; margin: 24px; }}
    .brand {{ display: flex; align-items: center; gap: 12px; }}
    .logo {{ height: 96px; width: auto; max-width: 120px; object-fit: contain; }}
    h1 {{ margin: 8px 0 0; font-size: 20px; }}
    .sub {{ color: #5A7388; font-size: 13px; }}
    .gold {{ height: 3px; background: #C4A35A; border: 0; margin: 12px 0 18px; }}
    .ok {{ color: #1B8458; }}
    .warn {{ color: #A82E26; }}
    .months {{ display: grid; grid-template-columns: repeat(6, 1fr); gap: 6px; max-width: 520px; }}
    .m {{ text-align: center; padding: 8px; border-radius: 6px; font-size: 12px; font-weight: 700; }}
    .m.on, td.on {{ background: #D4EFE3; color: #1B8458; }}
    .m.off, td.off {{ background: #E7EEF4; color: #5A7388; }}
    table {{ border-collapse: collapse; width: 100%; font-size: 12px; }}
    th, td {{ border: 1px solid #B7CDDD; padding: 6px 8px; text-align: center; }}
    th {{ background: #0A2F52; color: #EAF6FC; }}
    td:first-child, td:nth-child(4) {{ text-align: left; }}
    {css_grupo_municipio()}
    .foot {{ margin-top: 18px; color: #5A7388; font-size: 12px; }}
    .disclaimer {{ margin-top: 10px; font-size: 11px; color: #5A7388; }}
    @media print {{
      body {{ margin: 12px; }}
      .noprint {{ display: none; }}
    }}
  </style>
</head>
<body>
  <div class="brand">{logo_tag}
  <div>
  <h1>{html.escape(org_short)} — {html.escape(org_full)}</h1>
  <p class="sub">{html.escape(titulo)} · Ano {int(ano)}<br>
  Calendário considerado: {html.escape(cal)}<br>
  Gerado em {html.escape(gerado_em.strftime("%d/%m/%Y %H:%M"))} · CPF completo · uso interno</p>
  </div></div>
  <hr class="gold">
  {''.join(rows_html)}
  <p class="foot">Sócios neste relatório: {n} · Regulares: {n_reg} · Pendentes: {n_pen}</p>
  <p class="disclaimer">{html.escape(aviso)}</p>
  <p class="noprint sub">Use Imprimir do navegador → «Salvar como PDF» se quiser arquivo.</p>
</body>
</html>
"""


def salvar_html(html_text: str, *, nome_arquivo: str) -> Path:
    path = pasta_relatorios() / nome_arquivo
    path.write_text(html_text, encoding="utf-8")
    return path


def nome_arquivo_relatorio(ano: int, *, individual_nome: str = "") -> str:
    stamp = datetime.now().strftime("%Y%m%d_%H%M")
    if individual_nome:
        slug = "".join(ch if ch.isalnum() else "-" for ch in individual_nome)[:40].strip("-")
        return f"reap-{ano}-{slug}-{stamp}.html"
    return f"reap-{ano}-diretoria-{stamp}.html"


def itens_para_relatorio(
    pendentes: Iterable[SituacaoReap],
    regulares: Iterable[SituacaoReap],
) -> List[SituacaoReap]:
    todos = list(pendentes) + list(regulares)
    todos.sort(
        key=lambda s: (
            municipio_rotulo(getattr(s.pessoa, "municipio", "")),
            s.pessoa.nome.lower(),
        )
    )
    return todos
