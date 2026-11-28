"""Lotes do REAP e do Defeso Fácil.

REAP
----
O lote do REAP é o ano. ``Lote REAP 2026`` são os sócios que têm a linha do
ano 2026 na aba Reap. Para abrir o lote 2027 (janeiro em diante), o programa
cria para cada sócio escolhido a linha do ano 2027 com os 12 meses em branco;
depois é só marcar os meses à medida que forem feitos. O lote 2026 fica
guardado como estava.

Defeso Fácil
------------
O lote do Defeso tem nome livre (padrão ``Defeso 2026``) e fica na coluna
``lotes`` da aba Defeso. Um pescador pode estar em vários lotes
(ex.: ``Defeso 2026, Defeso 2027``), e assim dá para saber de que ano é cada
entrada. Fichas antigas sem lote contam como ``Defeso 2026``.
"""

from __future__ import annotations

import re
from typing import Iterable, List, Sequence

LOTE_DEFESO_PADRAO = "Defeso 2026"
LOTE_REAP_PADRAO = 2026


def nome_lote_reap(ano: int | str) -> str:
    return f"Lote REAP {int(ano)}"


def ano_do_lote_reap(valor: object) -> int:
    m = re.search(r"(\d{4})", str(valor or ""))
    if not m:
        raise ValueError("Informe o ano do lote (ex.: 2027).")
    ano = int(m.group(1))
    if ano < 2000 or ano > 2100:
        raise ValueError("Ano do lote fora do intervalo.")
    return ano


def normalizar_nome_lote(valor: object) -> str:
    nome = " ".join(str(valor or "").replace(",", " ").split())
    if not nome:
        return ""
    if nome.isdigit() and len(nome) == 4:
        return f"Defeso {nome}"
    return nome[:1].upper() + nome[1:]


def lotes_de_celula(valor: object) -> List[str]:
    out: List[str] = []
    for parte in str(valor or "").split(","):
        nome = normalizar_nome_lote(parte)
        if nome and nome.lower() not in {x.lower() for x in out}:
            out.append(nome)
    return out


def lotes_para_celula(lotes: Iterable[str]) -> str:
    return ", ".join(lotes_de_celula(",".join(str(x) for x in lotes)))


def lotes_efetivos(valor: object) -> List[str]:
    """Lotes da ficha; vazio = lote padrão (fichas antigas)."""
    return lotes_de_celula(valor) or [LOTE_DEFESO_PADRAO]


def com_lote(valor: object, lote: str) -> str:
    atuais = lotes_efetivos(valor)
    nome = normalizar_nome_lote(lote)
    if nome and nome.lower() not in {x.lower() for x in atuais}:
        atuais.append(nome)
    return lotes_para_celula(atuais)


def sem_lote(valor: object, lote: str) -> str:
    alvo = normalizar_nome_lote(lote).lower()
    restantes = [x for x in lotes_efetivos(valor) if x.lower() != alvo]
    if not restantes:
        raise ValueError("A ficha precisa ficar em pelo menos um lote.")
    return lotes_para_celula(restantes)


def ordenar_lotes(lotes: Sequence[str]) -> List[str]:
    def chave(nome: str):
        m = re.search(r"(\d{4})", nome)
        return (-(int(m.group(1)) if m else 0), nome.lower())

    vistos: List[str] = []
    for n in lotes:
        if n and n.lower() not in {x.lower() for x in vistos}:
            vistos.append(n)
    return sorted(vistos, key=chave)
