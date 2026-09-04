"""
Consulta pública MPA em processo/janela isolada (não derruba o EXE principal).

Fluxo:
1. Abre o site oficial em janela pywebview dedicada (ou subprocesso do próprio EXE).
2. No domínio do MPA, executa reCAPTCHA v3 + fetch da API pública.
3. Grava JSON de resultado em arquivo temporário e encerra.

URL oficial:
https://pesqbrasil-pescadorprofissional.mpa.gov.br/acesso-externo
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import tempfile
import threading
import time
from pathlib import Path
from typing import Any, Dict, Optional

from controle.consulta_rgp import normalize_situacao
from ui.formatters import only_digits

MPA_CONSULTA_URL = "https://pesqbrasil-pescadorprofissional.mpa.gov.br/acesso-externo"
MPA_RECAPTCHA_SITE_KEY = "6LeJP-srAAAAAFdZMYINP6CJ4COI_MAzFvk_0gs1"
WORKER_FLAG = "--consulta-rgp-worker"


def _js_consultar(cpf: str) -> str:
    """Script injetado na página MPA (domínio válido para o reCAPTCHA)."""
    cpf_js = json.dumps(only_digits(cpf))
    key_js = json.dumps(MPA_RECAPTCHA_SITE_KEY)
    return f"""
