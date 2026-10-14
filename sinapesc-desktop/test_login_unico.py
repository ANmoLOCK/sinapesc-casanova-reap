"""Bateria: login único primário (gate inicial + hub de módulos)."""

from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parent


def test_js_login_unico() -> None:
    js = (ROOT / "web" / "js" / "app.js").read_text(encoding="utf-8")
    assert "Acesso unificado" in js
    assert "Login único no início" in js
    assert "requireLogin" in js
    assert "isPublicScreen" in js
    assert "goReap" in js
    assert 'id="go-reap"' in js
    assert "← Módulos" in js
    assert 'afterLogin || "home"' in js
    assert "Login único ativo" in js
    assert "Sessão unificada · escolha o módulo" in js
    assert 'navigate("login"' in js
    assert "Entrar como administrador" not in js
    assert "Acesso administrativo" not in js
    # Começa na tela de login
    assert 'navigate("login", { push: false })' in js
    # Relatório Defeso continua com modal
    assert "openDefesoRelatorioModal" in js
    assert "dr-gerar" in js
    assert "JSON.stringify(colunas)" in js
    # Filtros de verificação Consulta RGP
    assert "nao_consultados" in js
    assert "Consultados recentes" in js
    assert "matchConsultaPeriodo" in js


def test_tk_labels_login_unico() -> None:
    ui = (ROOT / "ui" / "__init__.py").read_text(encoding="utf-8")
    assert "Acesso unificado" in ui
    assert "Login único no início" in ui
    assert "Entrar como administrador" not in ui
    assert "Acesso administrativo" not in ui


def test_version_bump() -> None:
    theme = (ROOT / "ui" / "theme.py").read_text(encoding="utf-8")
    assert 'APP_VERSION = "1.7.56"' in theme


if __name__ == "__main__":
    test_js_login_unico()
    test_tk_labels_login_unico()
    test_version_bump()
    print("OK login_unico")
