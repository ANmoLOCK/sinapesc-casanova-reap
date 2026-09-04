"""
Consulta pública MPA em processo/janela isolada (não derruba o EXE principal).

Fluxo:
1. Abre o site oficial em janela pywebview dedicada (ou subprocesso do próprio EXE).
2. No domínio do MPA, aguarda reCAPTCHA v3 + fetch da API pública.
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

from controle.consulta_rgp import extract_situacao_from_mpa, normalize_situacao
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
    const siteKey = {key_js};

    async function waitGrecaptcha(maxMs) {{
      const start = Date.now();
      while (Date.now() - start < maxMs) {{
        if (window.grecaptcha && typeof window.grecaptcha.execute === "function") {{
          await new Promise((resolve, reject) => {{
            try {{
              grecaptcha.ready(() => resolve(true));
            }} catch (e) {{
              reject(e);
            }}
          }});
          return true;
        }}
        await new Promise((r) => setTimeout(r, 400));
      }}
      return false;
    }}

    if (!(await waitGrecaptcha(8000))) {{
      // tenta carregar o script oficial se a página ainda não injetou
      await new Promise((resolve, reject) => {{
        const existing = document.querySelector('script[src*="recaptcha/api.js"]');
        if (existing && window.grecaptcha) {{ resolve(true); return; }}
        const s = document.createElement("script");
        s.src = "https://www.google.com/recaptcha/api.js?render=" + siteKey;
        s.async = true;
        s.onload = () => resolve(true);
        s.onerror = () => reject(new Error("Falha ao carregar reCAPTCHA"));
        document.head.appendChild(s);
      }});
      if (!(await waitGrecaptcha(20000))) {{
        return JSON.stringify({{ ok: false, error: "reCAPTCHA não carregou a tempo. Tente de novo." }});
      }}
    }}

    const token = await new Promise((resolve, reject) => {{
      try {{
        grecaptcha.ready(() => {{
          grecaptcha.execute(siteKey, {{ action: "submit" }})
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

    // O front oficial do MPA usa path + URLSearchParams (sem '?').
    // Mantemos fallback com query clássica.
    const urls = [
      "api/consulta-publica/pesquisa/" + params.toString(),
      "api/consulta-publica/pesquisa/?" + params.toString(),
      "/api/consulta-publica/pesquisa/" + params.toString(),
    ];

    let lastErr = "Consulta MPA sem resposta.";
    let raw = null;
    for (const url of urls) {{
      try {{
        const res = await fetch(url, {{ cache: "no-store", credentials: "same-origin" }});
        let data = null;
        try {{ data = await res.json(); }} catch (_) {{ data = null; }}
        if (!res.ok) {{
          lastErr = (data && (data.error || data.message || data.titulo)) || ("HTTP " + res.status);
          raw = data;
          continue;
        }}
        if (!data || typeof data !== "object") {{
          lastErr = "JSON inválido da API MPA.";
          continue;
        }}
        return JSON.stringify({{ ok: true, data: data, url: url }});
      }} catch (e) {{
        lastErr = String(e && e.message ? e.message : e);
      }}
    }}
    return JSON.stringify({{ ok: false, error: lastErr, raw: raw }});
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


def _enrich_ok_result(parsed: Dict[str, Any], digits: str) -> Dict[str, Any]:
    data = parsed.get("data") if isinstance(parsed.get("data"), dict) else {}
    situacao = extract_situacao_from_mpa(data)
    return {
        "ok": True,
        "data": data,
        "situacao": situacao,
        "cpf": digits,
    }


def run_consulta_in_webview(cpf: str, *, timeout_s: float = 120.0) -> Dict[str, Any]:
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
            # Espera Next.js + reCAPTCHA
            time.sleep(3.5)
            w = window_ref.get("w")
            if w is None:
                finish({"ok": False, "error": "Janela MPA não disponível."})
                return
            last_err = "Falha ao consultar."
            for attempt in range(6):
                try:
                    raw = w.evaluate_js(_js_consultar(digits))
                    parsed = _parse_worker_result(raw)
                    if parsed.get("ok") and isinstance(parsed.get("data"), dict):
                        finish(_enrich_ok_result(parsed, digits))
                        return
                    last_err = str(parsed.get("error") or last_err)
                except Exception as exc:  # noqa: BLE001
                    last_err = str(exc)
                time.sleep(2.0 + attempt * 0.5)
            finish({"ok": False, "error": last_err, "cpf": digits})

        threading.Thread(target=work, daemon=True).start()

    already = False
    try:
        already = bool(getattr(webview, "windows", None))
    except Exception:  # noqa: BLE001
        already = False

    try:
        w = webview.create_window(
            "Sinapesc — Consulta RGP (MPA)",
            MPA_CONSULTA_URL,
            width=980,
            height=760,
            background_color="#E7F1F7",
        )
        window_ref["w"] = w
        w.events.loaded += on_loaded
    except Exception as exc:  # noqa: BLE001
        return {"ok": False, "error": f"Não foi possível abrir janela MPA: {exc}"}

    if already:
        deadline = time.time() + timeout_s
        while not holder["done"] and time.time() < deadline:
            time.sleep(0.25)
        if not holder["done"]:
            finish({"ok": False, "error": "Tempo esgotado na consulta MPA.", "cpf": digits})
        return holder["result"] or {"ok": False, "error": "Sem resultado."}

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


def consultar_cpf_isolado(cpf: str, *, timeout_s: float = 130.0) -> Dict[str, Any]:
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
    err_path = out_path.with_suffix(".log")

    if getattr(sys, "frozen", False):
        cmd = [sys.executable, WORKER_FLAG, f"--cpf={digits}", f"--out={out_path}"]
        cwd = None
    else:
        main_py = Path(__file__).resolve().parents[1] / "main.py"
        cmd = [
            sys.executable,
            str(main_py),
            WORKER_FLAG,
            f"--cpf={digits}",
            f"--out={out_path}",
        ]
        cwd = str(main_py.parent)

    flags = 0
    if os.name == "nt":
        if hasattr(subprocess, "CREATE_NEW_PROCESS_GROUP"):
            flags |= subprocess.CREATE_NEW_PROCESS_GROUP  # type: ignore[attr-defined]

    try:
        err_f = open(err_path, "w", encoding="utf-8")  # noqa: SIM115
        proc = subprocess.Popen(
            cmd,
            cwd=cwd,
            stdout=err_f,
            stderr=subprocess.STDOUT,
            creationflags=flags,
        )
    except OSError as exc:
        try:
            out_path.unlink(missing_ok=True)
        except OSError:
            pass
        try:
            err_path.unlink(missing_ok=True)
        except OSError:
            pass
        # Fallback: mesma máquina / processo (ainda isolado por try no caller)
        return run_consulta_in_webview(digits, timeout_s=timeout_s)

    try:
        proc.wait(timeout=timeout_s)
    except subprocess.TimeoutExpired:
        try:
            proc.kill()
        except OSError:
            pass
        try:
            err_f.close()
        except Exception:  # noqa: BLE001
            pass
        try:
            out_path.unlink(missing_ok=True)
        except OSError:
            pass
        try:
            err_path.unlink(missing_ok=True)
        except OSError:
            pass
        return {"ok": False, "error": "Consulta MPA excedeu o tempo (subprocesso)."}

    try:
        err_f.close()
    except Exception:  # noqa: BLE001
        pass

    log_tail = ""
    try:
        log_tail = err_path.read_text(encoding="utf-8", errors="ignore")[-500:]
    except OSError:
        log_tail = ""

    try:
        text = out_path.read_text(encoding="utf-8")
        data = json.loads(text) if text.strip() else {"ok": False, "error": "Arquivo vazio."}
    except (OSError, json.JSONDecodeError) as exc:
        data = {
            "ok": False,
            "error": f"Não foi possível ler resultado: {exc}"
            + (f" | log: {log_tail}" if log_tail else ""),
        }
    finally:
        try:
            out_path.unlink(missing_ok=True)
        except OSError:
            pass
        try:
            err_path.unlink(missing_ok=True)
        except OSError:
            pass

    if not isinstance(data, dict):
        return {"ok": False, "error": "Resultado inválido."}

    if data.get("ok"):
        raw = data.get("data") if isinstance(data.get("data"), dict) else {}
        data["situacao"] = extract_situacao_from_mpa(raw) or normalize_situacao(
            str(data.get("situacao") or "")
        )
        data["cpf"] = digits
        return data

    # Worker falhou: tenta uma vez no processo atual (quando possível)
    if "Janela MPA" in str(data.get("error") or "") or "pywebview" in str(data.get("error") or ""):
        fallback = run_consulta_in_webview(digits, timeout_s=min(timeout_s, 90))
        if fallback.get("ok"):
            return fallback

    if log_tail and "log:" not in str(data.get("error") or ""):
        data["error"] = str(data.get("error") or "Falha na consulta") + f" | log: {log_tail}"
    return data


def abrir_site_mpa_no_navegador(cpf: str = "") -> None:
    """Abre o site oficial no Edge/Chrome (fallback manual)."""
    import webbrowser

    url = MPA_CONSULTA_URL
    digits = only_digits(cpf)
    try:
        webbrowser.open(url)
    except Exception:  # noqa: BLE001
        pass
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
