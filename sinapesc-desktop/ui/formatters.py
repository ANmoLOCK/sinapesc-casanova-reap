"""Utilitários de formatação (CPF, iniciais, nome na tela)."""

from __future__ import annotations

import math
import re
from typing import Any


def only_digits(value: str, max_len: int = 11) -> str:
    return "".join(ch for ch in str(value or "") if ch.isdigit())[:max_len]


def cpf_digitos_validos(digits: str) -> bool:
    """Valida dígitos verificadores do CPF (rejeita sequência repetida)."""
    d = "".join(ch for ch in str(digits or "") if ch.isdigit())
    if len(d) != 11 or d == d[0] * 11:
        return False
    nums = [int(ch) for ch in d]
    total = sum(nums[i] * (10 - i) for i in range(9))
    rest = (total * 10) % 11
    rest = 0 if rest == 10 else rest
    if rest != nums[9]:
        return False
    total = sum(nums[i] * (11 - i) for i in range(10))
    rest = (total * 10) % 11
    rest = 0 if rest == 10 else rest
    return rest == nums[10]


def cpf_para_celula(value: Any) -> str:
    """Valor para gravar na planilha: texto com 11 dígitos (prefixo ').

    Evita o Google Sheets tratar CPF como número e corromper dígitos.
    """
    digits = normalize_cpf(value)
    if len(digits) != 11:
        digits = "".join(ch for ch in str(value or "") if ch.isdigit())[:11]
    if not digits:
        return ""
    if digits.startswith("'"):
        return digits
    return f"'{digits}"


def normalize_cpf(value: Any) -> str:
    """CPF com 11 dígitos e zeros à esquerda (quando veio de número).

    Casos reais que quebravam a consulta MPA («CPF inválido»):
    - planilha/JSON numérico: ``095.453.325-90`` → ``9545332590`` (10 dígitos)
    - pywebview/float: ``9545332590.0`` → dígitos ``95453325900`` (11 errados)
    - string ``"9545332590.0"`` / notação científica
    - valor já gravado errado ``95453325900`` (recupera se DV atual inválido)

    Anti-corrupção (regressão 106.839.195-15 / 915.647.605-15):
    - 11 dígitos explícitos na máscara/digitação → **preservar** (mesmo DV inválido)
    - NÃO dar pad em string curta só porque o DV «bate» após zfill
      (``9156476051`` → ``09156476051`` era inventar outro CPF)
    - NÃO preferir zero à esquerda quando atual e candidato são ambos válidos
      (``10683919520`` → ``01068391952``)
    """
    if value is None or isinstance(value, bool):
        return ""

    digits = ""
    explicit_11 = False
    from_number = isinstance(value, (int, float)) and not isinstance(value, bool)

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
            from_number = True
        # Científica (ponto ou vírgula decimal)
        sci = raw.replace(",", ".")
        if re.fullmatch(r"\d+\.?\d*[eE][+-]?\d+", sci):
            try:
                digits = str(abs(int(round(float(sci)))))
                from_number = True
            except (TypeError, ValueError):
                digits = ""
        if not digits:
            visible = "".join(ch for ch in raw if ch.isdigit())
            if len(visible) >= 11:
                explicit_11 = True
                digits = visible
            else:
                digits = visible

    if not digits:
        return ""

    # Sobra de ".0" que virou dígito extra (12 chars terminando em 0)
    if len(digits) == 12 and digits.endswith("0"):
        cand = digits[:-1]
        if len(cand) >= 9:
            cand11 = cand.zfill(11) if len(cand) < 11 else cand[:11]
            if cpf_digitos_validos(cand11) or len(cand) <= 10:
                digits = cand
                from_number = True

    if len(digits) > 11:
        digits = digits[-11:]

    # 11 dígitos já explícitos na digitação/máscara → preservar o valor digitado.
    # Exceção: artefato já gravado com DV inválido (ex. 95453325900) → recover.
    if explicit_11 and len(digits) == 11:
        if from_number:
            return _recover_float_trailing_zero(digits, from_number=True)
        if not cpf_digitos_validos(digits):
            return _recover_float_trailing_zero(digits, from_number=False)
        return digits

    if len(digits) < 11:
        # 9–10 dígitos: zeros à esquerda perdidos (número ou texto da planilha).
        # A UI só salva com 11 dígitos; pad aqui cobre leitura legado da Sheets.
        if len(digits) >= 9:
            digits = digits.zfill(11)
        else:
            return digits

    digits = digits[:11]
    return _recover_float_trailing_zero(digits, from_number=from_number)


def _recover_float_trailing_zero(digits: str, *, from_number: bool = False) -> str:
    """Recupera CPF corrompido por float ``.0`` (ex.: ``95453325900`` → ``09545332590``).

    Se o atual é inválido e ``base.zfill(11)`` é válido → recupera.
    Se ambos são válidos → só prefere zero à esquerda quando ``from_number``
    (senão ``10683919520`` virava ``01068391952``).
    """
    if len(digits) != 11 or not digits.endswith("0"):
        return digits
    base = digits[:-1]
    if len(base) != 10:
        return digits
    cand = base.zfill(11)
    if cand == digits or not cpf_digitos_validos(cand):
        return digits
    if not cpf_digitos_validos(digits):
        return cand
    # Ambos válidos: só troca se veio de número (artefato clássico da planilha)
    if from_number and cand.startswith("0") and not digits.startswith("0"):
        return cand
    return digits


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
    text = str(name or "").strip()
    if not text:
        return ""
    return " ".join(_cap_word(w) for w in text.split())


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
