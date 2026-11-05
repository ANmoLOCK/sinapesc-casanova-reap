"""Tabela HTML do Informe Mensal — abre no navegador (imprimir / salvar PDF)."""

from __future__ import annotations

import html
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence

from controle.informe_mensal import (
    MESES_ORDEM,
    MESES_PESCA,
    MESES_PIRACEMA,
    MES_TITULO,
    PIRACEMA_LABEL,
    InformeMes,
    padrao_quantidades,
    resumo_socio,
)
from ui.formatters import format_cpf, format_nome


def _esc(v: Any) -> str:
    return html.escape(str(v if v is not None else ""))


def _celula_mes(mes: str, reg: Optional[InformeMes]) -> str:
    if mes in MESES_PIRACEMA:
        return f'<td class="pir" title="{_esc(PIRACEMA_LABEL)}">piracema</td>'
    if reg and reg.houve_pesca:
        spp = ", ".join(f"{e.nome} {int(e.kg)}kg" for e in reg.especies)
        return (
            f'<td class="ok" title="{_esc(spp)}">'
            f"<strong>{len(reg.especies)} spp</strong><br>"
            f"{int(reg.peso_mes)} kg<br>"
            f"{int(reg.dias)} dias"
            f"</td>"
        )
    return '<td class="off">—</td>'


def _bloco_detalhe(socio: Dict[str, Any], meses: Dict[str, InformeMes], ano: int) -> str:
    feitos = [m for m in MESES_PESCA if m in meses and meses[m].houve_pesca]
    if not feitos:
        return ""
    resumo = socio.get("resumo") or resumo_socio(meses, socio.get("cpf_raw") or socio.get("id") or "", ano)
    plano = resumo.get("plano_texto") or ""
    partes = [
        f'<section class="socio" id="socio-{_esc(socio.get("id") or "")}">',
        f"<h2>{_esc(socio.get('nome') or '')}</h2>",
        (
            f'<p class="meta">CPF {_esc(socio.get("cpf") or "")} · '
            f'Tel. {_esc(socio.get("telefone") or "—")} · '
            f'{_esc(socio.get("municipio") or "—")} · '
            f'{int(resumo.get("gerados") or 0)}/{int(resumo.get("total") or len(MESES_PESCA))} meses · '
            f'{int(resumo.get("peso_anual") or 0)} kg'
            f'{(" · plano " + _esc(plano)) if plano else ""}</p>'
        ),
    ]
    for m in feitos:
        r = meses[m]
        linhas = "".join(
            (
                f"<tr><td>{i}</td><td>{_esc(e.nome)}</td>"
                f"<td class='num'>{int(e.kg)}</td>"
                f"<td class='num'>R$ {float(e.valor):.2f}".replace(".", ",")
                + "</td></tr>"
            )
            for i, e in enumerate(r.especies, start=1)
        )
        partes.append(
            f"""
            <div class="mes-bloco">
              <h3>{_esc(MES_TITULO.get(m, m))}/{ano} — Houve pesca: SIM</h3>
              <p class="meta">{int(r.dias)} dias · {_esc(r.municipio)} · {_esc(r.local)} ·
                 {_esc(r.ambiente)} · {_esc(r.petrecho)} · total {int(r.peso_mes)} kg</p>
              <table class="esp">
                <thead><tr><th>#</th><th>Espécie</th><th>Kg</th><th>Valor (R$/kg)</th></tr></thead>
                <tbody>{linhas}</tbody>
              </table>
            </div>"""
        )
    partes.append("</section>")
    return "\n".join(partes)


