# Defeso Fácil — configuração

## O que colocar no `config.json`

Na pasta do EXE (`C:\Sinapesc\config.json`), use (ou complete) assim:

```json
{
  "spreadsheet_id": "ID_DA_PLANILHA_REAP",
  "defeso_spreadsheet_id": "1UxDjb78h7tYUnKXPcLVniuqAfWwrbvyf",
  "defeso_anexos_dir": "D:\\Meu Drive\\Sinapesc-Defeso",
  "defeso_drive_folder_id": "",
  "admin_email": "admin@sinapesc.local",
  "admin_password": "sinapesc",
  "public_site_url": "https://anmolock.github.io/sinapesc-casanova-reap"
}
```

Ou pela UI: **Configurações → Escolher pasta…** (recomendado).

### Campos

| Campo | O que é |
|-------|---------|
| `defeso_spreadsheet_id` | Planilha Defeso (dados da ficha) |
| `defeso_anexos_dir` | **Pasta local sincronizada** (Google Drive no PC). Ex.: `D:\Meu Drive\Sinapesc-Defeso` |
| `defeso_declaracao_fonte` | Letra no PDF: `allura` (padrão) · `bairro` · `mao` · `architects` · `padrao`. Engrenagem ⚙. Manuscritas usam efeito de caneta (letra a letra). |
| `defeso_drive_folder_id` | Avançado: ID de pasta via API (só Shared Drive / Workspace) |

---

## Anexos na nuvem (conta Gmail gratuita)

A Conta de Serviço (**robô**) **não tem espaço** no “Meu Drive”. Upload pela API dá 403.

**Solução (v1.7.4):** use o **Google Drive para desktop** e aponte a pasta:

1. Instale o Google Drive e espelhe/sincronize (ex. unidade **D:**)
2. Crie a pasta `Sinapesc-Defeso` dentro do Meu Drive
3. No EXE → **Configurações** → **Escolher pasta…** → selecione essa pasta
4. Anexe na ficha: o arquivo vai para `…\Sinapesc-Defeso\{CPF}\` e o Drive sobe com **sua** cota

Sem pasta configurada, anexos ficam em:

```text
%APPDATA%\SinapescREAP\backups\defeso_anexos\{CPF}\
```

### Opção Workspace (API)

1. Crie um **Drive compartilhado** (Shared Drive)
2. Pasta Defeso dentro dele + `client_email` como membro
3. Cole o ID em `defeso_drive_folder_id` (deixe `defeso_anexos_dir` vazio)

---

### Compartilhar planilha Defeso

1. Planilha REAP → `client_email` → Editor  
2. Planilha Defeso `1UxDjb78h7tYUnKXPcLVniuqAfWwrbvyf` → mesmo e-mail → Editor  

ID limpo (sem `?hl=pt-br`):

```text
1UxDjb78h7tYUnKXPcLVniuqAfWwrbvyf
```

## Fluxo

Home → **Defeso Fácil** → login → Abrir ficha → Salvar → Imprimir declaração → Anexar docs
