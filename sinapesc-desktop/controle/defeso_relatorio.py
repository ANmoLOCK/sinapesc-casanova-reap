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
    parse_parcelas,
    parcelas_para_relatorio,
    tem_parcela_preenchida,
)
from controle.relatorio import logo_data_uri, pasta_relatorios
from ui.formatters import display_nome, format_cpf, only_digits

# Colunas opcionais do relatório HTML (nome sempre entra).
COLUNAS_DEFESO_TODAS = (
    "nome",
    "cpf",
    "municipio",
    "telefone",
    "endereco",
    "parcelas",
    "entrada",
)
COLUNA_DEFESO_OBRIGATORIA = "nome"


def normalize_colunas_defeso(colunas: Any = None) -> List[str]:
    """
    Normaliza a seleção de colunas do relatório.

    Aceita lista, dict {coluna: bool} ou string CSV. Nome é sempre mantido.
    Se nada válido vier, devolve todas as colunas.
    """
    allowed = set(COLUNAS_DEFESO_TODAS)
    selected: List[str] = []

    if colunas is None or colunas == "" or colunas is False:
        return list(COLUNAS_DEFESO_TODAS)

    if isinstance(colunas, str):
        parts = [p.strip().lower() for p in colunas.replace(";", ",").split(",") if p.strip()]
        selected = [p for p in parts if p in allowed]
    elif isinstance(colunas, dict):
        for key in COLUNAS_DEFESO_TODAS:
            raw = colunas.get(key)
            if raw is None and key != COLUNA_DEFESO_OBRIGATORIA:
                continue
            on = True if raw is None and key == COLUNA_DEFESO_OBRIGATORIA else bool(raw)
            if on and key in allowed:
                selected.append(key)
    elif isinstance(colunas, (list, tuple, set)):
        for item in colunas:
            key = str(item or "").strip().lower()
            if key in allowed and key not in selected:
                selected.append(key)
    else:
        return list(COLUNAS_DEFESO_TODAS)

    if COLUNA_DEFESO_OBRIGATORIA not in selected:
        selected.insert(0, COLUNA_DEFESO_OBRIGATORIA)
    # Ordem canônica
    order = {k: i for i, k in enumerate(COLUNAS_DEFESO_TODAS)}
    selected = sorted(set(selected), key=lambda k: order.get(k, 99))
    return selected or list(COLUNAS_DEFESO_TODAS)


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
    colunas: Any = None,
    filtros_resumo: str = "",
) -> str:
    gerado_em = gerado_em or datetime.now()
    cols = normalize_colunas_defeso(colunas)
    logo = logo_data_uri()
    logo_tag = f'<img class="logo" src="{logo}" alt="{html.escape(org_short)}">' if logo else ""
    filtro_txt = (filtros_resumo or "").strip()
    if not filtro_txt and localidade:
        filtro_txt = f"Localidade: {localidade}"
    loc_txt = f" · {html.escape(filtro_txt)}" if filtro_txt else ""
    n = len(itens)
    n_ent = sum(1 for i in itens if i.get("entrada_confirmada"))

    headers = {
        "nome": "Nome",
        "cpf": "CPF",
        "municipio": "Município (REAP)",
        "telefone": "Telefone (REAP)",
        "endereco": "Endereço (Defeso)",
        "parcelas": "Parcelas",
        "entrada": "Entrada",
    }

    rows: List[str] = []
    for item in itens:
        cells: List[str] = []
        for col in cols:
            if col == "nome":
                cells.append(f"<td>{html.escape(display_nome(str(item.get('nome') or '')))}</td>")
            elif col == "cpf":
                cells.append(f"<td>{html.escape(format_cpf(str(item.get('cpf') or '')))}</td>")
            elif col == "municipio":
                cells.append(f"<td>{html.escape(str(item.get('municipio') or '—'))}</td>")
            elif col == "telefone":
                cells.append(f"<td>{html.escape(str(item.get('telefone') or '—'))}</td>")
            elif col == "endereco":
                end = html.escape(str(item.get("endereco") or "—")).replace("\n", "<br>")
                cells.append(f'<td class="addr">{end}</td>')
            elif col == "parcelas":
                parcelas = html.escape(str(item.get("parcelas") or "—")).replace("\n", "<br>")
                cells.append(f'<td class="parc">{parcelas}</td>')
            elif col == "entrada":
                ent = "Sim" if item.get("entrada_confirmada") else "Não"
                ent_cls = "ok" if item.get("entrada_confirmada") else "off"
                cells.append(f'<td class="{ent_cls}">{ent}</td>')
        rows.append("<tr>" + "".join(cells) + "</tr>")

    ths = "".join(f"<th>{html.escape(headers[c])}</th>" for c in cols if c in headers)
    table = "<table><thead><tr>" + ths + "</tr></thead><tbody>" + "".join(rows) + "</tbody></table>"

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


