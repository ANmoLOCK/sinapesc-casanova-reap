"""Utilitários de formatação (CPF, iniciais, nome na tela)."""

from __future__ import annotations

import math
import re
from typing import Any


def only_digits(value: str, max_len: int = 11) -> str:
    return "".join(ch for ch in str(value or "") if ch.isdigit())[:max_len]


def normalize_cpf(value: Any) -> str:
    """CPF com 11 dígitos e zeros à esquerda.

    Casos reais que quebravam a consulta MPA («CPF inválido»):
    - planilha/JSON numérico: ``095.453.325-90`` → ``9545332590`` (10 dígitos)
    - pywebview/float: ``9545332590.0`` → dígitos ``95453325900`` (11 errados)
    - string ``"9545332590.0"`` / notação científica
    """
    if value is None or isinstance(value, bool):
        return ""

    digits = ""

    if isinstance(value, int):
        digits = str(abs(value))
    elif isinstance(value, float):
        if not math.isfinite(value):
            return ""
        digits = str(abs(int(round(value))))
    else:
        raw = str(value).strip()
        if raw.startswith("'"):
            raw = raw[1:].strip()
        # Artefato de float/Sheets: "9545332590.0" / "09545332590.0"
        if re.fullmatch(r"\d+\.0+", raw):
            raw = raw.split(".", 1)[0]
        # Científica (ponto ou vírgula decimal)
        sci = raw.replace(",", ".")
        if re.fullmatch(r"\d+\.?\d*[eE][+-]?\d+", sci):
            try:
                digits = str(abs(int(round(float(sci)))))
            except (TypeError, ValueError):
                digits = ""
        if not digits:
            digits = "".join(ch for ch in raw if ch.isdigit())

    if not digits:
        return ""

    # Sobra de ".0" que virou dígito extra (12 chars terminando em 0)
    if len(digits) == 12 and digits.endswith("0"):
        digits = digits[:-1]
    if len(digits) > 11:
        digits = digits[-11:]

    if len(digits) < 11:
        # 9–10 dígitos = zero(s) à esquerda perdidos; <9 = digitação incompleta
        if len(digits) >= 9:
            digits = digits.zfill(11)
        else:
            return digits

    return digits[:11]


def format_cpf(digits: str) -> str:
    clean = normalize_cpf(digits)
    if len(clean) != 11:
        clean = only_digits(str(digits or ""))
    part1, part2, part3, part4 = clean[:3], clean[3:6], clean[6:9], clean[9:11]
    result = part1
    if part2:
        result += f".{part2}"
    if part3:
        result += f".{part3}"
    if part4:
        result += f"-{part4}"
    return result


def format_cpf_masked(digits: str) -> str:
    clean = normalize_cpf(digits)
    if len(clean) != 11:
        return format_cpf(digits)
    return f"***.***.{clean[6:9]}-**"


def get_initials(name: str) -> str:
    parts = [p for p in name.strip().split() if p]
    if not parts:
        return "?"
    if len(parts) == 1:
        return parts[0][:2].upper()
    return (parts[0][0] + parts[-1][0]).upper()


def _cap_word(word: str) -> str:
    if "-" in word:
        return "-".join(_cap_word(p) for p in word.split("-"))
    if not word:
        return word
    return word[:1].upper() + word[1:].lower()


def format_nome(name: str) -> str:
    """Primeira letra de cada palavra maiúscula. Caps Lock não altera o gravado.

    Gabriel Lourran Da Silva  — certo
    gabriel lourran da silva  — vira o certo
    GABRIEL LOURRAN DA SILVA  — vira o certo
    """
    parts = [p for p in (name or "").split() if p]
    if not parts:
        return ""
    return " ".join(_cap_word(p) for p in parts)


def display_nome(name: str) -> str:
    """Nome para a tela: sempre no formato título."""
    return format_nome(name)


def parse_lote_lines(raw: str) -> list[tuple[str, str]]:
    """Lê Nome + CPF de texto/CSV (uma pessoa por linha)."""
    itens: list[tuple[str, str]] = []
    for line in raw.splitlines():
        line = line.strip()
        if not line or line.lower().startswith("nome"):
            continue
        if ";" in line:
            parts = line.split(";", 1)
        elif "\t" in line:
            parts = line.split("\t", 1)
        elif "," in line:
            parts = line.rsplit(",", 1)
        else:
            parts = re.split(r"\s{2,}", line, maxsplit=1)
        if len(parts) < 2:
            continue
        itens.append((parts[0].strip().strip('"'), parts[1].strip().strip('"')))
    return itens
