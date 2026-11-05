# -*- coding: utf-8 -*-
"""Bateria de testes: CPF inválido na Consulta RGP (zeros, float, ponte JS)."""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))

from controle.consulta_rgp import (  # noqa: E402
    payload_to_registro,
    row_to_registro,
)
from controle.consulta_rgp_mpa import (  # noqa: E402
    _js_start_consulta,
    consultar_cpf_isolado,
    drive_consulta_on_window,
)
from ui.formatters import (  # noqa: E402
    cpf_digitos_validos,
    cpf_para_celula,
    normalize_cpf,
    only_digits,
)


TARGET_A = "09545332590"
TARGET_B = "05610690501"

# Entradas que o app realmente encontra (planilha, pywebview, digitação)
# Strings curtas SEM máscara NÃO recebem pad (anti-corrupção); números sim.
INPUTS_A = [
    "95453325900",  # float já gravado errado na planilha (DV inválido → recover)
    "095.453.325-90",
    "09545332590",
    "9545332590",  # texto planilha sem zero à esquerda
    9545332590,
    9545332590.0,
    "9545332590.0",
    "09545332590.0",
    "9.54533259E9",
    "9.54533259e+09",
    "'09545332590",
    " 095.453.325-90 ",
]
INPUTS_B = [
    "056.106.905-01",
    "05610690501",
    "5610690501",
    5610690501,
    5610690501.0,
    "5610690501.0",
    "05610690501.0",
    "5.610690501E9",
    "'05610690501",
]

# Casos do usuário: DV inválido, mas 11 dígitos digitados — NÃO inventar outro CPF
USER_PRESERVE = [
    ("106.839.195-15", "10683919515"),
    ("10683919515", "10683919515"),
    ("915.647.605-15", "91564760515"),
    ("91564760515", "91564760515"),
]
# Formas corrompidas que o bug antigo gerava (pad/recover)
USER_CORRUPT = ["01068391952", "09156476051"]


def test_normalize_battery_targets() -> None:
    for raw in INPUTS_A:
        got = normalize_cpf(raw)
        assert got == TARGET_A, f"A: {raw!r} → {got!r} (esperado {TARGET_A})"
        assert len(got) == 11
    for raw in INPUTS_B:
        got = normalize_cpf(raw)
        assert got == TARGET_B, f"B: {raw!r} → {got!r} (esperado {TARGET_B})"
        assert len(got) == 11


def test_user_cpf_preserve_no_invent() -> None:
    """Regressão: 106.839.195-15 / 915.647.605-15 não viram 010…/091…."""
    for raw, expect in USER_PRESERVE:
        got = normalize_cpf(raw)
        assert got == expect, f"{raw!r} → {got!r} (esperado {expect})"
        assert got not in USER_CORRUPT
        assert not cpf_digitos_validos(expect)  # DV inválido, mas deve gravar igual
    # Artefato perigoso: CPF válido terminando em 0 NÃO vira outro via recover
    assert cpf_digitos_validos("10683919520")
    assert normalize_cpf("10683919520") == "10683919520"
    assert normalize_cpf("10683919520") != "01068391952"
    assert normalize_cpf("91564760510") == "91564760510"
    assert normalize_cpf("91564760510") != "09156476051"
    # Receitas exatas do bug antigo (fix DV + recover / pad+recalc)
    assert normalize_cpf("106.839.195-15") != "01068391952"
    assert normalize_cpf("915.647.605-15") != "09156476051"


def test_cpf_para_celula_forces_text() -> None:
    for raw, digits in USER_PRESERVE:
        cell = cpf_para_celula(raw)
        assert cell == f"'{digits}", cell
        assert normalize_cpf(cell) == digits


def test_only_digits_float_trap() -> None:
    """Regressão: only_digits(str(float)) inventava dígito extra e passava no len==11."""
    trap = only_digits(str(9545332590.0))
    assert trap == "95453325900"
    assert len(trap) == 11
    # normalize NÃO pode seguir o only_digits cego
    assert normalize_cpf(9545332590.0) == TARGET_A
    assert normalize_cpf("9545332590.0") == TARGET_A


def test_sheet_row_and_payload() -> None:
    for raw, expect in [(9545332590, TARGET_A), (5610690501.0, TARGET_B), ("9545332590.0", TARGET_A)]:
        reg = row_to_registro(["id1", "", "Teste", raw])
        assert reg is not None
        assert reg.cpf == expect
        assert reg.to_dict()["cpf"] == expect
        row_cpf = reg.to_row()[3]
        assert row_cpf in {expect, f"'{expect}"}
        assert normalize_cpf(row_cpf) == expect

    reg2 = payload_to_registro({"nome": "X", "cpf": 9545332590.0})
    assert reg2.cpf == TARGET_A
    reg3 = payload_to_registro({"nome": "Y", "cpf": "5610690501.0"})
    assert reg3.cpf == TARGET_B

    # Usuário digita máscara → planilha guarda texto com apostrofe
    for raw, expect in USER_PRESERVE:
        reg = payload_to_registro({"nome": "Z", "cpf": raw})
        assert reg.cpf == expect
        assert reg.to_row()[3] == f"'{expect}"


