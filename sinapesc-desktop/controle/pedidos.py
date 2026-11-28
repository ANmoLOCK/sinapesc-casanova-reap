"""Pedidos da diretoria (presidente e vice) — aba Pedidos.

A diretoria escolhe o sócio e pede:
  - ``reap``: fazer o REAP do lote (ano) indicado;
  - ``defeso``: dar entrada no seguro-defeso do lote indicado.

O pedido cai em Notificações (no Abrir REAP ou no Defeso Fácil). A secretaria
marca como feito ou recusa; assim fica registrado quem pediu, quando e o que
foi feito.
"""

from __future__ import annotations

import uuid
from dataclasses import asdict, dataclass
from datetime import datetime
from typing import Any, Dict, List, Optional, Sequence

PEDIDOS_TAB = "Pedidos"
PEDIDOS_HEADER = [
    "id",
    "tipo",
    "personId",
    "nome",
    "cpf",
    "lote",
    "pedidoEm",
    "pedidoPor",
    "pedidoPorNome",
    "status",
    "decididoEm",
    "decididoPor",
    "obs",
]

TIPO_REAP = "reap"
TIPO_DEFESO = "defeso"
TIPOS = (TIPO_REAP, TIPO_DEFESO)
TIPO_LABEL = {
    TIPO_REAP: "Fazer REAP",
    TIPO_DEFESO: "Entrada no seguro-defeso",
}

STATUS_PENDENTE = "pendente"
STATUS_FEITO = "feito"
STATUS_RECUSADO = "recusado"
STATUS_VALIDOS = (STATUS_PENDENTE, STATUS_FEITO, STATUS_RECUSADO)


def now_stamp() -> str:
    return datetime.now().astimezone().strftime("%Y-%m-%d %H:%M:%S")


def normalizar_tipo(valor: Any) -> str:
    t = str(valor or "").strip().lower()
    if t in ("seguro", "entrada", "defeso_entrada"):
        return TIPO_DEFESO
    return t if t in TIPOS else ""


@dataclass
class Pedido:
    id: str
    tipo: str
    person_id: str
    nome: str
    cpf: str
    lote: str
    pedido_em: str
    pedido_por: str
    pedido_por_nome: str = ""
    status: str = STATUS_PENDENTE
    decidido_em: str = ""
    decidido_por: str = ""
    obs: str = ""

    def to_row(self) -> List[str]:
        return [
            self.id,
            self.tipo,
            self.person_id,
            self.nome,
            self.cpf,
            self.lote,
            self.pedido_em,
            self.pedido_por,
            self.pedido_por_nome,
            self.status,
            self.decidido_em,
            self.decidido_por,
            self.obs,
        ]

    def to_dict(self) -> Dict[str, Any]:
        d = asdict(self)
        d["tipo_label"] = TIPO_LABEL.get(self.tipo, self.tipo)
        return d


def row_to_pedido(row: Sequence[Any] | None) -> Optional[Pedido]:
    if not row:
        return None
    c = [str(x) if x is not None else "" for x in row]
    while len(c) < len(PEDIDOS_HEADER):
        c.append("")
    pid = c[0].strip()
    tipo = normalizar_tipo(c[1])
    if not pid or pid.lower() == "id" or not tipo:
        return None
    status = c[9].strip().lower()
    if status not in STATUS_VALIDOS:
        status = STATUS_PENDENTE
    return Pedido(
        id=pid,
        tipo=tipo,
        person_id=c[2].strip(),
        nome=c[3].strip(),
        cpf=c[4].strip(),
        lote=c[5].strip(),
        pedido_em=c[6].strip(),
        pedido_por=c[7].strip(),
        pedido_por_nome=c[8].strip(),
        status=status,
        decidido_em=c[10].strip(),
        decidido_por=c[11].strip(),
        obs=c[12].strip(),
    )


def novo_pedido(
    *,
    tipo: str,
    person_id: str,
    nome: str,
    cpf: str,
    lote: str,
    pedido_por: str,
    pedido_por_nome: str = "",
    obs: str = "",
) -> Pedido:
    t = normalizar_tipo(tipo)
    if not t:
        raise ValueError("Tipo de pedido inválido.")
    if not str(person_id or "").strip() and not str(cpf or "").strip():
        raise ValueError("Escolha o sócio do pedido.")
    if not str(lote or "").strip():
        raise ValueError("Informe o lote do pedido.")
    return Pedido(
        id=uuid.uuid4().hex[:12],
        tipo=t,
        person_id=str(person_id or "").strip(),
        nome=str(nome or "").strip(),
        cpf=str(cpf or "").strip(),
        lote=str(lote).strip(),
        pedido_em=now_stamp(),
        pedido_por=str(pedido_por or "").strip(),
        pedido_por_nome=str(pedido_por_nome or "").strip(),
        obs=str(obs or "").strip(),
    )


def resumo(pedidos: Sequence[Pedido]) -> Dict[str, int]:
    out = {s: 0 for s in STATUS_VALIDOS}
    for p in pedidos:
        out[p.status] = out.get(p.status, 0) + 1
    return out
