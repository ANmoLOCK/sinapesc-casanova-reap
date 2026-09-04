"""Utilitários de formatação (CPF, iniciais, nome na tela)."""

from __future__ import annotations

import re
from typing import Any


def only_digits(value: str, max_len: int = 11) -> str:
    return "".join(ch for ch in str(value or "") if ch.isdigit())[:max_len]


def normalize_cpf(value: Any) -> str:
    """CPF com 11 dígitos e zeros à esquerda.

    Google Sheets / JSON numérico costuma devolver 095.453.325-90 como
    ``9545332590`` (10 dígitos). Sem o pad, a consulta MPA falha com
    «CPF inválido».
    """
    if value is None:
        return ""
    if isinstance(value, bool):
        return ""
    if isinstance(value, int):
        raw = str(value)
    elif isinstance(value, float):
        if not value.is_integer():
            raw = f"{value:.0f}"
        else:
            raw = str(int(value))
    else:
        raw = str(value).strip()
        if re.fullmatch(r"\d+\.?\d*[eE][+-]?\d+", raw):
            try:
                raw = str(int(float(raw)))
            except (TypeError, ValueError):
                pass

    digits = "".join(ch for ch in raw if ch.isdigit())
    if not digits:
        return ""
    if len(digits) > 11:
        # notação científica / lixo: fica com os 11 da direita
        digits = digits[-11:]
    if len(digits) < 11:
        # 9–10 dígitos = zero inicial perdido; <9 = incompleto (não inventa)
        if len(digits) >= 9:
            digits = digits.zfill(11)
        else:
            return digits
    return digits[:11]


def format_cpf(digits: str) -> str:
    clean = normalize_cpf(digits)
    if len(clean) != 11:
        clean = only_digits(digits)
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
    import re

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