def test_mpa_gate_accepts_all_inputs() -> None:
    class Gate:
        def __init__(self) -> None:
            self.started = False
            self.last_start = ""

        def evaluate_js(self, script: str):
            if "grecaptcha" in script or "recaptchaToken" in script:
                self.started = True
                self.last_start = script
                return True
            return {"done": True, "ok": True, "data": {"situacao": "Ativo"}}

    for raw in INPUTS_A:
        g = Gate()
        r = drive_consulta_on_window(g, raw, timeout_s=3, poll_s=0.01, settle_s=0)
        assert r.get("ok") is True, (raw, r)
        assert r.get("cpf") == TARGET_A
        assert json.dumps(TARGET_A) in g.last_start

    for raw in INPUTS_B:
        g = Gate()
        r = drive_consulta_on_window(g, raw, timeout_s=3, poll_s=0.01, settle_s=0)
        assert r.get("ok") is True, (raw, r)
        assert r.get("cpf") == TARGET_B


def test_consultar_cpf_isolado_gate() -> None:
    """Não dispara worker: só valida o gate de 11 dígitos."""
    bad = consultar_cpf_isolado("12345", timeout_s=1)
    assert bad.get("ok") is False
    assert "inválido" in str(bad.get("error") or "").lower()

    # Se passar do gate, tentaria subprocesso — mockando via normalize no start script
    assert json.dumps(TARGET_A) in _js_start_consulta(9545332590.0)
    assert json.dumps(TARGET_B) in _js_start_consulta("5610690501.0")


def test_api_consultar_accepts_dict_and_args() -> None:
    from webapp.api import _parse_consulta_rgp_args

    rid, digits = _parse_consulta_rgp_args({"id": "abc", "cpf": 9545332590.0})
    assert rid == "abc" and digits == TARGET_A
    rid, digits = _parse_consulta_rgp_args(json.dumps({"id": "xyz", "cpf": "056.106.905-01"}))
    assert rid == "xyz" and digits == TARGET_B
    rid, digits = _parse_consulta_rgp_args("abc", 5610690501)
    assert rid == "abc" and digits == TARGET_B
    rid, digits = _parse_consulta_rgp_args(json.dumps({"id": "z", "cpf": "95453325900"}))
    assert rid == "z" and digits == TARGET_A


def test_js_has_object_consulta_and_helpers() -> None:
    js = (ROOT / "web" / "js" / "app.js").read_text(encoding="utf-8")
    masks = (ROOT / "web" / "js" / "masks.js").read_text(encoding="utf-8")
    assert "function normalizeCpf" in js
    assert "function cpfForConsulta" in js
    assert "function consultarRgpRegistro" in js
    assert "JSON.stringify" in js
    assert "consultar_rgp_pessoa" in js
    assert "fixCpfDigits" in js
    assert "cpf: cpfN" in js
    # anti-corrupção no JS
    assert "explicit11" in masks
    assert "fromNumber" in masks
    assert "preservar digitação" in masks or "preservar" in masks
    api_src = (ROOT / "webapp" / "api.py").read_text(encoding="utf-8")
    assert 'normalize_cpf(local.get("cpf")' in api_src
    assert "_parse_consulta_rgp_args" in api_src
    # não deve mais preferir arg só por zero à esquerda
    assert "arg_cpf.startswith" not in api_src


def test_corrupted_float_stored_recovers() -> None:
    # …900 com dígito verificador inválido → recupera
    assert normalize_cpf("95453325900") == TARGET_A
    assert not cpf_digitos_validos("95453325900")
    # …010 passa no DV por coincidência — como STRING não forçamos troca
    # (evita 10683919520 → 01068391952). Número/float ainda recupera via pad.
    assert cpf_digitos_validos("56106905010")
    assert normalize_cpf("56106905010") == "56106905010"
    assert normalize_cpf(5610690501.0) == TARGET_B
    assert normalize_cpf("5610690501.0") == TARGET_B
    assert cpf_digitos_validos(TARGET_A)
    assert cpf_digitos_validos(TARGET_B)
    # only_digits(str(float)) gera 11 dígitos com zero extra; DV inválido → recover A
    assert only_digits(str(9545332590.0)) == "95453325900"
    assert normalize_cpf(only_digits(str(9545332590.0))) == TARGET_A
    # B com only_digits vira …010 (DV válido por coincidência) — não forçamos troca em string
    assert only_digits(str(5610690501.0)) == "56106905010"
    assert normalize_cpf(only_digits(str(5610690501.0))) == "56106905010"


def test_incomplete_still_rejected() -> None:
    assert len(normalize_cpf("12345")) == 5
    assert len(normalize_cpf("")) == 0
    assert normalize_cpf(None) == ""
    # string 10 dígitos da planilha (zero à esquerda perdido) → pad
    assert normalize_cpf("9545332590") == TARGET_A


def test_js_masks_source_guards() -> None:
    """Garante guards anti-corrupção no masks.js."""
    masks = (ROOT / "web" / "js" / "masks.js").read_text(encoding="utf-8")
    assert "explicit11" in masks
    assert "fromNumber" in masks
    assert "preservar digitação" in masks or "Preservar digitação" in masks
    # não preferir zero à esquerda sem fromNumber
    assert "fromNumber && cand.startsWith" in masks

if __name__ == "__main__":
    test_normalize_battery_targets()
    test_user_cpf_preserve_no_invent()
    test_cpf_para_celula_forces_text()
    test_only_digits_float_trap()
    test_sheet_row_and_payload()
    test_mpa_gate_accepts_all_inputs()
    test_consultar_cpf_isolado_gate()
    test_api_consultar_accepts_dict_and_args()
    test_js_has_object_consulta_and_helpers()
    test_corrupted_float_stored_recovers()
    test_incomplete_still_rejected()
    test_js_masks_source_guards()
    print("OK — bateria CPF consulta passou.")