def _flag_doc_on(valor: Any) -> bool:
    return bool(str(valor or "").strip()) and str(valor).strip().lower() not in ("nao", "não", "false", "0", "off")


def _endereco_completo(f: FichaDefeso) -> bool:
    return all(
        str(getattr(f, k, "") or "").strip()
        for k in ("endereco", "numero", "bairro", "uf", "cep")
    )


def normalize_filtros_defeso(
    filtros: Any = None,
    *,
    localidade: str = "",
    somente_entrada: bool = False,
    somente_parcela: bool = False,
) -> Dict[str, Any]:
    """
    Normaliza filtros do relatório Defeso.

    Campos:
      localidade, uf, busca, entrada (todas|sim|nao),
      parcela (todas|com|sem|1|2|3|4), telefone (todos|com|sem),
      endereco (todos|completo|incompleto), status (""|rascunho|salvo|…),
      doc_identidade, doc_carteira, doc_caf (bool),
      ordenar (nome|recente)
    """
    raw: Dict[str, Any] = {}
    if isinstance(filtros, dict):
        raw = dict(filtros)
    elif isinstance(filtros, str) and filtros.strip():
        text = filtros.strip()
        if text[:1] in "{[":
            import json

            try:
                parsed = json.loads(text)
                if isinstance(parsed, dict):
                    raw = parsed
            except json.JSONDecodeError:
                raw = {}

    loc = str(raw.get("localidade") or localidade or "").strip()
    entrada = str(raw.get("entrada") or "").strip().lower()
    if not entrada:
        if somente_entrada:
            entrada = "sim"
        else:
            entrada = "todas"
    if entrada not in ("todas", "sim", "nao", "não"):
        entrada = "todas"
    if entrada == "não":
        entrada = "nao"

    parcela = str(raw.get("parcela") or "").strip().lower()
    if not parcela:
        parcela = "com" if somente_parcela else "todas"
    if parcela not in ("todas", "com", "sem", "1", "2", "3", "4"):
        parcela = "todas"

    telefone = str(raw.get("telefone") or "todos").strip().lower()
    if telefone not in ("todos", "com", "sem"):
        telefone = "todos"

    endereco = str(raw.get("endereco") or "todos").strip().lower()
    if endereco not in ("todos", "completo", "incompleto"):
        endereco = "todos"

    ordenar = str(raw.get("ordenar") or "nome").strip().lower()
    if ordenar not in ("nome", "recente"):
        ordenar = "nome"

    status = str(raw.get("status") or "").strip().lower()
    uf = str(raw.get("uf") or "").strip().upper()[:2]
    busca = str(raw.get("busca") or "").strip()

    return {
        "localidade": loc,
        "uf": uf,
        "busca": busca,
        "entrada": entrada,
        "parcela": parcela,
        "telefone": telefone,
        "endereco": endereco,
        "status": status,
        "doc_identidade": bool(raw.get("doc_identidade")),
        "doc_carteira": bool(raw.get("doc_carteira")),
        "doc_caf": bool(raw.get("doc_caf")),
        "ordenar": ordenar,
    }


def resumo_filtros_defeso(filtros: Dict[str, Any]) -> str:
    """Texto curto para o subtítulo do HTML."""
    parts: List[str] = []
    if filtros.get("localidade"):
        parts.append(str(filtros["localidade"]))
    if filtros.get("uf"):
        parts.append(f"UF {filtros['uf']}")
    if filtros.get("entrada") == "sim":
        parts.append("entrada confirmada")
    elif filtros.get("entrada") == "nao":
        parts.append("entrada pendente")
    parc = str(filtros.get("parcela") or "todas")
    if parc == "com":
        parts.append("com parcela")
    elif parc == "sem":
        parts.append("sem parcela")
    elif parc in ("1", "2", "3", "4"):
        parts.append(f"{parc}ª parcela preenchida")
    if filtros.get("telefone") == "com":
        parts.append("com telefone")
    elif filtros.get("telefone") == "sem":
        parts.append("sem telefone")
    if filtros.get("endereco") == "completo":
        parts.append("endereço completo")
    elif filtros.get("endereco") == "incompleto":
        parts.append("endereço incompleto")
    if filtros.get("status"):
        parts.append(f"status {filtros['status']}")
    docs = []
    if filtros.get("doc_identidade"):
        docs.append("ID")
    if filtros.get("doc_carteira"):
        docs.append("carteira")
    if filtros.get("doc_caf"):
        docs.append("CAF")
    if docs:
        parts.append("docs: " + "+".join(docs))
    if filtros.get("busca"):
        parts.append(f"busca «{filtros['busca']}»")
    return " · ".join(parts)


