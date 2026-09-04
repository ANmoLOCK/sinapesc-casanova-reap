# Sinapesc REAP — Casa Nova

**Sinapesc — Sindicato Dos Aquicultores E Pescadores De Casa Nova**

> **© Gabriel Lourran Da Silva Costa — Todos os direitos reservados**  
> O software Sinapesc REAP foi desenvolvido por **Gabriel**. O Sindicato recebe **licença por prazo indeterminado**. O **código-fonte permanece de propriedade do autor**.  
> **Contato:** gabriel730costa@gmail.com · Ver [`LICENSE`](./LICENSE) · [`DIREITOS-AUTORAIS`](./docs/DIREITOS-AUTORAIS.md) · [`CONTRATO`](./docs/CONTRATO-LICENCA-SINAPESC.md)

Controle de **REAP** (não é pagamento): a secretaria usa o EXE no Windows; o associado consulta o CPF no celular **sem o notebook ligado**.

| | |
|--|--|
| Repositório | https://github.com/ANmoLOCK/sinapesc-casanova-reap |
| Versão atual | [**v1.7.39**](https://github.com/ANmoLOCK/sinapesc-casanova-reap/releases/tag/v1.7.39) |
| Site (consulta) | https://anmolock.github.io/sinapesc-casanova-reap/consulta.html |
| Planilha (leitor) | https://docs.google.com/spreadsheets/d/1ydaWGF53VTkXyIyhf5XKJek5PKMDZO1_cD3CrRePft4/edit?usp=sharing |

---

## Download do EXE (v1.7.39)

**Link direto (ZIP):**

https://github.com/ANmoLOCK/sinapesc-casanova-reap/releases/download/v1.7.39/SinapescREAP-Windows-v1.7.39.zip

Página da release: https://github.com/ANmoLOCK/sinapesc-casanova-reap/releases/tag/v1.7.39

Versão anterior: [v1.7.38](https://github.com/ANmoLOCK/sinapesc-casanova-reap/releases/tag/v1.7.38)

Guia Defeso: [`docs/DEFESO-FACIL.md`](./docs/DEFESO-FACIL.md)

O ZIP traz `SinapescREAP.exe`, `config.json`, `LEIA-ME.txt` e tutoriais. Extraia numa pasta (ex.: `C:\Sinapesc\`) e coloque o `google-credentials.json` junto.

---

## Site público

| Página | URL |
|--------|-----|
| Consulta por CPF (QR da sede) | https://anmolock.github.io/sinapesc-casanova-reap/consulta.html |

**URL para colar no EXE** (Configurações — sem `/consulta.html`):

```text
https://anmolock.github.io/sinapesc-casanova-reap
```

O site lê só as abas **Pessoas** e **Reap**. CPF no celular fica **mascarado**.

---

## O que há na v1.7.39

- Consulta RGP volta a mostrar o **mesmo rodapé** dos outros módulos (crédito + status da planilha)

## O que há na v1.7.38

- **Corrige CPF inválido** na Consulta RGP (zeros à esquerda / artefato float da planilha)
- Recupera `95453325900` → `095.453.325-90` e `56106905010` → `056.106.905-01`
- JS envia CPF como JSON string (sem virar número na ponte pywebview)
- Regrava o CPF corrigido na planilha ao consultar

## O que há na v1.7.34

- UI Consulta RGP reformulada: sem «Salvar senha» no topo
- Senha Gov.br no modal Cadastrar sócio; Editar abre painel lateral completo

## O que há na v1.7.33

- Senha Gov.br salva na planilha Consulta RGP (aba Config)
- Tudo que se preenche no módulo vai para o Google Sheets

## O que há na v1.7.32

- Consulta RGP sem toggles de configuração; campo **Senha Gov.br** no topo
- Layout folgado (header, KPIs, tabela e painel) alinhado ao mockup

## O que há na v1.7.31

- Corrige Consulta RGP: consulta MPA grava situação (não só abre o site)
- Polling estável no worker (não depende de Promise async do pywebview)
- «Abrir site MPA» só no botão manual; falha mostra erro sem abrir o navegador

## O que há na v1.7.30

- Consulta MPA mais robusta: espera reCAPTCHA, grava situação RGP no módulo
- Cadastro automático dispara consulta e atualiza tabela/KPIs
- UI com mais respiro (menos apertada)

## O que há na v1.7.29

- Consulta RGP em tela cheia, proporções fiéis ao mockup (sem achatar)
- Header navy alto, KPIs com ícone à esquerda, linhas de tabela espaçosas
- Painel lateral e modal de cadastro com mais altura e respiro

## O que há na v1.7.28

- Modal **Cadastrar sócio** sólido (sem transparência), campos em grade limpa
- Mesmo padrão visual na edição do painel lateral

## O que há na v1.7.27

- Consulta RGP: usuário real no header, chips de situação, coluna Município
- **Consultar** abre o painel; consulta MPA fica no painel
- Painel sem abas: botão **Editar cadastro**
- **Cadastrar sócio** salva e consulta MPA automaticamente

## O que há na v1.7.26

- Corrige cota 60 ao abrir Consulta RGP
- **Cadastrar sócio** na planilha Consulta (nome, CPF, município, telefone, observação)
- Sem sync Consulta ↔ REAP nesta etapa
- Interface fiel ao mockup

## O que há na v1.7.24

- **Módulo Consulta RGP** na Home (4º card): KPIs, tabela e sidebar
- Planilha/aba `ConsultaRGP` com sync a partir do REAP
- Consulta MPA em janela isolada (situação Ativo, Aguardando análise, Rascunho, Finalizada, etc.)
- Importação para REAP/Defeso **somente se Ativo** (REAP: município+telefone · Defeso: CPF+nome)

## O que há na v1.7.23

- Município REAP e município Defeso **totalmente isolados** na tela e nas planilhas
- Salvar Defeso não altera o que aparece na ficha REAP (nem o campo readonly «Município (REAP)»)
- Lista Defeso mostra REAP e Defeso separados; filtro de localidade usa só município REAP

## O que há na v1.7.22

- Salvar ficha Defeso **não altera** mais a planilha REAP
- Município/telefone REAP: só leitura para conferência e relatório Defeso

## O que há na v1.7.21

- Município do REAP: só conferência na ficha Defeso e no relatório — **não** entra na declaração
- Sync deixa de gravar município REAP na ficha Defeso (só telefone)

## O que há na v1.7.20

- Relatório REAP e Defeso: filtro por localidade
- Defeso: filtro «entrada confirmada» e «com parcela disponível»
- Ficha Defeso: até 3 telefones e 3 e-mails rápidos (atalhos gravados no PC)
- Sinc. Planilhas: batch + retry 429 (não estoura cota com muitos sócios)

## O que há na v1.7.19

- Declaração e Juntar PDF abrem no navegador de verdade (Edge/Chrome ou HTML wrapper)
- Continua limpando o PDF antigo do CPF ao regenerar

## O que há na v1.7.18

- Declaração (e pacote PDF) voltam a abrir no navegador automaticamente
- Ao regenerar declaração (ex.: trocar fonte), o PDF antigo do mesmo CPF é apagado

## O que há na v1.7.17

- Bateria final: declaração/PDF usam formulário atual; sync município ao salvar sócio

## O que há na v1.7.16

- Fix: salvar ficha Defeso (erro de payload / cannot access)

## O que há na v1.7.15

- Relatório Defeso só com quem está no REAP (sem sócio fantasma)
- Rodapé de crédito do autor restaurado

## O que há na v1.7.14

- Defeso: 4 parcelas profissionais + checkbox de entrada corrigido
- Relatório HTML: município/telefone do REAP; endereço só rua/nº/bairro/UF/CEP do Defeso

## O que há na v1.7.13

- REAP: UF e telefone visíveis ao abrir meses + filtro por localidade
- Defeso: relatório HTML, parcelas recebidas e entrada confirmada

## O que há na v1.7.12

- REAP: campo **Número (telefone)** no + Sócio
- Lote e Config.Atalhos: colunas **Município** e **Número**

## O que há na v1.7.11

- **Defeso Fácil:** filtros Localidade, Entradas confirmadas e Atualizar
- Coluna **município** no REAP + sync automático com planilha Defeso
- Botão **Sinc. Planilhas** no módulo Sócios (ao lado de Lista pública)

## O que há na v1.7.10

- Defeso: **Juntar PDF** (declaração + identidade + carteira + CAF) com checkboxes
- Ícone **Aa** no lugar da engrenagem para escolher a letra da declaração

## O que há na v1.7.9

- Declaração com **letra de mão** (caneta azul, letra a letra) — Allura / Bairro / Mão suja / Caderno

## O que há na v1.7.8

- Fix engrenagem ⚙ da declaração: a fonte escolhida (Times / Allura / Architects) passa a ser usada de verdade na impressão

## O que há na v1.7.7

- Declaração Defeso: **sempre** gera o PDF oficial do MTE com nome/CPF/endereço etc. em azul por cima (Padrão · Allura · Architects)

## O que há na v1.7.6

- Pasta anexos Defeso: exemplos apontam para unidade **D:** (`D:\Meu Drive\Sinapesc-Defeso`)

## O que há na v1.7.5

- Defeso Fácil: engrenagem ⚙ para escolher fonte da declaração (Padrão · Allura · Architects Daughter)
- Fontes manuscritas preenchem o PDF oficial do MTE

## O que há na v1.7.4

- Anexos Defeso: **escolher pasta** do Google Drive no PC (ex. `D:\Meu Drive\Sinapesc-Defeso`) — o Drive sincroniza com a sua cota
- Sem pasta: continua em AppData local; ID Drive API fica opcional/avançado

## O que há na v1.7.3

- Anexos Defeso: se o Google negar cota do robô (403), **salva na pasta local** do EXE
- Explica limite: Conta de Serviço não tem espaço no Meu Drive — use Shared Drive ou local

## O que há na v1.7.2

- Corrige anexos Defeso que **não subiam para o Drive** (bug no cliente de upload)

## O que há na v1.7.1

- Corrige erro ao abrir Defeso Fácil: lista de CPFs do REAP não cai mais se a planilha Defeso falhar
- Mensagem clara se REAP ou Defeso estiver sem permissão / ID inválido
- Aceita ID com `?hl=pt-br` ou URL completa

## O que há na v1.7.0

- **Defeso Fácil** na home: ficha do pescador (REAP), salvar na planilha Defeso, imprimir declaração
- Anexos Identidade / Carteira de pesca / CAF → pasta no Google Drive por CPF
- Config: `defeso_spreadsheet_id` + `defeso_drive_folder_id` (ver `docs/DEFESO-FACIL.md`)

## O que há na v1.6.21

- Corrige contador preso em **agora** (↻ Atualizar passa a respeitar a planilha)
- Remove sync automático (8 min)
- Ao sair da secretaria (home / config / sair), puxa a planilha atualizada do Google

## O que há na v1.6.20

- **Sync automático** com a planilha a cada **8 minutos** (sócios + contador da Auditoria)
- Removido o intervalo de 3 minutos

## O que há na v1.6.19

- Sync automático com a planilha (intervalo antigo: 3 minutos)
- Outros admins passam a ver marcações/contadores sem clicar em Atualizar

## O que há na v1.6.18

- Removida a legenda redundante dos formatos de tempo
- Filtro em Sócios: **Mais recente** · **Alterados (30 dias)** · **Alterados (1 ano)** · **A–Z**
- Contador ao lado do nome atualiza na hora ao marcar/desmarcar (sem esperar a planilha)

## O que há na v1.6.17

- **Última alteração REAP** ao lado do nome do sócio (`1min atrás`, `4h atrás`, `14d`, `1ano15d`)
- Contador lido da aba **Auditoria** da planilha — qualquer admin que abrir o EXE vê os mesmos tempos
- Visível em **Sócios** e **Pendências**; atualiza após marcar/desmarcar mês

## O que há na v1.6.16

- **Rodapé restaurado:** Pronto · usuário admin · Conectado visíveis de novo
- Direitos autorais movidos para linha discreta abaixo do rodapé (sem cobrir status)

## O que há na v1.6.15

- **Direitos autorais reservados:** declaração oficial de autoria (Gabriel), licença indeterminada ao Sindicato e código-fonte do autor
- Documentos: `LICENSE`, `COPYRIGHT`, `docs/DIREITOS-AUTORAIS.md`, `docs/CONTRATO-LICENCA-SINAPESC.md`
- Inclui v1.6.14: QR sem link visível; site só consulta por CPF; aviso legal fixo

### Interface web (pywebview)
- **HTML + CSS real** dentro da janela (WebView2 no Windows) — avatares circulares, pílulas, abas sublinhadas
- Header: logo, e-mail acima dos botões, **← Voltar · Lista pública · ⚙ Configurações · Sair**
- Abas: **Sócios · Pendências · Relatório · Backup · Auditoria · Config.Atalhos · Lista pública**
- Cartões com avatar, **▦ QR · ✎ Editar · 🗑 Excluir**, chevron ▲/▼
- Meses em pílulas: verde ✓ (regular) · vermelho ! (pendente)
- Rodapé: **Pronto · Usuário · Conectado** | **Sinapesc REAP**
- Tkinter legado ainda disponível: `SinapescREAP.exe --tk`

### v1.6.2 / v1.6.1 / v1.6.0 (mantidos)
- Header compacto: logo, e-mail logado, botões **Voltar · Lista pública · Configurações · Sair**
- Abas da secretaria: **Pendências · Relatório · Backup · Auditoria · Sócios · Config.Atalhos**
- Tela **Sócios** mais limpa (busca + ações no topo, sem fileira extra de botões)
- **Voltar** com histórico — volta à tela anterior sem deslogar
- Rodapé com usuário, conexão e versão

### Funções v1.6.0 (mantidas)

| Aba / botão | Função |
|-------------|--------|
| **Pendências** | Quem falta no calendário do ano (padrão **mar–out**). Marca só o que falta. |
| **Relatório** | HTML com **CPF completo** (só admin). Imprimir → PDF. Sem R$. |
| **Backup** | CSV local das abas Pessoas + Reap (`backups/`). Lembrete a cada 7 dias. |
| **Auditoria** | Histórico na aba **Auditoria** da planilha (todos os admins veem). Ao lado do nome: **última alteração REAP** (`1min atrás`, `4h atrás`, …). |
| **Config.Atalhos** | Lote pré-marcado, marcar em massa, copiar ano. |

Na primeira conexão o EXE cria as abas **Auditoria** e **Config**.

Código: `sinapesc-desktop/controle/` (regras) · `sinapesc-desktop/ui/` (telas + `chrome.py`)

---

## Instalação rápida

1. Extraia o ZIP do EXE  
2. Coloque `google-credentials.json` na mesma pasta  
3. Em `config.json`:

```json
"public_site_url": "https://anmolock.github.io/sinapesc-casanova-reap"
```

4. Abra o `.exe` → **Configurações** → **Salvar** → **Testar conexão**  
5. **QR Consulta CPF** → imprimir na sede  
6. Login admin → use as abas da secretaria  

Guia completo: [`TUTORIAL_IMPLEMENTACAO.md`](./TUTORIAL_IMPLEMENTACAO.md)  
API Google: [`sinapesc-desktop/COMO_INTEGRAR_API.md`](./sinapesc-desktop/COMO_INTEGRAR_API.md)  
Histórico: [`CHANGELOG.md`](./CHANGELOG.md)

---

## Duas peças

| Peça | Quem usa | PC ligado? |
|------|----------|------------|
| `SinapescREAP.exe` | Secretaria | Sim, na sede |
| Site `consulta.html` | Associado (QR) | Não |

Mesma planilha: EXE grava (Editor); site só lê (Leitor).

---

## Histórico de versões

| Versão | O que entrou | EXE |
|--------|----------------|-----|
| **v1.7.10** | Juntar PDF Defeso (declaração+anexos) + ícone Aa | [ZIP](https://github.com/ANmoLOCK/sinapesc-casanova-reap/releases/download/v1.7.10/SinapescREAP-Windows-v1.7.10.zip) |
| **v1.7.9** | Declaração letra de mão (caneta) no PDF oficial | [ZIP](https://github.com/ANmoLOCK/sinapesc-casanova-reap/releases/download/v1.7.9/SinapescREAP-Windows-v1.7.9.zip) |
| **v1.7.8** | Fix: fonte da declaração (engrenagem) passa a gravar/aplicar | [ZIP](https://github.com/ANmoLOCK/sinapesc-casanova-reap/releases/download/v1.7.8/SinapescREAP-Windows-v1.7.8.zip) |
| **v1.7.7** | Declaração sempre no PDF oficial MTE (Times/Allura/Architects) | [ZIP](https://github.com/ANmoLOCK/sinapesc-casanova-reap/releases/download/v1.7.7/SinapescREAP-Windows-v1.7.7.zip) |
| **v1.7.6** | Pasta Drive anexos: exemplo em D: | [ZIP](https://github.com/ANmoLOCK/sinapesc-casanova-reap/releases/download/v1.7.6/SinapescREAP-Windows-v1.7.6.zip) |
| **v1.7.5** | Fontes manuscritas na declaração Defeso (Allura / Architects) | [ZIP](https://github.com/ANmoLOCK/sinapesc-casanova-reap/releases/download/v1.7.5/SinapescREAP-Windows-v1.7.5.zip) |
| **v1.7.4** | Pasta Google Drive sync para anexos Defeso | [ZIP](https://github.com/ANmoLOCK/sinapesc-casanova-reap/releases/download/v1.7.4/SinapescREAP-Windows-v1.7.4.zip) |
| **v1.7.3** | Anexos: fallback local se Drive SA sem cota | [ZIP](https://github.com/ANmoLOCK/sinapesc-casanova-reap/releases/download/v1.7.3/SinapescREAP-Windows-v1.7.3.zip) |
| **v1.7.2** | Fix anexos Defeso → Google Drive | [ZIP](https://github.com/ANmoLOCK/sinapesc-casanova-reap/releases/download/v1.7.2/SinapescREAP-Windows-v1.7.2.zip) |
| **v1.7.1** | Fix lista Defeso (CPFs REAP isolados + ID limpo) | [ZIP](https://github.com/ANmoLOCK/sinapesc-casanova-reap/releases/download/v1.7.1/SinapescREAP-Windows-v1.7.1.zip) |
| **v1.7.0** | Defeso Fácil (ficha, declaração, anexos Drive) | [ZIP](https://github.com/ANmoLOCK/sinapesc-casanova-reap/releases/download/v1.7.0/SinapescREAP-Windows-v1.7.0.zip) |
| **v1.6.21** | Fix contador “agora” + remove sync auto; refresh ao sair | [ZIP](https://github.com/ANmoLOCK/sinapesc-casanova-reap/releases/download/v1.6.21/SinapescREAP-Windows-v1.6.21.zip) |
| **v1.6.20** | Sync automático da planilha a cada 8 min | [ZIP](https://github.com/ANmoLOCK/sinapesc-casanova-reap/releases/download/v1.6.20/SinapescREAP-Windows-v1.6.20.zip) |
| **v1.6.19** | Sync automático da planilha a cada 3 min | [ZIP](https://github.com/ANmoLOCK/sinapesc-casanova-reap/releases/download/v1.6.19/SinapescREAP-Windows-v1.6.19.zip) |
| **v1.6.18** | Filtro 30d/1ano + contador instantâneo; sem legenda | [ZIP](https://github.com/ANmoLOCK/sinapesc-casanova-reap/releases/download/v1.6.18/SinapescREAP-Windows-v1.6.18.zip) |
| **v1.6.17** | Última alteração REAP ao lado do nome (planilha Auditoria) | [ZIP](https://github.com/ANmoLOCK/sinapesc-casanova-reap/releases/download/v1.6.17/SinapescREAP-Windows-v1.6.17.zip) |
| **v1.6.16** | Rodapé status + copyright em linha separada | [ZIP](https://github.com/ANmoLOCK/sinapesc-casanova-reap/releases/download/v1.6.16/SinapescREAP-Windows-v1.6.16.zip) |
| v1.6.15 | Direitos autorais reservados + licença indeterminada | [ZIP](https://github.com/ANmoLOCK/sinapesc-casanova-reap/releases/download/v1.6.15/SinapescREAP-Windows-v1.6.15.zip) |
| v1.6.14 | QR sem link visível + site só consulta CPF | [ZIP](https://github.com/ANmoLOCK/sinapesc-casanova-reap/releases/download/v1.6.14/SinapescREAP-Windows-v1.6.14.zip) |
| v1.6.13 | Impressão no navegador (sem `about:`) | [ZIP](https://github.com/ANmoLOCK/sinapesc-casanova-reap/releases/download/v1.6.13/SinapescREAP-Windows-v1.6.13.zip) |
| v1.6.12 | Nome com primeira letra maiúscula ao salvar | [ZIP](https://github.com/ANmoLOCK/sinapesc-casanova-reap/releases/download/v1.6.12/SinapescREAP-Windows-v1.6.12.zip) |
| v1.6.11 | Lote 50 sócios sem perder o preenchimento | [ZIP](https://github.com/ANmoLOCK/sinapesc-casanova-reap/releases/download/v1.6.11/SinapescREAP-Windows-v1.6.11.zip) |
| v1.6.10 | Mês instantâneo, CPF `105.205.585-45`, lista sem Atualizar | [ZIP](https://github.com/ANmoLOCK/sinapesc-casanova-reap/releases/download/v1.6.10/SinapescREAP-Windows-v1.6.10.zip) |
| v1.6.9 | Marca d'água, layout centralizado, escala padrão | [ZIP](https://github.com/ANmoLOCK/sinapesc-casanova-reap/releases/download/v1.6.9/SinapescREAP-Windows-v1.6.9.zip) |
| v1.6.8 | Selo no ícone, relatório e marca d'água | [ZIP](https://github.com/ANmoLOCK/sinapesc-casanova-reap/releases/download/v1.6.8/SinapescREAP-Windows-v1.6.8.zip) |
| v1.6.7 | Logo selo fiel ao original | [ZIP](https://github.com/ANmoLOCK/sinapesc-casanova-reap/releases/download/v1.6.7/SinapescREAP-Windows-v1.6.7.zip) |
| v1.6.6 | Filtro sócios, imprimir QR, logo selo SINAPESC | [ZIP](https://github.com/ANmoLOCK/sinapesc-casanova-reap/releases/download/v1.6.6/SinapescREAP-Windows-v1.6.6.zip) |
| v1.6.5 | Escala compacta + atalhos completos (lote visual, copiar ano) | [ZIP](https://github.com/ANmoLOCK/sinapesc-casanova-reap/releases/download/v1.6.5/SinapescREAP-Windows-v1.6.5.zip) |
| v1.6.4 | UI web pywebview — idêntica ao mockup (HTML/CSS no EXE) | [ZIP](https://github.com/ANmoLOCK/sinapesc-casanova-reap/releases/download/v1.6.4/SinapescREAP-Windows-v1.6.4.zip) |
| v1.6.2 | UI Tkinter refinada (cartões, meses, abas, busca) | [ZIP](https://github.com/ANmoLOCK/sinapesc-casanova-reap/releases/download/v1.6.2/SinapescREAP-Windows-v1.6.2.zip) |
| v1.6.1 | UI fusionada, Voltar, abas, rodapé limpo | [ZIP](https://github.com/ANmoLOCK/sinapesc-casanova-reap/releases/download/v1.6.1/SinapescREAP-Windows-v1.6.1.zip) |
| v1.6.0 | Pendências, relatório, backup, auditoria na planilha | [ZIP](https://github.com/ANmoLOCK/sinapesc-casanova-reap/releases/download/v1.6.0/SinapescREAP-Windows-v1.6.0.zip) |
| v1.5.1 | Config.Atalhos (lote, massa, copiar ano) | [ZIP](https://github.com/ANmoLOCK/sinapesc-casanova-reap/releases/download/v1.5.1/SinapescREAP-Windows-v1.5.1.zip) |
| v1.5.0 | Lote visual, site Pages, QR permanente | [ZIP](https://github.com/ANmoLOCK/sinapesc-casanova-reap/releases/download/v1.5.0/SinapescREAP-Windows-v1.5.0.zip) |

Versões antigas: [`CHANGELOG.md`](./CHANGELOG.md)

---

## Pastas do repositório

| Pasta | Função |
|-------|--------|
| `sinapesc-desktop/` | Programa Windows (pywebview + Google Sheets) |
| `sinapesc-desktop/web/` | Interface HTML/CSS (mockup aprovado) |
| `sinapesc-desktop/webapp/` | Ponte Python ↔ JavaScript |
| `sinapesc-desktop/controle/` | Pendências, relatório, backup, auditoria |
| `site-publico/` | Site estático (GitHub Pages) |
| `.github/workflows/` | Build EXE + deploy site |

---

## Segurança

- Relatório admin: **CPF completo** · consulta pública: **CPF mascarado**
- Aba **Auditoria**: só no EXE/planilha; o site não lê
- Não compartilhe `google-credentials.json` nem senha do admin
