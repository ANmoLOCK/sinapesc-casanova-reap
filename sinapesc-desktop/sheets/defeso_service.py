"""CRUD da aba Defeso em planilha dedicada (Defeso Fácil)."""

from __future__ import annotations

from typing import Dict, Iterable, List, Optional

from controle.defeso import (
    DEFESO_HEADER,
    DEFESO_TAB,
    FichaDefeso,
    now_stamp,
    payload_to_ficha,
    row_to_ficha,
    validar_ficha,
)
from sheets.client import GoogleSheetsClient, SheetsConfigError, normalize_sheet_id
from ui.formatters import only_digits


class DefesoService:
    def __init__(self, client: GoogleSheetsClient) -> None:
        self.client = client
        self._ready = False

    @classmethod
    def from_config(cls, cfg: dict) -> "DefesoService":
        sid = normalize_sheet_id(
            str(cfg.get("defeso_spreadsheet_id") or cfg.get("spreadsheet_id") or "")
        )
        if not sid:
            raise SheetsConfigError(
                "Configure o ID da planilha Defeso (defeso_spreadsheet_id) em config.json."
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
        if DEFESO_TAB not in existing:
            self.client._service.spreadsheets().batchUpdate(
                spreadsheetId=self.client.spreadsheet_id,
                body={"requests": [{"addSheet": {"properties": {"title": DEFESO_TAB}}}]},
            ).execute()
            self.client.update_values(f"{DEFESO_TAB}!A1", [DEFESO_HEADER])
        else:
            header = self.client.get_values(f"{DEFESO_TAB}!A1:Z1")
            if not header:
                self.client.update_values(f"{DEFESO_TAB}!A1", [DEFESO_HEADER])
            elif header and header[0]:
                row = list(header[0])
                extras = [
                    (21, "telefoneReap"),
                    (22, "parcelasRecebidas"),
                    (23, "entradaConfirmada"),
                    (24, "observacao"),
                    (25, "lotes"),
                ]
                changed = False
                for idx, label in extras:
                    while len(row) <= idx:
                        row.append("")
                        changed = True
                    if not str(row[idx]).strip():
                        row[idx] = label
                        changed = True
                if changed:
                    self.client.update_values(f"{DEFESO_TAB}!A1:Z1", [row[: len(DEFESO_HEADER)]])
        self._ready = True

    def listar(self) -> List[FichaDefeso]:
        self.ensure()
        rows = self.client.get_values(f"{DEFESO_TAB}!A2:Z")
        out: List[FichaDefeso] = []
        for r in rows:
            f = row_to_ficha(r)
            if f:
                out.append(f)
        return out

    def por_id(self, ficha_id: str) -> Optional[FichaDefeso]:
        fid = (ficha_id or "").strip()
        if not fid:
            return None
        for f in self.listar():
            if f.id == fid:
                return f
        return None

    def por_cpf(self, cpf: str) -> Optional[FichaDefeso]:
        digits = only_digits(cpf)
        if len(digits) != 11:
            return None
        for f in self.listar():
            if only_digits(f.cpf) == digits:
                return f
        return None

    def _row_index(self, ficha_id: str) -> int:
        """Índice 1-based da planilha (2 = primeira linha de dados). -1 se não achar."""
        self.ensure()
        rows = self.client.get_values(f"{DEFESO_TAB}!A2:A")
        for i, r in enumerate(rows):
            if r and str(r[0]).strip() == ficha_id:
                return i + 2
        return -1

    def salvar(self, payload: Dict) -> FichaDefeso:
        self.ensure()
        existing = None
        fid = str(payload.get("id") or "").strip()
        if fid:
            existing = self.por_id(fid)
        if existing is None:
            cpf = only_digits(str(payload.get("cpf") or ""))
            if len(cpf) == 11:
                existing = self.por_cpf(cpf)
        ficha = payload_to_ficha(payload, existing=existing)
        err = validar_ficha(ficha)
        if err:
            raise ValueError(err)

        row_idx = self._row_index(ficha.id) if existing and existing.id == ficha.id else -1
        if row_idx < 0 and existing:
            # mesmo CPF, id diferente → atualiza a linha existente
            ficha.id = existing.id
            ficha.criado_em = existing.criado_em or ficha.criado_em
            ficha.tem_identidade = existing.tem_identidade
            ficha.tem_carteira_pesca = existing.tem_carteira_pesca
            ficha.tem_caf = existing.tem_caf
            if "observacao" not in payload:
                ficha.observacao = existing.observacao
            row_idx = self._row_index(ficha.id)

        if row_idx > 0:
            self.client.update_values(f"{DEFESO_TAB}!A{row_idx}", [ficha.to_row()])
        else:
            self.client.append_values(f"{DEFESO_TAB}!A2", [ficha.to_row()])
        return ficha

    def atualizar_municipio(self, ficha_id: str, municipio: str) -> FichaDefeso:
        """Atualiza apenas o município na ficha existente."""
        ficha = self.por_id(ficha_id)
        if not ficha:
            raise ValueError("Ficha Defeso não encontrada.")
        ficha.municipio = str(municipio or "").strip()
        ficha.atualizado_em = now_stamp()
        row_idx = self._row_index(ficha.id)
        if row_idx < 0:
            raise ValueError("Linha da ficha não encontrada.")
        self.client.update_values(f"{DEFESO_TAB}!L{row_idx}", [[ficha.municipio]])
        self.client.update_values(f"{DEFESO_TAB}!T{row_idx}", [[ficha.atualizado_em]])
        return ficha

    def atualizar_telefone_reap(self, ficha_id: str, telefone: str) -> FichaDefeso:
        """Atualiza telefone vindo do REAP (coluna telefoneReap)."""
        ficha = self.por_id(ficha_id)
        if not ficha:
            raise ValueError("Ficha Defeso não encontrada.")
        ficha.telefone_reap = str(telefone or "").strip()
        ficha.atualizado_em = now_stamp()
        row_idx = self._row_index(ficha.id)
        if row_idx < 0:
            raise ValueError("Linha da ficha não encontrada.")
        self.client.update_values(f"{DEFESO_TAB}!V{row_idx}", [[ficha.telefone_reap]])
        self.client.update_values(f"{DEFESO_TAB}!T{row_idx}", [[ficha.atualizado_em]])
        return ficha

    def marcar_anexo(self, ficha_id: str, kind: str, presente: bool = True) -> FichaDefeso:
        ficha = self.por_id(ficha_id)
        if not ficha:
            raise ValueError("Ficha Defeso não encontrada.")
        flag = "sim" if presente else ""
        if kind == "identidade":
            ficha.tem_identidade = flag
        elif kind in ("pesca", "carteira_pesca"):
            ficha.tem_carteira_pesca = flag
        elif kind == "caf":
            ficha.tem_caf = flag
        else:
            raise ValueError("Tipo de anexo inválido.")
        ficha.atualizado_em = now_stamp()
        row_idx = self._row_index(ficha.id)
        if row_idx < 0:
            raise ValueError("Linha da ficha não encontrada.")
        self.client.update_values(f"{DEFESO_TAB}!A{row_idx}", [ficha.to_row()])
        return ficha

    # ---- lotes (coluna Z) -------------------------------------------------

    def listar_lotes(self) -> List[Dict[str, object]]:
        """Lotes existentes com a quantidade de fichas em cada um."""
        from controle.lotes import LOTE_DEFESO_PADRAO, lotes_efetivos, ordenar_lotes

        contagem: Dict[str, int] = {}
        nomes: List[str] = []
        for f in self.listar():
            for nome in lotes_efetivos(f.lotes):
                chave = nome.lower()
                if chave not in contagem:
                    nomes.append(nome)
                    contagem[chave] = 0
                contagem[chave] += 1
        if not nomes:
            nomes = [LOTE_DEFESO_PADRAO]
        return [{"nome": n, "total": contagem.get(n.lower(), 0)} for n in ordenar_lotes(nomes)]

    def _gravar_lotes(self, mudancas: Dict[str, str]) -> int:
        if not mudancas:
            return 0
        self.ensure()
        rows = self.client.get_values(f"{DEFESO_TAB}!A2:A")
        linha_por_id = {str(r[0]).strip(): i + 2 for i, r in enumerate(rows) if r and str(r[0]).strip()}
        agora = now_stamp()
        data = []
        for fid, valor in mudancas.items():
            linha = linha_por_id.get(fid)
            if not linha:
                continue
            data.append({"range": f"{DEFESO_TAB}!Z{linha}", "values": [[valor]]})
            data.append({"range": f"{DEFESO_TAB}!T{linha}", "values": [[agora]]})
        self.client.batch_update_values(data)
        return len(data) // 2

    def adicionar_ao_lote(self, ficha_ids: Iterable[str], lote: str) -> int:
        from controle.lotes import com_lote, normalizar_nome_lote

        nome = normalizar_nome_lote(lote)
        if not nome:
            raise ValueError("Informe o nome do lote (ex.: Defeso 2027).")
        alvo = {str(x).strip() for x in ficha_ids if str(x).strip()}
        mudancas = {}
        for f in self.listar():
            if f.id in alvo:
                novo = com_lote(f.lotes, nome)
                if novo != f.lotes:
                    mudancas[f.id] = novo
        return self._gravar_lotes(mudancas)

    def remover_do_lote(self, ficha_id: str, lote: str) -> int:
        from controle.lotes import sem_lote

        ficha = self.por_id(ficha_id)
        if not ficha:
            raise ValueError("Ficha Defeso não encontrada.")
        return self._gravar_lotes({ficha.id: sem_lote(ficha.lotes, lote)})

    def criar_lote(self, nome: str, *, copiar_de: str = "") -> Dict[str, object]:
        """Cria o lote novo. Com ``copiar_de``, todos daquele lote entram no novo."""
        from controle.lotes import lotes_efetivos, normalizar_nome_lote

        novo = normalizar_nome_lote(nome)
        if not novo:
            raise ValueError("Informe o nome do lote (ex.: Defeso 2027).")
        origem = normalizar_nome_lote(copiar_de).lower()
        ids = []
        if origem:
            ids = [f.id for f in self.listar() if origem in {x.lower() for x in lotes_efetivos(f.lotes)}]
        total = self.adicionar_ao_lote(ids, novo) if ids else 0
        return {"lote": novo, "copiados": total}
