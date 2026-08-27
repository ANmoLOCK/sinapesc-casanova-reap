# Sinapesc Desktop

Programa Windows (**pywebview** + Google Sheets) para controle REAP da secretaria.

**Licença:** software proprietário de **Gabriel Lourran Da Silva Costa** — ver [`../LICENSE`](../LICENSE).

A interface padrão é **HTML/CSS** dentro da janela (WebView2), idêntica ao mockup aprovado. Tkinter legado: `python main.py --tk`.

| Documento | Link |
|-----------|------|
| README principal (download, site, versões) | [../README.md](../README.md) |
| Changelog | [../CHANGELOG.md](../CHANGELOG.md) |
| API Google | [COMO_INTEGRAR_API.md](./COMO_INTEGRAR_API.md) |
| Site público | [../site-publico/](../site-publico/) |

## Versão

**v1.7.21** — Município REAP só conferência/relatório; declaração usa só o do Defeso.

## Requisitos (Windows)

- Windows 10 ou 11
- **WebView2 Runtime** (Microsoft Edge) — na maioria dos PCs já está instalado
- Conta de serviço Google + planilha compartilhada

## Desenvolvimento

```bash
pip install -r requirements.txt
python main.py          # UI web (padrão)
python main.py --tk     # Tkinter legado
```

## Build EXE (Windows)

```bash
build_exe.bat
```

Gera `dist\SinapescREAP.exe` e pasta `release\` pronta para zipar.

Ou dispare o workflow [build-windows-exe.yml](../.github/workflows/build-windows-exe.yml) (branch `main` ou tag `v*`).

**Download pronto:** [SinapescREAP-Windows-v1.7.3.zip](https://github.com/ANmoLOCK/sinapesc-casanova-reap/releases/download/v1.7.3/SinapescREAP-Windows-v1.7.3.zip)

## Estrutura

| Pasta / arquivo | Função |
|-----------------|--------|
| `web/` | Frontend HTML/CSS/JS (interface principal) |
| `webapp/` | API Python ↔ JavaScript (pywebview) |
| `ui/` | Tkinter legado (`--tk`) |
| `controle/` | Regras: calendário, pendências, relatório, backup, auditoria |
| `sheets/` | Cliente e serviço Google Sheets |
| `build_exe.spec` | PyInstaller (empacota `web/` + `assets/`) |