def montar_html_informe(
    *,
    org_short: str,
    org_full: str,
    ano: int,
    socios: Sequence[Dict[str, Any]],
    por_pessoa: Dict[str, Dict[str, InformeMes]],
    gerado_em: Optional[datetime] = None,
    somente_com_meses: bool = False,
) -> str:
    """HTML com tabela geral (1 linha por sócio) + detalhe dos meses preenchidos."""
    from controle.relatorio import logo_data_uri  # import tardio (evita ciclo ui↔relatorio)

    gerado_em = gerado_em or datetime.now()
    logo = logo_data_uri()
    logo_tag = f'<img class="logo" src="{logo}" alt="{_esc(org_short)}">' if logo else ""

    lista = list(socios)
    if somente_com_meses:
        lista = [s for s in lista if (s.get("resumo") or {}).get("gerados")]

    n = len(lista)
    n_com = sum(1 for s in lista if (s.get("resumo") or {}).get("gerados"))
    n_ok = sum(
        1
        for s in lista
        if int((s.get("resumo") or {}).get("gerados") or 0) >= len(MESES_PESCA)
    )

    thead = (
        "<tr><th>Sócio</th><th>CPF</th><th>Telefone</th><th>Município</th>"
        + "".join(f"<th>{_esc(MES_TITULO[m][:3])}</th>" for m in MESES_ORDEM)
        + "<th>Gerados</th><th>Kg ano</th><th>Plano</th></tr>"
    )
    body: List[str] = []
    for s in lista:
        meses = por_pessoa.get(s.get("id") or "", {}) or {}
        resumo = s.get("resumo") or {}
        tds = "".join(_celula_mes(m, meses.get(m)) for m in MESES_ORDEM)
        plano = resumo.get("plano_texto") or padrao_quantidades(meses)
        body.append(
            "<tr>"
            f'<td class="nome"><a href="#socio-{_esc(s.get("id") or "")}">{_esc(s.get("nome") or "")}</a></td>'
            f'<td class="mono">{_esc(s.get("cpf") or format_cpf(s.get("cpf_raw") or ""))}</td>'
            f"<td>{_esc(s.get('telefone') or '—')}</td>"
            f"<td>{_esc(s.get('municipio') or '—')}</td>"
            f"{tds}"
            f'<td class="num">{int(resumo.get("gerados") or 0)}/{int(resumo.get("total") or len(MESES_PESCA))}</td>'
            f'<td class="num">{int(resumo.get("peso_anual") or 0)}</td>'
            f'<td class="mono plano">{_esc(plano)}</td>'
            "</tr>"
        )

    detalhes = "".join(
        _bloco_detalhe(s, por_pessoa.get(s.get("id") or "", {}) or {}, ano)
        for s in lista
        if (s.get("resumo") or {}).get("gerados")
    )
    if not detalhes:
        detalhes = '<p class="vazio">Nenhum mês de pesca preenchido neste ano.</p>'

    return f"""<!DOCTYPE html>
<html lang="pt-BR">
<head>
  <meta charset="utf-8">
  <title>Informe Mensal {int(ano)} — {_esc(org_short)}</title>
  <style>
    body {{ font-family: Segoe UI, Arial, sans-serif; color: #0A2F52; margin: 24px; }}
    .brand {{ display: flex; align-items: center; gap: 12px; }}
    .logo {{ height: 96px; width: auto; max-width: 120px; object-fit: contain; }}
    h1 {{ margin: 8px 0 0; font-size: 20px; }}
    h2 {{ margin: 22px 0 4px; font-size: 16px; color: #0A2F52; border-bottom: 2px solid #C4A35A; padding-bottom: 4px; }}
    h3 {{ margin: 12px 0 4px; font-size: 13.5px; }}
    .sub {{ color: #5A7388; font-size: 13px; }}
    .meta {{ color: #5A7388; font-size: 12px; margin: 2px 0 8px; }}
    .gold {{ height: 3px; background: #C4A35A; border: 0; margin: 12px 0 18px; }}
    table.resumo {{ border-collapse: collapse; width: 100%; font-size: 11.5px; margin-bottom: 18px; }}
    table.resumo th, table.resumo td {{ border: 1px solid #B7CDDD; padding: 5px 6px; text-align: center; vertical-align: middle; }}
    table.resumo th {{ background: #0A2F52; color: #EAF6FC; font-weight: 600; }}
    table.resumo td.nome {{ text-align: left; font-weight: 600; white-space: nowrap; }}
    table.resumo td.nome a {{ color: #0A2F52; text-decoration: none; }}
    table.resumo td.nome a:hover {{ text-decoration: underline; }}
    table.resumo td.ok {{ background: #D4EFE3; color: #1B8458; font-size: 10.5px; line-height: 1.25; }}
    table.resumo td.off {{ background: #E7EEF4; color: #5A7388; }}
    table.resumo td.pir {{ background: #C9CED3; color: #5A636B; font-size: 10px; }}
    table.resumo td.num {{ text-align: right; white-space: nowrap; }}
    table.resumo td.mono, .mono {{ font-family: Consolas, "Courier New", monospace; font-size: 11px; }}
    table.resumo td.plano {{ text-align: left; white-space: nowrap; }}
    table.esp {{ border-collapse: collapse; width: 100%; max-width: 520px; font-size: 12px; margin-bottom: 8px; }}
    table.esp th, table.esp td {{ border: 1px solid #B7CDDD; padding: 4px 8px; }}
    table.esp th {{ background: #14507E; color: #EAF6FC; text-align: left; }}
    table.esp td.num {{ text-align: right; }}
    .mes-bloco {{ margin: 6px 0 14px; padding: 8px 10px; background: #F3F8FC; border: 1px solid #D5E4EE; }}
    .legenda {{ font-size: 12px; color: #5A7388; margin: 0 0 10px; }}
    .legenda span {{ display: inline-block; padding: 2px 8px; margin-right: 6px; border: 1px solid #B7CDDD; }}
    .legenda .ok {{ background: #D4EFE3; }}
    .legenda .off {{ background: #E7EEF4; }}
    .legenda .pir {{ background: #C9CED3; }}
    .foot {{ margin-top: 18px; color: #5A7388; font-size: 12px; }}
    .vazio {{ color: #5A7388; font-style: italic; }}
    .noprint {{ margin-top: 8px; }}
    @media print {{
      body {{ margin: 10px; }}
      .noprint {{ display: none; }}
      a {{ color: inherit; text-decoration: none; }}
      .mes-bloco {{ break-inside: avoid; }}
      .socio {{ break-before: page; }}
      .socio:first-of-type {{ break-before: auto; }}
    }}
  </style>
</head>
<body>
  <div class="brand">{logo_tag}
  <div>
    <h1>{_esc(org_short)} — {_esc(org_full)}</h1>
    <p class="sub">Informe Mensal · Ano {int(ano)} · tabela por sócio com os meses preenchidos<br>
    Gerado em {_esc(gerado_em.strftime("%d/%m/%Y %H:%M"))} · CPF completo · uso interno da secretaria</p>
  </div></div>
  <hr class="gold">
  <p class="legenda">
    <span class="ok">mês gerado</span>
    <span class="off">pendente</span>
    <span class="pir">piracema</span>
    · Jan/Fev/Nov/Dez = {_esc(PIRACEMA_LABEL)} · Mar→Out = pesca
  </p>
  <table class="resumo">
    <thead>{thead}</thead>
    <tbody>{''.join(body) if body else '<tr><td colspan="17">Nenhum sócio.</td></tr>'}</tbody>
  </table>
  <h2>Detalhe dos meses preenchidos</h2>
  {detalhes}
  <p class="foot">Sócios nesta tabela: {n} · Com pelo menos 1 mês: {n_com} · Completos (Mar–Out): {n_ok}</p>
  <p class="noprint sub">Use Imprimir do navegador → «Salvar como PDF» se quiser arquivo.
  O HTML fica na pasta de relatórios do Sinapesc.</p>
</body>
</html>
"""