(async function() {{
  try {{
    const cpf = {cpf_js};
    if (!window.grecaptcha) {{
      return JSON.stringify({{ ok: false, error: "reCAPTCHA ainda não carregou. Tente de novo." }});
    }}
    const token = await new Promise((resolve, reject) => {{
      try {{
        grecaptcha.ready(() => {{
          grecaptcha.execute({key_js}, {{ action: "submit" }})
            .then(resolve)
            .catch(reject);
        }});
      }} catch (e) {{
        reject(e);
      }}
    }});
    const params = new URLSearchParams();
    params.append("cpf", cpf);
    params.append("recaptchaToken", token);
    const res = await fetch("api/consulta-publica/pesquisa/" + params.toString(), {{
      cache: "no-store",
    }});
    const data = await res.json();
    if (!res.ok) {{
      return JSON.stringify({{
        ok: false,
        error: (data && (data.error || data.message)) || ("HTTP " + res.status),
        raw: data,
      }});
    }}
    return JSON.stringify({{ ok: true, data: data }});
  }} catch (e) {{
    return JSON.stringify({{ ok: false, error: String(e && e.message ? e.message : e) }});
  }}
}})()
"""


def _parse_worker_result(raw: Any) -> Dict[str, Any]:
    if raw is None:
        return {"ok": False, "error": "Sem resposta da janela MPA."}
    if isinstance(raw, dict):
        return raw
    text = str(raw).strip()
    if not text:
        return {"ok": False, "error": "Resposta vazia da janela MPA."}
    # pywebview às vezes devolve string JSON com aspas extras
    try:
        data = json.loads(text)
    except json.JSONDecodeError:
        try:
            data = json.loads(json.loads(text))
        except Exception:  # noqa: BLE001
            return {"ok": False, "error": f"Resposta inválida: {text[:200]}"}
    if isinstance(data, dict):
        return data
    return {"ok": False, "error": "Formato inesperado da consulta."}


def run_consulta_in_webview(cpf: str, *, timeout_s: float = 90.0) -> Dict[str, Any]:
    """Abre janela isolada no site MPA, consulta e fecha (bloqueante)."""
    digits = only_digits(cpf)
    if len(digits) != 11:
        return {"ok": False, "error": "CPF inválido (11 dígitos)."}

    try:
        import webview
    except ImportError:
        return {"ok": False, "error": "pywebview indisponível para consulta MPA."}

    holder: Dict[str, Any] = {"done": False, "result": None}
    window_ref: Dict[str, Any] = {"w": None}

    def finish(payload: Dict[str, Any]) -> None:
        if holder["done"]:
            return
        holder["done"] = True
        holder["result"] = payload
        w = window_ref.get("w")
        try:
            if w is not None:
                w.destroy()
        except Exception:  # noqa: BLE001
            pass

    def on_loaded() -> None:
        def work() -> None:
            # Espera scripts/reCAPTCHA do Next.js
            time.sleep(2.5)
            w = window_ref.get("w")
            if w is None:
                finish({"ok": False, "error": "Janela MPA não disponível."})
                return
            last_err = "Falha ao consultar."
            for attempt in range(4):
                try:
                    raw = w.evaluate_js(_js_consultar(digits))
                    parsed = _parse_worker_result(raw)
                    if parsed.get("ok") and isinstance(parsed.get("data"), dict):
                        data = parsed["data"]
                        situacao = normalize_situacao(str(data.get("situacao") or ""))
                        finish(
                            {
                                "ok": True,
                                "data": data,
                                "situacao": situacao,
                                "cpf": digits,
                            }
                        )
                        return
                    last_err = str(parsed.get("error") or last_err)
                except Exception as exc:  # noqa: BLE001
                    last_err = str(exc)
                time.sleep(1.5 + attempt)
            finish({"ok": False, "error": last_err, "cpf": digits})

        threading.Thread(target=work, daemon=True).start()

    # Se o GUI já está rodando (app principal), create_window após start.
    already = False
    try:
        already = bool(getattr(webview, "windows", None))
    except Exception:  # noqa: BLE001
        already = False

    try:
        w = webview.create_window(
            "Sinapesc — Consulta RGP (MPA)",
            MPA_CONSULTA_URL,
            width=960,
            height=720,
            background_color="#E7F1F7",
        )
        window_ref["w"] = w
        w.events.loaded += on_loaded
    except Exception as exc:  # noqa: BLE001
        return {"ok": False, "error": f"Não foi possível abrir janela MPA: {exc}"}

    if already:
        # Janela adicional no loop existente — aguarda resultado
        deadline = time.time() + timeout_s
        while not holder["done"] and time.time() < deadline:
            time.sleep(0.25)
        if not holder["done"]:
            finish({"ok": False, "error": "Tempo esgotado na consulta MPA.", "cpf": digits})
        return holder["result"] or {"ok": False, "error": "Sem resultado."}

    # Processo worker dedicado: start() bloqueia até destroy
    def watchdog() -> None:
        time.sleep(timeout_s)
        if not holder["done"]:
            finish({"ok": False, "error": "Tempo esgotado na consulta MPA.", "cpf": digits})

    threading.Thread(target=watchdog, daemon=True).start()
    try:
        webview.start()
    except Exception as exc:  # noqa: BLE001
        if not holder["done"]:
            return {"ok": False, "error": f"Falha no motor da janela: {exc}"}
    return holder["result"] or {"ok": False, "error": "Consulta encerrada sem resultado."}


def run_worker_cli(argv: Optional[list[str]] = None) -> int:
    """CLI: python main.py --consulta-rgp-worker --cpf=... --out=arquivo.json"""
    parser = argparse.ArgumentParser(add_help=False)
    parser.add_argument(WORKER_FLAG, action="store_true")
    parser.add_argument("--cpf", required=True)
    parser.add_argument("--out", required=True)
    args, _ = parser.parse_known_args(argv if argv is not None else sys.argv[1:])
    out_path = Path(args.out)
    try:
        result = run_consulta_in_webview(args.cpf)
    except Exception as exc:  # noqa: BLE001
        result = {"ok": False, "error": str(exc)}
    try:
        out_path.write_text(json.dumps(result, ensure_ascii=False), encoding="utf-8")
    except OSError as exc:
        sys.stderr.write(f"Falha ao gravar resultado: {exc}\n")
        return 2
    return 0 if result.get("ok") else 1


def consultar_cpf_isolado(cpf: str, *, timeout_s: float = 100.0) -> Dict[str, Any]:
    """
    Dispara consulta em subprocesso separado (estilo .bat / PowerShell),
    para não travar nem derrubar o app principal.
    """
    digits = only_digits(cpf)
    if len(digits) != 11:
        return {"ok": False, "error": "CPF inválido (11 dígitos)."}

    fd, tmp_name = tempfile.mkstemp(prefix="sinapesc-rgp-", suffix=".json")
    os.close(fd)
    out_path = Path(tmp_name)

    if getattr(sys, "frozen", False):
        cmd = [sys.executable, WORKER_FLAG, f"--cpf={digits}", f"--out={out_path}"]
    else:
        # main.py na pasta sinapesc-desktop
        main_py = Path(__file__).resolve().parents[1] / "main.py"
        cmd = [
            sys.executable,
            str(main_py),
            WORKER_FLAG,
            f"--cpf={digits}",
            f"--out={out_path}",
        ]

    flags = 0
    if os.name == "nt":
        if hasattr(subprocess, "CREATE_NEW_PROCESS_GROUP"):
            flags |= subprocess.CREATE_NEW_PROCESS_GROUP  # type: ignore[attr-defined]
        if hasattr(subprocess, "CREATE_NO_WINDOW"):
            # Mantém janela do worker visível para reCAPTCHA; sem CREATE_NO_WINDOW
            pass

    try:
        proc = subprocess.Popen(
            cmd,
            cwd=str(Path(cmd[1]).parent) if not getattr(sys, "frozen", False) else None,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            creationflags=flags,
        )
    except OSError as exc:
        try:
            out_path.unlink(missing_ok=True)
        except OSError:
            pass
        # Fallback: tentar na mesma thread (ainda isolado por try/except no caller)
        return run_consulta_in_webview(digits, timeout_s=timeout_s)

    try:
        proc.wait(timeout=timeout_s)
    except subprocess.TimeoutExpired:
        try:
            proc.kill()
        except OSError:
            pass
        try:
            out_path.unlink(missing_ok=True)
        except OSError:
            pass
        return {"ok": False, "error": "Consulta MPA excedeu o tempo (subprocesso)."}

    try:
        text = out_path.read_text(encoding="utf-8")
        data = json.loads(text) if text.strip() else {"ok": False, "error": "Arquivo vazio."}
    except (OSError, json.JSONDecodeError) as exc:
        data = {"ok": False, "error": f"Não foi possível ler resultado: {exc}"}
    finally:
        try:
            out_path.unlink(missing_ok=True)
        except OSError:
            pass

    if isinstance(data, dict) and data.get("ok") and "situacao" not in data:
        raw = data.get("data") if isinstance(data.get("data"), dict) else {}
        data["situacao"] = normalize_situacao(str(raw.get("situacao") or ""))
    return data if isinstance(data, dict) else {"ok": False, "error": "Resultado inválido."}


def abrir_site_mpa_no_navegador(cpf: str = "") -> None:
    """Abre o site oficial no Edge/Chrome (fallback manual)."""
    import webbrowser

    url = MPA_CONSULTA_URL
    digits = only_digits(cpf)
    # O site não aceita CPF na query de forma documentada; abre a página limpa.
    try:
        webbrowser.open(url)
    except Exception:  # noqa: BLE001
        pass
    # Copia CPF para área de transferência quando possível
    if digits and len(digits) == 11:
        try:
            import tkinter as tk

            r = tk.Tk()
            r.withdraw()
            r.clipboard_clear()
            r.clipboard_append(digits)
            r.update()
            r.destroy()
        except Exception:  # noqa: BLE001
            pass
