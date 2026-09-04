"""Função 3 — Exportar Consulta RGP (CSV + HTML para imprimir/PDF)."""

from __future__ import annotations

import csv
import html
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Set

from controle.auditoria import parse_em
from controle.backup import backup_root
from controle.consulta_rgp import normalize_situacao, situacao_match_filtro
from controle.relatorio import logo_data_uri
from ui.formatters import format_cpf, format_nome, only_digits


# Colunas disponíveis no HTML (ordem de exibição)
COLUNAS_HTML: List[tuple[str, str]] = [
    ("nome", "Nome"),
    ("cpf", "CPF"),
    ("municipio", "Município"),
    ("telefone", "Telefone"),
    ("situacao", "Situação RGP"),
    ("govbr_senha", "Senha Gov.br"),
    ("ultima_consulta", "Última consulta"),
    ("observacao", "Observação"),
    ("email", "E-mail"),
    ("uf", "UF"),
    ("codigo_rgp", "Código RGP"),
]

COLUNAS_PADRAO_GERAL = ["nome", "cpf", "municipio", "telefone", "situacao", "govbr_senha"]
COLUNAS_PADRAO_EXPORT = [
    "nome",
    "cpf",
    "telefone",
    "municipio",
    "situacao",
    "ultima_consulta",
    "observacao",
]


def pasta_export_consulta() -> Path:
    dest = backup_root() / "consulta-rgp-export"
    dest.mkdir(parents=True, exist_ok=True)
    return dest


def _parse_data_filtro(valor: str, *, fim_do_dia: bool = False) -> Optional[datetime]:
    text = (valor or "").strip()
    if not text:
        return None
    dt = parse_em(text)
    if dt is None:
        for fmt in (
            "%Y-%m-%d %H:%M",
            "%d/%m/%Y %H:%M",
            "%Y-%m-%d",
            "%d/%m/%Y",
            "%Y-%m-%dT%H:%M",
        ):
            try:
                piece = text[:19] if "T" in fmt or " " in fmt else text[:10]
                dt = datetime.strptime(piece, fmt)
                break
            except ValueError:
                continue
    if dt is None:
        return None
    if fim_do_dia and dt.hour == 0 and dt.minute == 0 and dt.second == 0 and len(text) <= 10:
        return dt.replace(hour=23, minute=59, second=59)
    return dt


def _parse_stamp_registro(valor: str) -> Optional[datetime]:
    """Aceita stamps gravados na planilha (com/sem segundos, ISO ou BR)."""
    return _parse_data_filtro(valor, fim_do_dia=False)


def _norm_list(raw: Any) -> List[str]:
    if raw is None:
        return []
    if isinstance(raw, str):
        text = raw.strip()
        if not text:
            return []
        if text.startswith("["):
            import json

            try:
                raw = json.loads(text)
            except json.JSONDecodeError:
                return [x.strip() for x in text.split(",") if x.strip()]
        else:
            return [x.strip() for x in text.split(",") if x.strip()]
    if isinstance(raw, (list, tuple, set)):
        return [str(x).strip() for x in raw if str(x).strip()]
    return [str(raw).strip()] if str(raw).strip() else []


