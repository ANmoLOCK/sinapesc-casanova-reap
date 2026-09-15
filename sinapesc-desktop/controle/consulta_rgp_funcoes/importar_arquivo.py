"""Importa nome/CPF (e opcionalmente município/telefone) de PDF, XLS/XLSX, TXT/CSV.

Evita estourar cota do Sheets: o parsing é local; a gravação usa
``ConsultaRgpService.upsert_lote_batch`` (poucas chamadas à API).

Captura **nome + CPF juntos** em formatos comuns:
  Nome;CPF · Nome,CPF · Nome\\tCPF · «Nome Completo 095.453.325-90»
  «09545332590 Nome Completo» · colunas Excel invertidas · PDF linha a linha
"""

from __future__ import annotations

import csv
import io
import re
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Tuple

from ui.formatters import cpf_digitos_validos, format_nome, normalize_cpf

# (nome, cpf, municipio, telefone)
LoteItem = Tuple[str, str, str, str]

# Máscara com ou sem pontuação (095.453.325-90 ou 09545332590)
_CPF_MASK = re.compile(
    r"(?<!\d)(\d{3}\.?\d{3}\.?\d{3}-?\d{2})(?!\d)"
)
_CPF_DIGITS = re.compile(r"(?<!\d)(\d{11})(?!\d)")
_EXT_OK = {".txt", ".csv", ".pdf", ".xls", ".xlsx"}
_PLACEHOLDER_NOME = re.compile(r"^cpf\s*\d", re.I)


def _cell_str(v: Any) -> str:
    if v is None:
        return ""
    if isinstance(v, float):
        # planilha: CPF como número 9545332590.0 → preserva dígitos
        if v == int(v) and abs(v) < 1e15:
            return str(int(v))
        return str(v).strip()
    if isinstance(v, int):
        return str(v)
    return str(v).strip()


def _is_placeholder_nome(nome: str) -> bool:
    n = (nome or "").strip()
    if not n:
        return True
    if _PLACEHOLDER_NOME.match(n):
        return True
    # só dígitos / pontuação = não é nome
    if not re.search(r"[A-Za-zÀ-ÿ]", n):
        return True
    return False


def _clean_nome(raw: str) -> str:
    text = (raw or "").strip(" -|;,\t.\"'")
    text = re.sub(r"\s+", " ", text)
    # remove CPF residual no meio do nome
    text = _CPF_MASK.sub(" ", text)
    text = re.sub(r"\s+", " ", text).strip(" -|;,\t.")
    if _is_placeholder_nome(text):
        return ""
    return format_nome(text)


def _find_cpf_spans(text: str) -> List[re.Match[str]]:
    """CPFs mascarados ou 11 dígitos; evita capturas sobrepostas."""
    found: List[re.Match[str]] = []
    covered: set[int] = set()
    for rx in (_CPF_MASK, _CPF_DIGITS):
        for m in rx.finditer(text):
            digits = normalize_cpf(m.group(1))
            if len(digits) != 11:
                continue
            # evita overlap
            if any(i in covered for i in range(m.start(), m.end())):
                continue
            covered.update(range(m.start(), m.end()))
            found.append(m)
    found.sort(key=lambda m: m.start())
    return found


