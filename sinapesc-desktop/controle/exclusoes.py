"""Fila de exclusão de sócios — operador pede, admin aprova/recusa."""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Dict, List, Optional, Sequence

EXCLUSOES_TAB = "ExclusoesPendentes"
EXCLUSOES_HEADER = [
    "id",
    "personId",
    "nome",
    "cpf",
    "pedidoEm",
    "pedidoPor",
    "status",
    "decididoEm",
    "decididoPor",
    "motivo",
]

STATUS_PENDENTE = "pendente"
STATUS_APROVADO = "aprovado"
STATUS_RECUSADO = "recusado"
STATUS_VALIDOS = (STATUS_PENDENTE, STATUS_APROVADO, STATUS_RECUSADO)


def now_stamp() -> str:
    return datetime.now().astimezone().strftime("%Y-%m-%d %H:%M:%S")


@dataclass
class PedidoExclusao:
    id: str
    person_id: str
    nome: str
    cpf: str
    pedido_em: str
    pedido_por: str
    status: str = STATUS_PENDENTE
    decidido_em: str = ""
    decidido_por: str = ""
    motivo: str = ""

    def to_row(self) -> List[str]:
        return [
            self.id,
            self.person_id,
            self.nome,
            self.cpf,
            self.pedido_em,
            self.pedido_por,
            self.status,
            self.decidido_em,
            self.decidido_por,
            self.motivo,
        ]

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "person_id": self.person_id,
            "nome": self.nome,
            "cpf": self.cpf,
            "pedido_em": self.pedido_em,
            "pedido_por": self.pedido_por,
            "status": self.status,
            "decidido_em": self.decidido_em,
            "decidido_por": self.decidido_por,
            "motivo": self.motivo,
            "pendente": self.status == STATUS_PENDENTE,
        }


def row_to_pedido(row: Sequence[Any] | None) -> Optional[PedidoExclusao]:
    if not row:
        return None
    cells = [str(c) if c is not None else "" for c in row]
    while len(cells) < len(EXCLUSOES_HEADER):
        cells.append("")
    eid = cells[0].strip()
    pid = cells[1].strip()
    if not eid or eid.lower() == "id" or not pid:
        return None
    st = cells[6].strip().lower() or STATUS_PENDENTE
    if st not in STATUS_VALIDOS:
        st = STATUS_PENDENTE
    return PedidoExclusao(
        id=eid,
        person_id=pid,
        nome=cells[2].strip(),
        cpf=cells[3].strip(),
        pedido_em=cells[4].strip(),
        pedido_por=cells[5].strip(),
        status=st,
        decidido_em=cells[7].strip(),
        decidido_por=cells[8].strip(),
        motivo=cells[9].strip(),
    )


def novo_pedido(
    *,
    person_id: str,
    nome: str,
    cpf: str,
    pedido_por: str,
    motivo: str = "",
) -> PedidoExclusao:
    return PedidoExclusao(
        id=str(uuid.uuid4()),
        person_id=str(person_id or "").strip(),
        nome=str(nome or "").strip(),
        cpf=str(cpf or "").strip(),
        pedido_em=now_stamp(),
        pedido_por=str(pedido_por or "").strip(),
        status=STATUS_PENDENTE,
        motivo=str(motivo or "").strip(),
    )
