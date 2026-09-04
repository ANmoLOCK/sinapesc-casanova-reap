"""Importa nome/CPF (e opcionalmente município/telefone) de PDF, XLS/XLSX, TXT/CSV.

Evita estourar cota do Sheets: o parsing é local; a gravação usa
``ConsultaRgpService.upsert_lote_batch`` (poucas chamadas à API).
"""

from __future__ import annotations

import csv
import io
import re
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Tuple

from ui.formatters import format_nome, normalize_cpf

# (nome, cpf, municipio, telefone)
LoteItem = Tuple[str, str, str, str]

_CPF_MASK = re.compile(
    r"(?<!\d)(\d{3}\.?\d{3}\.?\d{3}-?\d{2})(?!\d)"
)
_EXT_OK = {".txt", ".csv", ".pdf", ".xls", ".xlsx"}


def _cell_str(v: Any) -> str:
    if v is None:
        return ""
    if isinstance(v, float):
        # planilha: CPF como número 9545332590.0
        if v == int(v) and abs(v) < 1e15:
            return str(int(v))
        return str(v).strip()
    if isinstance(v, int):
        return str(v)
    return str(v).strip()


def _pick_cols(header: Sequence[str]) -> Dict[str, int]:
    """Mapeia índices por nome de coluna (pt/en)."""
    idx: Dict[str, int] = {}
    aliases = {
        "nome": ("nome", "name", "pescador", "associado", "socio", "sócio"),
        "cpf": ("cpf", "documento", "doc"),
        "municipio": ("municipio", "município", "cidade", "localidade", "mun"),
        "telefone": (
            "telefone",
            "fone",
            "celular",
            "whatsapp",
            "numero",
            "número",
            "tel",
            "contato",
        ),
    }
    for i, raw in enumerate(header):
        key = re.sub(r"[^a-z0-9áéíóúãõâêôç]", "", (raw or "").strip().lower())
        key_ascii = (
            key.replace("á", "a")
            .replace("é", "e")
            .replace("í", "i")
            .replace("ó", "o")
            .replace("ú", "u")
            .replace("ã", "a")
            .replace("õ", "o")
            .replace("â", "a")
            .replace("ê", "e")
            .replace("ô", "o")
            .replace("ç", "c")
        )
        for field, names in aliases.items():
            if field in idx:
                continue
            if key_ascii in names or key in names:
                idx[field] = i
    return idx


def _row_from_cells(cells: Sequence[str], colmap: Optional[Dict[str, int]] = None) -> Optional[LoteItem]:
    cells = [_cell_str(c) for c in cells]
    if not any(cells):
        return None

    nome = mun = tel = cpf_raw = ""

    if colmap and ("nome" in colmap or "cpf" in colmap):
        if "nome" in colmap and colmap["nome"] < len(cells):
            nome = cells[colmap["nome"]]
        if "cpf" in colmap and colmap["cpf"] < len(cells):
            cpf_raw = cells[colmap["cpf"]]
        if "municipio" in colmap and colmap["municipio"] < len(cells):
            mun = cells[colmap["municipio"]]
        if "telefone" in colmap and colmap["telefone"] < len(cells):
            tel = cells[colmap["telefone"]]
    else:
        # Heurística: célula com 11 dígitos (após normalize) = CPF;
        # primeira célula textual longa = nome; resto mun/tel.
        cpf_i = -1
        for i, c in enumerate(cells):
            d = normalize_cpf(c)
            if len(d) == 11:
                cpf_i = i
                cpf_raw = c
                break
        if cpf_i < 0:
            # tenta achar CPF mascarado dentro da célula
            for i, c in enumerate(cells):
                m = _CPF_MASK.search(c)
                if m:
                    cpf_i = i
                    cpf_raw = m.group(1)
                    # se a célula misturou nome+cpf
                    before = c[: m.start()].strip(" -|;,\t")
                    if before and len(before) > 3:
                        nome = before
                    break
        if cpf_i < 0:
            return None
        if not nome:
            for i, c in enumerate(cells):
                if i == cpf_i:
                    continue
                if re.search(r"[A-Za-zÀ-ÿ]", c) and len(c) >= 3:
                    nome = c
                    break
        extras = [cells[i] for i in range(len(cells)) if i != cpf_i and cells[i] != nome]
        for ex in extras:
            digits = re.sub(r"\D", "", ex)
            if len(digits) >= 8 and not mun and not re.search(r"[A-Za-zÀ-ÿ]{3,}", ex):
                tel = tel or ex
            elif re.search(r"[A-Za-zÀ-ÿ]", ex) and not mun:
                mun = ex
            elif digits and not tel:
                tel = ex

    cpf = normalize_cpf(cpf_raw)
    nome = format_nome(nome) if nome else ""
    if len(cpf) != 11:
        return None
    if not nome:
        nome = f"CPF {cpf}"
    return (nome, cpf, (mun or "").strip(), (tel or "").strip())


