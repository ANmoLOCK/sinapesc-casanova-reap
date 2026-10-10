"""
Consulta pública MPA em processo/janela isolada (não derruba o EXE principal).

Fluxo confiável:
1. Abre o site oficial em janela pywebview (subprocesso do EXE).
2. Injeta script SÍNCRONO que inicia a consulta async e grava em window.__sinapescRgp.
3. Python faz POLLING até done=true (evaluate_js NÃO espera Promise async).
4. Grava JSON de resultado e encerra.

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
from typing import Any, Dict, Optional, Protocol

from controle.consulta_rgp import extract_situacao_from_mpa, flatten_mpa_payload, normalize_situacao
from ui.formatters import normalize_cpf, only_digits

MPA_CONSULTA_URL = "https://pesqbrasil-pescadorprofissional.mpa.gov.br/acesso-externo"
MPA_RECAPTCHA_SITE_KEY = "6LeJP-srAAAAAFdZMYINP6CJ4COI_MAzFvk_0gs1"
WORKER_FLAG = "--consulta-rgp-worker"


class _EvalWindow(Protocol):
    def evaluate_js(self, script: str) -> Any: ...


def _js_start_consulta(cpf: str) -> str:
    """
    Dispara a consulta em background e devolve true imediatamente.

    Resultado fica em window.__sinapescRgp = {done, ok, data|error}.
    Isso evita depender do pywebview aguardar Promise de async IIFE.
    """
    cpf_js = json.dumps(normalize_cpf(cpf) or only_digits(cpf))
    key_js = json.dumps(MPA_RECAPTCHA_SITE_KEY)
    return f"""
(function() {{
  window.__sinapescRgp = {{ done: false, ok: false, error: "Consultando…" }};
  (async function() {{
    try {{
      const cpf = {cpf_js};
      const siteKey = {key_js};

      async function waitGrecaptcha(maxMs) {{
        const start = Date.now();
        while (Date.now() - start < maxMs) {{
          if (window.grecaptcha && typeof window.grecaptcha.execute === "function") {{
            await new Promise((resolve, reject) => {{
              try {{ grecaptcha.ready(() => resolve(true)); }}
              catch (e) {{ reject(e); }}
            }});
            return true;
          }}
          await new Promise((r) => setTimeout(r, 350));
        }}
        return false;
      }}

      if (!(await waitGrecaptcha(10000))) {{
        await new Promise((resolve, reject) => {{
          const s = document.createElement("script");
          s.src = "https://www.google.com/recaptcha/api.js?render=" + siteKey;
          s.async = true;
          s.onload = () => resolve(true);
          s.onerror = () => reject(new Error("Falha ao carregar reCAPTCHA"));
          document.head.appendChild(s);
        }});
        if (!(await waitGrecaptcha(25000))) {{
          window.__sinapescRgp = {{
            done: true, ok: false,
            error: "reCAPTCHA não carregou. Verifique a internet e tente de novo."
          }};
          return;
        }}
      }}

      const token = await new Promise((resolve, reject) => {{
        try {{
          grecaptcha.ready(() => {{
            grecaptcha.execute(siteKey, {{ action: "submit" }})
              .then(resolve).catch(reject);
          }});
        }} catch (e) {{ reject(e); }}
      }});

      const params = new URLSearchParams();
      params.append("cpf", cpf);
      params.append("recaptchaToken", token);

      // Front oficial: path + URLSearchParams (sem '?')
      const urls = [
        "api/consulta-publica/pesquisa/" + params.toString(),
        "/api/consulta-publica/pesquisa/" + params.toString(),
        "api/consulta-publica/pesquisa/?" + params.toString()
      ];

      let lastErr = "Consulta MPA sem resposta.";
      for (const url of urls) {{
        try {{
          const res = await fetch(url, {{ cache: "no-store", credentials: "same-origin" }});
          let data = null;
          try {{ data = await res.json(); }} catch (_) {{ data = null; }}
          if (!res.ok) {{
            const msg = (data && (data.error || data.message || data.titulo)) || ("HTTP " + res.status);
            const low = String(msg).toLowerCase();
            if (low.includes("não foi encontrado") || low.includes("nao foi encontrado") || low.includes("inválido") || low.includes("invalido")) {{
              window.__sinapescRgp = {{
                done: true, ok: true,
                data: {{ sem_registros: true, situacao: "Não encontrado", cpf: cpf, error: msg }}
              }};
              return;
            }}
            lastErr = msg;
            continue;
          }}
          if (!data || typeof data !== "object") {{
            lastErr = "JSON inválido da API MPA.";
            continue;
          }}
          if (Array.isArray(data.content) && data.content.length === 0) {{
            window.__sinapescRgp = {{
              done: true, ok: true,
              data: {{ sem_registros: true, situacao: "Não encontrado", cpf: cpf }}
            }};
            return;
          }}
          window.__sinapescRgp = {{ done: true, ok: true, data: data, url: url }};
          return;
        }} catch (e) {{
          lastErr = String(e && e.message ? e.message : e);
        }}
      }}
      window.__sinapescRgp = {{ done: true, ok: false, error: lastErr }};
    }} catch (e) {{
      window.__sinapescRgp = {{
        done: true, ok: false,
        error: String(e && e.message ? e.message : e)
      }};
    }}
  }})();
  return true;
}})()
"""


def _js_poll_resultado() -> str:
    return """
