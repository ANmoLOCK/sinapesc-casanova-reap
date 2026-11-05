"""Abas InformeMensal + InformeAuditoria dentro da planilha do REAP."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Dict, List, Optional

from controle.auditoria import AUDITORIA_COLUNAS, EventoAuditoria, evento_para_row, row_to_evento
from controle.informe_mensal import (
    INFORME_AUDITORIA_TAB,
    INFORME_DATA_RANGE,
    INFORME_HEADER,
    INFORME_HEADER_RANGE,
    INFORME_TAB,
    InformeMes,
    row_to_informe,
)
from sheets.client import GoogleSheetsClient


class InformeMensalService:
    def __init__(self, client: GoogleSheetsClient) -> None:
        self.client = client
        self.actor: str = ""
        self._ready = False
        self._audit_silent = False

    def ensure(self) -> None:
        if self._ready:
            return
        meta = (
            self.client._service.spreadsheets()
            .get(spreadsheetId=self.client.spreadsheet_id)
            .execute()
        )
        existing = {
            sheet["properties"]["title"]
            for sheet in meta.get("sheets", [])
            if sheet.get("properties", {}).get("title")
        }
        to_add = [
            {"addSheet": {"properties": {"title": title}}}
            for title in (INFORME_TAB, INFORME_AUDITORIA_TAB)
            if title not in existing
        ]
        if to_add:
            self.client.batch_update(to_add)

        header = self.client.get_values(f"{INFORME_TAB}!{INFORME_HEADER_RANGE}")
        if not header or not header[0] or list(header[0]) != INFORME_HEADER:
            self.client.update_values(f"{INFORME_TAB}!A1", [INFORME_HEADER])

        aud = self.client.get_values(f"{INFORME_AUDITORIA_TAB}!A1:I1")
        if not aud or not aud[0]:
            self.client.update_values(f"{INFORME_AUDITORIA_TAB}!A1", [AUDITORIA_COLUNAS])
        self._ready = True

    def _linhas(self) -> List[tuple]:
        """[(row_idx, InformeMes)] — 1 GET."""
        self.ensure()
        rows = self.client.get_values(f"{INFORME_TAB}!{INFORME_DATA_RANGE}")
        out = []
        for i, r in enumerate(rows):
            reg = row_to_informe(r)
            if reg:
                out.append((i + 2, reg))
        return out

    def listar(self, ano: Optional[int] = None) -> List[InformeMes]:
        regs = [reg for _, reg in self._linhas()]
        if ano is not None:
            regs = [r for r in regs if r.ano == int(ano)]
        return regs

    def meses_do_socio(self, person_id: str, ano: int) -> Dict[str, InformeMes]:
        return {
            r.mes: r
            for r in self.listar(ano)
            if r.person_id == person_id
        }

    def salvar(self, reg: InformeMes) -> InformeMes:
        """Upsert por (personId, ano, mês)."""
        linhas = self._linhas()
        row_idx = next(
            (
                idx
                for idx, r in linhas
                if r.person_id == reg.person_id and r.ano == reg.ano and r.mes == reg.mes
            ),
            -1,
        )
        if row_idx > 0:
            self.client.update_values(f"{INFORME_TAB}!A{row_idx}", [reg.to_row()])
        else:
            self.client.append_values(f"{INFORME_TAB}!A2", [reg.to_row()])
        return reg

    def excluir(self, person_id: str, ano: int, mes: str) -> Optional[InformeMes]:
        linhas = self._linhas()
        alvo = next(
            (
                (idx, r)
                for idx, r in linhas
                if r.person_id == person_id and r.ano == int(ano) and r.mes == mes
            ),
            None,
        )
        if not alvo:
            return None
        row_idx, reg = alvo
        tab_id = self.client.get_sheet_ids_by_title().get(INFORME_TAB)
        if tab_id is None:
            raise ValueError("Aba InformeMensal não encontrada.")
        self.client.batch_update(
            [
                {
                    "deleteDimension": {
                        "range": {
                            "sheetId": tab_id,
                            "dimension": "ROWS",
                            "startIndex": row_idx - 1,
                            "endIndex": row_idx,
                        }
                    }
                }
            ]
        )
        return reg

    def registrar_auditoria(
        self,
        acao: str,
        detalhe: str,
        *,
        person_id: str = "",
        nome: str = "",
        ano: str = "",
        meses: str = "",
    ) -> None:
        """Grava na aba InformeAuditoria. Nunca interrompe a ação."""
        if self._audit_silent:
            return
        evt = EventoAuditoria(
            id=str(uuid.uuid4()),
            em=datetime.now().astimezone().strftime("%Y-%m-%d %H:%M:%S"),
            usuario=(self.actor or "").strip() or "(sem login)",
            acao=acao,
            detalhe=detalhe,
            person_id=person_id or "",
            nome=nome or "",
            ano=str(ano or ""),
            meses=meses or "",
        )
        self._audit_silent = True
        try:
            self.ensure()
            self.client.append_values(f"{INFORME_AUDITORIA_TAB}!A2", [evento_para_row(evt)])
        except Exception:  # noqa: BLE001
            pass
        finally:
            self._audit_silent = False

    def listar_auditoria(self, limite: int = 500) -> List[EventoAuditoria]:
        self.ensure()
        rows = self.client.get_values(f"{INFORME_AUDITORIA_TAB}!A2:I")
        eventos = [e for e in (row_to_evento(r) for r in rows) if e]
        eventos.reverse()
        return eventos[: max(1, int(limite))]