def parse_texto_lote(raw: str) -> Tuple[List[LoteItem], List[str]]:
    """TXT/CSV colado ou lido de arquivo. Aceita ; , tab ou espaços."""
    itens: List[LoteItem] = []
    erros: List[str] = []
    if not (raw or "").strip():
        return itens, ["Arquivo/texto vazio."]

    # Detecta CSV com cabeçalho
    sample = raw[:4096]
    try:
        dialect = csv.Sniffer().sniff(sample, delimiters=";,\t|")
        delim = dialect.delimiter
    except csv.Error:
        delim = ";" if sample.count(";") >= sample.count(",") else ","

    reader = csv.reader(io.StringIO(raw), delimiter=delim)
    rows = [list(r) for r in reader]
    if not rows:
        return itens, ["Nenhuma linha."]

    colmap: Optional[Dict[str, int]] = None
    start = 0
    first = [_cell_str(c) for c in rows[0]]
    joined = " ".join(first).lower()
    if "cpf" in joined or "nome" in joined:
        colmap = _pick_cols(first)
        start = 1

    vistos: set[str] = set()
    for i, row in enumerate(rows[start:], start=start + 1):
        item = _row_from_cells(row, colmap)
        if not item:
            # linha em branco
            if any(_cell_str(c) for c in row):
                erros.append(f"Linha {i}: sem nome+CPF válido.")
            continue
        nome, cpf, mun, tel = item
        if cpf in vistos:
            erros.append(f"Linha {i}: CPF {cpf} duplicado no arquivo (ignorado).")
            continue
        vistos.add(cpf)
        itens.append((nome, cpf, mun, tel))

    # Fallback: linhas livres com CPF no meio do texto
    if not itens:
        for i, line in enumerate(raw.splitlines(), start=1):
            line = line.strip()
            if not line or line.lower().startswith("nome"):
                continue
            m = _CPF_MASK.search(line)
            if not m:
                continue
            cpf = normalize_cpf(m.group(1))
            if len(cpf) != 11 or cpf in vistos:
                continue
            before = line[: m.start()].strip(" -|;,\t")
            after = line[m.end() :].strip(" -|;,\t")
            nome = format_nome(before) if before else f"CPF {cpf}"
            mun = tel = ""
            if after:
                parts = re.split(r"[;|\t]+", after)
                parts = [p.strip() for p in parts if p.strip()]
                if parts:
                    if re.search(r"[A-Za-zÀ-ÿ]", parts[0]):
                        mun = parts[0]
                        if len(parts) > 1:
                            tel = parts[1]
                    else:
                        tel = parts[0]
            vistos.add(cpf)
            itens.append((nome, cpf, mun, tel))

    return itens, erros


