# Changelog — Sinapesc REAP (desktop)

Todas as versões notáveis do programa Windows.

Formato: mais recente primeiro.

---

---

---

## [v1.7.41] — 2026-09-04 — Senha Gov.br no Editar + formulário organizado

**Tag:** [`v1.7.41`](https://github.com/ANmoLOCK/sinapesc-casanova-reap/releases/tag/v1.7.41)  
**Download:** https://github.com/ANmoLOCK/sinapesc-casanova-reap/releases/download/v1.7.41/SinapescREAP-Windows-v1.7.41.zip

- Editar sócio mostra a senha Gov.br (antes só no cadastro novo)
- Formulário em seções: dados do sócio · acesso Gov.br · observação
- Salvar no Editar grava a senha na aba Config da planilha
- Botão «Editar» abre o modal completo (não só o painel lateral)

## [v1.7.40] — 2026-09-04 — Lote, consulta automática e auditoria RGP

**Tag:** [`v1.7.40`](https://github.com/ANmoLOCK/sinapesc-casanova-reap/releases/tag/v1.7.40)  
**Download:** https://github.com/ANmoLOCK/sinapesc-casanova-reap/releases/download/v1.7.40/SinapescREAP-Windows-v1.7.40.zip

- Cadastro em lote na Consulta RGP (mesmo quadro do REAP)
- Consulta automática em lote (todos ou selecionados) com estimativa de tempo (~20 min / 500)
- Header global como nos outros módulos (sem chip ADMIN)
- Aba Auditoria na planilha Consulta RGP (captura alterações)

## [v1.7.39] — 2026-09-04 — Rodapé global na Consulta RGP

**Tag:** [`v1.7.39`](https://github.com/ANmoLOCK/sinapesc-casanova-reap/releases/tag/v1.7.39)  
**Download:** https://github.com/ANmoLOCK/sinapesc-casanova-reap/releases/download/v1.7.39/SinapescREAP-Windows-v1.7.39.zip

- Consulta RGP volta a exibir o **mesmo rodapé** dos outros módulos
- Status (ex.: «Carregando Consulta RGP…», «Consultando RGP no MPA…»), usuário, conexão e crédito do autor


**Tag:** [`v1.7.38`](https://github.com/ANmoLOCK/sinapesc-casanova-reap/releases/tag/v1.7.38)  
**Download:** https://github.com/ANmoLOCK/sinapesc-casanova-reap/releases/download/v1.7.38/SinapescREAP-Windows-v1.7.38.zip

- JS envia `JSON.stringify({id,cpf})` — sem coerção numérica na ponte
- `normalize_cpf` recupera `95453325900` → `09545332590` e `56106905010` → `05610690501`
  (este último passava no dígito verificador por coincidência e quebrava no MPA)
- Regrava CPF normalizado na planilha ao consultar

## [v1.7.37] — 2026-09-04 — CPF inválido (bateria + float/ponte)

**Tag:** [`v1.7.37`](https://github.com/ANmoLOCK/sinapesc-casanova-reap/releases/tag/v1.7.37)  
**Download:** https://github.com/ANmoLOCK/sinapesc-casanova-reap/releases/download/v1.7.37/SinapescREAP-Windows-v1.7.37.zip

- Causa raiz: `only_digits(str(9545332590.0))` → `95453325900` (11 dígitos errados)
- `normalize_cpf` trata float, `"….0"`, científica e zero à esquerda
- `cadastrar_consulta_rgp` e consulta MPA usam normalize; JS chama com objeto `{id,cpf}`
- Bateria `test_cpf_consulta_battery.py` (095… / 056… em todos os formatos)

## [v1.7.36] — 2026-09-04 — CPF zero à esquerda + UI compacta

**Tag:** [`v1.7.36`](https://github.com/ANmoLOCK/sinapesc-casanova-reap/releases/tag/v1.7.36)  
**Download:** https://github.com/ANmoLOCK/sinapesc-casanova-reap/releases/download/v1.7.36/SinapescREAP-Windows-v1.7.36.zip

- `normalize_cpf`: recupera zero à esquerda perdido (ex.: `9545332590` → `09545332590`)
- Consulta MPA / cadastro / planilha usam CPF normalizado (11 dígitos)
- Testado no site MPA: `095.453.325-90` e `056.106.905-01` retornam situação; sem zero falha
- UI Consulta RGP compactada (header, KPIs, linhas da tabela) para mais área útil

## [v1.7.35] — 2026-09-04 — Scroll estável + detalhes em modal

**Tag:** [`v1.7.35`](https://github.com/ANmoLOCK/sinapesc-casanova-reap/releases/tag/v1.7.35)  
**Download:** https://github.com/ANmoLOCK/sinapesc-casanova-reap/releases/download/v1.7.35/SinapescREAP-Windows-v1.7.35.zip

- Remove painel lateral que apertava/cortava a tabela
- KPIs + tabela em área com scroll próprio (`.rgp-body-scroll`)
- Clique na linha, **Consultar** ou **Editar** abre modal largo (Resumo / Dados cadastrais)
- Tabela em largura total; mais espaço para colunas e ações

## [v1.7.34] — 2026-09-04 — UI reformulada + senha no cadastro

**Tag:** [`v1.7.34`](https://github.com/ANmoLOCK/sinapesc-casanova-reap/releases/tag/v1.7.34)  
**Download:** https://github.com/ANmoLOCK/sinapesc-casanova-reap/releases/download/v1.7.34/SinapescREAP-Windows-v1.7.34.zip

- Remove campo/botão «Salvar senha» do topo do módulo
- Senha Gov.br só no modal **Cadastrar sócio** (grava na planilha Config)
- **Editar** abre o painel lateral completo (aba Dados cadastrais)
- Abas Resumo / Dados cadastrais; layout folgado alinhado ao mockup

## [v1.7.33] — 2026-09-04 — Senha Gov.br na planilha

**Tag:** [`v1.7.33`](https://github.com/ANmoLOCK/sinapesc-casanova-reap/releases/tag/v1.7.33)  
**Download:** https://github.com/ANmoLOCK/sinapesc-casanova-reap/releases/download/v1.7.33/SinapescREAP-Windows-v1.7.33.zip

- Senha Gov.br gravada na aba **Config** da planilha Consulta RGP (`chave|valor`)
- Cadastros/edição já iam na aba **ConsultaRGP**; preferências também ficam na planilha
- Fonte da verdade = Google Sheets (não só config local)

## [v1.7.32] — 2026-09-04 — Layout folgado + senha Gov.br

**Tag:** [`v1.7.32`](https://github.com/ANmoLOCK/sinapesc-casanova-reap/releases/tag/v1.7.32)  
**Download:** https://github.com/ANmoLOCK/sinapesc-casanova-reap/releases/download/v1.7.32/SinapescREAP-Windows-v1.7.32.zip

- Remove barra CONFIGURAÇÕES com toggles (Gov.br / Importar REAP)
- Campo **Senha Gov.br** no topo (com Salvar senha) + Cadastrar sócio
- Layout espaçoso alinhado ao mockup (header, KPIs, linhas da tabela, painel)

## [v1.7.31] — 2026-09-04 — Corrige consulta MPA (polling + gravação)

**Tag:** [`v1.7.31`](https://github.com/ANmoLOCK/sinapesc-casanova-reap/releases/tag/v1.7.31)  
**Download:** https://github.com/ANmoLOCK/sinapesc-casanova-reap/releases/download/v1.7.31/SinapescREAP-Windows-v1.7.31.zip

- Consulta MPA: script síncrono + polling (pywebview não espera Promise async)
- Botão Consultar da tabela dispara a consulta de verdade e grava a situação
- Falha não abre mais o navegador sozinha — use «Abrir site MPA» só se precisar
- Trata «não encontrado» e envelopes `content[]` da API pública
- Testes FakeWindow de polling antes do build

## [v1.7.30] — 2026-09-04 — Consulta MPA grava situação + UI folgada

**Tag:** [`v1.7.30`](https://github.com/ANmoLOCK/sinapesc-casanova-reap/releases/tag/v1.7.30)  
**Download:** https://github.com/ANmoLOCK/sinapesc-casanova-reap/releases/download/v1.7.30/SinapescREAP-Windows-v1.7.30.zip

- Worker MPA: espera reCAPTCHA, múltiplas URLs, parse de situação (texto/número)
- Após consulta, grava situação/última consulta e atualiza lista + KPIs
- Cadastro → consulta automática com atraso seguro na fila
- Layout menos apertado (header, KPIs, tabela, modal)

## [v1.7.29] — 2026-09-04 — Consulta RGP UI fiel ao mockup

**Tag:** [`v1.7.29`](https://github.com/ANmoLOCK/sinapesc-casanova-reap/releases/tag/v1.7.29)  
**Download:** https://github.com/ANmoLOCK/sinapesc-casanova-reap/releases/download/v1.7.29/SinapescREAP-Windows-v1.7.29.zip

- Layout full-bleed (sem limite 1100px / sem header duplo achatado)
- Espaçamentos e tipografia alinhados ao mockup
- KPIs, tabela, sidebar e modal com altura/respiro corretos

## [v1.7.28] — 2026-09-04 — Cadastro sócio sólido

**Tag:** [`v1.7.28`](https://github.com/ANmoLOCK/sinapesc-casanova-reap/releases/tag/v1.7.28)  
**Download:** https://github.com/ANmoLOCK/sinapesc-casanova-reap/releases/download/v1.7.28/SinapescREAP-Windows-v1.7.28.zip

- Corrige modal quase transparente (`modal-card` sem estilo)
- Formulário opaco branco, labels e inputs organizados em grade
- Edição no painel lateral com o mesmo padrão

## [v1.7.27] — 2026-09-04 — Consulta RGP UI (opções escolhidas)

**Tag:** [`v1.7.27`](https://github.com/ANmoLOCK/sinapesc-casanova-reap/releases/tag/v1.7.27)  
**Download:** https://github.com/ANmoLOCK/sinapesc-casanova-reap/releases/download/v1.7.27/SinapescREAP-Windows-v1.7.27.zip

- Header com usuário logado real
- Chips rápidos de situação + coluna Município
- Consultar abre painel; MPA só no painel; Editar abre formulário
- Painel sem abas com **Editar cadastro**
- Cadastrar sócio dispara consulta MPA automática

## [v1.7.26] — 2026-09-04 — Consulta RGP cadastro local (sem sync REAP)

**Tag:** [`v1.7.26`](https://github.com/ANmoLOCK/sinapesc-casanova-reap/releases/tag/v1.7.26)  
**Download:** https://github.com/ANmoLOCK/sinapesc-casanova-reap/releases/download/v1.7.26/SinapescREAP-Windows-v1.7.26.zip

- Corrige erro de cota (quota 60) ao abrir o módulo (loop de leitura da planilha)
- Botão **Cadastrar sócio** (nome, CPF, município, telefone, observação)
- Sem importação Consulta ↔ REAP nesta etapa
- UI fiel ao mockup (header navy, KPIs, tabela, sidebar)

## [v1.7.25] — 2026-09-04 — Consulta RGP independente

**Tag:** [`v1.7.25`](https://github.com/ANmoLOCK/sinapesc-casanova-reap/releases/tag/v1.7.25)  
**Download:** https://github.com/ANmoLOCK/sinapesc-casanova-reap/releases/download/v1.7.25/SinapescREAP-Windows-v1.7.25.zip

- Módulo Consulta opera sozinho: importação manual de registros
- UI alinhada ao mockup

## [v1.7.24] — 2026-09-04 — Módulo Consulta RGP
## [v1.7.24] — 2026-09-04 — Módulo Consulta RGP

**Tag:** [`v1.7.24`](https://github.com/ANmoLOCK/sinapesc-casanova-reap/releases/tag/v1.7.24)  
**Download:** https://github.com/ANmoLOCK/sinapesc-casanova-reap/releases/download/v1.7.24/SinapescREAP-Windows-v1.7.24.zip

- Home: 4º card **Módulo Consulta** (Consulta RGP)
- Planilha/aba `ConsultaRGP` + sync a partir do REAP
- Consulta no site MPA em processo/janela isolada (não derruba o EXE)
- Importação REAP (município+telefone) e Defeso (CPF+nome) **somente se Ativo**

## [v1.7.23] — 2026-08-31 — Município REAP isolado na tela

**Tag:** [`v1.7.23`](https://github.com/ANmoLOCK/sinapesc-casanova-reap/releases/tag/v1.7.23)  
**Download:** https://github.com/ANmoLOCK/sinapesc-casanova-reap/releases/download/v1.7.23/SinapescREAP-Windows-v1.7.23.zip

### O que entrou
- `load_pessoas` não preenche mais REAP com município/UF/tel vindos do Defeso
- Lista Defeso: filtro e exibição usam município REAP; declaração Defeso fica separada
- Salvar ficha Defeso devolve `municipio_reap` lido da planilha REAP (campo readonly estável)

---

## [v1.7.22] — 2026-08-28 — Defeso não altera planilha REAP

**Tag:** [`v1.7.22`](https://github.com/ANmoLOCK/sinapesc-casanova-reap/releases/tag/v1.7.22)  
**Download:** https://github.com/ANmoLOCK/sinapesc-casanova-reap/releases/download/v1.7.22/SinapescREAP-Windows-v1.7.22.zip

### O que entrou
- Salvar ficha Defeso deixa de chamar `update_pessoa_municipio` no REAP
- Sync não copia mais município Defeso → REAP
- REAP município/telefone: só leitura para relatório Defeso e campo readonly na tela

---

## [v1.7.21] — 2026-08-27 — Município REAP fora da declaração

**Tag:** [`v1.7.21`](https://github.com/ANmoLOCK/sinapesc-casanova-reap/releases/tag/v1.7.21)  
**Download:** https://github.com/ANmoLOCK/sinapesc-casanova-reap/releases/download/v1.7.21/SinapescREAP-Windows-v1.7.21.zip

### O que entrou
- Município cadastrado no REAP aparece no Defeso só para **conferir** e no **relatório**
- Declaração usa apenas o município digitado na ficha Defeso
- Sync/salvar sócio não gravam mais o município REAP no campo da declaração

---

## [v1.7.20] — 2026-08-27 — Filtros relatório, atalhos contato, sync cota

**Tag:** [`v1.7.20`](https://github.com/ANmoLOCK/sinapesc-casanova-reap/releases/tag/v1.7.20)  
**Download:** https://github.com/ANmoLOCK/sinapesc-casanova-reap/releases/download/v1.7.20/SinapescREAP-Windows-v1.7.20.zip

### O que entrou
- Relatório REAP: escolher **localidade** (município) antes de gerar
- Relatório / lista Defeso: localidade + **entrada confirmada** + **com parcela disponível**
- Ficha Defeso: bloco de **atalhos** com até 3 telefones e 3 e-mails gravados no PC («Usar» preenche a declaração)
- **Sinc. Planilhas**: deixa de fazer 1 leitura/escrita por sócio; usa batch + retry em 429/quota (erro com muitos registros)

---

## [v1.7.19] — 2026-08-25 — Abrir declaração/pacote no navegador de verdade

**Tag:** [`v1.7.19`](https://github.com/ANmoLOCK/sinapesc-casanova-reap/releases/tag/v1.7.19)  
**Download:** https://github.com/ANmoLOCK/sinapesc-casanova-reap/releases/download/v1.7.19/SinapescREAP-Windows-v1.7.19.zip

### O que entrou
- Ao gerar **declaração** ou **juntar PDF**, abre no Edge/Chrome pelos caminhos reais do Windows
- Se não achar o navegador no PATH, cria um HTML ao lado do PDF (`.html` sempre abre no navegador, como antes) — não depende do Acrobat

---

## [v1.7.18] — 2026-08-25 — Declaração no navegador + limpa PDF antigo

**Tag:** [`v1.7.18`](https://github.com/ANmoLOCK/sinapesc-casanova-reap/releases/tag/v1.7.18)  
**Download:** https://github.com/ANmoLOCK/sinapesc-casanova-reap/releases/download/v1.7.18/SinapescREAP-Windows-v1.7.18.zip

### O que entrou
- Gerar declaração / pacote PDF abre de novo no **navegador** (Edge/Chrome), como o relatório
- Ao regenerar a declaração (troca de fonte ou novos dados), apaga o PDF/HTML anterior do mesmo CPF e deixa só o arquivo novo

---

## [v1.7.17] — 2026-08-24 — Bateria final: bugs Defeso/REAP

**Tag:** [`v1.7.17`](https://github.com/ANmoLOCK/sinapesc-casanova-reap/releases/tag/v1.7.17)  
**Download:** https://github.com/ANmoLOCK/sinapesc-casanova-reap/releases/download/v1.7.17/SinapescREAP-Windows-v1.7.17.zip

### O que entrou
- Declaração/Juntar PDF gravam o formulário atual (não ignoram edições)
- Parcelas 1°–4° entram no auto-save de declaração/pacote
- Salvar sócio sincroniza município **e** telefone no Defeso
- Fallback de telefone no REAP usa `telefoneReap` da planilha Defeso
- Filtro de localidade do relatório alinhado com a lista
- Campo município editável da ficha volta a ser respeitado no save

---

## [v1.7.16] — 2026-08-24 — Fix salvar ficha Defeso (payload pywebview)

**Tag:** [`v1.7.16`](https://github.com/ANmoLOCK/sinapesc-casanova-reap/releases/tag/v1.7.16)  
**Download:** https://github.com/ANmoLOCK/sinapesc-casanova-reap/releases/download/v1.7.16/SinapescREAP-Windows-v1.7.16.zip

### O que entrou
- Fix: **Salvar na planilha** no Defeso Fácil falhava com erro de payload (objeto JS inacessível na thread)
- Dados da ficha agora são convertidos/serializados antes do salvamento assíncrono

---

## [v1.7.15] — 2026-08-23 — Relatório sem sócio fantasma + rodapé de volta

**Tag:** [`v1.7.15`](https://github.com/ANmoLOCK/sinapesc-casanova-reap/releases/tag/v1.7.15)  
**Download:** https://github.com/ANmoLOCK/sinapesc-casanova-reap/releases/download/v1.7.15/SinapescREAP-Windows-v1.7.15.zip

### O que entrou
- Relatório HTML Defeso: **só sócios que existem na planilha REAP** (ignora fichas órfãs)
- Rodapé com crédito do autor **restaurado** na tela do programa

---

## [v1.7.14] — 2026-08-23 — Parcelas 1°–4°, tel/município REAP no relatório

**Tag:** [`v1.7.14`](https://github.com/ANmoLOCK/sinapesc-casanova-reap/releases/tag/v1.7.14)  
**Download:** https://github.com/ANmoLOCK/sinapesc-casanova-reap/releases/download/v1.7.14/SinapescREAP-Windows-v1.7.14.zip

### O que entrou
- Caixa profissional de **4 parcelas** (1°–4°) na ficha Defeso → vai pro relatório HTML
- Relatório: **município e telefone do REAP**; do Defeso só rua, nº, bairro, UF e CEP
- Telefone REAP aparece na lista e na ficha Defeso (campo só leitura)
- Checkbox **Entrada confirmada** corrigido

---

## [v1.7.13] — 2026-08-23 — REAP UF/tel + relatório Defeso + parcelas

**Tag:** [`v1.7.13`](https://github.com/ANmoLOCK/sinapesc-casanova-reap/releases/tag/v1.7.13)  
**Download:** https://github.com/ANmoLOCK/sinapesc-casanova-reap/releases/download/v1.7.13/SinapescREAP-Windows-v1.7.13.zip

### O que entrou
- **REAP (meses):** ao abrir o sócio, mostra município, **UF** e **telefone**
- **REAP:** filtro por **Localidade** (município)
- **Defeso Fácil:** relatório **HTML** (nome, CPF, tel REAP, endereço Defeso, parcelas)
- **Defeso:** datas de parcelas recebidas + caixinha **Entrada confirmada**
- Sync **Sinc. Planilhas** também copia telefone REAP → coluna `telefoneReap` no Defeso

---

## [v1.7.12] — 2026-08-23 — Número + município no lote/atalhos

**Tag:** [`v1.7.12`](https://github.com/ANmoLOCK/sinapesc-casanova-reap/releases/tag/v1.7.12)  
**Download:** https://github.com/ANmoLOCK/sinapesc-casanova-reap/releases/download/v1.7.12/SinapescREAP-Windows-v1.7.12.zip

### O que entrou
- Campo **Número (telefone)** no cadastro/edição de sócio (+ Sócio)
- **Município** e **Número** também no **Cadastro em lote** e no lote aberto por **Config.Atalhos**
- Coluna `telefone` na planilha Pessoas (migração automática)
- Colar lista: `Nome;CPF;Município;Número`

---

## [v1.7.11] — 2026-08-23 — Filtros Defeso + sync município REAP ↔ Defeso

**Tag:** [`v1.7.11`](https://github.com/ANmoLOCK/sinapesc-casanova-reap/releases/tag/v1.7.11)  
**Download:** https://github.com/ANmoLOCK/sinapesc-casanova-reap/releases/download/v1.7.11/SinapescREAP-Windows-v1.7.11.zip

### O que entrou
- **Defeso Fácil:** filtros **Localidade**, **Entradas confirmadas** e botão **↻ Atualizar**
- Coluna **município** na planilha REAP (Pessoas) — campo no cadastro de sócio
- **Sinc. Planilhas** no módulo Sócios/REAP (ao lado de Lista pública): copia município REAP → Defeso e preenche vazios no REAP a partir do Defeso
- Ao salvar ficha Defeso ou sócio, município sincroniza automaticamente entre os dois módulos

---

## [v1.7.10] — 2026-08-22 — Pacote PDF Defeso + ícone de letra

**Tag:** [`v1.7.10`](https://github.com/ANmoLOCK/sinapesc-casanova-reap/releases/tag/v1.7.10)  
**Download:** https://github.com/ANmoLOCK/sinapesc-casanova-reap/releases/download/v1.7.10/SinapescREAP-Windows-v1.7.10.zip

### O que entrou
- Engrenagem da declaração trocada por ícone **Aa** (letra), no azul do app
- Botão **Juntar PDF** ao lado de Gerar declaração
- Caixinhas: Declaração · Identidade · Carteira de pescador · CAF → um único PDF

---

## [v1.7.9] — 2026-08-22 — Declaração com letra de mão (caneta)

**Tag:** [`v1.7.9`](https://github.com/ANmoLOCK/sinapesc-casanova-reap/releases/tag/v1.7.9)  
**Download:** https://github.com/ANmoLOCK/sinapesc-casanova-reap/releases/download/v1.7.9/SinapescREAP-Windows-v1.7.9.zip

### O que entrou
- Texto da declaração desenhado **letra a letra** com leve variação (tamanho/altura) — parece escrito à mão
- Fontes: **Manuscrita (Allura)** padrão · **Letra de bairro** · **Mão suja** · Caderno · Times
- Tamanho maior (~18–22) e azul de caneta igual aos previews do chat

---

## [v1.7.8] — 2026-08-22 — Fonte da declaração passa a gravar de verdade

**Tag:** [`v1.7.8`](https://github.com/ANmoLOCK/sinapesc-casanova-reap/releases/tag/v1.7.8)  
**Download:** https://github.com/ANmoLOCK/sinapesc-casanova-reap/releases/download/v1.7.8/SinapescREAP-Windows-v1.7.8.zip

### O que entrou
- Fix: engrenagem ⚙ salvava a fonte no AppData, mas a impressão lia só o `config.json` ao lado do EXE — sempre saía a mesma fonte
- Agora o AppData sobrescreve as prefs da UI; a impressão também envia a fonte escolhida na hora

---

## [v1.7.7] — 2026-08-22 — Declaração sempre no PDF oficial

**Tag:** [`v1.7.7`](https://github.com/ANmoLOCK/sinapesc-casanova-reap/releases/tag/v1.7.7)  
**Download:** https://github.com/ANmoLOCK/sinapesc-casanova-reap/releases/download/v1.7.7/SinapescREAP-Windows-v1.7.7.zip

### O que entrou
- **Imprimir declaração** sempre preenche o PDF oficial do MTE (texto azul nos espaços)
- Fonte **Padrão (Times)** também no PDF — não gera mais HTML separado
- Allura / Architects Daughter continuam no mesmo modelo

---

## [v1.7.6] — 2026-08-22 — Pasta Drive padrão em D:

**Tag:** [`v1.7.6`](https://github.com/ANmoLOCK/sinapesc-casanova-reap/releases/tag/v1.7.6)  
**Download:** https://github.com/ANmoLOCK/sinapesc-casanova-reap/releases/download/v1.7.6/SinapescREAP-Windows-v1.7.6.zip

### O que entrou
- Exemplos/placeholders da pasta anexos Defeso: unidade **D:** (`D:\Meu Drive\Sinapesc-Defeso`)

---

## [v1.7.5] — 2026-08-22 — Fontes manuscritas na declaração Defeso

**Tag:** [`v1.7.5`](https://github.com/ANmoLOCK/sinapesc-casanova-reap/releases/tag/v1.7.5)  
**Download:** https://github.com/ANmoLOCK/sinapesc-casanova-reap/releases/download/v1.7.5/SinapescREAP-Windows-v1.7.5.zip

### O que entrou
- Engrenagem ⚙ na ficha Defeso Fácil para escolher fonte da declaração
- Fontes: **Padrão (Times)**, **Allura (manuscrita)**, **Architects Daughter**
- Allura/Architects preenchem o PDF oficial do MTE (azul nos espaços); Padrão mantém o HTML atual
- Sem município/data automática na linha de assinatura (fica em branco)

---

## [v1.7.4] — 2026-08-21 — Pasta Google Drive sync para anexos

**Tag:** [`v1.7.4`](https://github.com/ANmoLOCK/sinapesc-casanova-reap/releases/tag/v1.7.4)  
**Download:** https://github.com/ANmoLOCK/sinapesc-casanova-reap/releases/download/v1.7.4/SinapescREAP-Windows-v1.7.4.zip

### O que entrou
- Configurações: **Escolher pasta…** / **Abrir pasta** para anexos Defeso
- Grava em pasta do Google Drive no PC (ex. `D:\Meu Drive\Sinapesc-Defeso\{CPF}\`) — sync usa a cota do usuário
- Campo `defeso_anexos_dir` no `config.json`; ID Drive API fica avançado/opcional

---

## [v1.7.3] — 2026-08-21 — Anexos locais se Drive sem cota

**Tag:** [`v1.7.3`](https://github.com/ANmoLOCK/sinapesc-casanova-reap/releases/tag/v1.7.3)  
**Download:** https://github.com/ANmoLOCK/sinapesc-casanova-reap/releases/download/v1.7.3/SinapescREAP-Windows-v1.7.3.zip

### O que entrou
- Erro 403 `storageQuotaExceeded` da Conta de Serviço: anexo é salvo em pasta local
- Aviso na tela explicando Shared Drive vs Meu Drive

---

## [v1.7.2] — 2026-08-21 — Fix anexos no Google Drive

**Tag:** [`v1.7.2`](https://github.com/ANmoLOCK/sinapesc-casanova-reap/releases/tag/v1.7.2)  
**Download:** https://github.com/ANmoLOCK/sinapesc-casanova-reap/releases/download/v1.7.2/SinapescREAP-Windows-v1.7.2.zip

### O que entrou
- Corrige bug: métodos de upload estavam fora da classe — anexar não ia para o Drive

---

## [v1.7.1] — 2026-08-21 — Fix lista Defeso / CPFs REAP

**Tag:** [`v1.7.1`](https://github.com/ANmoLOCK/sinapesc-casanova-reap/releases/tag/v1.7.1)  
**Download:** https://github.com/ANmoLOCK/sinapesc-casanova-reap/releases/download/v1.7.1/SinapescREAP-Windows-v1.7.1.zip

### O que entrou
- Leitura REAP (CPFs) isolada da planilha Defeso — falha no Defeso não zera a lista
- Aviso claro na tela se faltar compartilhar a planilha Defeso
- Normaliza ID (`?hl=pt-br`, URL completa)

---

## [v1.7.0] — 2026-08-21 — Defeso Fácil

**Tag:** [`v1.7.0`](https://github.com/ANmoLOCK/sinapesc-casanova-reap/releases/tag/v1.7.0)  
**Download:** https://github.com/ANmoLOCK/sinapesc-casanova-reap/releases/download/v1.7.0/SinapescREAP-Windows-v1.7.0.zip

### O que entrou
- Módulo **Defeso Fácil** (card na home): lista integrada ao REAP, ficha, salvar aba `Defeso`, gerar/imprimir declaração
- Anexos Identidade · Carteira de pesca · CAF → Google Drive `Defeso/{CPF}/`
- Config: `defeso_spreadsheet_id`, `defeso_drive_folder_id` — guia em `docs/DEFESO-FACIL.md`

---

## [v1.6.21] — 2026-08-21 — Contador respeita a planilha + sem sync auto

**Tag:** [`v1.6.21`](https://github.com/ANmoLOCK/sinapesc-casanova-reap/releases/tag/v1.6.21)  
**Download:** https://github.com/ANmoLOCK/sinapesc-casanova-reap/releases/download/v1.6.21/SinapescREAP-Windows-v1.6.21.zip

### O que entrou
- Corrige bug do contador preso em **agora** após ↻ Atualizar
- Remove atualização automática periódica
- Ao sair da secretaria, recarrega sócios/contador da planilha Google

---

## [v1.6.20] — 2026-08-21 — Sync automático a cada 8 minutos

**Tag:** [`v1.6.20`](https://github.com/ANmoLOCK/sinapesc-casanova-reap/releases/tag/v1.6.20)  
**Download:** https://github.com/ANmoLOCK/sinapesc-casanova-reap/releases/download/v1.6.20/SinapescREAP-Windows-v1.6.20.zip

### O que entrou
- Intervalo de sync automático alterado de **3 minutos** para **8 minutos**
- Menos uso da API Sheets; outros admins veem contadores em até ~8 min

---

## [v1.6.19] — 2026-08-21 — Sync automático a cada 3 minutos

**Tag:** [`v1.6.19`](https://github.com/ANmoLOCK/sinapesc-casanova-reap/releases/tag/v1.6.19)  
**Download:** https://github.com/ANmoLOCK/sinapesc-casanova-reap/releases/download/v1.6.19/SinapescREAP-Windows-v1.6.19.zip

### O que entrou
- EXE sincroniza a planilha automaticamente a cada **3 minutos** (sócios + última alteração da Auditoria)
- Pausado enquanto houver modal/lote aberto; status “Sincronizando…”
- Outros admins veem contadores atualizados sem clicar em Atualizar (até ~3 min)

---

## [v1.6.18] — 2026-08-21 — Filtro por alterações recentes + contador instantâneo

**Tag:** [`v1.6.18`](https://github.com/ANmoLOCK/sinapesc-casanova-reap/releases/tag/v1.6.18)  
**Download:** https://github.com/ANmoLOCK/sinapesc-casanova-reap/releases/download/v1.6.18/SinapescREAP-Windows-v1.6.18.zip

### O que entrou
- Removida a legenda redundante (`1min atrás` / `4h atrás` / …)
- Filtro em Sócios: **Mais recente**, **Alterados (30 dias)**, **Alterados (1 ano)**, **A–Z**
- Contador ao lado do nome atualiza na hora ao marcar/desmarcar (sem recarregar a planilha)

---

## [v1.6.17] — 2026-08-19 — Última alteração REAP ao lado do nome

**Tag:** [`v1.6.17`](https://github.com/ANmoLOCK/sinapesc-casanova-reap/releases/tag/v1.6.17)  
**Download:** https://github.com/ANmoLOCK/sinapesc-casanova-reap/releases/download/v1.6.17/SinapescREAP-Windows-v1.6.17.zip

### O que entrou
- Contador **última alteração** ao lado do nome: `agora`, `1min atrás`, `4h atrás`, `14d`, `1ano15d`
- Dados lidos da aba **Auditoria** da planilha (eventos `toggle_mes`) — visível a todos os admins
- Telas **Sócios** e **Pendências**; recarrega da planilha após marcar/desmarcar mês

---

## [v1.6.16] — 2026-08-19 — Rodapé status restaurado

**Tag:** [`v1.6.16`](https://github.com/ANmoLOCK/sinapesc-casanova-reap/releases/tag/v1.6.16)  
**Download:** https://github.com/ANmoLOCK/sinapesc-casanova-reap/releases/download/v1.6.16/SinapescREAP-Windows-v1.6.16.zip

### O que entrou
- Restaura rodapé **Pronto · admin · Conectado**
- Copyright em linha `.footer-legal` abaixo, sem barra fixa cobrindo a tela

---

## [v1.6.15] — 2026-08-19 — Direitos autorais reservados

**Tag:** [`v1.6.15`](https://github.com/ANmoLOCK/sinapesc-casanova-reap/releases/tag/v1.6.15)  
**Download:** https://github.com/ANmoLOCK/sinapesc-casanova-reap/releases/download/v1.6.15/SinapescREAP-Windows-v1.6.15.zip

### O que entrou
- Declaração oficial: software de Gabriel; Sindicato com licença indeterminada; código-fonte do autor
- `docs/DIREITOS-AUTORAIS.md`, `LICENSE` e `COPYRIGHT` atualizados
- EXE inclui LICENSE e COPYRIGHT na pasta de instalação

---

## [v1.6.14] — 2026-08-19 — QR sem link visível + site sem lista pública

**Tag:** [`v1.6.14`](https://github.com/ANmoLOCK/sinapesc-casanova-reap/releases/tag/v1.6.14)  
**Download:** https://github.com/ANmoLOCK/sinapesc-casanova-reap/releases/download/v1.6.14/SinapescREAP-Windows-v1.6.14.zip

### O que entrou
- QR: removido texto do link na prévia (modal), no HTML de impressão e na imagem PNG final
- Site público: removido botão **Lista pública** — consulta individual por CPF apenas
- `lista.html` redireciona para `consulta.html`; backup em `site-publico/_backup/`

---

## [v1.6.13] — 2026-08-19 — Impressão abre no navegador (sem erro about:)

**Tag:** [`v1.6.13`](https://github.com/ANmoLOCK/sinapesc-casanova-reap/releases/tag/v1.6.13)  
**Download:** https://github.com/ANmoLOCK/sinapesc-casanova-reap/releases/download/v1.6.13/SinapescREAP-Windows-v1.6.13.zip

### O que entrou
- Relatório abre arquivo HTML local no navegador padrão para imprimir
- QR (consulta, lista e individual) gera HTML local e abre no navegador para impressão formal
- Correção do erro de abrir `about:` pedindo aplicativo no Windows

---

## [v1.6.12] — 2026-08-18 — Nome sempre com a primeira letra maiúscula

**Tag:** [`v1.6.12`](https://github.com/ANmoLOCK/sinapesc-casanova-reap/releases/tag/v1.6.12)  
**Download:** https://github.com/ANmoLOCK/sinapesc-casanova-reap/releases/download/v1.6.12/SinapescREAP-Windows-v1.6.12.zip

### O que entrou
- Ao salvar, o nome vira **Gabriel Lourran Da Silva** mesmo com Caps Lock
- `gabriel lourran da silva` e `GABRIEL LOURRAN DA SILVA` não ficam gravados assim
- Vale para cadastro único, edição, lote e lista na tela

---

## [v1.6.11] — 2026-08-18 — Lote de 50 sócios sem perder o preenchimento

**Tag:** [`v1.6.11`](https://github.com/ANmoLOCK/sinapesc-casanova-reap/releases/tag/v1.6.11)  
**Download:** https://github.com/ANmoLOCK/sinapesc-casanova-reap/releases/download/v1.6.11/SinapescREAP-Windows-v1.6.11.zip

### O que entrou
- Cadastro em lote **não fecha a janela** se der erro — nomes e CPFs continuam na tela
- Rascunho guardado automaticamente; dá para colar lista `Nome;CPF`
- Envio em JSON (50+ sócios) e nova tentativa se o Google travar (429/timeout)
- Teste automático com 50 sócios

---

## [v1.6.10] — 2026-08-18 — Mês instantâneo, CPF formatado e fila da planilha

**Tag:** [`v1.6.10`](https://github.com/ANmoLOCK/sinapesc-casanova-reap/releases/tag/v1.6.10)  
**Download:** https://github.com/ANmoLOCK/sinapesc-casanova-reap/releases/download/v1.6.10/SinapescREAP-Windows-v1.6.10.zip

### O que entrou
- **Mês instantâneo:** ao clicar na pílula (JAN…DEZ) ela muda na hora (verde ✓ / cinza !); a planilha grava em segundo plano. Se der erro, a pílula volta e avisa
- **Sem precisar de Atualizar:** a fila da planilha não bloqueia mais o recarregamento da lista
- **CPF visível com máscara:** `105.205.585-45` (não mais `10520558545`) na lista, no cadastro e no lote
- CPF duplicado continua bloqueado no cadastro e na edição

---

## [v1.6.9] — 2026-08-18 — Marca d'água, layout centralizado e escala padrão

**Tag:** [`v1.6.9`](https://github.com/ANmoLOCK/sinapesc-casanova-reap/releases/tag/v1.6.9)  
**Download:** https://github.com/ANmoLOCK/sinapesc-casanova-reap/releases/download/v1.6.9/SinapescREAP-Windows-v1.6.9.zip

### O que entrou
- Marca d'água do selo **SINAPESC** no fundo da área de conteúdo (atrás dos cards), grande e centralizada — como na prévia
- Correção: o CSS apontava para um arquivo que não existia (`web/assets/`), então o selo **não aparecia**
- Camada irmã de `#content` (não some ao trocar de tela)
- **Layout centralizado:** lista, abas, botões e rodapé no meio da janela (não mais colados à esquerda)
- **Escala padrão (100%):** fonte 14px, zoom 1, janela 1280×800

---

## [v1.6.8] — 2026-08-18 — Selo oficial, ícone, relatório e marca d'água

**Tag:** [`v1.6.8`](https://github.com/ANmoLOCK/sinapesc-casanova-reap/releases/tag/v1.6.8)  
**Download:** https://github.com/ANmoLOCK/sinapesc-casanova-reap/releases/download/v1.6.8/SinapescREAP-Windows-v1.6.8.zip

### O que entrou
- Logo **redesenhada fiel ao carimbo original** (peixe, montanha, faixa SINAPESC)
- Ícone do EXE, logo do programa e relatórios HTML usam o mesmo selo
- **Marca d'água visível** no fundo das telas (atrás dos cards)
- Escala da logo corrigida: `object-fit: contain` (antes o círculo recortava o selo)
- QR interno usa o selo no centro (não mais a letra S)

---

## [v1.6.7] — 2026-08-18 — Logo selo SINAPESC fiel ao original

**Tag:** [`v1.6.7`](https://github.com/ANmoLOCK/sinapesc-casanova-reap/releases/tag/v1.6.7)  
**Download:** https://github.com/ANmoLOCK/sinapesc-casanova-reap/releases/download/v1.6.7/SinapescREAP-Windows-v1.6.7.zip

### O que entrou
- Logo redesenhada **fiel ao selo original**: círculo, peixe tucunaré saltando, faixa SINAPESC, texto curvo Casa Nova - BA
- Aplicada no programa, ícone do EXE e relatórios HTML

---

## [v1.6.6] — 2026-08-18 — Filtro de sócios, imprimir QR e logo SINAPESC

**Tag:** [`v1.6.6`](https://github.com/ANmoLOCK/sinapesc-casanova-reap/releases/tag/v1.6.6)  
**Download:** https://github.com/ANmoLOCK/sinapesc-casanova-reap/releases/download/v1.6.6/SinapescREAP-Windows-v1.6.6.zip

### O que entrou
- Sócios novos aparecem **no topo** (mais recente → mais antigo)
- **Filtro** na toolbar: Mais recente | A–Z (ao lado de Atualizar · Lote · + Novo sócio)
- QR: botão **Imprimir**
- Logo oficial do selo SINAPESC no programa e nos relatórios HTML

---

## [v1.6.5] — 2026-08-18 — Escala compacta + funções restauradas

**Tag:** [`v1.6.5`](https://github.com/ANmoLOCK/sinapesc-casanova-reap/releases/tag/v1.6.5)  
**Download:** https://github.com/ANmoLOCK/sinapesc-casanova-reap/releases/download/v1.6.5/SinapescREAP-Windows-v1.6.5.zip

### O que entrou
- Escala da UI: fontes legíveis, padding reduzido, conteúdo com largura máxima (não “estica” a 1280px)
- Config.Atalhos como **aba completa**: (1) lote pré-marcado, (2) marcar em massa com busca/substituir, (3) copiar ano
- Presets **Mar → Out / Ano inteiro / Limpar**
- Cadastro em lote visual (linhas Nome + CPF + lixeira)
- Configurações: Gerar QRs, QR Consulta CPF, pasta dos QRs
- Auditoria: exportar CSV
- Modal JS corrigido (botões Salvar/Importar voltaram a funcionar)

---

## [v1.6.4] — 2026-08-18 — UI web pywebview (idêntica ao mockup)

**Tag:** [`v1.6.4`](https://github.com/ANmoLOCK/sinapesc-casanova-reap/releases/tag/v1.6.4)  
**Download:** https://github.com/ANmoLOCK/sinapesc-casanova-reap/releases/download/v1.6.4/SinapescREAP-Windows-v1.6.4.zip

### O que entrou
- Interface **HTML + CSS** dentro da janela via **pywebview** (WebView2 no Windows)
- Mockup aprovado com fidelidade real: header navy, abas sublinhadas, cartões, pílulas de mês, rodapé limpo
- Ponte `webapp/api.py` reutiliza `sheets/` e `controle/` (login, sócios, REAP, pendências, relatório, backup, auditoria, QRs)
- Tkinter mantido como fallback: `SinapescREAP.exe --tk`
- Correções: nomes CAPS, relatório individual, lista/QR sem login admin, navegação Voltar

---

## [v1.6.2] — 2026-08-18 — UI fiel ao mockup aprovado (Tkinter)

**Tag:** [`v1.6.2`](https://github.com/ANmoLOCK/sinapesc-casanova-reap/releases/tag/v1.6.2)  
**Download:** https://github.com/ANmoLOCK/sinapesc-casanova-reap/releases/download/v1.6.2/SinapescREAP-Windows-v1.6.2.zip

### O que entrou
- Módulo `ui/widgets.py` (busca com lupa, botões outline/primary, cartões, pills de mês)
- Header: e-mail acima dos botões; abas com sublinhado branco na ativa
- Ordem das abas igual ao mockup (+ Auditoria)
- Cartões: avatar circular, ações com ícones, chevron ▲/▼
- Meses em fila horizontal verde ✓ / vermelho !
- Rodapé: Pronto · Usuário · Conectado

---

## [v1.6.1] — 2026-08-18 — Interface fusionada + rodapé limpo

**Tag:** [`v1.6.1`](https://github.com/ANmoLOCK/sinapesc-casanova-reap/releases/tag/v1.6.1)  
**Download:** https://github.com/ANmoLOCK/sinapesc-casanova-reap/releases/download/v1.6.1/SinapescREAP-Windows-v1.6.1.zip

### O que entrou
- **UI reorganizada:** header compacto, abas em texto (Pendências · Relatório · Backup · Auditoria · Sócios · Config.Atalhos)
- Botões outline no topo: **Voltar · Lista pública · Configurações · Sair**
- **Voltar** com histórico (não desloga ao voltar)
- Tela Sócios mais limpa: busca + ações no topo, sem segunda fileira de botões coloridos
- Rodapé: usuário, conexão, versão (removido texto “safra”)
- Nova página **Backup** na aba (gerar, abrir pasta, listar recentes)
- Módulo `ui/chrome.py` centraliza shell e navegação

### Inclui tudo da v1.6.0
Pendências, relatório HTML (CPF admin), backup CSV, auditoria na planilha.

---

## [v1.6.0] — 2026-08-18 — Pendências, relatório, backup e auditoria na planilha

**Tag:** [`v1.6.0`](https://github.com/ANmoLOCK/sinapesc-casanova-reap/releases/tag/v1.6.0)  
**Download direto:** https://github.com/ANmoLOCK/sinapesc-casanova-reap/releases/download/v1.6.0/SinapescREAP-Windows-v1.6.0.zip  
**Repo:** https://github.com/ANmoLOCK/sinapesc-casanova-reap  
**Consulta:** https://anmolock.github.io/sinapesc-casanova-reap/consulta.html  
**Plano:** [`PLANO_FUNCOES_v16.md`](./PLANO_FUNCOES_v16.md)

### O que entrou
- **Pendências REAP:** lista só quem falta no calendário do ano (padrão mar–out). Marca somente os meses pendentes, em lote, sem apagar o que já está marcado.
- **Calendário compartilhado:** aba **Config** na planilha (`calendario_padrao` / `calendario_2026`). Todos os admins usam a mesma regra.
- **Relatório de conformidade:** HTML com logo Sinapesc, **CPF completo** (somente o admin, pela tela Relatório), grade do ano, carimbo Regular/Pendente. Sem R$. Abrir no navegador → Imprimir → Salvar como PDF. A consulta pública no celular continua com CPF mascarado.
- **Backup CSV local:** cópia das abas Pessoas + Reap em `backups/` ao lado do EXE (ou AppData). Lembrete a cada 7 dias no login admin. Guarda os últimos 12.
- **Auditoria na planilha:** aba **Auditoria**. Cada admin vê o que o outro marcou: “fulano marcou OUT/2026 em Maria”. O site público **não** lê essa aba.

### Organização (código separado)
- Regras em `sinapesc-desktop/controle/`
- Telas em `ui/tela_pendencias.py`, `ui/tela_relatorio.py`, `ui/tela_backup.py`, `ui/tela_auditoria.py`
- Planilha: `sheets/client.py` cria as abas novas na primeira conexão

### Bugs corrigidos nesta leva
- Clique duplo na planilha: `_run_bg` zera o “ocupado” mesmo se o callback falhar (B13)
- Exceção do thread não se perde no `lambda` (Python 3)
- Relatório do admin deixa de mascarar o CPF (B15); site público permanece mascarado
- Auditoria deixa de ser só local (B14)

### O que não mudou
- Consulta pública por CPF
- Cadastro em lote e Config.Atalhos
- Sem pagamento / boleto / valor em R$

---

## [v1.5.1] — 2026-08-17 — Config.Atalhos

**Tag:** [`v1.5.1`](https://github.com/ANmoLOCK/sinapesc-casanova-reap/releases/tag/v1.5.1)  
**Download:** https://github.com/ANmoLOCK/sinapesc-casanova-reap/releases/download/v1.5.1/SinapescREAP-Windows-v1.5.1.zip  
**Consulta:** https://anmolock.github.io/sinapesc-casanova-reap/consulta.html  
**Sugestões:** [`MELHORIAS.md`](./MELHORIAS.md)

### O que entrou
- Botão **Config.Atalhos** no admin (ao lado de Atualizar)
- **Lote com REAP já marcado** (Mar→Out, um mês ou ano inteiro)
- **Marcar meses em massa** nos sócios existentes (opção de só a busca; não apaga pagos, salvo “substituir”)
- **Copiar REAP** de um ano para outro
- Escritas na planilha em **batch** (`values.batchUpdate` + append), para não estourar cota da API

### O que não mudou
- Site público, QR permanente, lote visual Nome/CPF, tema azul

---

## [v1.5.0] — 2026-08-17 — Lote visual + site no ar + EXE

**Tag:** [`v1.5.0`](https://github.com/ANmoLOCK/sinapesc-casanova-reap/releases/tag/v1.5.0)  
**EXE (download direto):** https://github.com/ANmoLOCK/sinapesc-casanova-reap/releases/download/v1.5.0/SinapescREAP-Windows-v1.5.0.zip  
**Página da release:** https://github.com/ANmoLOCK/sinapesc-casanova-reap/releases/tag/v1.5.0  
**Repo:** https://github.com/ANmoLOCK/sinapesc-casanova-reap  
**Consulta:** https://anmolock.github.io/sinapesc-casanova-reap/consulta.html

### Download
Actions → [run 32050211734](https://github.com/ANmoLOCK/sinapesc-casanova-reap/actions/runs/32050211734) → Artifacts → **SinapescREAP-Windows**.

### Melhorias (detalhe)
- **Lote visual:** cada sócio em uma linha com Nome, CPF (máscara) e lixeira; botão + Adicionar linha
- Importar CSV/TXT preenche as linhas (não substitui por caixona de texto)
- Site público no repositório `sinapesc-casanova-reap` (GitHub Pages / `gh-pages`)
- `config.js` com spreadsheetId da planilha leitora
- Parser da aba Pessoas ignora cabeçalho do gviz
- EXE: `normalize_public_base` — aceita URL com `/consulta.html` e grava a raiz
- Configurações: salvar URL do site sem bloquear o QR (B12)
- README da raiz reorganizado (download, atualizações, versões, bugs)

### O que não mudou
- Consulta por CPF no celular sem o PC ligado
- Marcação mês a mês no EXE
- Tema azul, logo Sinapesc, QR permanente em `qr-codes/`

---

## [v1.4.0] — 2026-08-15 — Site público gratuito + UI azul Sinapesc

**Tag:** `v1.4.0`  
**EXE:** https://github.com/ANmoLOCK/SINDICATO-DA-PESCA---REAP-GERAL/actions/runs/31863086521  
**Tutorial:** [`TUTORIAL_IMPLEMENTACAO.md`](./TUTORIAL_IMPLEMENTACAO.md)

### Melhorias
- **Opção A:** pasta `site-publico/` (consulta/lista/pessoa) lendo a planilha sem o notebook ligado
- Deploy GitHub Pages via `.github/workflows/deploy-site.yml`
- EXE: tema premium **azul oceano**, logo Sinapesc e gráfica de peixe
- QRs permanentes apontam para `public_site_url` (URL fixa do site)
- Configurações: campo **URL do site público** + gerar QRs do site
- Poster do QR com cores institucionais azuis + dourado
- Tutorial passo a passo de implementação (`TUTORIAL_IMPLEMENTACAO.md`)

### Bugs / ajustes
- Consulta pública deixa de depender de túnel/PC ligado (B11)
- Salvamento de configurações alinhado ao fluxo do site (sem campos órfãos do túnel)

---

## [v1.3.0] — 2026-08-15 — QR estável + consulta CPF + UI premium

**Tag:** [`v1.3.0`](https://github.com/ANmoLOCK/SINDICATO-DA-PESCA---REAP-GERAL/releases/tag/v1.3.0)

### Melhorias
- UI pública/desktop mais premium
- Página **/consulta** — associado digita CPF e vê só o próprio REAP
- QR com padrão visual único (selo Sinapesc + moldura)
- Cofre `qr-codes/` — QRs permanentes (consulta, lista, individual)
- Link público **reutilizado** (não gera URL nova à toa)
- Túnel pode permanecer ativo ao fechar o app

### Bugs / ajustes
- Removido texto `X/12 pagos` das páginas do QR
- Removida frase “CPF parcialmente oculto” da lista pública online
- QR individual/`lista` não mudam a cada geração enquanto o link estiver válido

---


## [v1.2.0] — 2026-08-15 — Casa Nova + link público + lote

**Tag:** [`v1.2.0`](https://github.com/ANmoLOCK/SINDICATO-DA-PESCA---REAP-GERAL/releases/tag/v1.2.0)  
**Commit:** `0372e20`  
**EXE:** https://github.com/ANmoLOCK/SINDICATO-DA-PESCA---REAP-GERAL/actions/runs/31858767536

### Melhorias
- Nome oficial: **Sinapesc — Sindicato Dos Aquicultores E Pescadores De Casa Nova**
- Interface visual mais premium (faixa dourada, tipografia, botões)
- Botão **Criar link público** (Cloudflare Tunnel automático; preenche a URL)
- **Cadastro em lote** (colar linhas ou importar CSV `Nome;CPF`)
- Botão de link público também no diálogo do QR

### Bugs resolvidos
- Removido texto redundante `0/12 pagos` na lista
- QR inacessível fora da Wi‑Fi (agora há link https com 1 clique)
- Cadastro em massa inviável (agora há lote)

---

## [v1.1.0] — 2026-08-15 — Scroll, accordion e QR online

**Tag:** [`v1.1.0`](https://github.com/ANmoLOCK/SINDICATO-DA-PESCA---REAP-GERAL/releases/tag/v1.1.0)  
**Commit:** `6e1035a`  
**EXE:** https://github.com/ANmoLOCK/SINDICATO-DA-PESCA---REAP-GERAL/actions/runs/31857220864

### Melhorias
- Lista compacta: clique no nome abre anos/REAP
- QR da lista pública e comprovante individual (PNG imprimível)
- Página web embutida (porta 8765) com atualização automática

### Bugs resolvidos
- Scroll quebrado / mousewheel inconsistente (B01)
- Interface poluída com todos os meses sempre visíveis (B02)

---

## [v1.0.0] — 2026-08-15 — Primeira versão estável (.exe)

**Tag:** [`v1.0.0`](https://github.com/ANmoLOCK/SINDICATO-DA-PESCA---REAP-GERAL/releases/tag/v1.0.0)  
**Commit:** `3cad999`  
**EXE:** https://github.com/ANmoLOCK/SINDICATO-DA-PESCA---REAP-GERAL/actions/runs/31854798304

### Melhorias
- Reformulação do app web Next.js em programa desktop
- Integração Google Sheets didática (`sheets/client.py` + guia)
- Configuração por arquivos ao lado do `.exe`
- CI GitHub Actions gerando artefato Windows

### Bugs resolvidos
- Build Windows falhava por ícone PNG sem conversão ICO/Pillow (B03)
- Falta de fluxo claro para API Google (B04 — guia + import JSON)

---

## Origem (antes das tags)

- App web original (ZIP Next.js) → base da lógica Pessoas/Reap
- Branch de desenvolvimento: `cursor/sinapesc-desktop-exe-46d6`
- PR: https://github.com/ANmoLOCK/SINDICATO-DA-PESCA---REAP-GERAL/pull/1
