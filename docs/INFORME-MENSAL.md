# Informe Mensal — REAP mês a mês por sócio

**Versão:** v1.8.0 (2026-11-05)  
**Download do EXE:** https://github.com/ANmoLOCK/sinapesc-casanova-reap/releases/download/v1.8.0/SinapescREAP-Windows-v1.8.0.zip  
**Página da release:** https://github.com/ANmoLOCK/sinapesc-casanova-reap/releases/tag/v1.8.0  
**Origem do cérebro:** pacote `reap-informe-mensal-v1.8.0.zip` (`cerebro_reformulacao.py` v4)

---

## 1. O que é

Módulo novo do SINAPESC que gera o **REAP do Informe Mensal** de cada sócio, **um mês por vez**, e salva o resultado **dentro da planilha do REAP**. Toda geração e alteração fica registrada na aba **Auditoria** do módulo.

![Hub com o botão Informe Mensal](previews/informe-mensal/informe_01_home.png)

## 2. Como abrir

1. Abra o EXE e entre com o **login único**.
2. No hub de módulos, card **Secretaria**, clique em **Informe Mensal** (ao lado de **Abrir REAP**).
3. Para voltar ao hub use **← Módulos** (não pede senha de novo).

## 3. Tela de sócios

![Lista de sócios](previews/informe-mensal/informe_02_lista.png)

- Os sócios vêm da aba **Pessoas** da planilha REAP: **nome, CPF, telefone e município**.
- **Ano:** escolha o ano do informe (padrão: ano atual).
- **Busca:** por nome, CPF ou telefone (com ou sem pontuação).
- **Filtro:** Todos · Com meses pendentes · Nenhum mês gerado · Completos (Mar–Out) · Com avisos do cérebro.
- **Meses (Jan → Dez):** quadradinho verde = gerado, branco = pendente, cinza = piracema.
- **Gerados:** quantos dos 8 meses de pesca já têm REAP. **Kg ano:** soma dos kg já gerados.
- Clique na linha (ou em **Abrir**) para abrir a caixa do sócio.

## 4. Caixa do sócio (os 12 meses)

![Caixa do sócio](previews/informe-mensal/informe_04_socio_pendente.png)

| Mês | Situação |
|-----|----------|
| Janeiro | **ÉPOCA DE PIRACEMA** (cinza, não clica) |
| Fevereiro | **ÉPOCA DE PIRACEMA** (cinza, não clica) |
| Março → Outubro | Liberados: *Pendente — gerar REAP* ou ✓ com dias · espécies · kg |
| Novembro | **ÉPOCA DE PIRACEMA** (cinza, não clica) |
| Dezembro | **ÉPOCA DE PIRACEMA** (cinza, não clica) |

Abaixo dos meses aparece o resumo do ano: meses gerados (x/8), peso acumulado, alvo do ano do sócio, faixa 540–650 kg e a contagem de espécies por mês. Se alguma regra do ano estiver fora, aparece um aviso amarelo.

### 4.1 Gerar o REAP de um mês

1. Clique no mês pendente.
2. Confira o **Município** (Casa Nova ou Remanso; vem do cadastro do sócio).
3. Clique **Gerar REAP de <mês>**.

O cérebro gera e **já salva na planilha** (aba `InformeMensal`).

![Mês gerado](previews/informe-mensal/informe_05_gerado.png)

O detalhe mostra: houve pesca SIM, dias de pesca, local (Rio · BAHIA), município, ambiente (Água Doce), petrecho (Emalhe), espécies na ordem, kg e valor médio (R$/kg), total do mês, quem gerou e quando.

### 4.2 Botões do mês gerado

| Botão | O que faz |
|-------|-----------|
| **Copiar texto** | Copia o REAP em texto para conferir/colar no Informe Mensal do gov.br |
| **Editar** | Ajuste manual de dias, município, espécies, kg e ordem (↑) |
| **Regerar** | Pede confirmação e gera um novo REAP para o mês, sem repetir os outros meses |
| **Excluir mês** | Pede confirmação e remove a linha do mês da planilha |

