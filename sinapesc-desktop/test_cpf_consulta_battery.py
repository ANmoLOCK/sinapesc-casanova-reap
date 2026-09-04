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
from ui.formatters import normalize_cpf, only_digits  # noqa: E402


TARGET_A = "09545332590"
TARGET_B = "05610690501"

# Entradas que o app realmente encontra (planilha, pywebview, digitação)
INPUTS_A = [
    "95453325900",  # float já gravado errado na planilha
    "095.453.325-90",
    "09545332590",
    "9545332590",
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
    "56106905010",  # float .0 já gravado; DV passa por coincidência — deve recuperar
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


def test_normalize_battery_targets() -> None:
    for raw in INPUTS_A:
        got = normalize_cpf(raw)
        assert got == TARGET_A, f"A: {raw!r} → {got!r} (esperado {TARGET_A})"
        assert len(got) == 11
    for raw in INPUTS_B:
        got = normalize_cpf(raw)
        assert got == TARGET_B, f"B: {raw!r} → {got!r} (esperado {TARGET_B})"
        assert len(got) == 11


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
        assert len(reg.to_row()[3]) == 11
        assert reg.to_row()[3] == expect

    reg2 = payload_to_registro({"nome": "X", "cpf": 9545332590.0})
    assert reg2.cpf == TARGET_A
    reg3 = payload_to_registro({"nome": "Y", "cpf": "5610690501.0"})
    assert reg3.cpf == TARGET_B


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
    assert "function normalizeCpf" in js
    assert "function cpfForConsulta" in js
    assert "function consultarRgpRegistro" in js
    assert "JSON.stringify" in js
    assert "consultar_rgp_pessoa" in js
    assert "fixCpfDigits" in js
    assert "cpf: cpfN" in js
    api_src = (ROOT / "webapp" / "api.py").read_text(encoding="utf-8")
    assert 'normalize_cpf(local.get("cpf")' in api_src
    assert "_parse_consulta_rgp_args" in api_src


def test_corrupted_float_stored_recovers() -> None:
    from ui.formatters import cpf_digitos_validos

    # …900 com dígito verificador inválido → recupera
    assert normalize_cpf("95453325900") == TARGET_A
    assert not cpf_digitos_validos("95453325900")
    # …010 passa no DV por coincidência — ainda assim recupera zero à esquerda
    assert cpf_digitos_validos("56106905010")
    assert normalize_cpf("56106905010") == TARGET_B
    assert cpf_digitos_validos(TARGET_A)
    assert cpf_digitos_validos(TARGET_B)
    # entrada float ainda na ponte (antes de gravar errado)
    assert normalize_cpf(5610690501.0) == TARGET_B
    assert normalize_cpf("5610690501.0") == TARGET_B
    assert normalize_cpf(only_digits(str(5610690501.0))) == TARGET_B


def test_incomplete_still_rejected() -> None:
    assert len(normalize_cpf("12345")) == 5
    assert len(normalize_cpf("")) == 0
    assert normalize_cpf(None) == ""


if __name__ == "__main__":
    test_normalize_battery_targets()
    test_only_digits_float_trap()
    test_sheet_row_and_payload()
    test_mpa_gate_accepts_all_inputs()
    test_consultar_cpf_isolado_gate()
    test_api_consultar_accepts_dict_and_args()
    test_js_has_object_consulta_and_helpers()
    test_corrupted_float_stored_recovers()
    test_incomplete_still_rejected()
    print("OK — bateria CPF consulta passou.")