def filtrar_registros_export(
    registros: Sequence[Any],
    *,
    municipio: str = "",
    situacao: str = "",
    ultima_de: str = "",
    ultima_ate: str = "",
    ids: Optional[Sequence[Any]] = None,
    busca: str = "",
    municipios: Optional[Sequence[str]] = None,
    situacoes: Optional[Sequence[str]] = None,
    com_senha: str = "",
) -> List[Any]:
    """Filtra registros para export/relatório.

    ``com_senha``: "" | "any" | "com" | "sem"
    """
    mun_q = (municipio or "").strip().lower()
    munis = [m.lower() for m in _norm_list(municipios)]
    sit_q = (situacao or "").strip()
    sits = _norm_list(situacoes)
    idset: Set[str] = {str(x).strip() for x in (ids or []) if str(x).strip()}
    q = (busca or "").strip().lower()
    digits = only_digits(busca) if busca else ""
    senha_mode = (com_senha or "").strip().lower()
    if senha_mode in ("", "any", "todas", "todos"):
        senha_mode = ""

    dt_de = _parse_data_filtro(ultima_de, fim_do_dia=False)
    dt_ate = _parse_data_filtro(ultima_ate, fim_do_dia=True)

    out: List[Any] = []
    for r in registros:
        if idset:
            rid = str(getattr(r, "id", "") or "").strip()
            if rid not in idset:
                continue

        if munis:
            mun = str(getattr(r, "municipio", "") or "").strip().lower()
            if not any(m == mun or m in mun for m in munis):
                continue
        elif mun_q:
            mun = str(getattr(r, "municipio", "") or "").strip().lower()
            if mun_q not in mun:
                continue

        if sits:
            sit_val = getattr(r, "situacao_rgp", "") or ""
            if not any(situacao_match_filtro(sit_val, s) for s in sits):
                continue
        elif sit_q and not situacao_match_filtro(getattr(r, "situacao_rgp", "") or "", sit_q):
            continue

        ultima = _parse_stamp_registro(str(getattr(r, "ultima_consulta_em", "") or ""))
        if dt_de and (ultima is None or ultima < dt_de):
            continue
        if dt_ate and (ultima is None or ultima > dt_ate):
            continue

        if q or (digits and len(digits) >= 3):
            blob = " ".join(
                str(getattr(r, k, "") or "").lower()
                for k in ("nome", "cpf", "telefone", "municipio", "observacao", "email")
            )
            ok = bool(q and q in blob)
            if not ok and digits and len(digits) >= 3:
                ok = digits in only_digits(str(getattr(r, "cpf", "") or ""))
            if not ok:
                continue

        if senha_mode in ("com", "com_senha", "sim"):
            if not str(getattr(r, "govbr_senha", "") or "").strip():
                continue
        elif senha_mode in ("sem", "sem_senha", "nao", "não"):
            if str(getattr(r, "govbr_senha", "") or "").strip():
                continue

        out.append(r)

    out.sort(
        key=lambda r: (
            format_nome(str(getattr(r, "nome", "") or "")).lower(),
            str(getattr(r, "cpf", "") or ""),
        )
    )
    return out


def _celula(reg: Any, col: str, *, senha_fallback: str = "") -> str:
    if col == "nome":
        return format_nome(str(getattr(reg, "nome", "") or "")) or "—"
    if col == "cpf":
        return format_cpf(str(getattr(reg, "cpf", "") or "")) or "—"
    if col == "municipio":
        return str(getattr(reg, "municipio", "") or "") or "—"
    if col == "telefone":
        return str(getattr(reg, "telefone", "") or "") or "—"
    if col == "situacao":
        return normalize_situacao(getattr(reg, "situacao_rgp", "") or "") or "—"
    if col == "govbr_senha":
        senha = str(getattr(reg, "govbr_senha", "") or "").strip() or senha_fallback
        return senha or "—"
    if col == "ultima_consulta":
        return str(getattr(reg, "ultima_consulta_em", "") or "") or "—"
    if col == "observacao":
        return str(getattr(reg, "observacao", "") or "") or "—"
    if col == "email":
        return str(getattr(reg, "email", "") or "") or "—"
    if col == "uf":
        return str(getattr(reg, "uf", "") or "") or "—"
    if col == "codigo_rgp":
        return str(getattr(reg, "codigo_rgp", "") or "") or "—"
    return "—"


def _resolver_colunas(colunas: Optional[Sequence[str]], *, modo_geral: bool) -> List[str]:
    allowed = {k for k, _ in COLUNAS_HTML}
    raw = _norm_list(colunas)
    if not raw:
        return list(COLUNAS_PADRAO_GERAL if modo_geral else COLUNAS_PADRAO_EXPORT)
    out = [c for c in raw if c in allowed]
    return out or list(COLUNAS_PADRAO_GERAL if modo_geral else COLUNAS_PADRAO_EXPORT)


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
        "govbrSenha",
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
                str(getattr(r, "govbr_senha", "") or ""),
            ]
        )
    return rows


