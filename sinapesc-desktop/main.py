"""
Sinapesc Desktop — Controle de REAP
===================================

Copyright (c) 2024-2026 Gabriel Lourran Da Silva Costa
gabriel730costa@gmail.com
Software proprietário — ver LICENSE na raiz do repositório.

Ponto de entrada do programa para notebook/computador.
Execute:  python main.py
Gere .exe: build_exe.bat  (Windows)
"""

from __future__ import annotations

import sys
from pathlib import Path

# Garante imports locais ao rodar fora de um pacote instalado
ROOT = Path(__file__).resolve().parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


def main() -> None:
    if "--consulta-rgp-worker" in sys.argv:
        from controle.consulta_rgp_mpa import run_worker_cli

        raise SystemExit(run_worker_cli())

    if "--tk" in sys.argv:
        from ui import SinapescApp

        app = SinapescApp()
        app.mainloop()
        return

    from webapp.launcher import run_web_app

    run_web_app()


if __name__ == "__main__":
    main()