(function() {
  try {
    return JSON.stringify(window.__sinapescRgp || { done: false, ok: false, error: "aguardando" });
  } catch (e) {
    return JSON.stringify({ done: false, ok: false, error: String(e) });
  }
})()
"""


# Compat: testes antigos ainda importam _js_consultar
def _js_consultar(cpf: str) -> str:
    return _js_start_consulta(cpf)


def _parse_worker_result(raw: Any) -> Dict[str, Any]:
    if raw is None:
        return {"ok": False, "error": "Sem resposta da janela MPA.", "done": True}
    if isinstance(raw, dict):
        return raw
    text = str(raw).strip()
    if not text:
        return {"ok": False, "error": "Resposta vazia da janela MPA.", "done": True}
    if text in ("true", "True"):
        return {"done": False, "ok": False, "error": "aguardando"}
    try:
        data = json.loads(text)
    except json.JSONDecodeError:
        try:
            data = json.loads(json.loads(text))
        except Exception:  # noqa: BLE001
            return {"ok": False, "error": f"Resposta inválida: {text[:200]}", "done": True}
    if isinstance(data, dict):
        return data
    return {"ok": False, "error": "Formato inesperado da consulta.", "done": True}


def _enrich_ok_result(data: Dict[str, Any], digits: str) -> Dict[str, Any]:
    flat = flatten_mpa_payload(data)
    situacao = extract_situacao_from_mpa(flat)
    return {
        "ok": True,
        "data": flat,
        "situacao": situacao,
        "cpf": digits,
    }


def drive_consulta_on_window(
    window: _EvalWindow,
    cpf: str,
    *,
    timeout_s: float = 100.0,
    poll_s: float = 0.45,
    settle_s: float = 3.0,
) -> Dict[str, Any]:
    """
    Protocolo estável: start sync + poll JSON em window.__sinapescRgp.

    Usado pelo worker real e pelos testes com FakeWindow.
    """
    digits = normalize_cpf(cpf)
    if len(digits) != 11:
        return {"ok": False, "error": "CPF inválido (11 dígitos)."}

    if settle_s > 0:
        time.sleep(settle_s)

    last_err = "Falha ao iniciar consulta."
    started = False
    for attempt in range(4):
        try:
            window.evaluate_js(_js_start_consulta(digits))
            started = True
            break
        except Exception as exc:  # noqa: BLE001
            last_err = str(exc)
            time.sleep(1.2 + attempt * 0.4)
    if not started:
        return {"ok": False, "error": f"Não iniciou script MPA: {last_err}", "cpf": digits}

    deadline = time.time() + timeout_s
    while time.time() < deadline:
        try:
            raw = window.evaluate_js(_js_poll_resultado())
            parsed = _parse_worker_result(raw)
        except Exception as exc:  # noqa: BLE001
            last_err = str(exc)
            time.sleep(poll_s)
            continue

        if parsed.get("done"):
            if parsed.get("ok") and isinstance(parsed.get("data"), dict):
                return _enrich_ok_result(parsed["data"], digits)
            return {
                "ok": False,
                "error": str(parsed.get("error") or "Consulta MPA sem resultado."),
                "cpf": digits,
                "raw": parsed.get("raw"),
            }
        last_err = str(parsed.get("error") or "Aguardando resposta MPA…")
        time.sleep(poll_s)

    return {"ok": False, "error": f"Tempo esgotado na consulta MPA. ({last_err})", "cpf": digits}


def run_consulta_in_webview(cpf: str, *, timeout_s: float = 120.0) -> Dict[str, Any]:
    """Abre janela isolada no site MPA, consulta e fecha (bloqueante)."""
    digits = normalize_cpf(cpf)
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
            w = window_ref.get("w")
            if w is None:
                finish({"ok": False, "error": "Janela MPA não disponível."})
                return
            try:
                finish(drive_consulta_on_window(w, digits, timeout_s=timeout_s - 5))
            except Exception as exc:  # noqa: BLE001
                finish({"ok": False, "error": str(exc), "cpf": digits})

        threading.Thread(target=work, daemon=True).start()

    windows = []
    try:
        windows = list(getattr(webview, "windows", []) or [])
    except Exception:  # noqa: BLE001
        windows = []
    already = len(windows) > 0

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
        # Edge no Windows (mesmo motor do EXE principal)
        gui = "edgechromium" if sys.platform == "win32" else None
        if gui:
            webview.start(gui=gui)
        else:
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
    Dispara consulta em subprocesso separado para não derrubar o app principal.
    """
    digits = normalize_cpf(cpf)
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
    if os.name == "nt" and hasattr(subprocess, "CREATE_NEW_PROCESS_GROUP"):
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
        return {"ok": False, "error": f"Não iniciou worker MPA: {exc}"}

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
        for p in (out_path, err_path):
            try:
                p.unlink(missing_ok=True)
            except OSError:
                pass
        return {"ok": False, "error": "Consulta MPA excedeu o tempo (subprocesso)."}

    try:
        err_f.close()
    except Exception:  # noqa: BLE001
        pass

    log_tail = ""
    try:
        log_tail = err_path.read_text(encoding="utf-8", errors="ignore")[-600:]
    except OSError:
        log_tail = ""

    try:
        text = out_path.read_text(encoding="utf-8")
        data = json.loads(text) if text.strip() else {"ok": False, "error": "Arquivo vazio do worker."}
    except (OSError, json.JSONDecodeError) as exc:
        data = {
            "ok": False,
            "error": f"Não foi possível ler resultado do worker: {exc}"
            + (f" | log: {log_tail}" if log_tail else ""),
        }
    finally:
        for p in (out_path, err_path):
            try:
                p.unlink(missing_ok=True)
            except OSError:
                pass

    if not isinstance(data, dict):
        return {"ok": False, "error": "Resultado inválido do worker."}

    if data.get("ok"):
        raw = data.get("data") if isinstance(data.get("data"), dict) else {}
        flat = flatten_mpa_payload(raw)
        sit = extract_situacao_from_mpa(flat)
        if not sit or sit == "Não consultado":
            sit = normalize_situacao(str(data.get("situacao") or ""))
        data["data"] = flat
        data["situacao"] = sit
        data["cpf"] = digits
        data["ok"] = True
        return data

    err = str(data.get("error") or "Falha na consulta MPA.")
    low = err.lower()
    # Trata "não encontrado" do MPA como consulta concluída (grava na planilha).
    if "não foi encontrado" in low or "nao foi encontrado" in low:
        return {
            "ok": True,
            "data": {"sem_registros": True, "situacao": "Não encontrado", "cpf": digits},
            "situacao": "Não encontrado",
            "cpf": digits,
        }
    if log_tail and "log:" not in err:
        err = f"{err} | log: {log_tail}"
    return {"ok": False, "error": err, "cpf": digits}


def abrir_site_mpa_no_navegador(cpf: str = "") -> None:
    """Abre o site oficial no Edge/Chrome (fallback manual)."""
    import webbrowser

    digits = normalize_cpf(cpf) or only_digits(cpf)
    try:
        webbrowser.open(MPA_CONSULTA_URL)
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