def montar_html_informe_socio(
    *,
    org_short: str,
    org_full: str,
    ano: int,
    socio: Dict[str, Any],
    meses: Dict[str, InformeMes],
    gerado_em: Optional[datetime] = None,
) -> str:
    """HTML individual: só os meses preenchidos daquele sócio."""
    from controle.relatorio import logo_data_uri

    gerado_em = gerado_em or datetime.now()
    logo = logo_data_uri()
    logo_tag = f'<img class="logo" src="{logo}" alt="{_esc(org_short)}">' if logo else ""
    resumo = socio.get("resumo") or resumo_socio(
        meses, socio.get("cpf_raw") or socio.get("id") or "", ano
    )
    feitos = [m for m in MESES_PESCA if m in meses and meses[m].houve_pesca]
    plano = resumo.get("plano_texto") or ""
    nome = socio.get("nome") or ""

    if not feitos:
        corpo = (
            '<p class="vazio">Este sócio ainda não tem nenhum mês de pesca preenchido '
            f"em {int(ano)}.</p>"
        )
    else:
        thead = (
            "<tr><th>Mês</th><th>Dias</th><th>Espécies</th><th>Kg</th>"
            "<th>Município</th><th>Peixes (kg)</th></tr>"
        )
        rows = []
        for m in feitos:
            r = meses[m]
            peixes = "; ".join(f"{e.nome} {int(e.kg)} kg" for e in r.especies)
            rows.append(
                "<tr>"
                f"<td class='nome'>{_esc(MES_TITULO.get(m, m))}</td>"
                f"<td class='num'>{int(r.dias)}</td>"
                f"<td class='num'>{len(r.especies)}</td>"
                f"<td class='num'>{int(r.peso_mes)}</td>"
                f"<td>{_esc(r.municipio)}</td>"
                f"<td class='peixes'>{_esc(peixes)}</td>"
                "</tr>"
            )
        corpo = f"""
        <p class="legenda">Somente os <strong>{len(feitos)}</strong> mês(es) preenchido(s)
        de Março a Outubro · Jan/Fev/Nov/Dez = {_esc(PIRACEMA_LABEL)} (não listados).</p>
        <table class="resumo">
          <thead>{thead}</thead>
          <tbody>{''.join(rows)}</tbody>
        </table>
        <h2>Detalhe por mês</h2>
        {_bloco_detalhe(socio, meses, ano)}
        """

    return f"""<!DOCTYPE html>
<html lang="pt-BR">
<head>
  <meta charset="utf-8">
  <title>Informe Mensal {int(ano)} — {_esc(nome)}</title>
  <style>
    body {{ font-family: Segoe UI, Arial, sans-serif; color: #0A2F52; margin: 24px; }}
    .brand {{ display: flex; align-items: center; gap: 12px; }}
    .logo {{ height: 96px; width: auto; max-width: 120px; object-fit: contain; }}
    h1 {{ margin: 8px 0 0; font-size: 20px; }}
    h2 {{ margin: 22px 0 4px; font-size: 16px; color: #0A2F52; border-bottom: 2px solid #C4A35A; padding-bottom: 4px; }}
    h3 {{ margin: 12px 0 4px; font-size: 13.5px; }}
    .sub {{ color: #5A7388; font-size: 13px; }}
    .meta {{ color: #5A7388; font-size: 12px; margin: 2px 0 8px; }}
    .gold {{ height: 3px; background: #C4A35A; border: 0; margin: 12px 0 18px; }}
    table.resumo {{ border-collapse: collapse; width: 100%; font-size: 12.5px; margin-bottom: 18px; }}
    table.resumo th, table.resumo td {{ border: 1px solid #B7CDDD; padding: 7px 10px; text-align: center; vertical-align: middle; }}
    table.resumo th {{ background: #0A2F52; color: #EAF6FC; font-weight: 600; }}
    table.resumo td.nome {{ text-align: left; font-weight: 600; }}
    table.resumo td.num {{ text-align: right; white-space: nowrap; }}
    table.resumo td.peixes {{ text-align: left; font-size: 12px; }}
    table.esp {{ border-collapse: collapse; width: 100%; max-width: 520px; font-size: 12px; margin-bottom: 8px; }}
    table.esp th, table.esp td {{ border: 1px solid #B7CDDD; padding: 4px 8px; }}
    table.esp th {{ background: #14507E; color: #EAF6FC; text-align: left; }}
    table.esp td.num {{ text-align: right; }}
    .mes-bloco {{ margin: 6px 0 14px; padding: 8px 10px; background: #F3F8FC; border: 1px solid #D5E4EE; }}
    .legenda {{ font-size: 12px; color: #5A7388; margin: 0 0 10px; }}
    .foot {{ margin-top: 18px; color: #5A7388; font-size: 12px; }}
    .vazio {{ color: #5A7388; font-style: italic; }}
    .card-socio {{
      background: #F3F8FC; border: 1px solid #B7CDDD; padding: 12px 14px; margin-bottom: 14px;
    }}
    .card-socio strong {{ color: #0A2F52; }}
    @media print {{
      body {{ margin: 10px; }}
      .noprint {{ display: none; }}
      .mes-bloco {{ break-inside: avoid; }}
    }}
  </style>
</head>
<body>
  <div class="brand">{logo_tag}
  <div>
    <h1>{_esc(org_short)} — {_esc(org_full)}</h1>
    <p class="sub">Informe Mensal individual · Ano {int(ano)} · somente meses preenchidos<br>
    Gerado em {_esc(gerado_em.strftime("%d/%m/%Y %H:%M"))} · CPF completo · uso interno</p>
  </div></div>
  <hr class="gold">
  <div class="card-socio">
    <strong>{_esc(nome)}</strong><br>
    CPF {_esc(socio.get("cpf") or "")} · Tel. {_esc(socio.get("telefone") or "—")} ·
    {_esc(socio.get("municipio") or "—")}<br>
    {int(resumo.get("gerados") or 0)}/{int(resumo.get("total") or len(MESES_PESCA))} meses ·
    {int(resumo.get("peso_anual") or 0)} kg no ano
    {(" · plano " + _esc(plano)) if plano else ""}
  </div>
  {corpo}
  <p class="foot">Meses preenchidos: {len(feitos)} · Peso acumulado: {int(resumo.get("peso_anual") or 0)} kg</p>
  <p class="noprint sub">Use Imprimir do navegador → «Salvar como PDF» se quiser arquivo.</p>
</body>
</html>
"""


