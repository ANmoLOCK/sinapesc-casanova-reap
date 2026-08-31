# Site público Sinapesc (GitHub Pages)

Consulta **individual por CPF** — sem o notebook ligado.

## Links no ar

- Site: https://anmolock.github.io/sinapesc-casanova-reap/
- Consulta CPF: https://anmolock.github.io/sinapesc-casanova-reap/consulta.html
- **Consulta em lote (secretaria):** https://anmolock.github.io/sinapesc-casanova-reap/consulta-lote.html

> A lista pública foi removida do site (sem botão e sem exposição de quantidade de associados).
> Backup da página antiga: `_backup/lista.html`

## Consulta em lote

Página `consulta-lote.html` — uso interno da secretaria:

1. Carrega a planilha uma vez (mesmo método da consulta individual)
2. Cole CPFs (um por linha, ou separados por vírgula / `;`)
3. Consulta todos automaticamente
4. Resumo: encontrados / não encontrados / inválidos
5. Expanda «Ver meses» por sócio; filtre por ano REAP (opcional)
6. Exporte CSV ou imprima

Não coloque QR desta página na sede — use só a consulta individual (`consulta.html`).

Planilha (modo leitor):  
https://docs.google.com/spreadsheets/d/1ydaWGF53VTkXyIyhf5XKJek5PKMDZO1_cD3CrRePft4/edit?usp=sharing

## No EXE

Em **Configurações**, cole **somente a raiz** (sem `/consulta.html`):

```text
https://anmolock.github.io/sinapesc-casanova-reap
```

Depois: **Salvar** → **Gerar QRs do site** → **QR Consulta CPF** → imprimir.
