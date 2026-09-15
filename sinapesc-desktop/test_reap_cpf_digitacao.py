# -*- coding: utf-8 -*-
"""Regressão: digitação/gravação de CPF no módulo REAP (sem inventar outro CPF)."""

from __future__ import annotations

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))

# Evita ui/__init__.py (tkinter) — carrega só formatters
import importlib.util

_spec = importlib.util.spec_from_file_location(
    "ui.formatters", ROOT / "ui" / "formatters.py"
)
_fmt = importlib.util.module_from_spec(_spec)
assert _spec.loader is not None
sys.modules["ui.formatters"] = _fmt
_spec.loader.exec_module(_fmt)

format_cpf = _fmt.format_cpf
format_cpf_input = _fmt.format_cpf_input
normalize_cpf = _fmt.normalize_cpf
only_digits = _fmt.only_digits



USER_CASES = [
    ("106.839.195-15", "10683919515"),
    ("915.647.605-15", "91564760515"),
]
CORRUPT = {"01068391952", "09156476051", "01068391951"}


def test_format_cpf_input_no_pad_mid_typing() -> None:
    """No 9º/10º dígito NÃO pode virar outro CPF (bug do maxlength)."""
    # Simula digitação progressiva dos CPFs do usuário
    seq1 = "10683919515"
    for i in range(1, len(seq1) + 1):
        partial = seq1[:i]
        shown = format_cpf_input(partial)
        digits = only_digits(shown)
        assert digits == partial, f"step {i}: {partial!r} → {shown!r} ({digits})"
        assert only_digits(shown) not in CORRUPT

    seq2 = "91564760515"
    for i in range(1, len(seq2) + 1):
        partial = seq2[:i]
        shown = format_cpf_input(partial)
        assert only_digits(shown) == partial

    # Os valores que format_cpf (com normalize) inventava no meio da digitação
    assert format_cpf_input("1068391951") == "106.839.195-1"
    assert format_cpf_input("9156476051") == "915.647.605-1"
    assert only_digits(format_cpf_input("1068391951")) != "01068391951"
    assert only_digits(format_cpf_input("9156476051")) != "09156476051"


def test_format_cpf_still_pads_for_display_legacy() -> None:
    """format_cpf (exibição/planilha legada) continua recuperando zero à esquerda."""
    assert format_cpf("9545332590") == "095.453.325-90"
    assert format_cpf("106.839.195-15") == "106.839.195-15"
    assert format_cpf("915.647.605-15") == "915.647.605-15"


def test_user_cpf_preserved_on_normalize() -> None:
    for masked, digits in USER_CASES:
        assert normalize_cpf(masked) == digits
        assert normalize_cpf(digits) == digits
        assert digits not in CORRUPT


def test_reap_sheets_writes_text_cpf() -> None:
    from sheets.service import _format_cpf

    for masked, digits in USER_CASES:
        cell = _format_cpf(masked)
        assert cell == f"'{digits}", cell
        # leitura: só dígitos
        assert only_digits(cell) == digits


def test_tk_ui_uses_format_cpf_input() -> None:
    src = (ROOT / "ui" / "__init__.py").read_text(encoding="utf-8")
    assert "format_cpf_input" in src
    # máscara do lote não pode usar format_cpf (pad no KeyRelease)
    assert "shown = format_cpf_input(digits)" in src
    assert "shown = format_cpf(digits)" not in src


def test_web_reap_inputs_use_formatCpfInput() -> None:
    app = (ROOT / "web" / "js" / "app.js").read_text(encoding="utf-8")
    assert 'id="m-cpf"' in app
    assert "formatCpfInput(pessoa?.cpf_raw" in app
    # inputs de lote (REAP e RGP) usam formatCpfInput
    assert app.count("formatCpfInput(cpf)") >= 2
    # save_pessoa manda só dígitos
    assert "cpfDigits" in app or "onlyDigits" in app
    assert 'id="m-save"' in app


def test_masks_js_bind_still_safe() -> None:
    js = (ROOT / "web" / "js" / "masks.js").read_text(encoding="utf-8")
    m = re.search(r"function formatCpfInput\(value\) \{(.+?)\n  \}", js, re.S)
    assert m, "formatCpfInput missing"
    body = m.group(1)
    assert "padStart" not in body
    assert "normalizeCpf" not in body
    assert "fixCpfDigits" not in body


def test_version() -> None:
    theme = (ROOT / "ui" / "theme.py").read_text(encoding="utf-8")
    assert 'APP_VERSION = "1.7.51"' in theme


if __name__ == "__main__":
    test_format_cpf_input_no_pad_mid_typing()
    test_format_cpf_still_pads_for_display_legacy()
    test_user_cpf_preserved_on_normalize()
    test_reap_sheets_writes_text_cpf()
    test_tk_ui_uses_format_cpf_input()
    test_web_reap_inputs_use_formatCpfInput()
    test_masks_js_bind_still_safe()
    test_version()
    print("OK — REAP CPF digitação.")