def itens_defeso_para_relatorio(
    fichas: Sequence[FichaDefeso],
    *,
    telefones_reap: Dict[str, str],
    municipios_reap: Dict[str, str],
    nomes_reap: Dict[str, str] | None = None,
    cpfs_reap: Sequence[str] | None = None,
    localidade: str = "",
    somente_entrada: bool = False,
    somente_parcela: bool = False,
    filtros: Any = None,
) -> List[Dict[str, Any]]:
    """
    Monta linhas do relatório.

    Só inclui CPF que existe na planilha REAP (Pessoas) — evita sócio fantasma
    que exista só como lixo/órfão na planilha Defeso.
    """
    fcfg = normalize_filtros_defeso(
        filtros,
        localidade=localidade,
        somente_entrada=somente_entrada,
        somente_parcela=somente_parcela,
    )
    loc = str(fcfg["localidade"] or "").strip().lower()
    nomes = nomes_reap or {}
    if cpfs_reap is not None:
        allowed = {only_digits(c) for c in cpfs_reap if len(only_digits(c)) == 11}
    else:
        allowed = set(municipios_reap) | set(telefones_reap) | set(nomes)

    by_cpf: Dict[str, FichaDefeso] = {}
    for f in fichas:
        cpf = only_digits(f.cpf)
        if len(cpf) == 11:
            by_cpf[cpf] = f

    busca = str(fcfg["busca"] or "").strip().lower()
    busca_digits = only_digits(busca)
    out: List[Dict[str, Any]] = []

    for cpf in allowed:
        if len(cpf) != 11:
            continue
        f = by_cpf.get(cpf)
        if f is None:
            continue
        mun_reap = str(municipios_reap.get(cpf) or "").strip()
        mun_defeso = str(f.municipio or "").strip()
        mun_filtro = mun_reap or mun_defeso
        if loc and mun_filtro.lower() != loc:
            continue
        if fcfg["uf"] and str(f.uf or "").strip().upper()[:2] != fcfg["uf"]:
            continue

        ent = entrada_confirmada_flag(f)
        if fcfg["entrada"] == "sim" and not ent:
            continue
        if fcfg["entrada"] == "nao" and ent:
            continue

        parcelas = parse_parcelas(f.parcelas_recebidas or "")
        tem_parc = tem_parcela_preenchida(f)
        parc_mode = fcfg["parcela"]
        if parc_mode == "com" and not tem_parc:
            continue
        if parc_mode == "sem" and tem_parc:
            continue
        if parc_mode in ("1", "2", "3", "4"):
            idx = int(parc_mode) - 1
            if not str(parcelas[idx] or "").strip():
                continue

        nome = str(nomes.get(cpf) or f.nome or "").strip()
        if not nome:
            continue
        tel = telefone_relatorio(f, telefones_reap.get(cpf, ""))
        if fcfg["telefone"] == "com" and not tel:
            continue
        if fcfg["telefone"] == "sem" and tel:
            continue

        end_ok = _endereco_completo(f)
        if fcfg["endereco"] == "completo" and not end_ok:
            continue
        if fcfg["endereco"] == "incompleto" and end_ok:
            continue

        st = str(f.status or "").strip().lower()
        if fcfg["status"] and st != fcfg["status"]:
            continue

        if fcfg["doc_identidade"] and not _flag_doc_on(f.tem_identidade):
            continue
        if fcfg["doc_carteira"] and not _flag_doc_on(f.tem_carteira_pesca):
            continue
        if fcfg["doc_caf"] and not _flag_doc_on(f.tem_caf):
            continue

        if busca:
            nome_l = nome.lower()
            if busca not in nome_l and not (busca_digits and busca_digits in cpf):
                continue

        out.append(
            {
                "nome": nome,
                "cpf": cpf,
                "telefone": tel,
                "municipio": mun_reap or mun_defeso,
                "endereco": endereco_defeso_relatorio(f),
                "parcelas": parcelas_para_relatorio(f.parcelas_recebidas or ""),
                "entrada_confirmada": ent,
                "status": st,
                "atualizado_em": str(f.atualizado_em or f.criado_em or ""),
                "uf": str(f.uf or "").strip().upper()[:2],
            }
        )

    if fcfg["ordenar"] == "recente":
        out.sort(
            key=lambda r: str(r.get("atualizado_em") or ""),
            reverse=True,
        )
    else:
        out.sort(key=lambda r: str(r.get("nome") or "").lower())
    return out


def salvar_html_defeso(html_text: str, *, nome_arquivo: str) -> Path:
    path = pasta_relatorios() / nome_arquivo
    path.write_text(html_text, encoding="utf-8")
    return path
