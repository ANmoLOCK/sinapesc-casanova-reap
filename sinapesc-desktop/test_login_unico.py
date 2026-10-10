"""Bateria: login único na UI (hub + sessão compartilhada)."""

from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parent


def test_js_login_unico() -> None:
    js = (ROOT / "web" / "js" / "app.js").read_text(encoding="utf-8")
    assert "Acesso unificado" in js
    assert "Uma entrada para REAP, Defeso Fácil e Consulta RGP" in js
    assert "goLoginUnico" in js
    assert "goReap" in js
    assert 'id="go-reap"' in js
    assert "← Módulos" in js
    assert 'afterLogin || "home"' in js
    assert "Login único ativo" in js
    assert "Sessão unificada · escolha o módulo" in js
    assert "Entrar como administrador" not in js
    assert "Acesso administrativo" not in js
    # Relatório Defeso (já na base) continua com modal
    assert "openDefesoRelatorioModal" in js
    assert "dr-gerar" in js
    assert "JSON.stringify(colunas)" in js


def test_tk_labels_login_unico() -> None:
    ui = (ROOT / "ui" / "__init__.py").read_text(encoding="utf-8")
    assert "Acesso unificado" in ui
    assert "Uma entrada para REAP, Defeso Fácil e Consulta RGP." in ui
    assert '"Entrar"' in ui or "\"Entrar\"" in ui
    assert "Entrar como administrador" not in ui
    assert "Acesso administrativo" not in ui


def test_version_bump() -> None:
    from ui.theme import APP_VERSION

    assert APP_VERSION == "1.7.54"


if __name__ == "__main__":
    test_js_login_unico()
    test_tk_labels_login_unico()
    test_version_bump()
    print("OK login_unico")