### 4.3 Editar

![Editar](previews/informe-mensal/informe_06_editar.png)

O sistema **não salva** se a edição quebrar uma regra do mês:

- dias entre **16 e 21**;
- **4, 5, 6 ou 8** espécies;
- só peixes do catálogo, sem repetir no mesmo mês;
- kg **inteiro entre 5 e 22**;
- os kg não podem ser todos iguais;
- o conjunto espécies + kg não pode ser igual ao de outro mês do mesmo sócio.

O **valor** é sempre o preço varejo da espécie (não se digita).

## 5. Regras do cérebro

### 5.1 Calendário

| Mês | Pesca |
|-----|-------|
| Jan / Fev / Nov / Dez | NÃO — época de piracema |
| Mar → Out | SIM nos 8 meses |

### 5.2 Preços varejo (VALOR no site = preço, não multiplica por kg)

| Peixe | R$/kg |
|-------|------:|
| Tucunaré | 18 |
| Tambaqui | 21 |
| Tilápia | 16 |
| Curimatã | 15 |
| Dourado-de-água-doce | 23 |
| Piranha | 15 |
| Piau | 14 |
| Pescada | 19 |

### 5.3 Espécies, valores e kg mudam por mês (atividade sazonal)

Cada mês favorece peixes diferentes (mais kg e mais chance de entrar na lista):

| Mês | Mais ativos | Menos ativos |
|-----|-------------|--------------|
| Março | Curimatã, Tilápia, Piau | Tambaqui, Dourado |
| Abril | Curimatã, Tilápia, Piau, Tucunaré | Tambaqui, Dourado |
| Maio | Tilápia, Piau, Curimatã, Pescada | Dourado |
| Junho | Tambaqui, Tilápia, Pescada | Piranha |
| Julho | Tambaqui, Pescada, Tilápia | Piranha |
| Agosto | Tambaqui, Pescada, Tilápia | Curimatã, Piranha |
| Setembro | Tucunaré, Piranha, Tilápia | Dourado |
| Outubro | Tucunaré, Piranha, Tilápia, Piau | Dourado |

### 5.4 Nunca repetir (intercalação)

Como o operador gera **um mês por vez**, cada mês novo é calculado olhando os meses que o sócio já tem salvos:

- **Quantidade de espécies:** o ano fecha com a mistura **4 / 5 / 6 / 8**, no máximo 3 meses com 4 (nada de `4,4,4,4,4,4,6,8`), e evita repetir a quantidade do mês vizinho.
- **Conjunto espécies + kg:** nunca igual ao de outro mês do ano.
- **Posição dos peixes:** a ordem nunca se repete, e o primeiro peixe é diferente do primeiro do mês vizinho.
- **Dias:** diferentes dos do mês vizinho e, quando possível, de todos os outros meses.
- **Kg:** inteiros com viés da época; dentro do mês uns peixes pegam mais, outros menos.
- **Peso anual:** cada sócio tem um **alvo próprio** entre **540 e 650 kg** (fixo pelo CPF + ano). Os meses dividem esse alvo e o último mês gerado fecha a conta.
- **Entre sócios:** a assinatura do mês é comparada com a de todos os sócios; nenhum mês sai idêntico ao de outro pescador.

A ordem de geração não importa: o operador pode gerar Junho antes de Março.

## 6. Auditoria

![Auditoria](previews/informe-mensal/informe_08_auditoria.png)

Aba **Auditoria** dentro do módulo, com busca e filtro por ação:

| Ação | Exemplo do texto |
|------|------------------|
| **Gerou** | Gerou REAP de Junho/2026 — Antônio Pereira Lima: 6 espécies, 20 dias, 88 kg |
| **Regerou** | Regerou REAP de Abril/2026 — …: 8 espécies, 19 dias, 105 kg (antes: 5 espécies, 18 dias, 72 kg) |
| **Alterou** | Alterou REAP de Julho/2026 — …: dias 18→20; Tambaqui 22→7 kg; +Piau 9 kg; −Pescada |
| **Excluiu** | Excluiu REAP de Outubro/2026 — … (5 espécies, 18 dias, 81 kg) |

