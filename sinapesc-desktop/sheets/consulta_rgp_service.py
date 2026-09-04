"""CRUD da aba ConsultaRGP em planilha dedicada (ou fallback REAP)."""

from __future__ import annotations

from typing import Dict, List, Optional

from controle.consulta_rgp import (
    CONSULTA_RGP_HEADER,
    CONSULTA_RGP_TAB,
    RegistroConsultaRgp,
    new_id,
    now_stamp,
    payload_to_registro,
    row_to_registro,
)
from sheets.client import GoogleSheetsClient, SheetsConfigError, normalize_sheet_id
from ui.formatters import format_nome, only_digits


class ConsultaRgpService:
    def __init__(self, client: GoogleSheetsClient) -> None:
        self.client = client
        self._ready = False

    @classmethod
    def from_config(cls, cfg: dict) -> "ConsultaRgpService":
        sid = normalize_sheet_id(
            str(
                cfg.get("consulta_rgp_spreadsheet_id")
                or cfg.get("spreadsheet_id")
                or ""
            )
        )
        if not sid:
            raise SheetsConfigError(
                "Configure o ID da planilha Consulta RGP "
                "(consulta_rgp_spreadsheet_id) ou o spreadsheet_id do REAP."
            )
        credentials_json = cfg.get("credentials_json")
        client = GoogleSheetsClient(
            service_account_email=cfg.get("service_account_email", ""),
            private_key=cfg.get("private_key", ""),
            spreadsheet_id=sid,
            credentials_info=credentials_json if isinstance(credentials_json, dict) else None,
        )
        return cls(client)

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
        if CONSULTA_RGP_TAB not in existing:
            self.client._service.spreadsheets().batchUpdate(
                spreadsheetId=self.client.spreadsheet_id,
                body={
                    "requests": [
                        {"addSheet": {"properties": {"title": CONSULTA_RGP_TAB}}}
                    ]
                },
            ).execute()
            self.client.update_values(f"{CONSULTA_RGP_TAB}!A1", [CONSULTA_RGP_HEADER])
        else:
            header = self.client.get_values(f"{CONSULTA_RGP_TAB}!A1:S1")
            if not header:
                self.client.update_values(f"{CONSULTA_RGP_TAB}!A1", [CONSULTA_RGP_HEADER])
            elif header and header[0]:
                row = list(header[0])
                changed = False
                for idx, label in enumerate(CONSULTA_RGP_HEADER):
                    while len(row) <= idx:
                        row.append("")
                        changed = True
                    if not str(row[idx]).strip():
                        row[idx] = label
                        changed = True
                if changed:
                    self.client.update_values(
                        f"{CONSULTA_RGP_TAB}!A1:S1",
                        [row[: len(CONSULTA_RGP_HEADER)]],
                    )
        self._ready = True

    def listar(self) -> List[RegistroConsultaRgp]:
        self.ensure()
        rows = self.client.get_values(f"{CONSULTA_RGP_TAB}!A2:S")
        out: List[RegistroConsultaRgp] = []
        for r in rows:
            reg = row_to_registro(r)
            if reg:
                out.append(reg)
        return out

    def por_id(self, registro_id: str) -> Optional[RegistroConsultaRgp]:
        rid = (registro_id or "").strip()
        if not rid:
            return None
        for r in self.listar():
            if r.id == rid:
                return r
        return None

    def por_cpf(self, cpf: str) -> Optional[RegistroConsultaRgp]:
        digits = only_digits(cpf)
        if len(digits) != 11:
            return None
        for r in self.listar():
            if only_digits(r.cpf) == digits:
                return r
        return None

    def _row_index(self, registro_id: str) -> int:
        self.ensure()
        rows = self.client.get_values(f"{CONSULTA_RGP_TAB}!A2:A")
        for i, r in enumerate(rows):
            if r and str(r[0]).strip() == registro_id:
                return i + 2
        return -1

    def salvar(self, payload: Dict) -> RegistroConsultaRgp:
        self.ensure()
        existing = None
        rid = str(payload.get("id") or "").strip()
        if rid:
            existing = self.por_id(rid)
        if existing is None:
            cpf = only_digits(str(payload.get("cpf") or ""))
            if len(cpf) == 11:
                existing = self.por_cpf(cpf)
        reg = payload_to_registro(payload, existing=existing)
        if not reg.cpf or len(only_digits(reg.cpf)) != 11:
            raise ValueError("CPF inválido para Consulta RGP.")
        if not reg.nome.strip():
            raise ValueError("Nome obrigatório.")

        row_idx = self._row_index(reg.id) if existing and existing.id == reg.id else -1
        if row_idx < 0 and existing:
            reg.id = existing.id
            reg.criado_em = existing.criado_em or reg.criado_em
            reg.timeline = existing.timeline or reg.timeline
            row_idx = self._row_index(reg.id)

        if row_idx > 0:
            self.client.update_values(f"{CONSULTA_RGP_TAB}!A{row_idx}", [reg.to_row()])
        else:
            self.client.append_values(f"{CONSULTA_RGP_TAB}!A2", [reg.to_row()])
        return reg

    def upsert_manual(
        self,
        *,
        nome: str,
        cpf: str,
        telefone: str = "",
        municipio: str = "",
        uf: str = "",
        email: str = "",
        observacao: str = "",
        person_id: str = "",
    ) -> RegistroConsultaRgp:
        """Inclui/atualiza registro na Consulta (módulo independente — dados vindos do usuário)."""
        digits = only_digits(cpf)
        if len(digits) != 11:
            raise ValueError("CPF inválido (11 dígitos).")
        existing = self.por_cpf(digits)
        agora = now_stamp()
        if existing:
            payload = {
                "id": existing.id,
                "person_id": person_id or existing.person_id,
                "nome": nome or existing.nome,
                "cpf": digits,
                "telefone": telefone if telefone is not None else existing.telefone,
                "municipio": municipio if municipio is not None else existing.municipio,
                "uf": uf or existing.uf,
                "email": email if email is not None else existing.email,
                "observacao": observacao if observacao is not None else existing.observacao,
                "situacao_rgp": existing.situacao_rgp,
                "ultima_consulta_em": existing.ultima_consulta_em,
                "codigo_rgp": existing.codigo_rgp,
                "categoria": existing.categoria,
                "importado_reap_em": existing.importado_reap_em,
                "importado_defeso_em": existing.importado_defeso_em,
                "cadastro_reap_em": existing.cadastro_reap_em,
                "timeline": existing.timeline,
            }
            # Se telefone/município vieram no lote, atualiza
            if str(telefone or "").strip():
                payload["telefone"] = str(telefone).strip()
            if str(municipio or "").strip():
                payload["municipio"] = str(municipio).strip()
            return self.salvar(payload)

        reg = RegistroConsultaRgp(
            id=new_id(),
            person_id=person_id or "",
            nome=format_nome(nome),
            cpf=digits,
            telefone=str(telefone or "").strip(),
            municipio=str(municipio or "").strip(),
            uf=str(uf or "").strip().upper()[:2],
            email=str(email or "").strip(),
            observacao=str(observacao or "").strip(),
            criado_em=agora,
            atualizado_em=agora,
        )
        reg.append_timeline("Cadastro criado", ator="Usuário")
        self.ensure()
        self.client.append_values(f"{CONSULTA_RGP_TAB}!A2", [reg.to_row()])
        return reg

    def marcar_import_reap(self, registro_id: str) -> RegistroConsultaRgp:
        reg = self.por_id(registro_id)
        if not reg:
            raise ValueError("Registro Consulta RGP não encontrado.")
        reg.importado_reap_em = now_stamp()
        reg.atualizado_em = reg.importado_reap_em
        reg.append_timeline("Importado para REAP (município + telefone)", ator="Sistema")
        row_idx = self._row_index(reg.id)
        if row_idx < 0:
            raise ValueError("Linha não encontrada.")
        self.client.update_values(f"{CONSULTA_RGP_TAB}!A{row_idx}", [reg.to_row()])
        return reg

    def marcar_import_defeso(self, registro_id: str) -> RegistroConsultaRgp:
        reg = self.por_id(registro_id)
        if not reg:
            raise ValueError("Registro Consulta RGP não encontrado.")
        reg.importado_defeso_em = now_stamp()
        reg.atualizado_em = reg.importado_defeso_em
        reg.append_timeline("Importado para Defeso (CPF + nome)", ator="Sistema")
        row_idx = self._row_index(reg.id)
        if row_idx < 0:
            raise ValueError("Linha não encontrada.")
        self.client.update_values(f"{CONSULTA_RGP_TAB}!A{row_idx}", [reg.to_row()])
        return reg
