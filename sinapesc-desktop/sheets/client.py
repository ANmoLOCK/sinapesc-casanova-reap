"""
=============================================================================
GOOGLE SHEETS — CAMADA DE CLIENTE (didática)
=============================================================================

Este arquivo ensina, passo a passo, como o programa conversa com a planilha.

PASSO 0 — O que você precisa no Google Cloud
--------------------------------------------
1. Crie um projeto em https://console.cloud.google.com
2. Ative a API "Google Sheets API"
3. Crie uma Conta de Serviço (IAM > Contas de serviço)
4. Gere uma chave JSON da conta de serviço
5. Abra a planilha no Google Drive e COMPARTILHE com o e-mail da
   conta de serviço (ex.: sinapesc@projeto.iam.gserviceaccount.com)
   com permissão de Editor.
6. Copie o ID da planilha da URL:
   https://docs.google.com/spreadsheets/d/ESTE_E_O_ID/edit

PASSO 1 — Autenticação (JWT / Conta de Serviço)
-----------------------------------------------
Em vez de o usuário fazer login no Google a cada vez, usamos uma
"conta de robô" (service account). O Google valida o e-mail + chave
privada e libera o escopo spreadsheets.

PASSO 2 — Cliente da API v4
---------------------------
`googleapiclient.discovery.build("sheets", "v4", credentials=creds)`
cria o objeto que chama endpoints REST:
  - spreadsheets().get(...)
  - spreadsheets().values().get / update / append
  - spreadsheets().batchUpdate(...)

PASSO 3 — Abas (tabs)
------------------------------------
Pessoas:    id | nome | cpf | criadoEm | municipio
Reap:       id | personId | ano | jan..dez | atualizadoEm
Auditoria:  id | em | usuario | acao | detalhe | personId | nome | ano | meses
Config:     chave | valor   (calendário REAP compartilhado entre admins)
"""

from __future__ import annotations

import time
from typing import Any, List, Optional, Sequence

from google.oauth2 import service_account
from googleapiclient.discovery import build

from .models import MESES

# Escopo mínimo das planilhas (Drive fica só no cliente Drive).
SCOPES = ["https://www.googleapis.com/auth/spreadsheets"]
DRIVE_SCOPES = [
    "https://www.googleapis.com/auth/spreadsheets",
    "https://www.googleapis.com/auth/drive",
]


def normalize_sheet_id(value: str) -> str:
    """Aceita ID puro ou URL completa do Google Sheets/Drive."""
    raw = (value or "").strip()
    if not raw:
        return ""
    # remove query/hash
    raw = raw.split("?", 1)[0].split("#", 1)[0].strip()
    # URL /d/<id>/
    if "/d/" in raw:
        raw = raw.split("/d/", 1)[1]
        raw = raw.split("/", 1)[0]
    # URL /folders/<id>
    if "/folders/" in raw:
        raw = raw.split("/folders/", 1)[1]
        raw = raw.split("/", 1)[0]
    return raw.strip()


PESSOAS_TAB = "Pessoas"
REAP_TAB = "Reap"
AUDITORIA_TAB = "Auditoria"
CONFIG_TAB = "Config"

PESSOAS_HEADER = ["id", "nome", "cpf", "criadoEm", "municipio"]
REAP_HEADER = ["id", "personId", "ano", *MESES, "atualizadoEm"]
AUDITORIA_HEADER = [
    "id",
    "em",
    "usuario",
    "acao",
    "detalhe",
    "personId",
    "nome",
    "ano",
    "meses",
]
CONFIG_HEADER = ["chave", "valor"]


class SheetsConfigError(Exception):
    """Credenciais ou ID da planilha ausentes / inválidos."""