def parse_pdf_lote(path: Path) -> Tuple[List[LoteItem], List[str]]:
    try:
        import pymupdf as fitz
    except ImportError as exc:  # pragma: no cover
        raise ValueError("Biblioteca pymupdf não instalada.") from exc

    doc = fitz.open(str(path))
    try:
        chunks: List[str] = []
        for page in doc:
            chunks.append(page.get_text("text") or "")
        text = "\n".join(chunks)
    finally:
        doc.close()

    itens, erros = parse_texto_lote(text)
    if itens:
        return itens, erros

    # PDF sem delimitadores: varre CPF + texto à esquerda na mesma linha
    vistos: set[str] = set()
    out: List[LoteItem] = []
    for line in text.splitlines():
        line = line.strip()
        if not line:
            continue
        for m in _CPF_MASK.finditer(line):
            cpf = normalize_cpf(m.group(1))
            if len(cpf) != 11 or cpf in vistos:
                continue
            before = line[: m.start()].strip(" -|;,\t.")
            # remove ruído de números isolados no início
            before = re.sub(r"^[\d\s./-]+", "", before).strip()
            nome = format_nome(before) if len(before) >= 3 else f"CPF {cpf}"
            vistos.add(cpf)
            out.append((nome, cpf, "", ""))
    if not out:
        erros.append("PDF sem pares nome/CPF reconhecíveis.")
    return out, erros


def parse_xlsx_lote(path: Path) -> Tuple[List[LoteItem], List[str]]:
    try:
        import openpyxl
    except ImportError as exc:  # pragma: no cover
        raise ValueError(
            "Biblioteca openpyxl não instalada. Atualize o EXE / requirements."
        ) from exc

    wb = openpyxl.load_workbook(str(path), read_only=True, data_only=True)
    try:
        ws = wb.active
        matrix: List[List[str]] = []
        for row in ws.iter_rows(values_only=True):
            matrix.append([_cell_str(c) for c in (row or ())])
    finally:
        wb.close()

    if not matrix:
        return [], ["Planilha vazia."]

    # Reusa parser de texto via CSV virtual
    buf = io.StringIO()
    writer = csv.writer(buf, delimiter=";")
    for row in matrix:
        writer.writerow(row)
    return parse_texto_lote(buf.getvalue())


def parse_xls_lote(path: Path) -> Tuple[List[LoteItem], List[str]]:
    try:
        import xlrd
    except ImportError as exc:  # pragma: no cover
        raise ValueError(
            "Biblioteca xlrd não instalada (necessária para .xls). "
            "Salve como .xlsx/.csv ou atualize o EXE."
        ) from exc

    book = xlrd.open_workbook(str(path))
    sheet = book.sheet_by_index(0)
    matrix: List[List[str]] = []
    for r in range(sheet.nrows):
        matrix.append([_cell_str(sheet.cell_value(r, c)) for c in range(sheet.ncols)])
    if not matrix:
        return [], ["Planilha vazia."]
    buf = io.StringIO()
    writer = csv.writer(buf, delimiter=";")
    for row in matrix:
        writer.writerow(row)
    return parse_texto_lote(buf.getvalue())


def parse_arquivo_lote(path: str | Path) -> Dict[str, Any]:
    """Detecta extensão e devolve {itens, erros, origem, total}."""
    p = Path(path).expanduser()
    if not p.is_file():
        raise ValueError(f"Arquivo não encontrado: {p}")
    ext = p.suffix.lower()
    if ext not in _EXT_OK:
        raise ValueError(
            f"Formato não suportado ({ext or 'sem extensão'}). "
            "Use PDF, XLS, XLSX, TXT ou CSV."
        )

    if ext in (".txt", ".csv"):
        raw = p.read_text(encoding="utf-8-sig", errors="replace")
        itens, erros = parse_texto_lote(raw)
        origem = "texto"
    elif ext == ".pdf":
        itens, erros = parse_pdf_lote(p)
        origem = "pdf"
    elif ext == ".xlsx":
        itens, erros = parse_xlsx_lote(p)
        origem = "xlsx"
    else:  # .xls
        itens, erros = parse_xls_lote(p)
        origem = "xls"

    return {
        "itens": itens,
        "erros": erros[:80],
        "origem": origem,
        "arquivo": str(p),
        "nome_arquivo": p.name,
        "total": len(itens),
    }


def itens_para_dicts(itens: Sequence[LoteItem]) -> List[Dict[str, str]]:
    return [
        {"nome": n, "cpf": c, "municipio": m, "telefone": t}
        for n, c, m, t in itens
    ]
