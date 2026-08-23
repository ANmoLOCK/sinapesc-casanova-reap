"""Modelos de dados do Sinapesc (equivalente ao lib/types.ts da versão web)."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List, Literal, Optional

MesKey = Literal[
    "jan", "fev", "mar", "abr", "mai", "jun",
    "jul", "ago", "set", "out", "nov", "dez",
]

MESES: List[MesKey] = [
    "jan", "fev", "mar", "abr", "mai", "jun",
    "jul", "ago", "set", "out", "nov", "dez",
]

MESES_LABEL: Dict[MesKey, str] = {
    "jan": "Janeiro",
    "fev": "Fevereiro",
    "mar": "Março",
    "abr": "Abril",
    "mai": "Maio",
    "jun": "Junho",
    "jul": "Julho",
    "ago": "Agosto",
    "set": "Setembro",
    "out": "Outubro",
    "nov": "Novembro",
    "dez": "Dezembro",
}


@dataclass
class Pessoa:
    id: str
    nome: str
    cpf: str
    criado_em: str
    municipio: str = ""


@dataclass
class ReapAno:
    id: str
    person_id: str
    ano: int
    meses: Dict[MesKey, bool]
    atualizado_em: str


@dataclass
class PessoaComReap(Pessoa):
    anos: List[ReapAno] = field(default_factory=list)


def meses_vazios() -> Dict[MesKey, bool]:
    return {mes: False for mes in MESES}


def meses_no_intervalo(inicio: str, fim: str) -> List[MesKey]:
    """Meses inclusivos de inicio até fim (ex.: mar → out)."""
    ini = str(inicio or "").strip().lower()[:3]
    end = str(fim or "").strip().lower()[:3]
    if ini not in MESES or end not in MESES:
        raise ValueError("Mês inválido. Use jan, fev, mar, … dez.")
    i, j = MESES.index(ini), MESES.index(end)  # type: ignore[arg-type]
    if i > j:
        i, j = j, i
    return MESES[i : j + 1]


def meses_para_flags(meses_on: Optional[List[str]] = None) -> List[str]:
    """Lista de 12 TRUE/FALSE na ordem de MESES — uma escrita só na planilha."""
    ligados = {str(m).strip().lower()[:3] for m in (meses_on or [])}
    return ["TRUE" if mes in ligados else "FALSE" for mes in MESES]