class GoogleSheetsClient:
    """
    Cliente fino sobre a Google Sheets API v4.

    Responsabilidade única: autenticar e executar operações de baixo nível
    (ler células, escrever células, criar abas). A regra de negócio fica
    em `service.py`.
    """

    def __init__(
        self,
        service_account_email: str,
        private_key: str,
        spreadsheet_id: str,
        *,
        credentials_info: Optional[dict] = None,
    ) -> None:
        if not spreadsheet_id:
            raise SheetsConfigError("GOOGLE_SHEET_ID (ID da planilha) não informado.")

        self.spreadsheet_id = normalize_sheet_id(spreadsheet_id)
        if not self.spreadsheet_id:
            raise SheetsConfigError("ID da planilha inválido.")
        self._service = None
        self._tabs_ready = False

        # ---------------------------------------------------------------
        # PASSO 1: montar as credenciais da Conta de Serviço
        # ---------------------------------------------------------------
        # Aceitamos duas formas:
        #   A) JSON completo da chave (recomendado no desktop)
        #   B) e-mail + private_key (compatível com o .env da versão web)
        if credentials_info:
            creds = service_account.Credentials.from_service_account_info(
                credentials_info,
                scopes=SCOPES,
            )
        else:
            if not service_account_email or not private_key:
                raise SheetsConfigError(
                    "Informe o JSON da Conta de Serviço ou e-mail + chave privada."
                )
            # No Windows/JSON às vezes a chave vem com "\\n" literais;
            # substituímos para quebras de linha reais do PEM.
            key = private_key.replace("\\n", "\n").strip()
            info = {
                "type": "service_account",
                "client_email": service_account_email.strip(),
                "private_key": key,
                "token_uri": "https://oauth2.googleapis.com/token",
            }
            creds = service_account.Credentials.from_service_account_info(
                info,
                scopes=SCOPES,
            )

        # ---------------------------------------------------------------
        # PASSO 2: criar o cliente HTTP da Sheets API v4
        # ---------------------------------------------------------------
        # cache_discovery=False evita aviso de cache em ambientes empacotados (.exe)
        self._service = build("sheets", "v4", credentials=creds, cache_discovery=False)

    # ------------------------------------------------------------------
    # PASSO 3: garantir que as abas existem com cabeçalho correto
    # ------------------------------------------------------------------
    def ensure_tabs(self) -> None:
        """Cria as abas Pessoas, Reap, Auditoria e Config se ainda não existirem."""
        if self._tabs_ready:
            return

        meta = (
            self._service.spreadsheets()
            .get(spreadsheetId=self.spreadsheet_id)
            .execute()
        )
        existing = {
            sheet["properties"]["title"]
            for sheet in meta.get("sheets", [])
            if sheet.get("properties", {}).get("title")
        }

        wanted = (
            (PESSOAS_TAB, PESSOAS_HEADER),
            (REAP_TAB, REAP_HEADER),
            (AUDITORIA_TAB, AUDITORIA_HEADER),
            (CONFIG_TAB, CONFIG_HEADER),
        )
        requests: List[dict] = []
        for title, _header in wanted:
            if title not in existing:
                requests.append({"addSheet": {"properties": {"title": title}}})

        if requests:
            self._service.spreadsheets().batchUpdate(
                spreadsheetId=self.spreadsheet_id,
                body={"requests": requests},
            ).execute()

        for title, header in wanted:
            if title not in existing:
                self.update_values(f"{title}!A1", [header])

        # Planilhas antigas: acrescenta coluna municipio em Pessoas
        p_header = self.get_values(f"{PESSOAS_TAB}!A1:E1")
        if p_header and p_header[0]:
            row = list(p_header[0])
            while len(row) < 4:
                row.append("")
            if len(row) == 4:
                row.append("municipio")
                self.update_values(f"{PESSOAS_TAB}!A1:E1", [row])
            elif len(row) >= 5 and not str(row[4]).strip():
                row[4] = "municipio"
                self.update_values(f"{PESSOAS_TAB}!A1:E1", [row[:5]])

        self._tabs_ready = True

    # ------------------------------------------------------------------
    # Operações básicas de valores (o "CRUD" de células)
    # ------------------------------------------------------------------
    def get_values(self, range_a1: str) -> List[List[str]]:
        """
        Lê um intervalo no formato A1 (ex.: 'Pessoas!A2:D').

        Retorna lista de linhas; cada linha é lista de strings.
        Células vazias no final da linha podem ser omitidas pela API.
        """
        result = (
            self._service.spreadsheets()
            .values()
            .get(spreadsheetId=self.spreadsheet_id, range=range_a1)
            .execute()
        )
        return result.get("values", []) or []

    def update_values(self, range_a1: str, values: Sequence[Sequence[Any]]) -> None:
        """Escreve valores em um intervalo (sobrescreve)."""
        self._service.spreadsheets().values().update(
            spreadsheetId=self.spreadsheet_id,
            range=range_a1,
            valueInputOption="RAW",
            body={"values": list(values)},
        ).execute()

    def append_values(self, range_a1: str, values: Sequence[Sequence[Any]]) -> None:
        """
        Acrescenta linhas no final da tabela (abaixo dos dados existentes).

        `insertDataOption=INSERT_ROWS` empurra linhas em vez de sobrescrever.
        Repete até 4 vezes se o Google devolver 429/500/503/timeout (lote grande).
        """
        last_exc: Exception | None = None
        for attempt in range(4):
            try:
                self._service.spreadsheets().values().append(
                    spreadsheetId=self.spreadsheet_id,
                    range=range_a1,
                    valueInputOption="RAW",
                    insertDataOption="INSERT_ROWS",
                    body={"values": list(values)},
                ).execute()
                return
            except Exception as exc:  # noqa: BLE001
                last_exc = exc
                msg = str(exc).lower()
                retryable = any(
                    token in msg
                    for token in ("429", "500", "503", "timeout", "timed out", "backend error", "rate")
                )
                if attempt < 3 and retryable:
                    time.sleep(1.2 * (attempt + 1))
                    continue
                raise
        if last_exc:
            raise last_exc

    def batch_update_values(self, data: List[dict], *, chunk_size: int = 500) -> None:
        """Várias faixas de células em poucas chamadas (limite Google: ~1000 faixas/request)."""
        if not data:
            return
        size = max(1, int(chunk_size))
        for i in range(0, len(data), size):
            chunk = data[i : i + size]
            self._service.spreadsheets().values().batchUpdate(
                spreadsheetId=self.spreadsheet_id,
                body={"valueInputOption": "RAW", "data": chunk},
            ).execute()

    def batch_update(self, requests: List[dict]) -> None:
        """Envia várias alterações estruturais de uma vez (ex.: apagar linhas)."""
        if not requests:
            return
        self._service.spreadsheets().batchUpdate(
            spreadsheetId=self.spreadsheet_id,
            body={"requests": requests},
        ).execute()

    def get_sheet_ids_by_title(self) -> dict[str, int]:
        """Mapa título da aba -> sheetId numérico (necessário para deleteDimension)."""
        meta = (
            self._service.spreadsheets()
            .get(spreadsheetId=self.spreadsheet_id)
            .execute()
        )
        out: dict[str, int] = {}
        for sheet in meta.get("sheets", []):
            props = sheet.get("properties") or {}
            title = props.get("title")
            sheet_id = props.get("sheetId")
            if title is not None and sheet_id is not None:
                out[title] = int(sheet_id)
        return out
