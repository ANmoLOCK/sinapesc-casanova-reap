"""
Serviço de negócio: Pessoas + REAP sobre a planilha Google.

Tradução didática do antigo `lib/sheets.ts` (Next.js) para desktop Python.
Cada função pública corresponde a uma ação da interface.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Dict, List, Optional

from .client import (
    AUDITORIA_TAB,
    CONFIG_TAB,
    PESSOAS_TAB,
    REAP_TAB,
    GoogleSheetsClient,
    SheetsConfigError,
)
from .models import MESES, MesKey, Pessoa, PessoaComReap, ReapAno, meses_para_flags, meses_vazios

# Reexport para a UI
__all__ = ["SheetsService", "SheetsConfigError"]


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _format_cpf(digits: str) -> str:
    clean = "".join(ch for ch in (digits or "") if ch.isdigit())[:11]
    if len(clean) != 11:
        return clean
    return f"{clean[:3]}.{clean[3:6]}.{clean[6:9]}-{clean[9:]}"


def _format_nome(name: str) -> str:
    parts = [p for p in (name or "").split() if p]
    if not parts:
        return ""
    out = []
    for word in parts:
        if "-" in word:
            out.append("-".join(p[:1].upper() + p[1:].lower() if p else "" for p in word.split("-")))
        else:
            out.append(word[:1].upper() + word[1:].lower())
    return " ".join(out)


def _row_to_pessoa(row: List[str]) -> Pessoa:
    return Pessoa(
        id=row[0] if len(row) > 0 else "",
        nome=row[1] if len(row) > 1 else "",
        cpf=row[2] if len(row) > 2 else "",
        criado_em=row[3] if len(row) > 3 else "",
        municipio=row[4].strip() if len(row) > 4 else "",
        telefone=row[5].strip() if len(row) > 5 else "",
    )


def _cell_bool(value: str) -> bool:
    return str(value).strip().upper() == "TRUE"


def _row_to_reap(row: List[str]) -> ReapAno:
    meses: Dict[MesKey, bool] = {}
    for idx, mes in enumerate(MESES):
        cell = row[3 + idx] if len(row) > 3 + idx else "FALSE"
        meses[mes] = _cell_bool(cell)
    return ReapAno(
        id=row[0] if len(row) > 0 else "",
        person_id=row[1] if len(row) > 1 else "",
        ano=int(row[2]) if len(row) > 2 and str(row[2]).strip().isdigit() else 0,
        meses=meses,
        atualizado_em=row[3 + len(MESES)] if len(row) > 3 + len(MESES) else "",
    )


def _col_letter(index_zero_based: int) -> str:
    """Converte 0->A, 1->B, ... (suficiente para as ~16 colunas do REAP)."""
    return chr(ord("A") + index_zero_based)


class SheetsService:
    """Fachada usada pela interface gráfica."""

    def __init__(self, client: GoogleSheetsClient) -> None:
        self.client = client
        self.actor = ""
        self._audit_silent = False

    @classmethod
    def from_config(cls, cfg: dict) -> "SheetsService":
        """
        Monta o serviço a partir do dicionário salvo em config.json.

        Campos aceitos:
          - spreadsheet_id (obrigatório)
          - credentials_json (dict completo da chave Google)  OU
          - service_account_email + private_key
        """
        credentials_json = cfg.get("credentials_json")
        from sheets.client import normalize_sheet_id

        client = GoogleSheetsClient(
            service_account_email=cfg.get("service_account_email", ""),
            private_key=cfg.get("private_key", ""),
            spreadsheet_id=normalize_sheet_id(cfg.get("spreadsheet_id", "")),
            credentials_info=credentials_json if isinstance(credentials_json, dict) else None,
        )
        return cls(client)

    # ---- leituras -----------------------------------------------------

    def _pessoas_rows(self) -> tuple[List[List[str]], int]:
        self.client.ensure_tabs()
        rows = self.client.get_values(f"{PESSOAS_TAB}!A2:F")
        return rows, 2  # dados começam na linha 2 (1 = cabeçalho)

    def _reap_rows(self) -> tuple[List[List[str]], int]:
        self.client.ensure_tabs()
        last_col = _col_letter(3 + len(MESES))  # coluna de atualizadoEm
        rows = self.client.get_values(f"{REAP_TAB}!A2:{last_col}")
        return rows, 2

    def get_all_pessoas(self) -> List[Pessoa]:
        rows, _ = self._pessoas_rows()
        return [_row_to_pessoa(r) for r in rows if r and r[0]]

    def get_all_reap(self) -> List[ReapAno]:
        rows, _ = self._reap_rows()
        return [_row_to_reap(r) for r in rows if r and r[0]]

    def get_all_pessoas_com_reap(self) -> List[PessoaComReap]:
        pessoas = self.get_all_pessoas()
        reap = self.get_all_reap()
        resultado: List[PessoaComReap] = []
        for p in pessoas:
            anos = sorted(
                [r for r in reap if r.person_id == p.id],
                key=lambda x: x.ano,
                reverse=True,
            )
            resultado.append(
                PessoaComReap(
                    id=p.id,
                    nome=p.nome,
                    cpf=p.cpf,
                    criado_em=p.criado_em,
                    municipio=p.municipio,
                    telefone=getattr(p, "telefone", "") or "",
                    anos=anos,
                )
            )
        return resultado

    def get_pessoa_com_reap(self, person_id: str) -> Optional[PessoaComReap]:
        for p in self.get_all_pessoas_com_reap():
            if p.id == person_id:
                return p
        return None

    # ---- escritas -----------------------------------------------------

    def pessoa_por_cpf(self, cpf: str, except_id: str = "") -> Optional[Pessoa]:
        digits = "".join(ch for ch in (cpf or "") if ch.isdigit())[:11]
        if len(digits) != 11:
            return None
        for p in self.get_all_pessoas():
            other = "".join(ch for ch in (p.cpf or "") if ch.isdigit())[:11]
            if other == digits and p.id != except_id:
                return p
        return None

    def add_pessoa(
        self, nome: str, cpf: str, municipio: str = "", telefone: str = ""
    ) -> PessoaComReap:
        self.client.ensure_tabs()
        dup = self.pessoa_por_cpf(cpf)
        if dup:
            raise ValueError(f"CPF já cadastrado: {dup.nome}")
        nome = _format_nome(nome)
        cpf = _format_cpf(cpf)
        person_id = str(uuid.uuid4())
        now = _now_iso()
        ano_atual = datetime.now().year

        mun = str(municipio or "").strip()
        tel = str(telefone or "").strip()
        self.client.append_values(
            f"{PESSOAS_TAB}!A2",
            [[person_id, nome, cpf, now, mun, tel]],
        )

        reap_id = str(uuid.uuid4())
        meses_row = ["FALSE"] * len(MESES)
        self.client.append_values(
            f"{REAP_TAB}!A2",
            [[reap_id, person_id, ano_atual, *meses_row, now]],
        )

        criado = PessoaComReap(
            id=person_id,
            nome=nome,
            cpf=cpf,
            criado_em=now,
            municipio=mun,
            telefone=tel,
            anos=[
                ReapAno(
                    id=reap_id,
                    person_id=person_id,
                    ano=ano_atual,
                    meses=meses_vazios(),
                    atualizado_em=now,
                )
            ],
        )
        self._registrar_auditoria(
            "cadastro",
            f"cadastrou sócio {nome}",
            person_id=person_id,
            nome=nome,
            ano=ano_atual,
        )
        return criado

    def add_pessoas_lote(
        self,
        itens: List[tuple],
        *,
        ano: Optional[int] = None,
        meses_on: Optional[List[str]] = None,
    ) -> dict:
        """
        Cadastra vários sócios de uma vez (2 escritas na API: Pessoas + Reap).
        itens = [(nome, cpf)] ou [(nome, cpf, municipio, telefone), ...]
        meses_on = meses já marcados no ano (ex.: ['mar','abr',...,'out']).
        """
        self.client.ensure_tabs()
        existentes = {
            "".join(ch for ch in (p.cpf or "") if ch.isdigit())[:11]
            for p in self.get_all_pessoas()
        }
        now = _now_iso()
        try:
            ano_alvo = int(ano or datetime.now().year)
        except (TypeError, ValueError):
            ano_alvo = datetime.now().year
        flags = meses_para_flags(meses_on)

        pessoas_rows: List[list] = []
        reap_rows: List[list] = []
        ids: List[str] = []
        erros: List[str] = []
        vistos: set[str] = set()

        for i, item in enumerate(itens, start=1):
            if not isinstance(item, (list, tuple)) or len(item) < 2:
                erros.append(f"Linha {i}: dados inválidos.")
                continue
            nome = item[0]
            cpf = item[1]
            mun = str(item[2] if len(item) > 2 else "").strip()
            tel = str(item[3] if len(item) > 3 else "").strip()
            nome = _format_nome(nome)
            cpf = "".join(ch for ch in (cpf or "") if ch.isdigit())[:11]
            if not nome:
                erros.append(f"Linha {i}: nome vazio.")
                continue
            if len(cpf) != 11:
                erros.append(f"Linha {i} ({nome}): CPF deve ter 11 dígitos.")
                continue
            if cpf in existentes or cpf in vistos:
                erros.append(f"Linha {i} ({nome}): CPF já cadastrado ou duplicado no lote.")
                continue
            vistos.add(cpf)
            person_id = str(uuid.uuid4())
            reap_id = str(uuid.uuid4())
            pessoas_rows.append([person_id, nome, _format_cpf(cpf), now, mun, tel])
            reap_rows.append([reap_id, person_id, ano_alvo, *flags, now])
            ids.append(person_id)

        if pessoas_rows:
            self.client.append_values(f"{PESSOAS_TAB}!A2", pessoas_rows)
            try:
                self.client.append_values(f"{REAP_TAB}!A2", reap_rows)
            except Exception as exc:  # noqa: BLE001
                raise RuntimeError(
                    "Os nomes foram gravados, mas o REAP falhou. "
                    "Não importe o mesmo lote de novo — abra Atualizar e complete o ano. "
                    f"Detalhe: {exc}"
                ) from exc
            meses_txt = ",".join(meses_on or []) or "(nenhum mês pré-marcado)"
            self._registrar_auditoria(
                "lote",
                f"cadastrou {len(ids)} sócio(s) em lote (ano {ano_alvo}, {meses_txt})",
                ano=ano_alvo,
                meses=meses_on or [],
            )

        return {"ok": len(ids), "erros": erros, "ids": ids, "ano": ano_alvo, "meses": meses_on or []}

    def marcar_meses_em_massa(
        self,
        *,
        ano: int,
        meses_on: List[str],
        person_ids: Optional[List[str]] = None,
        substituir: bool = False,
    ) -> dict:
        """
        Marca meses em vários sócios com poucas chamadas à API
        (1 leitura + 1 batchUpdate + 1 append se faltar o ano).
        Por padrão só liga os meses pedidos; não apaga os já pagos.
        """
        ligados = [m for m in (meses_on or []) if str(m).strip().lower()[:3] in MESES]
        if not ligados:
            raise ValueError("Escolha pelo menos um mês.")
        ano = int(ano)
        pessoas = self.get_all_pessoas()
        if person_ids:
            wanted = set(person_ids)
            pessoas = [p for p in pessoas if p.id in wanted]
        if not pessoas:
            return {"ok": 0, "criados": 0, "atualizados": 0, "erros": ["Nenhum sócio selecionado."]}

        rows, start = self._reap_rows()
        now = _now_iso()
        data: List[dict] = []
        novos: List[list] = []
        atualizados = 0
        by_person_year = {}
        for i, r in enumerate(rows):
            if len(r) > 2 and r[1] and str(r[2]).strip().isdigit():
                by_person_year[(r[1], int(str(r[2]).strip()))] = (i, r)

        last_col = _col_letter(3 + len(MESES))
        for p in pessoas:
            key = (p.id, ano)
            if key in by_person_year:
                i, r = by_person_year[key]
                flags = []
                for idx, mes in enumerate(MESES):
                    cell = r[3 + idx] if len(r) > 3 + idx else "FALSE"
                    on = _cell_bool(cell)
                    if mes in ligados:
                        on = True
                    elif substituir:
                        on = False
                    flags.append("TRUE" if on else "FALSE")
                row_number = start + i
                data.append(
                    {
                        "range": f"{REAP_TAB}!D{row_number}:{last_col}{row_number}",
                        "values": [[*flags, now]],
                    }
                )
                atualizados += 1
            else:
                novos.append([str(uuid.uuid4()), p.id, ano, *meses_para_flags(ligados), now])

        if data:
            self.client.batch_update_values(data)
        if novos:
            self.client.append_values(f"{REAP_TAB}!A2", novos)

        total = atualizados + len(novos)
        if total:
            self._registrar_auditoria(
                "marcar_massa",
                f"marcou {', '.join(m.upper() for m in ligados)} em {ano} para {total} sócio(s)"
                + (" (substituiu o ano)" if substituir else ""),
                ano=ano,
                meses=ligados,
            )

        return {
            "ok": total,
            "atualizados": atualizados,
            "criados": len(novos),
            "erros": [],
        }

    def copiar_reap_ano(
        self,
        ano_origem: int,
        ano_destino: int,
        person_ids: Optional[List[str]] = None,
    ) -> dict:
        """Copia os 12 meses de um ano para outro (cria o ano destino se não existir)."""
        ano_origem = int(ano_origem)
        ano_destino = int(ano_destino)
        if ano_origem == ano_destino:
            raise ValueError("Ano de origem e destino devem ser diferentes.")
        pessoas = self.get_all_pessoas()
        if person_ids:
            wanted = set(person_ids)
            pessoas = [p for p in pessoas if p.id in wanted]
        rows, start = self._reap_rows()
        now = _now_iso()
        origem: dict[str, List[str]] = {}
        destino_idx: dict[str, int] = {}
        for i, r in enumerate(rows):
            if len(r) < 3 or not r[1] or not str(r[2]).strip().isdigit():
                continue
            pid, ano = r[1], int(str(r[2]).strip())
            if ano == ano_origem:
                flags = []
                for idx in range(len(MESES)):
                    cell = r[3 + idx] if len(r) > 3 + idx else "FALSE"
                    flags.append("TRUE" if _cell_bool(cell) else "FALSE")
                origem[pid] = flags
            if ano == ano_destino:
                destino_idx[pid] = i

        data: List[dict] = []
        novos: List[list] = []
        pulados = 0
        last_col = _col_letter(3 + len(MESES))
        for p in pessoas:
            flags = origem.get(p.id)
            if not flags:
                pulados += 1
                continue
            if p.id in destino_idx:
                row_number = start + destino_idx[p.id]
                data.append(
                    {
                        "range": f"{REAP_TAB}!D{row_number}:{last_col}{row_number}",
                        "values": [[*flags, now]],
                    }
                )
            else:
                novos.append([str(uuid.uuid4()), p.id, ano_destino, *flags, now])

        if data:
            self.client.batch_update_values(data)
        if novos:
            self.client.append_values(f"{REAP_TAB}!A2", novos)

        total = len(data) + len(novos)
        if total:
            self._registrar_auditoria(
                "copiar_ano",
                f"copiou REAP {ano_origem} → {ano_destino} em {total} sócio(s) (pulados: {pulados})",
                ano=ano_destino,
            )

        return {
            "ok": total,
            "atualizados": len(data),
            "criados": len(novos),
            "pulados": pulados,
            "erros": [],
        }

    def update_pessoa(
        self,
        person_id: str,
        nome: str,
        cpf: str,
        municipio: str = "",
        telefone: str = "",
    ) -> None:
        dup = self.pessoa_por_cpf(cpf, except_id=person_id)
        if dup:
            raise ValueError(f"CPF já cadastrado: {dup.nome}")
        nome = _format_nome(nome)
        cpf = _format_cpf(cpf)
        mun = str(municipio or "").strip()
        tel = str(telefone or "").strip()
        rows, start = self._pessoas_rows()
        idx = next((i for i, r in enumerate(rows) if r and r[0] == person_id), -1)
        if idx < 0:
            raise ValueError("Pessoa não encontrada.")
        row_number = start + idx
        criado = rows[idx][3] if len(rows[idx]) > 3 else ""
        self.client.update_values(
            f"{PESSOAS_TAB}!B{row_number}:F{row_number}",
            [[nome, cpf, criado, mun, tel]],
        )
        self._registrar_auditoria(
            "editar",
            f"editou sócio {nome}" + (f" ({mun})" if mun else ""),
            person_id=person_id,
            nome=nome,
        )

    def update_pessoa_municipio(self, person_id: str, municipio: str) -> None:
        """Atualiza só a coluna municipio (sincronização Defeso → REAP)."""
        mun = str(municipio or "").strip()
        rows, start = self._pessoas_rows()
        idx = next((i for i, r in enumerate(rows) if r and r[0] == person_id), -1)
        if idx < 0:
            raise ValueError("Pessoa não encontrada.")
        row_number = start + idx
        row = list(rows[idx])
        while len(row) < 5:
            row.append("")
        nome = row[1] if len(row) > 1 else ""
        self.client.update_values(f"{PESSOAS_TAB}!E{row_number}", [[mun]])
        if mun:
            self._registrar_auditoria(
                "sync_municipio",
                f"município → {mun} ({nome})",
                person_id=person_id,
                nome=nome,
            )

    def delete_pessoa(self, person_id: str) -> None:
        self.client.ensure_tabs()
        sheet_ids = self.client.get_sheet_ids_by_title()
        pessoas_sheet_id = sheet_ids.get(PESSOAS_TAB)
        reap_sheet_id = sheet_ids.get(REAP_TAB)

        pessoas_rows, pessoas_start = self._pessoas_rows()
        reap_rows, reap_start = self._reap_rows()

        requests: List[dict] = []

        p_idx = next((i for i, r in enumerate(pessoas_rows) if r and r[0] == person_id), -1)
        nome_apagado = ""
        if p_idx >= 0 and len(pessoas_rows[p_idx]) > 1:
            nome_apagado = str(pessoas_rows[p_idx][1])
        if p_idx >= 0 and pessoas_sheet_id is not None:
            # deleteDimension usa índice 0-based (linha 1 da planilha = índice 0)
            row_index = pessoas_start + p_idx - 1
            requests.append(
                {
                    "deleteDimension": {
                        "range": {
                            "sheetId": pessoas_sheet_id,
                            "dimension": "ROWS",
                            "startIndex": row_index,
                            "endIndex": row_index + 1,
                        }
                    }
                }
            )

        # Apagar de baixo para cima para não deslocar índices
        reap_indexes = sorted(
            [
                reap_start + i - 1
                for i, r in enumerate(reap_rows)
                if len(r) > 1 and r[1] == person_id
            ],
            reverse=True,
        )
        if reap_sheet_id is not None:
            for row_index in reap_indexes:
                requests.append(
                    {
                        "deleteDimension": {
                            "range": {
                                "sheetId": reap_sheet_id,
                                "dimension": "ROWS",
                                "startIndex": row_index,
                                "endIndex": row_index + 1,
                            }
                        }
                    }
                )

        self.client.batch_update(requests)
        if requests:
            self._registrar_auditoria(
                "excluir",
                f"removeu sócio {nome_apagado or person_id} e o histórico REAP",
                person_id=person_id,
                nome=nome_apagado,
            )

    def toggle_mes(
        self,
        person_id: str,
        ano: int,
        mes: MesKey,
        novo_status: bool,
        *,
        nome: str = "",
    ) -> None:
        rows, start = self._reap_rows()
        idx = next(
            (
                i
                for i, r in enumerate(rows)
                if len(r) > 2 and r[1] == person_id and str(r[2]).strip() == str(ano)
            ),
            -1,
        )
        if idx < 0:
            raise ValueError("Ano não encontrado para esta pessoa.")

        row_number = start + idx
        mes_idx = MESES.index(mes)
        col = _col_letter(3 + mes_idx)
        now = _now_iso()

        self.client.update_values(
            f"{REAP_TAB}!{col}{row_number}",
            [["TRUE" if novo_status else "FALSE"]],
        )
        atualizado_col = _col_letter(3 + len(MESES))
        self.client.update_values(
            f"{REAP_TAB}!{atualizado_col}{row_number}",
            [[now]],
        )
        verbo = "marcou" if novo_status else "desmarcou"
        self._registrar_auditoria(
            "toggle_mes",
            f"{verbo} {str(mes).upper()}/{ano} em {nome or person_id}",
            person_id=person_id,
            nome=nome,
            ano=ano,
            meses=[str(mes)],
        )

    def add_ano(self, person_id: str, ano: int, *, nome: str = "") -> ReapAno:
        rows, _ = self._reap_rows()
        ja_existe = any(
            len(r) > 2 and r[1] == person_id and str(r[2]).strip() == str(ano)
            for r in rows
        )
        if ja_existe:
            raise ValueError("Este ano já existe para esta pessoa.")

        reap_id = str(uuid.uuid4())
        now = _now_iso()
        meses_row = ["FALSE"] * len(MESES)
        self.client.append_values(
            f"{REAP_TAB}!A2",
            [[reap_id, person_id, ano, *meses_row, now]],
        )
        criado = ReapAno(
            id=reap_id,
            person_id=person_id,
            ano=ano,
            meses=meses_vazios(),
            atualizado_em=now,
        )
        self._registrar_auditoria(
            "add_ano",
            f"adicionou o ano {ano} para {nome or person_id}",
            person_id=person_id,
            nome=nome,
            ano=ano,
        )
        return criado

    # ---- auditoria / config / backup (planilha compartilhada) ---------

    def _registrar_auditoria(
        self,
        acao: str,
        detalhe: str,
        *,
        person_id: str = "",
        nome: str = "",
        ano: object = "",
        meses: Optional[List[str]] = None,
    ) -> None:
        """Grava na aba Auditoria. Nunca levanta erro (não desfaz a ação principal)."""
        if self._audit_silent:
            return
        from controle.auditoria import evento_para_row, EventoAuditoria

        meses_txt = ",".join(str(m) for m in (meses or []) if m)
        evt = EventoAuditoria(
            id=str(uuid.uuid4()),
            em=datetime.now().astimezone().strftime("%Y-%m-%d %H:%M:%S"),
            usuario=(self.actor or "").strip() or "(sem login)",
            acao=acao,
            detalhe=detalhe,
            person_id=person_id or "",
            nome=nome or "",
            ano="" if ano in (None, "") else str(ano),
            meses=meses_txt,
        )
        self._audit_silent = True
        try:
            self.client.ensure_tabs()
            self.client.append_values(f"{AUDITORIA_TAB}!A2", [evento_para_row(evt)])
        except Exception:
            pass
        finally:
            self._audit_silent = False

    def registrar_evento(self, acao: str, detalhe: str, **kwargs) -> None:
        """Uso da UI (backup, relatório) — mesma aba que as outras ações."""
        self._registrar_auditoria(acao, detalhe, **kwargs)

    def listar_auditoria(self, limite: int = 400):
        from controle.auditoria import EventoAuditoria, row_to_evento

        self.client.ensure_tabs()
        rows = self.client.get_values(f"{AUDITORIA_TAB}!A2:I")
        eventos: List[EventoAuditoria] = []
        for r in rows:
            evt = row_to_evento(r)
            if evt:
                eventos.append(evt)
        eventos.reverse()
        return eventos[: max(1, int(limite))]

    def _config_map(self) -> Dict[str, str]:
        self.client.ensure_tabs()
        rows = self.client.get_values(f"{CONFIG_TAB}!A2:B")
        out: Dict[str, str] = {}
        for r in rows:
            if r and str(r[0]).strip():
                out[str(r[0]).strip()] = str(r[1]).strip() if len(r) > 1 else ""
        return out

    def _config_set(self, chave: str, valor: str) -> None:
        self.client.ensure_tabs()
        rows = self.client.get_values(f"{CONFIG_TAB}!A2:B")
        idx = next((i for i, r in enumerate(rows) if r and str(r[0]).strip() == chave), -1)
        if idx >= 0:
            self.client.update_values(f"{CONFIG_TAB}!B{idx + 2}", [[valor]])
        else:
            self.client.append_values(f"{CONFIG_TAB}!A2", [[chave, valor]])

    def get_calendario(self, ano: Optional[int] = None) -> List[str]:
        from controle.calendario import CALENDARIO_PADRAO, chave_calendario, parse_meses

        try:
            mapa = self._config_map()
        except Exception:
            return list(CALENDARIO_PADRAO)
        raw = ""
        if ano is not None:
            raw = mapa.get(chave_calendario(int(ano)), "")
        if not raw:
            raw = mapa.get("calendario_padrao", "")
        meses = parse_meses(raw)
        if meses:
            return meses
        if "calendario_padrao" not in mapa:
            try:
                self._config_set("calendario_padrao", ",".join(CALENDARIO_PADRAO))
            except Exception:
                pass
        return list(CALENDARIO_PADRAO)

    def set_calendario(self, meses: List[str], *, ano: Optional[int] = None) -> List[str]:
        from controle.calendario import (
            CALENDARIO_PADRAO,
            chave_calendario,
            meses_para_texto,
            normalizar_meses,
        )

        ligados = normalizar_meses(meses) or list(CALENDARIO_PADRAO)
        chave = chave_calendario(ano)
        self._config_set(chave, ",".join(ligados))
        alvo = f"ano {ano}" if ano is not None else "padrão"
        self._registrar_auditoria(
            "calendario",
            f"definiu calendário {alvo}: {meses_para_texto(ligados)}",
            ano=ano or "",
            meses=ligados,
        )
        return ligados

    def exportar_abas(self) -> dict:
        """Linhas brutas (com cabeçalho) para backup CSV."""
        self.client.ensure_tabs()
        pessoas = self.client.get_values(f"{PESSOAS_TAB}!A1:E")
        last_col = _col_letter(3 + len(MESES))
        reap = self.client.get_values(f"{REAP_TAB}!A1:{last_col}")
        if not pessoas:
            from .client import PESSOAS_HEADER

            pessoas = [PESSOAS_HEADER]
        if not reap:
            from .client import REAP_HEADER

            reap = [REAP_HEADER]
        return {"pessoas": pessoas, "reap": reap}
