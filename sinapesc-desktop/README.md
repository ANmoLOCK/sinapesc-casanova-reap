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

**v1.7.45** — Scroll da lista + import nome+CPF (TXT/XLSX/PDF).

**v1.7.44** — Filtros RGP oficiais + anti-cota na consulta em lote.

**v1.7.43** — Import PDF/XLS/TXT anti-cota + relatório HTML geral (senha Gov.br).

**v1.7.42** — 4 funções RGP (fila/alertas/export/vencidos).

**v1.7.41** — Senha Gov.br no Editar + formulário organizado.

**v1.7.40** — Lote, consulta automática e auditoria RGP.

## Consulta RGP — filtros

Chips e select usam só:

1. Ativo  
2. Aguardando análise  
3. Finalizada  
4. Rascunho  
5. Aguardando atualização  

O robô (consultar selecionados / todos) **captura a situação real do MPA** e grava na planilha (pode ser Suspenso, Não encontrado, etc.). O filtro não limita o que é salvo.

## Anti-cota (Sheets)

| Operação | Antes | Agora |
|----------|-------|-------|
| Cadastro em lote ~500 | 1 write + audit por linha | `upsert_lote_batch` (poucas chamadas) |
| Consulta automática em lote | listar + salvar + audit por CPF | 1 mapa de linhas + 1 update/CPF + audit só no início/fim |

Evita erros **429 / quota / rateLimitExceeded** (~60 writes/min).

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

**Download pronto:** [SinapescREAP-Windows-v1.7.45.zip](https://github.com/ANmoLOCK/sinapesc-casanova-reap/releases/download/v1.7.45/SinapescREAP-Windows-v1.7.45.zip)

## Estrutura

| Pasta / arquivo | Função |
|-----------------|--------|
| `web/` | Frontend HTML/CSS/JS (interface principal) |
| `webapp/` | API Python ↔ JavaScript (pywebview) |
| `ui/` | Tkinter legado (`--tk`) |
| `controle/` | Regras: calendário, pendências, relatório, backup, auditoria, Consulta RGP |
| `controle/consulta_rgp_funcoes/` | Fila, alertas, export, vencidos, import arquivo |
| `sheets/` | Cliente e serviço Google Sheets |
| `build_exe.spec` | PyInstaller (empacota `web/` + `assets/`) |