def _html_export(
    regs: Sequence[Any],
    *,
    org_short: str,
    org_full: str,
    filtros: Dict[str, Any],
    govbr_senha: str = "",
    modo_geral: bool = False,
    colunas: Optional[Sequence[str]] = None,
    auto_print: bool = True,
) -> str:
    logo = logo_data_uri()
    logo_tag = f'<img class="logo" src="{logo}" alt="">' if logo else ""
    cols = _resolver_colunas(colunas, modo_geral=modo_geral)
    labels = {k: lab for k, lab in COLUNAS_HTML}

    filtro_bits: List[str] = []
    for k, label in (
        ("escopo", "Escopo"),
        ("municipio", "Município"),
        ("municipios", "Municípios"),
        ("situacao", "Situação"),
        ("situacoes", "Situações"),
        ("busca", "Busca"),
        ("ultima_de", "Última consulta de"),
        ("ultima_ate", "até"),
        ("com_senha", "Senha Gov.br"),
        ("ids_count", "Selecionados"),
    ):
        v = filtros.get(k)
        if v is None or v == "" or v == []:
            continue
        if isinstance(v, (list, tuple)):
            text = ", ".join(str(x) for x in v if str(x).strip())
        else:
            text = str(v).strip()
        if not text:
            continue
        if k == "com_senha":
            text = {"com": "somente com senha", "sem": "somente sem senha"}.get(text, text)
        if k == "ids_count":
            text = f"{text} registro(s)"
        filtro_bits.append(f"{label}: {text}")
    filtro_bits.append(f"Colunas: {', '.join(labels.get(c, c) for c in cols)}")
    filtro_txt = " · ".join(filtro_bits) if filtro_bits else "Sem filtros (lista completa)"

    senha_modulo = str(govbr_senha or "").strip()
    senha_bloco = ""
    if "govbr_senha" in cols:
        senha_bloco = (
            '<p class="gov"><strong>Senha Gov.br:</strong> '
            "cada sócio tem a própria senha (quando cadastrada).</p>"
        )

    thead = "".join(f"<th>{html.escape(labels.get(c, c))}</th>" for c in cols)
    trs = []
    for r in regs:
        cells = "".join(
            f"<td>{html.escape(_celula(r, c, senha_fallback=senha_modulo))}</td>" for c in cols
        )
        trs.append(f"<tr>{cells}</tr>")
    colspan = max(1, len(cols))
    body = "\n".join(trs) if trs else f'<tr><td colspan="{colspan}">Nenhum registro com os filtros escolhidos.</td></tr>'
    gerado = datetime.now().strftime("%d/%m/%Y %H:%M")
    titulo = "Relatório geral" if modo_geral else "exportação"
    print_script = (
        '<script>window.addEventListener("load", () => setTimeout(() => window.print(), 400));</script>'
        if auto_print
        else ""
    )
    # filtro_txt é texto puro — escapar só aqui (evita double-escape)
    return f"""<!DOCTYPE html>
<html lang="pt-BR"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Consulta RGP — {html.escape(titulo)}</title>
<style>
  body {{ font-family: Segoe UI, system-ui, sans-serif; color: #0A2F52; margin: 24px; }}
  .head {{ display:flex; gap:16px; align-items:center; margin-bottom: 12px; }}
  .logo {{ height: 56px; }}
  h1 {{ margin: 0; font-size: 20px; }}
  .sub {{ color:#5A7388; font-size: 12px; margin: 4px 0 16px; }}
  .gov {{ background:#E7F1F7; border:1px solid #D5E4EE; padding:8px 12px; font-size:13px; margin: 0 0 14px; }}
  table {{ width:100%; border-collapse: collapse; font-size: 12px; }}
  th, td {{ border: 1px solid #D5E4EE; padding: 6px 8px; text-align: left; vertical-align: top; }}
  th {{ background: #E7F1F7; }}
  tr:nth-child(even) td {{ background: #F8FBFD; }}
  @media print {{
    body {{ margin: 12px; }}
    .gov {{ -webkit-print-color-adjust: exact; print-color-adjust: exact; }}
    tr:nth-child(even) td {{ -webkit-print-color-adjust: exact; print-color-adjust: exact; }}
  }}
</style></head><body>
<div class="head">{logo_tag}<div>
  <h1>{html.escape(org_short)} — Consulta RGP ({html.escape(titulo)})</h1>
  <div class="sub">{html.escape(org_full)}</div>
</div></div>
{senha_bloco}
<p class="sub">{html.escape(filtro_txt)} · {len(regs)} registro(s) · gerado em {gerado}</p>
<table>
<thead><tr>
  {thead}
</tr></thead>
<tbody>
{body}
</tbody>
</table>
{print_script}
</body></html>"""