def nome_arquivo_informe(ano: int) -> str:
    stamp = datetime.now().strftime("%Y%m%d_%H%M")
    return f"informe-mensal-{int(ano)}-{stamp}.html"


def nome_arquivo_informe_socio(ano: int, nome: str) -> str:
    stamp = datetime.now().strftime("%Y%m%d_%H%M")
    slug = "".join(ch if ch.isalnum() else "-" for ch in (nome or "socio"))[:40].strip("-") or "socio"
    return f"informe-mensal-{int(ano)}-{slug}-{stamp}.html"


def salvar_html_informe(html_text: str, *, nome_arquivo: str) -> Path:
    from controle.relatorio import pasta_relatorios  # import tardio (evita ciclo ui↔relatorio)

    path = pasta_relatorios() / nome_arquivo
    path.write_text(html_text, encoding="utf-8")
    return path


def socios_para_tabela(
    pessoas: Sequence[Any],
    por_pessoa: Dict[str, Dict[str, InformeMes]],
    ano: int,
) -> List[Dict[str, Any]]:
    """Monta a mesma estrutura de dict usada pela tela (nome, cpf, resumo…)."""
    out: List[Dict[str, Any]] = []
    for p in pessoas:
        meses = por_pessoa.get(getattr(p, "id", ""), {}) or {}
        cpf_raw = "".join(ch for ch in str(getattr(p, "cpf", "") or "") if ch.isdigit())
        out.append(
            {
                "id": getattr(p, "id", ""),
                "nome": format_nome(getattr(p, "nome", "") or ""),
                "cpf": format_cpf(getattr(p, "cpf", "") or ""),
                "cpf_raw": cpf_raw,
                "telefone": getattr(p, "telefone", "") or "",
                "municipio": getattr(p, "municipio", "") or "",
                "resumo": resumo_socio(meses, cpf_raw or getattr(p, "id", ""), ano),
            }
        )
    out.sort(key=lambda s: s["nome"].casefold())
    return out
