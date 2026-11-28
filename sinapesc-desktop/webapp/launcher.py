"""Inicia a janela pywebview com a UI web."""

from __future__ import annotations

import faulthandler
import sys
import threading
import traceback
from datetime import datetime
from pathlib import Path
from typing import Any, Optional

from ui.theme import APP_TAGLINE, APP_VERSION, ORG_SHORT
from webapp.api import SinapescApi
from webapp.paths import web_index_url

_log_fh: Optional[Any] = None


def pasta_logs() -> Path:
    from config import app_data_dir, exe_dir

    for base in (exe_dir(), app_data_dir()):
        try:
            path = base / "logs"
            path.mkdir(parents=True, exist_ok=True)
            return path
        except OSError:
            continue
    return Path.cwd()


def registrar_erro(titulo: str, texto: str) -> None:
    fh = _log_fh
    if fh is None:
        return
    try:
        stamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        fh.write(f"\n[{stamp}] {titulo}\n{texto}\n")
        fh.flush()
    except Exception:  # noqa: BLE001
        pass


def preparar_log() -> Optional[Path]:
    """No EXE sem console stdout/stderr são None; manda tudo para um arquivo.

    O faulthandler grava a pilha mesmo quando o processo cai de uma vez
    (falha nativa no WebView2 ou no SSL), para descobrir a causa depois.
    """
    global _log_fh
    try:
        path = pasta_logs() / "sinapesc-erros.log"
        if path.is_file() and path.stat().st_size > 2_000_000:
            path.replace(path.with_suffix(".old.log"))
        _log_fh = path.open("a", encoding="utf-8", buffering=1)
    except OSError:
        return None
    _log_fh.write(f"\n=== Sinapesc {APP_VERSION} iniciado {datetime.now():%Y-%m-%d %H:%M:%S} ===\n")
    if sys.stdout is None:
        sys.stdout = _log_fh
    if sys.stderr is None:
        sys.stderr = _log_fh
    try:
        faulthandler.enable(file=_log_fh, all_threads=True)
    except Exception:  # noqa: BLE001
        pass

    def excepthook(tipo, valor, tb):  # type: ignore[no-untyped-def]
        registrar_erro("Erro não tratado", "".join(traceback.format_exception(tipo, valor, tb)))

    def thread_excepthook(args):  # type: ignore[no-untyped-def]
        nome = getattr(args.thread, "name", "?")
        registrar_erro(
            f"Erro na thread {nome}",
            "".join(traceback.format_exception(args.exc_type, args.exc_value, args.exc_traceback)),
        )

    sys.excepthook = excepthook
    threading.excepthook = thread_excepthook
    return path


def run_web_app() -> None:
    preparar_log()
    try:
        import webview
    except ImportError as exc:
        print("pywebview não instalado. Use: pip install pywebview", file=sys.stderr)
        print("Ou execute com --tk para a interface Tkinter.", file=sys.stderr)
        raise SystemExit(1) from exc

    api = SinapescApi()
    title = f"{ORG_SHORT} REAP — {APP_TAGLINE.split('·')[0].strip()}"

    window = webview.create_window(
        title,
        url=web_index_url(),
        js_api=api,
        width=1280,
        height=800,
        min_size=(900, 600),
        background_color="#0A2F52",
    )
    api.bind_window(window)
    try:
        window.events.closing += api.on_closing
    except Exception:  # noqa: BLE001
        pass

    # Edge WebView2 no Windows; no Linux usa GTK/WebKit automaticamente.
    gui = "edgechromium" if sys.platform == "win32" else None
    try:
        webview.start(gui=gui, debug=False)
    except Exception:  # noqa: BLE001
        registrar_erro("Janela fechou com erro", traceback.format_exc())
        raise