def _pick_cols(header: Sequence[str]) -> Dict[str, int]:
    """Mapeia índices por nome de coluna (pt/en)."""
    idx: Dict[str, int] = {}
    aliases = {
        "nome": ("nome", "name", "pescador", "associado", "socio", "sócio", "beneficiario", "beneficiário"),
        "cpf": ("cpf", "documento", "doc", "cic"),
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


def _pick_best_cpf_match(text: str) -> Optional[re.Match[str]]:
    """Escolhe o CPF certo na linha (evita pegar telefone 11 dígitos no fim)."""
    spans = _find_cpf_spans(text)
    if not spans:
        return None
    scored: List[Tuple[int, re.Match[str]]] = []
    for m in spans:
        digits = normalize_cpf(m.group(1))
        if len(digits) != 11:
            continue
        score = 0
        raw = m.group(1)
        if "." in raw or "-" in raw:
            score += 5  # máscara típica de CPF
        if cpf_digitos_validos(digits):
            score += 10
        # telefone costuma vir depois de ; e no final
        after = text[m.end() : m.end() + 8]
        before = text[max(0, m.start() - 8) : m.start()]
        if re.search(r"[A-Za-zÀ-ÿ]", before):
            score += 2  # texto (nome) antes → bom sinal
        if after.strip().startswith("(") or "tel" in before.lower():
            score -= 3
        scored.append((score, m))
    if not scored:
        return None
    scored.sort(key=lambda t: (t[0], -t[1].start()), reverse=True)
    best_score, best = scored[0]
    # se ninguém passou DV e o melhor é fraco, ainda assim devolve (usuário pode ter CPF inválido)
    return best


def _split_nome_cpf_from_text(text: str) -> Optional[LoteItem]:
    """Extrai nome+CPF de uma linha livre (TXT/PDF).

    Aceita CPF no fim («Maria 095…») ou no início («095… Maria»).
    """
    text = (text or "").strip()
    if not text:
        return None
    low = text.lower()
    if low.startswith("nome") and "cpf" in low and len(text) < 40:
        return None  # cabeçalho

    m = _pick_best_cpf_match(text)
    if not m:
        return None
    cpf = normalize_cpf(m.group(1))
    if len(cpf) != 11:
        return None

    before = text[: m.start()].strip(" -|;,\t.\"'")
    after = text[m.end() :].strip(" -|;,\t.\"'")

    # Partes extras após o CPF → mun / tel
    mun = tel = ""
    nome = ""

    if not _is_placeholder_nome(before):
        # Nome antes do CPF (mais comum)
        # Se before tem ; ou tab, primeira parte = nome
        parts = re.split(r"[;|\t]+", before)
        parts = [p.strip() for p in parts if p.strip()]
        if parts:
            # se a 1ª parte parece só número, pular
            if re.search(r"[A-Za-zÀ-ÿ]", parts[0]):
                nome = parts[0]
                rest = parts[1:]
            else:
                rest = parts
            for ex in rest:
                digits = re.sub(r"\D", "", ex)
                if len(digits) >= 8 and not re.search(r"[A-Za-zÀ-ÿ]{3,}", ex):
                    tel = tel or ex
                elif re.search(r"[A-Za-zÀ-ÿ]", ex) and not mun:
                    mun = ex
        # Município/telefone depois do CPF
        if after:
            after_parts = re.split(r"[;|\t]+", after)
            after_parts = [p.strip() for p in after_parts if p.strip()]
            for ex in after_parts:
                digits = re.sub(r"\D", "", ex)
                if len(digits) >= 8 and not re.search(r"[A-Za-zÀ-ÿ]{3,}", ex):
                    tel = tel or ex
                elif re.search(r"[A-Za-zÀ-ÿ]", ex) and not mun:
                    mun = ex
                elif digits and not tel:
                    tel = ex
    if _is_placeholder_nome(nome) and after:
        # CPF primeiro: «09545332590 Maria da Silva;Casa Nova;(74)…»
        parts = re.split(r"[;|\t]+", after)
        parts = [p.strip() for p in parts if p.strip()]
        if not parts:
            # só espaços: «09545332590 Maria da Silva Casa Nova»
            # pega tudo após CPF como nome até achar telefone longo
            nome_cand = after
            tel_m = re.search(r"(?:\(?\d{2}\)?\s*)?\d{4,5}[-\s]?\d{4}\b", after)
            if tel_m:
                tel = tel_m.group(0)
                nome_cand = after[: tel_m.start()].strip(" -|;,\t")
            nome = nome_cand
        else:
            for p in parts:
                if _is_placeholder_nome(nome) and re.search(r"[A-Za-zÀ-ÿ]", p):
                    # se parece telefone, não
                    d = re.sub(r"\D", "", p)
                    if len(d) >= 8 and not re.search(r"[A-Za-zÀ-ÿ]{3,}", p):
                        tel = tel or p
                    else:
                        nome = p
                elif not mun and re.search(r"[A-Za-zÀ-ÿ]", p) and p != nome:
                    mun = p
                elif not tel:
                    d = re.sub(r"\D", "", p)
                    if len(d) >= 8:
                        tel = p

    nome = _clean_nome(nome)
    if not nome:
        # última chance: qualquer trecho com letras na linha (sem o CPF)
        resto = (before + " " + after).strip()
        resto = _CPF_MASK.sub(" ", resto)
        resto = re.sub(r"\s+", " ", resto).strip()
        nome = _clean_nome(resto)

    if not nome:
        # Não inventar «CPF 000…» — deixa o chamador decidir
        return None

    return (nome, cpf, (mun or "").strip(), (tel or "").strip())


def _row_from_cells(cells: Sequence[str], colmap: Optional[Dict[str, int]] = None) -> Optional[LoteItem]:
    cells = [_cell_str(c) for c in cells]
    if not any(cells):
        return None

    # Uma única célula com texto livre → parser de linha
    non_empty = [c for c in cells if c]
    if len(non_empty) == 1:
        return _split_nome_cpf_from_text(non_empty[0])

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
        # Se a coluna «nome» na verdade tem CPF (planilha invertida)
        if nome and not cpf_raw:
            d = normalize_cpf(nome)
            if len(d) == 11 and _is_placeholder_nome(cpf_raw):
                cpf_raw, nome = nome, cpf_raw
        if cpf_raw and _is_placeholder_nome(nome):
            # tenta achar nome em outras células
            for c in cells:
                if c == cpf_raw:
                    continue
                if re.search(r"[A-Za-zÀ-ÿ]{3,}", c) and len(normalize_cpf(c)) != 11:
                    nome = c
                    break
        cpf = normalize_cpf(cpf_raw)
        nome = _clean_nome(nome)
        if len(cpf) == 11 and nome:
            return (nome, cpf, (mun or "").strip(), (tel or "").strip())
        # fallback: junta a linha
        joined = " ".join(non_empty)
        return _split_nome_cpf_from_text(joined)

    # Heurística sem cabeçalho: achar célula CPF + célula nome
    cpf_i = -1
    for i, c in enumerate(cells):
        d = normalize_cpf(c)
        if len(d) == 11 and (len(re.sub(r"\D", "", c)) >= 10 or _CPF_MASK.search(c)):
            # célula só com CPF (ou CPF+lixo curto)
            if not re.search(r"[A-Za-zÀ-ÿ]{3,}", c) or len(d) == 11:
                if not re.search(r"[A-Za-zÀ-ÿ]{3,}", c):
                    cpf_i = i
                    cpf_raw = c
                    break
    if cpf_i < 0:
        for i, c in enumerate(cells):
            m = _CPF_MASK.search(c)
            if m:
                cpf_i = i
                cpf_raw = m.group(1)
                before = c[: m.start()].strip(" -|;,\t")
                after = c[m.end() :].strip(" -|;,\t")
                if not _is_placeholder_nome(before):
                    nome = before
                elif not _is_placeholder_nome(after):
                    nome = after
                break

    if cpf_i < 0:
        return _split_nome_cpf_from_text(" ".join(non_empty))

    if _is_placeholder_nome(nome):
        for i, c in enumerate(cells):
            if i == cpf_i:
                continue
            if re.search(r"[A-Za-zÀ-ÿ]", c) and len(c) >= 3 and len(normalize_cpf(c)) != 11:
                nome = c
                break

    extras = [cells[i] for i in range(len(cells)) if i != cpf_i and cells[i] != nome]
    for ex in extras:
        digits = re.sub(r"\D", "", ex)
        if len(digits) >= 8 and not mun and not re.search(r"[A-Za-zÀ-ÿ]{3,}", ex):
            tel = tel or ex
        elif re.search(r"[A-Za-zÀ-ÿ]", ex) and not mun and _is_placeholder_nome(nome) is False:
            if ex != nome and not mun:
                mun = mun or ex
        elif digits and not tel:
            tel = ex

    cpf = normalize_cpf(cpf_raw)
    nome = _clean_nome(nome)
    if len(cpf) != 11:
        return None
    if not nome:
        return _split_nome_cpf_from_text(" ".join(non_empty))
    return (nome, cpf, (mun or "").strip(), (tel or "").strip())


def _looks_like_header(row: Sequence[str]) -> bool:
    joined = " ".join(_cell_str(c) for c in row).lower()
    return ("cpf" in joined and "nome" in joined) or joined.strip() in {
        "nome",
        "cpf",
        "nome;cpf",
        "nome,cpf",
    }


def parse_texto_lote(raw: str) -> Tuple[List[LoteItem], List[str]]:
    """TXT/CSV colado ou lido de arquivo. Aceita ; , tab, espaços e CPF↔nome invertido."""
    itens: List[LoteItem] = []
    erros: List[str] = []
    if not (raw or "").strip():
        return itens, ["Arquivo/texto vazio."]

    lines = [ln.strip() for ln in raw.splitlines()]
    # 1) Parser linha a linha (melhor para TXT sem delimitador claro)
    vistos: set[str] = set()
    pending_nome = ""

    for i, line in enumerate(lines, start=1):
        if not line:
            continue
        low = line.lower()
        if low.startswith("nome") and ("cpf" in low or len(line) < 30):
            continue

        item = _split_nome_cpf_from_text(line)
        if item:
            nome, cpf, mun, tel = item
            if cpf in vistos:
                erros.append(f"Linha {i}: CPF {cpf} duplicado (ignorado).")
                continue
            vistos.add(cpf)
            itens.append((nome, cpf, mun, tel))
            pending_nome = ""
            continue

        # Linha só com nome → próxima pode ser só CPF (comum em PDF/TXT)
        if re.search(r"[A-Za-zÀ-ÿ]{3,}", line) and not _find_cpf_spans(line):
            pending_nome = line
            continue
        # Linha só com CPF
        spans = _find_cpf_spans(line)
        if spans and pending_nome:
            cpf = normalize_cpf(spans[0].group(1))
            nome = _clean_nome(pending_nome)
            pending_nome = ""
            if len(cpf) == 11 and nome and cpf not in vistos:
                vistos.add(cpf)
                itens.append((nome, cpf, "", ""))
            continue
        pending_nome = ""

    if itens:
        return itens, erros

    # 2) Fallback CSV (planilhas exportadas)
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
    if _looks_like_header(rows[0]):
        colmap = _pick_cols([_cell_str(c) for c in rows[0]])
        start = 1

    for i, row in enumerate(rows[start:], start=start + 1):
        item = _row_from_cells(row, colmap)
        if not item:
            if any(_cell_str(c) for c in row):
                erros.append(f"Linha {i}: sem nome+CPF válidos juntos.")
            continue
        nome, cpf, mun, tel = item
        if cpf in vistos:
            erros.append(f"Linha {i}: CPF {cpf} duplicado no arquivo (ignorado).")
            continue
        vistos.add(cpf)
        itens.append((nome, cpf, mun, tel))

    if not itens and not erros:
        erros.append("Nenhum par nome+CPF encontrado. Use Nome e CPF na mesma linha.")
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
            # text + blocks ajuda a manter nome perto do CPF
            chunks.append(page.get_text("text") or "")
    finally:
        doc.close()

    text = "\n".join(chunks)
    itens, erros = parse_texto_lote(text)
    if itens:
        return itens, erros

    # PDF tabular: tenta também por blocos
    erros.append("PDF sem pares nome/CPF reconhecíveis na mesma linha.")
    return [], erros


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

    # Parse direto das células (não só CSV) — preserva colunas Nome|CPF
    itens: List[LoteItem] = []
    erros: List[str] = []
    colmap: Optional[Dict[str, int]] = None
    start = 0
    if matrix and _looks_like_header(matrix[0]):
        colmap = _pick_cols(matrix[0])
        start = 1
    vistos: set[str] = set()
    for i, row in enumerate(matrix[start:], start=start + 1):
        item = _row_from_cells(row, colmap)
        if not item:
            # tenta juntar a linha
            item = _split_nome_cpf_from_text(" ".join(c for c in row if c))
        if not item:
            if any(row):
                erros.append(f"Linha {i}: sem nome+CPF válidos.")
            continue
        nome, cpf, mun, tel = item
        if cpf in vistos:
            continue
        vistos.add(cpf)
        itens.append((nome, cpf, mun, tel))
    if not itens:
        # fallback texto
        buf = io.StringIO()
        writer = csv.writer(buf, delimiter=";")
        for row in matrix:
            writer.writerow(row)
        return parse_texto_lote(buf.getvalue())
    return itens, erros


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

    # Reusa o caminho XLSX (mesma lógica de colunas)
    itens: List[LoteItem] = []
    erros: List[str] = []
    colmap: Optional[Dict[str, int]] = None
    start = 0
    if matrix and _looks_like_header(matrix[0]):
        colmap = _pick_cols(matrix[0])
        start = 1
    vistos: set[str] = set()
    for i, row in enumerate(matrix[start:], start=start + 1):
        item = _row_from_cells(row, colmap) or _split_nome_cpf_from_text(
            " ".join(c for c in row if c)
        )
        if not item:
            if any(row):
                erros.append(f"Linha {i}: sem nome+CPF válidos.")
            continue
        nome, cpf, mun, tel = item
        if cpf in vistos:
            continue
        vistos.add(cpf)
        itens.append((nome, cpf, mun, tel))
    return itens, erros


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
        # Alguns TXT vêm em Latin-1
        if "\ufffd" in raw:
            raw = p.read_text(encoding="latin-1", errors="replace")
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

    # Rejeita itens sem nome real
    limpos: List[LoteItem] = []
    for nome, cpf, mun, tel in itens:
        if _is_placeholder_nome(nome):
            erros.append(f"CPF {cpf}: nome não encontrado na mesma linha.")
            continue
        limpos.append((nome, cpf, mun, tel))

    return {
        "itens": limpos,
        "erros": erros[:80],
        "origem": origem,
        "arquivo": str(p),
        "nome_arquivo": p.name,
        "total": len(limpos),
    }


def itens_para_dicts(itens: Sequence[LoteItem]) -> List[Dict[str, str]]:
    return [
        {"nome": n, "cpf": c, "municipio": m, "telefone": t}
        for n, c, m, t in itens
    ]