def exportar_consulta_rgp(
    registros: Sequence[Any],
    *,
    municipio: str = "",
    situacao: str = "",
    ultima_de: str = "",
    ultima_ate: str = "",
    ids: Optional[Sequence[Any]] = None,
    busca: str = "",
    municipios: Optional[Sequence[str]] = None,
    situacoes: Optional[Sequence[str]] = None,
    com_senha: str = "",
    colunas: Optional[Sequence[str]] = None,
    auto_print: bool = True,
    org_short: str = "Sinapesc",
    org_full: str = "",
    formatos: Optional[Sequence[str]] = None,
    govbr_senha: str = "",
    modo_geral: bool = False,
    escopo: str = "",
) -> Dict[str, Any]:
    """Gera CSV e/ou HTML. Retorna paths e contagem."""
    formatos = [str(f).lower() for f in (formatos or ("csv", "html"))]
    if modo_geral:
        formatos = ["html"]
    filtrados = filtrar_registros_export(
        registros,
        municipio=municipio,
        situacao=situacao,
        ultima_de=ultima_de,
        ultima_ate=ultima_ate,
        ids=ids,
        busca=busca,
        municipios=municipios,
        situacoes=situacoes,
        com_senha=com_senha,
    )
    cols = _resolver_colunas(colunas, modo_geral=modo_geral)
    stamp = datetime.now().strftime("%Y-%m-%d_%H%M")
    pasta = pasta_export_consulta()
    munis = _norm_list(municipios)
    sits = _norm_list(situacoes)
    id_list = [str(x).strip() for x in (ids or []) if str(x).strip()]
    out: Dict[str, Any] = {
        "total": len(filtrados),
        "csv_path": "",
        "html_path": "",
        "modo_geral": bool(modo_geral),
        "colunas": cols,
        "filtros": {
            "escopo": (escopo or "").strip(),
            "municipio": municipio or "",
            "municipios": munis,
            "situacao": situacao or "",
            "situacoes": sits,
            "busca": (busca or "").strip(),
            "ultima_de": ultima_de or "",
            "ultima_ate": ultima_ate or "",
            "com_senha": (com_senha or "").strip(),
            "ids_count": len(id_list) if id_list else "",
        },
    }
    if "csv" in formatos and not modo_geral:
        csv_path = pasta / f"consulta-rgp-{stamp}.csv"
        with csv_path.open("w", encoding="utf-8-sig", newline="") as fh:
            writer = csv.writer(fh)
            for row in _rows_csv(filtrados):
                writer.writerow(row)
        out["csv_path"] = str(csv_path)
    if "html" in formatos:
        prefix = "consulta-rgp-geral" if modo_geral else "consulta-rgp"
        html_path = pasta / f"{prefix}-{stamp}.html"
        html_path.write_text(
            _html_export(
                filtrados,
                org_short=org_short,
                org_full=org_full,
                filtros=out["filtros"],
                govbr_senha=govbr_senha,
                modo_geral=modo_geral,
                colunas=cols,
                auto_print=bool(auto_print),
            ),
            encoding="utf-8",
        )
        out["html_path"] = str(html_path)
    label = "Relatório HTML" if modo_geral else "Exportados"
    out["mensagem"] = (
        f"{label}: {len(filtrados)} registro(s)"
        + (f" · CSV: {Path(out['csv_path']).name}" if out["csv_path"] else "")
        + (f" · HTML: {Path(out['html_path']).name}" if out["html_path"] else "")
    )
    return out
