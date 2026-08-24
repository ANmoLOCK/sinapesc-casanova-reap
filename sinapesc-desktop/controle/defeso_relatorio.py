"""Relatório HTML do Defeso Fácil (uso interno da secretaria)."""

from __future__ import annotations

import html
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Sequence

from controle.defeso import (
    FichaDefeso,
    endereco_defeso_relatorio,
    entrada_confirmada_flag,
    parcelas_para_relatorio,
)
from controle.relatorio import logo_data_uri, pasta_relatorios
from ui.formatters import display_nome, format_cpf, only_digits


def telefone_relatorio(f: FichaDefeso | None, tel_reap: str = "") -> str:
    """Telefone do relatório: só REAP (planilha Pessoas)."""
    if tel_reap:
        return str(tel_reap).strip()
    if f is not None:
        return str(f.telefone_reap or "").strip()
    return ""


def montar_html_defeso(
    *,
    org_short: str,
    org_full: str,
    itens: Sequence[Dict[str, Any]],
    titulo: str,
    localidade: str = "",
    gerado_em: datetime | None = None,
) -> str:
    gerado_em = gerado_em or datetime.now()
    logo = logo_data_uri()
    logo_tag = f'<img class="logo" src="{logo}" alt="{html.escape(org_short)}">' if logo else ""
    loc_txt = f" · Localidade: {html.escape(localidade)}" if localidade else ""
    n = len(itens)
    n_ent = sum(1 for i in itens if i.get("entrada_confirmada"))

    rows: List[str] = []
    for item in itens:
        tel = html.escape(str(item.get("telefone") or "—"))
        mun = html.escape(str(item.get("municipio") or "—"))
        end = html.escape(str(item.get("endereco") or "—")).replace("\n", "<br>")
        parcelas = html.escape(str(item.get("parcelas") or "—")).replace("\n", "<br>")
        ent = "Sim" if item.get("entrada_confirmada") else "Não"
        ent_cls = "ok" if item.get("entrada_confirmada") else "off"
        rows.append(
            "<tr>"
            f"<td>{html.escape(display_nome(str(item.get('nome') or '')))}</td>"
            f"<td>{html.escape(format_cpf(str(item.get('cpf') or '')))}</td>"
            f"<td>{mun}</td>"
            f"<td>{tel}</td>"
            f"<td class=\"addr\">{end}</td>"
            f"<td class=\"parc\">{parcelas}</td>"
            f'<td class="{ent_cls}">{ent}</td>'
            "</tr>"
        )

    table = (
        "<table><thead><tr>"
        "<th>Nome</th><th>CPF</th><th>Município (REAP)</th><th>Telefone (REAP)</th>"
        "<th>Endereço (Defeso)</th><th>Parcelas</th><th>Entrada</th>"
        "</tr></thead><tbody>"
        + "".join(rows)
        + "</tbody></table>"
    )

    aviso = (
        "Uso interno. Só entram sócios cadastrados na planilha REAP (Pessoas). "
        "Município e telefone vêm do REAP. Endereço: rua, nº, bairro, UF e CEP da ficha Defeso."
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
    table {{ border-collapse: collapse; width: 100%; font-size: 12px; }}
    th, td {{ border: 1px solid #B7CDDD; padding: 6px 8px; text-align: left; vertical-align: top; }}
    th {{ background: #0A2F52; color: #EAF6FC; }}
    td.addr, td.parc {{ max-width: 220px; white-space: pre-line; }}
    .ok {{ color: #1B8458; font-weight: 700; }}
    .off {{ color: #5A7388; }}
    .foot {{ margin-top: 18px; color: #5A7388; font-size: 12px; }}
    .disclaimer {{ margin-top: 10px; font-size: 11px; color: #5A7388; }}
    @media print {{ body {{ margin: 12px; }} .noprint {{ display: none; }} }}
  </style>
</head>
<body>
  <div class="brand">{logo_tag}
  <div>
  <h1>{html.escape(org_short)} — {html.escape(org_full)}</h1>
  <p class="sub">{html.escape(titulo)}{loc_txt}<br>
  Gerado em {html.escape(gerado_em.strftime("%d/%m/%Y %H:%M"))} · CPF completo · uso interno</p>
  </div></div>
  <hr class="gold">
  {table}
  <p class="foot">Registros: {n} · Entrada confirmada: {n_ent}</p>
  <p class="disclaimer">{html.escape(aviso)}</p>
  <p class="noprint sub">Use Imprimir do navegador → «Salvar como PDF» se quiser arquivo.</p>
</body>
</html>
"""


def nome_arquivo_defeso_relatorio(*, localidade: str = "") -> str:
    stamp = datetime.now().strftime("%Y%m%d_%H%M")
    if localidade:
        slug = "".join(ch if ch.isalnum() else "-" for ch in localidade)[:30].strip("-")
        return f"defeso-{slug}-{stamp}.html"
    return f"defeso-geral-{stamp}.html"


def itens_defeso_para_relatorio(
    fichas: Sequence[FichaDefeso],
    *,
    telefones_reap: Dict[str, str],
    municipios_reap: Dict[str, str],
    nomes_reap: Dict[str, str] | None = None,
    cpfs_reap: Sequence[str] | None = None,
    localidade: str = "",
    somente_entrada: bool = False,
) -> List[Dict[str, Any]]:
    """
    Monta linhas do relatório.

    Só inclui CPF que existe na planilha REAP (Pessoas) — evita sócio fantasma
    que exista só como lixo/órfão na planilha Defeso.
    """
    loc = localidade.strip().lower()
    nomes = nomes_reap or {}
    # Conjunto de CPFs válidos do REAP
    if cpfs_reap is not None:
        allowed = {only_digits(c) for c in cpfs_reap if len(only_digits(c)) == 11}
    else:
        allowed = set(municipios_reap) | set(telefones_reap) | set(nomes)

    by_cpf: Dict[str, FichaDefeso] = {}
    for f in fichas:
        cpf = only_digits(f.cpf)
        if len(cpf) == 11:
            by_cpf[cpf] = f

    out: List[Dict[str, Any]] = []
    # Percorre só CPFs do REAP (ordem estável por nome)
    for cpf in sorted(allowed, key=lambda c: (nomes.get(c) or by_cpf.get(c) and by_cpf[c].nome or c).lower()):
        if len(cpf) != 11:
            continue
        f = by_cpf.get(cpf)
        mun_reap = str(municipios_reap.get(cpf) or "").strip()
        mun_defeso = str(f.municipio or "").strip() if f else ""
        mun_filtro = mun_reap or mun_defeso
        if loc and mun_filtro.lower() != loc:
            continue
        ent = entrada_confirmada_flag(f) if f else False
        if somente_entrada and not ent:
            continue
        # Sem ficha Defeso e sem filtro de entrada: ainda pode listar se quiser só com ficha
        if f is None:
            continue
        nome = str(nomes.get(cpf) or f.nome or "").strip()
        if not nome:
            continue
        tel = telefone_relatorio(f, telefones_reap.get(cpf, ""))
        out.append(
            {
                "nome": nome,
                "cpf": cpf,
                "telefone": tel,
                "municipio": mun_reap or mun_defeso,
                "endereco": endereco_defeso_relatorio(f),
                "parcelas": parcelas_para_relatorio(f.parcelas_recebidas or ""),
                "entrada_confirmada": ent,
            }
        )
    out.sort(key=lambda r: str(r.get("nome") or "").lower())
    return out


def salvar_html_defeso(html_text: str, *, nome_arquivo: str) -> Path:
    path = pasta_relatorios() / nome_arquivo
    path.write_text(html_text, encoding="utf-8")
    return path