Cada registro guarda data/hora, **usuário logado**, ação, detalhe, sócio, ano e mês.

## 7. Onde os dados ficam (planilha REAP)

O módulo usa a **mesma planilha do REAP** (`spreadsheet_id` do `config.json`). As abas são criadas sozinhas no primeiro uso.

### 7.1 Aba `InformeMensal` — uma linha por sócio/ano/mês

| Coluna | Conteúdo |
|--------|----------|
| id | identificador da linha |
| personId | id do sócio na aba Pessoas |
| cpf, nome, telefone | dados do sócio |
| ano, mes | ex.: `2026`, `jun` |
| houvePesca | `SIM` |
| dias | 16–21 |
| nEspecies | 4 / 5 / 6 / 8 |
| especies | texto legível: `Pescada 20 kg R$ 19,00; …` |
| especiesJson | lista na ordem: `[{"nome","kg","valor"}]` |
| pesoMes, faturamentoMes | soma de kg e kg × preço (referência) |
| municipio, local, petrecho, ambiente | Casa Nova/Remanso, Rio, Emalhe, Água Doce |
| assinatura | impressão digital do mês (anti-repetição) |
| geradoEm, geradoPor | quem gerou e quando |
| atualizadoEm, atualizadoPor | última alteração |
| motor | `cerebro_reformulacao/v4-mensal` (ou `+manual` após edição) |

### 7.2 Aba `InformeAuditoria`

`id | em | usuario | acao | detalhe | personId | nome | ano | meses` (mesmo formato da Auditoria dos outros módulos).

> A aba `Reap` (controle de meses marcados) **não** é alterada pelo Informe Mensal.

## 8. Arquivos do código

| Arquivo | Função |
|---------|--------|
| `sinapesc-desktop/controle/informe_mensal.py` | Cérebro mês a mês: regras, preços, sazonalidade, anti-repetição, validação, texto para o site |
| `sinapesc-desktop/sheets/informe_mensal_service.py` | Leitura/gravação das abas `InformeMensal` e `InformeAuditoria` |
| `sinapesc-desktop/webapp/api.py` | `load_informe_mensal`, `gerar_informe_mes`, `salvar_informe_mes`, `excluir_informe_mes`, `load_informe_auditoria` |
| `sinapesc-desktop/web/js/informe_mensal.js` | Tela do módulo (lista, caixa de meses, edição, auditoria) |
| `sinapesc-desktop/web/css/informe_mensal.css` | Visual (piracema em cinza, grade de meses) |
| `sinapesc-desktop/web/js/app.js` | Botão no hub, rota `informe_mensal`, cabeçalho ← Módulos |
| `sinapesc-desktop/build_exe.spec` | Inclui os módulos novos no EXE |
| `sinapesc-desktop/test_informe_mensal.py` | Testes do módulo |

## 9. Testes feitos

- 120 sócios simulados, cada um gerando os 8 meses em ordem aleatória: nenhuma regra quebrada, peso anual sempre entre 540 e 650 kg.
- Regerar, bloqueio da piracema, validação da edição, gravação/exclusão na planilha (cliente falso) e auditoria.
- Fluxo completo da API: gerar 8 meses, regerar, editar, excluir, auditoria.
- Fluxo da tela em navegador: gerar, editar, salvar e conferir a auditoria (as capturas deste documento).

Rodar localmente:

```bash
cd sinapesc-desktop
python test_informe_mensal.py
```

## 10. Mudanças da v1.8.0

- Botão **Informe Mensal** ao lado de **Abrir REAP**.
- Lista de sócios com busca, filtros, ano e progresso Jan → Dez.
- Caixa por sócio com 12 meses; Jan/Fev/Nov/Dez em cinza — **ÉPOCA DE PIRACEMA**.
- Gerar / Regerar / Editar / Excluir / Copiar texto por mês, salvando na planilha REAP.
- Cérebro v4 adaptado para mês a mês, sem repetir espécies, kg, posições ou dias.
- Aba **Auditoria** do módulo.
