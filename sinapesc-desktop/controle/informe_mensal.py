"""Informe Mensal — cérebro REAP (reformulação v6 sazonal) mês a mês.

Regras herdadas do cérebro ``reap-informe-mensal-v1.8.0`` + v6:
  - Jan / Fev / Nov / Dez = ÉPOCA DE PIRACEMA (não houve pesca)
  - Mar → Out = pesca, 16–21 dias, 4 / 5 / 6 / 8 espécies intercaladas
  - kg inteiro (5–22) com viés sazonal; 22 kg é raro (teto mole ~18)
  - VALOR = preço varejo sazonal (R$/kg, real inteiro, nunca < R$ 11) com
    variação de ±12% por sócio/mês; cada peixe tem época cara e época barata
  - Peixes por mês sorteados com peso: evita o mesmo peixe dos meses vizinhos,
    o vaivém "um mês sim, um não" e os peixes que já saíram muito nos outros sócios
  - PESO ANUAL (soma kg Mar–Out) 540–650, alvo próprio de cada sócio
  - Anti-repetição forte: peixe/kg/valor não repetem entre meses vizinhos
  - 8 espécies só para ~20% dos sócios (no máx. 1 mês), quando o pool ≥ 8

Diferença para o cérebro original: o original monta o ano inteiro de uma vez.
Aqui o operador gera um mês por vez; cada mês novo é condicionado aos meses
já salvos do sócio (contagens, espécies, ordem, dias, kg acumulado) para
nunca repetir e ainda fechar o ano dentro das regras.
"""

from __future__ import annotations

import hashlib
import json
import math
import random
import secrets
import uuid
from dataclasses import dataclass, field
from datetime import datetime
from functools import lru_cache
from itertools import combinations
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple

MOTOR = "cerebro_reformulacao/v6-sazonal"

INFORME_TAB = "InformeMensal"
INFORME_AUDITORIA_TAB = "InformeAuditoria"

MESES_ORDEM = ["jan", "fev", "mar", "abr", "mai", "jun", "jul", "ago", "set", "out", "nov", "dez"]
MESES_PESCA = ["mar", "abr", "mai", "jun", "jul", "ago", "set", "out"]
MESES_PIRACEMA = ["jan", "fev", "nov", "dez"]
MES_TITULO = {
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
PIRACEMA_LABEL = "ÉPOCA DE PIRACEMA"

PRECOS_VAREJO: Dict[str, float] = {
    "Tucunaré": 18.0,
    "Tambaqui": 21.0,
    "Tilápia": 16.0,
    "Curimatã": 15.0,
    "Dourado-de-água-doce": 23.0,
    "Piranha": 15.0,
    "Piau": 14.0,
    "Pescada": 19.0,
    "Pacu": 17.0,
    "Pirambeba": 13.0,
    "Cascudo": 12.0,
}
PRECOS_BASE: Dict[str, float] = dict(PRECOS_VAREJO)
# ordem fixa do catálogo (configuração universal do Informe Mensal);
# peixes cadastrados pelo admin (aba InformePeixes) entram no fim
ESPECIES_TODAS: Tuple[str, ...] = tuple(PRECOS_VAREJO.keys())
MIN_ESPECIES_ATIVAS = 4

PEIXES_TAB = "InformePeixes"
PEIXES_HEADER = ["nome", "preco", "criadoEm", "criadoPor"]
# nenhum peixe sai abaixo de R$ 11/kg; preços sempre em real inteiro (sem centavos)
PRECO_PISO = 11.0
PEIXE_PRECO_MIN = PRECO_PISO
PEIXE_PRECO_MAX = 200.0
# variação do preço varejo entre sócios/meses (evita o mesmo valor para todo mundo)
PRECO_JITTER = 0.12
# PRECO_SAZONAL é ampliado por este fator: safra barateia, escassez encarece
PRECO_AMPLITUDE = 2.0


def _chave_peixe(nome: str) -> str:
    import unicodedata

    s = unicodedata.normalize("NFKD", str(nome or "")).encode("ascii", "ignore").decode()
    return "".join(ch for ch in s.casefold() if ch.isalnum())


def peixes_extras() -> List[str]:
    return [n for n in ESPECIES_TODAS if n not in PRECOS_BASE]


def definir_peixes_extras(extras: Iterable[Tuple[str, Any]]) -> None:
    """Liga ao catálogo os peixes cadastrados na planilha (valem para todos)."""
    global ESPECIES_TODAS
    PRECOS_VAREJO.clear()
    PRECOS_VAREJO.update(PRECOS_BASE)
    chaves = {_chave_peixe(n) for n in PRECOS_VAREJO}
    for nome, preco in extras or ():
        nome = str(nome or "").strip()
        try:
            p = float(str(preco).replace(",", "."))
        except (TypeError, ValueError):
            continue
        k = _chave_peixe(nome)
        if not nome or not k or k in chaves or p <= 0:
            continue
        PRECOS_VAREJO[nome] = float(max(PRECO_PISO, round(p)))
        chaves.add(k)
    ESPECIES_TODAS = tuple(PRECOS_VAREJO.keys())
    _perfil_cache.cache_clear()


def validar_novo_peixe(nome: Any, preco: Any) -> Tuple[str, float]:
    """Nome limpo + preço R$/kg de um peixe novo; ``ValueError`` com a mensagem."""
    nome_txt = " ".join(str(nome or "").split())
    if len(nome_txt) < 2 or len(nome_txt) > 40:
        raise ValueError("Nome do peixe deve ter de 2 a 40 letras.")
    if any(not (ch.isalpha() or ch in " -'") for ch in nome_txt):
        raise ValueError("Nome do peixe só pode ter letras, espaço e hífen.")
    nome_txt = nome_txt[0].upper() + nome_txt[1:]
    if _chave_peixe(nome_txt) in {_chave_peixe(n) for n in PRECOS_VAREJO}:
        raise ValueError(f"{nome_txt} já está no catálogo.")
    try:
        p = float(round(float(str(preco).replace("R$", "").replace(",", ".").strip())))
    except (TypeError, ValueError):
        raise ValueError("Preço inválido (use R$ por kg, ex.: 15).") from None
    if not (PEIXE_PRECO_MIN <= p <= PEIXE_PRECO_MAX):
        raise ValueError(
            f"Preço deve ficar entre R$ {PEIXE_PRECO_MIN:.2f} e R$ {PEIXE_PRECO_MAX:.2f} por kg."
        )
    return nome_txt, p


def especies_ativas_de_config(cfg: Dict[str, Any]) -> List[str]:
    """Peixes ligados no cérebro. Peixe recém-cadastrado já entra ligado em todo PC."""
    off = cfg.get("informe_especies_off")
    if isinstance(off, list):
        desl = {str(n) for n in off}
        ativos = [n for n in ESPECIES_TODAS if n not in desl]
        if len(ativos) >= MIN_ESPECIES_ATIVAS:
            return ativos
    lst = cfg.get("informe_especies")
    if not lst:
        return list(ESPECIES_TODAS)
    ativos = normalizar_especies_ativas(lst)
    return ativos + [n for n in peixes_extras() if n not in ativos]


def config_especies(ativas: Sequence[str]) -> Dict[str, List[str]]:
    lig = set(ativas)
    return {
        "informe_especies": [n for n in ESPECIES_TODAS if n in lig],
        "informe_especies_off": [n for n in ESPECIES_TODAS if n not in lig],
    }


def normalizar_especies_ativas(raw: Any = None) -> List[str]:
    """Lista canônica dos peixes ativos no cérebro (universal para todos os sócios).

    Vazio / inválido → catálogo completo. Ordem = ``ESPECIES_TODAS``.
    """
    if raw is None or raw == "" or raw == []:
        return list(ESPECIES_TODAS)
    if isinstance(raw, str):
        partes = [p.strip() for p in raw.replace(";", ",").split(",") if p.strip()]
    elif isinstance(raw, (list, tuple, set)):
        partes = [str(p).strip() for p in raw if str(p).strip()]
    else:
        return list(ESPECIES_TODAS)
    vistos = set()
    out: List[str] = []
    for nome in ESPECIES_TODAS:
        if nome in partes and nome not in vistos:
            out.append(nome)
            vistos.add(nome)
    return out or list(ESPECIES_TODAS)


def validar_especies_ativas(raw: Any) -> List[str]:
    """Erros da seleção (precisa de pelo menos ``MIN_ESPECIES_ATIVAS`` peixes do catálogo)."""
    if raw is None or raw == "" or raw == []:
        return []
    if isinstance(raw, str):
        partes = [p.strip() for p in raw.replace(";", ",").split(",") if p.strip()]
    elif isinstance(raw, (list, tuple, set)):
        partes = [str(p).strip() for p in raw if str(p).strip()]
    else:
        return ["Seleção de peixes inválida."]
    desconhecidos = [p for p in partes if p not in PRECOS_VAREJO]
    erros: List[str] = []
    if desconhecidos:
        erros.append(f"Peixe(s) fora do catálogo: {', '.join(desconhecidos)}.")
    ativos = [p for p in ESPECIES_TODAS if p in set(partes)]
    if len(ativos) < MIN_ESPECIES_ATIVAS:
        erros.append(
            f"Selecione pelo menos {MIN_ESPECIES_ATIVAS} peixes para o cérebro gerar o REAP."
        )
    return erros


def contagens_para_pool(n_pool: int) -> Tuple[int, ...]:
    return tuple(c for c in CONTAGENS if c <= int(n_pool))


def contagens_obrigatorias_para_pool(n_pool: int) -> Tuple[int, ...]:
    return tuple(c for c in CONTAGENS_OBRIGATORIAS if c <= int(n_pool))


KG_MIN = 5
KG_MAX = 22
# teto mole: a maioria dos peixes fica ≤ 18 kg; 19–22 só em pico + sorte
KG_SOFT_MAX = 18
KG_ANO_MIN = 540
KG_ANO_MAX = 650
ALVOS_KG_ANO = [540, 548, 555, 565, 575, 585, 595, 605, 615, 625, 635, 645, 650]
DIAS_MIN = 16
DIAS_MAX = 21
CONTAGENS = (4, 5, 6, 8)
CONTAGENS_OBRIGATORIAS = (4, 5, 6)
# máximo de meses por quantidade no ano; 8 espécies = no máximo um mês
CONTAGEM_MAX_ANO = {4: 3, 5: 3, 6: 3, 8: 1}
# Sorteio do plano anual de quantidades (Mar → Out) de cada sócio
PESO_QUANTIDADE = {4: 0.42, 5: 0.34, 6: 0.24}
# cada repetição da mesma quantidade no ano multiplica o peso por este fator
FATOR_REPETICAO = 0.40
# ~1 em 5 sócios tem um mês com 8 — parece safra boa, não padrão artificial
CHANCE_SOCIO_TER_8 = 0.20
# mês com 8 espécies cai mais no meio da safra do que nas pontas
PESO_POSICAO_8 = [0.45, 0.7, 1.0, 1.35, 1.35, 1.0, 0.7, 0.45]
AMOSTRAS_PROBABILIDADE = 4000
MUNICIPIOS = ("Casa Nova", "Remanso")

LOCAL_PADRAO = {
    "local": "Rio",
    "uf": "BAHIA",
    "ambiente": "Água Doce",
    "petrecho": "Emalhe",
}

# Atividade sazonal (São Francisco / BA): abundância × época de pesca.
# Picos deslocados entre meses vizinhos para reduzir repetição (ex.: Tucunaré
# forte em set/out, fraco em ago; Pescada forte em jul, moderada em mai).
ATIVIDADE: Dict[str, Dict[str, float]] = {
    "mar": {
        "Curimatã": 1.35, "Pacu": 1.28, "Cascudo": 1.18, "Piau": 1.15,
        "Tilápia": 1.08, "Pirambeba": 1.00, "Tucunaré": 0.95, "Piranha": 0.92,
        "Pescada": 0.85, "Tambaqui": 0.78, "Dourado-de-água-doce": 0.65,
    },
    "abr": {
        "Cascudo": 1.30, "Curimatã": 1.22, "Pacu": 1.18, "Piau": 1.12,
        "Tilápia": 1.05, "Tucunaré": 1.00, "Pirambeba": 0.95, "Piranha": 0.95,
        "Pescada": 0.90, "Tambaqui": 0.85, "Dourado-de-água-doce": 0.72,
    },
    "mai": {
        "Piau": 1.28, "Cascudo": 1.18, "Curimatã": 1.10, "Tilápia": 1.05,
        "Pacu": 1.00, "Tambaqui": 0.98, "Tucunaré": 0.95, "Pescada": 0.92,
        "Pirambeba": 0.90, "Piranha": 0.88, "Dourado-de-água-doce": 0.78,
    },
    "jun": {
        "Tambaqui": 1.32, "Pacu": 1.15, "Tilápia": 1.08, "Cascudo": 1.05,
        "Piau": 1.00, "Pescada": 0.98, "Dourado-de-água-doce": 0.95,
        "Curimatã": 0.90, "Tucunaré": 0.88, "Pirambeba": 0.85, "Piranha": 0.82,
    },
    "jul": {
        "Tambaqui": 1.30, "Pescada": 1.25, "Dourado-de-água-doce": 1.10,
        "Pacu": 1.05, "Tilápia": 1.00, "Piau": 0.95, "Cascudo": 0.92,
        "Curimatã": 0.88, "Tucunaré": 0.85, "Pirambeba": 0.82, "Piranha": 0.80,
    },
    "ago": {
        "Pescada": 1.22, "Tambaqui": 1.18, "Dourado-de-água-doce": 1.12,
        "Cascudo": 1.00, "Tilápia": 0.98, "Pacu": 0.95, "Piau": 0.92,
        "Pirambeba": 0.90, "Tucunaré": 0.82, "Curimatã": 0.80, "Piranha": 0.85,
    },
    "set": {
        "Tucunaré": 1.35, "Piranha": 1.22, "Pirambeba": 1.20, "Tilápia": 1.05,
        "Piau": 1.00, "Pacu": 0.95, "Pescada": 0.90, "Tambaqui": 0.88,
        "Cascudo": 0.85, "Curimatã": 0.82, "Dourado-de-água-doce": 0.78,
    },
    "out": {
        "Tucunaré": 1.38, "Pirambeba": 1.28, "Piranha": 1.25, "Piau": 1.08,
        "Tilápia": 1.02, "Pacu": 0.92, "Cascudo": 0.88, "Pescada": 0.85,
        "Tambaqui": 0.82, "Curimatã": 0.80, "Dourado-de-água-doce": 0.72,
    },
}

# Multiplicador de preço varejo por mês (escassez ↑ preço; safra ↑ oferta ↓ preço).
# Valores arredondados depois para 0,0 ou 0,5.
PRECO_SAZONAL: Dict[str, Dict[str, float]] = {
    "mar": {
        "Curimatã": 0.92, "Pacu": 0.94, "Cascudo": 0.95, "Tilápia": 0.96,
        "Piau": 0.97, "Tucunaré": 1.05, "Pescada": 1.08, "Tambaqui": 1.10,
        "Dourado-de-água-doce": 1.06, "Piranha": 1.02, "Pirambeba": 1.00,
    },
    "abr": {
        "Cascudo": 0.93, "Curimatã": 0.94, "Pacu": 0.95, "Piau": 0.96,
        "Tilápia": 0.97, "Tucunaré": 1.03, "Pescada": 1.06, "Tambaqui": 1.08,
        "Dourado-de-água-doce": 1.05, "Piranha": 1.00, "Pirambeba": 0.98,
    },
    "mai": {
        "Piau": 0.94, "Cascudo": 0.95, "Curimatã": 0.97, "Tilápia": 0.98,
        "Pacu": 1.00, "Tambaqui": 1.02, "Pescada": 1.04, "Tucunaré": 1.02,
        "Dourado-de-água-doce": 1.03, "Piranha": 1.01, "Pirambeba": 1.00,
    },
    "jun": {
        "Tambaqui": 0.93, "Pacu": 0.96, "Tilápia": 0.98, "Cascudo": 0.98,
        "Pescada": 1.00, "Piau": 1.00, "Dourado-de-água-doce": 1.00,
        "Curimatã": 1.02, "Tucunaré": 1.04, "Piranha": 1.03, "Pirambeba": 1.02,
    },
    "jul": {
        "Tambaqui": 0.92, "Pescada": 0.94, "Dourado-de-água-doce": 0.96,
        "Pacu": 0.98, "Tilápia": 1.00, "Cascudo": 1.00, "Piau": 1.01,
        "Curimatã": 1.04, "Tucunaré": 1.06, "Piranha": 1.05, "Pirambeba": 1.04,
    },
    "ago": {
        "Pescada": 0.95, "Tambaqui": 0.96, "Dourado-de-água-doce": 0.97,
        "Cascudo": 1.00, "Tilápia": 1.02, "Pacu": 1.02, "Piau": 1.03,
        "Pirambeba": 1.04, "Tucunaré": 1.08, "Curimatã": 1.06, "Piranha": 1.05,
    },
    "set": {
        "Tucunaré": 0.94, "Piranha": 0.95, "Pirambeba": 0.94, "Tilápia": 0.98,
        "Piau": 1.00, "Pacu": 1.04, "Pescada": 1.06, "Tambaqui": 1.08,
        "Cascudo": 1.05, "Curimatã": 1.06, "Dourado-de-água-doce": 1.08,
    },
    "out": {
        "Tucunaré": 0.93, "Pirambeba": 0.93, "Piranha": 0.94, "Piau": 0.98,
        "Tilápia": 1.00, "Pacu": 1.05, "Cascudo": 1.06, "Pescada": 1.08,
        "Tambaqui": 1.10, "Curimatã": 1.08, "Dourado-de-água-doce": 1.10,
    },
}

INFORME_HEADER = [
    "id",
    "personId",
    "cpf",
    "nome",
    "telefone",
    "ano",
    "mes",
    "houvePesca",
    "dias",
    "nEspecies",
    "especies",
    "especiesJson",
    "pesoMes",
    "faturamentoMes",
    "municipio",
    "local",
    "petrecho",
    "ambiente",
    "assinatura",
    "geradoEm",
    "geradoPor",
    "atualizadoEm",
    "atualizadoPor",
    "motor",
    "planoContagens",
]
INFORME_HEADER_RANGE = "A1:Y1"
INFORME_DATA_RANGE = "A2:Y"


def now_stamp() -> str:
    return datetime.now().astimezone().strftime("%Y-%m-%d %H:%M:%S")


def normalizar_mes(mes: Any) -> str:
    raw = str(mes or "").strip().lower()
    raw = raw.replace("ç", "c")
    for key, titulo in MES_TITULO.items():
        tit = titulo.lower().replace("ç", "c")
        if raw in (key, tit) or (len(raw) >= 3 and tit.startswith(raw)):
            return key
    raise ValueError(f"Mês inválido: {mes!r}")


def eh_piracema(mes: str) -> bool:
    return normalizar_mes(mes) in MESES_PIRACEMA


def normalizar_municipio(valor: Any, padrao: str = "Casa Nova") -> str:
    m = str(valor or "").strip().casefold().replace(" ", "")
    if m == "remanso":
        return "Remanso"
    if m == "casanova":
        return "Casa Nova"
    return padrao


@dataclass
class Especie:
    nome: str
    kg: int
    valor: float

    def to_dict(self) -> Dict[str, Any]:
        return {"nome": self.nome, "kg": int(self.kg), "valor": float(self.valor)}


@dataclass
class InformeMes:
    id: str
    person_id: str
    cpf: str
    nome: str
    telefone: str
    ano: int
    mes: str
    houve_pesca: bool
    dias: int
    especies: List[Especie] = field(default_factory=list)
    municipio: str = "Casa Nova"
    local: str = LOCAL_PADRAO["local"]
    petrecho: str = LOCAL_PADRAO["petrecho"]
    ambiente: str = LOCAL_PADRAO["ambiente"]
    assinatura: str = ""
    gerado_em: str = ""
    gerado_por: str = ""
    atualizado_em: str = ""
    atualizado_por: str = ""
    motor: str = MOTOR
    plano: str = ""

    @property
    def peso_mes(self) -> int:
        return sum(int(e.kg) for e in self.especies)

    @property
    def faturamento_mes(self) -> float:
        return round(sum(int(e.kg) * float(e.valor) for e in self.especies), 2)

    def especies_texto(self) -> str:
        return "; ".join(
            f"{e.nome} {int(e.kg)} kg R$ {float(e.valor):.2f}".replace(".", ",")
            for e in self.especies
        )

    def to_row(self) -> List[Any]:
        return [
            self.id,
            self.person_id,
            self.cpf,
            self.nome,
            self.telefone,
            str(self.ano),
            self.mes,
            "SIM" if self.houve_pesca else "NAO",
            str(int(self.dias)),
            str(len(self.especies)),
            self.especies_texto(),
            json.dumps([e.to_dict() for e in self.especies], ensure_ascii=False),
            str(self.peso_mes),
            f"{self.faturamento_mes:.2f}",
            self.municipio,
            self.local,
            self.petrecho,
            self.ambiente,
            self.assinatura,
            self.gerado_em,
            self.gerado_por,
            self.atualizado_em,
            self.atualizado_por,
            self.motor,
            self.plano,
        ]

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "person_id": self.person_id,
            "cpf": self.cpf,
            "nome": self.nome,
            "telefone": self.telefone,
            "ano": self.ano,
            "mes": self.mes,
            "mes_titulo": MES_TITULO.get(self.mes, self.mes),
            "houve_pesca": self.houve_pesca,
            "dias": int(self.dias),
            "n_especies": len(self.especies),
            "especies": [e.to_dict() for e in self.especies],
            "peso_mes": self.peso_mes,
            "faturamento_mes": self.faturamento_mes,
            "municipio": self.municipio,
            "local": self.local,
            "petrecho": self.petrecho,
            "ambiente": self.ambiente,
            "uf": LOCAL_PADRAO["uf"],
            "assinatura": self.assinatura,
            "gerado_em": self.gerado_em,
            "gerado_por": self.gerado_por,
            "atualizado_em": self.atualizado_em,
            "atualizado_por": self.atualizado_por,
            "motor": self.motor,
            "plano": self.plano,
        }


def _parse_especies(json_cell: str) -> List[Especie]:
    raw = (json_cell or "").strip()
    out: List[Especie] = []
    if raw:
        try:
            data = json.loads(raw)
        except json.JSONDecodeError:
            data = []
        for item in data if isinstance(data, list) else []:
            if not isinstance(item, dict):
                continue
            nome = str(item.get("nome") or "").strip()
            if not nome:
                continue
            try:
                kg = int(round(float(item.get("kg") or 0)))
            except (TypeError, ValueError):
                kg = 0
            try:
                valor = float(item.get("valor") or PRECOS_VAREJO.get(nome, 0.0))
            except (TypeError, ValueError):
                valor = PRECOS_VAREJO.get(nome, 0.0)
            out.append(Especie(nome, kg, valor))
    return out


def row_to_informe(row: Sequence[Any] | None) -> Optional[InformeMes]:
    if not row:
        return None
    cells = [str(c) if c is not None else "" for c in row]
    while len(cells) < len(INFORME_HEADER):
        cells.append("")
    rid = cells[0].strip()
    if not rid or rid.lower() == "id":
        return None
    try:
        mes = normalizar_mes(cells[6])
    except ValueError:
        return None
    try:
        ano = int(str(cells[5]).strip())
    except ValueError:
        return None
    try:
        dias = int(float(cells[8] or 0))
    except ValueError:
        dias = 0
    return InformeMes(
        id=rid,
        person_id=cells[1].strip(),
        cpf=cells[2].strip(),
        nome=cells[3].strip(),
        telefone=cells[4].strip(),
        ano=ano,
        mes=mes,
        houve_pesca=cells[7].strip().upper() in ("SIM", "TRUE", "S"),
        dias=dias,
        especies=_parse_especies(cells[11]),
        municipio=cells[14].strip() or "Casa Nova",
        local=cells[15].strip() or LOCAL_PADRAO["local"],
        petrecho=cells[16].strip() or LOCAL_PADRAO["petrecho"],
        ambiente=cells[17].strip() or LOCAL_PADRAO["ambiente"],
        assinatura=cells[18].strip(),
        gerado_em=cells[19].strip(),
        gerado_por=cells[20].strip(),
        atualizado_em=cells[21].strip(),
        atualizado_por=cells[22].strip(),
        motor=cells[23].strip() or MOTOR,
        plano=cells[24].strip(),
    )


# --------------------------------------------------------------------------
# Assinaturas (anti-repetição)
# --------------------------------------------------------------------------


def assinatura_nomes(nomes: Iterable[str]) -> str:
    lst = sorted(nomes)
    return f"{len(lst)}|" + "|".join(lst)


def assinatura_conjunto(especies: Sequence[Especie]) -> str:
    pares = sorted((e.nome, int(e.kg)) for e in especies)
    return f"{len(pares)}|" + "|".join(f"{n}:{k}" for n, k in pares)


def assinatura_ordem(especies: Sequence[Especie]) -> str:
    return ">".join(e.nome for e in especies)


def assinatura_mes(mes: str, especies: Sequence[Especie], dias: int) -> str:
    nomes = sorted(e.nome for e in especies)
    kgs = sorted(int(e.kg) for e in especies)
    peso = sum(kgs)
    raw = f"{mes}|{dias}|{len(especies)}|{','.join(nomes)}|{kgs}|{peso}"
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:20]


def _hash_int(texto: str) -> int:
    return int(hashlib.sha256(texto.encode("utf-8")).hexdigest(), 16)


def alvo_peso_anual(cpf: str, ano: int) -> int:
    """Alvo próprio (estável) do sócio no ano — cada sócio fecha num total diferente."""
    h = _hash_int(f"{cpf}|{ano}|alvo")
    base = ALVOS_KG_ANO[h % len(ALVOS_KG_ANO)]
    jitter = (-6, -3, 0, 2, 5)[(h >> 8) % 5]
    return max(KG_ANO_MIN, min(KG_ANO_MAX, base + jitter))


# --------------------------------------------------------------------------
# Perfil humanizado do sócio (kg e espécies variam por pessoa)
# --------------------------------------------------------------------------


@lru_cache(maxsize=4096)
def _perfil_cache(chave: str) -> Tuple[Tuple[Tuple[str, float], ...], Tuple[Tuple[str, float], ...], int]:
    rng = random.Random(_hash_int(f"{chave}|perfil"))
    pref = tuple((n, round(rng.uniform(0.8, 1.25), 3)) for n in PRECOS_VAREJO)
    pico = rng.randrange(len(MESES_PESCA))
    amp = rng.uniform(0.08, 0.22)
    ritmo = tuple(
        (
            m,
            round(1 + amp * math.cos(2 * math.pi * (i - pico) / len(MESES_PESCA)) + rng.uniform(-0.04, 0.04), 3),
        )
        for i, m in enumerate(MESES_PESCA)
    )
    return pref, ritmo, pico


def perfil_socio(cpf: str, ano: int) -> Dict[str, Any]:
    """Preferência de cada sócio por espécie (0,80–1,25) e ritmo de produção por mês.

    Estável por CPF + ano: o mesmo pescador tem sempre o mesmo "jeito" de pescar,
    e dois pescadores nunca pescam igual.
    """
    pref, ritmo, pico = _perfil_cache(f"{cpf}|{ano}")
    return {"pref": dict(pref), "ritmo": dict(ritmo), "pico": MESES_PESCA[pico]}


def _fator(mes: str, nome: str, perfil: Dict[str, Any]) -> float:
    return (ATIVIDADE.get(mes) or {}).get(nome, 1.0) * perfil["pref"].get(nome, 1.0)


def _mult_sazonal(nome: str, mes: str) -> float:
    tab = PRECO_SAZONAL.get(mes) or {}
    if nome in tab:
        return 1.0 + (float(tab[nome]) - 1.0) * PRECO_AMPLITUDE
    if nome not in PRECOS_VAREJO or mes not in MESES_PESCA:
        return 1.0
    # peixe cadastrado: época cara/barata própria, estável pelo nome
    fase = _hash_int("sazonal|" + _chave_peixe(nome)) % 8
    i = MESES_PESCA.index(mes)
    return 1.0 + 0.14 * math.sin(2 * math.pi * (i + fase) / 8.0)


def preco_mes(nome: str, mes: str) -> float:
    """Preço varejo de referência do peixe no mês (R$/kg, real inteiro, piso R$ 11)."""
    base = float(PRECOS_VAREJO.get(nome, 0.0))
    if base <= 0:
        return 0.0
    return float(max(PRECO_PISO, round(base * _mult_sazonal(nome, mes))))


def faixa_preco(nome: str, mes: str) -> Tuple[float, float]:
    ref = preco_mes(nome, mes)
    if ref <= 0:
        return 0.0, 0.0
    lo = max(PRECO_PISO, float(math.floor(ref * (1 - PRECO_JITTER))))
    hi = max(lo + 1.0, float(math.ceil(ref * (1 + PRECO_JITTER))))
    return lo, hi


def sortear_preco(
    rng: random.Random,
    nome: str,
    mes: str,
    evitar: Optional[Iterable[float]] = None,
    uso_outros: Optional[Iterable[float]] = None,
) -> float:
    """Preço do peixe para este sócio/mês: varia em volta da referência sazonal.

    ``evitar`` = valores proibidos (mesmo peixe no mês vizinho);
    ``uso_outros`` = valores já usados pelos outros sócios neste mês (pesam menos).
    """
    lo, hi = faixa_preco(nome, mes)
    if hi <= 0:
        return 0.0
    opcoes = [lo + float(i) for i in range(int(round(hi - lo)) + 1)]
    proib = {round(float(v), 2) for v in (evitar or ())}
    livres = [v for v in opcoes if round(v, 2) not in proib] or opcoes
    ref = preco_mes(nome, mes)
    cont: Dict[float, int] = {}
    for v in uso_outros or ():
        k = round(float(v), 2)
        cont[k] = cont.get(k, 0) + 1
    pesos = [
        (1.0 / (1.0 + abs(v - ref) / max(ref, 1.0) * 6)) * (0.6 ** cont.get(round(v, 2), 0))
        for v in livres
    ]
    return float(rng.choices(livres, weights=pesos, k=1)[0])


def _preco_socio(
    rng: random.Random,
    nome: str,
    mes: str,
    salvos: Dict[str, "InformeMes"],
    precos_outros: Optional[Dict[str, Iterable[float]]] = None,
) -> float:
    return sortear_preco(
        rng, nome, mes, _precos_usados(salvos, mes, nome), (precos_outros or {}).get(nome)
    )


def _precos_usados(salvos: Dict[str, "InformeMes"], mes: str, nome: str) -> set:
    """Preços do mesmo peixe nos meses vizinhos (não repete valor colado)."""
    out: set = set()
    for v in _vizinhos(mes, salvos):
        for e in v.especies:
            if e.nome == nome:
                out.add(round(float(e.valor), 2))
    return out


def _especies_vizinhos(mes: str, salvos: Dict[str, InformeMes]) -> frozenset:
    nomes: set = set()
    for v in _vizinhos(mes, salvos):
        nomes.update(e.nome for e in v.especies)
    return frozenset(nomes)


def _kgs_usados_especie(
    salvos: Dict[str, InformeMes], mes: str, nome: str
) -> set:
    usados: set = set()
    for m, r in salvos.items():
        if m == mes or not r.houve_pesca:
            continue
        for e in r.especies:
            if e.nome == nome:
                usados.add(int(e.kg))
    return usados


def _valores_usados_mes(salvos: Dict[str, InformeMes], mes: str) -> set:
    """Totais de faturamento (R$) já usados em outros meses do sócio."""
    out: set = set()
    for m, r in salvos.items():
        if m == mes or not r.houve_pesca:
            continue
        out.add(round(float(r.faturamento_mes), 2))
    return out


def _kg_teto(rng: random.Random, mes: str, nome: str, perfil: Dict[str, Any]) -> int:
    """Teto individual: 22 kg só em pico + sorte (evita chuva de 22)."""
    f = _fator(mes, nome, perfil)
    if f >= 1.28 and rng.random() < 0.08:
        return KG_MAX
    if f >= 1.18 and rng.random() < 0.18:
        return min(KG_MAX, 20)
    if f >= 1.10 and rng.random() < 0.28:
        return min(KG_MAX, 19)
    return KG_SOFT_MAX


# --------------------------------------------------------------------------
# Plano anual de quantidades de espécies (probabilístico, único por sócio)
# --------------------------------------------------------------------------


def plano_str(seq: Sequence[int]) -> str:
    return "-".join(str(int(c)) for c in seq)


def plano_parse(texto: str) -> Optional[List[int]]:
    partes = [p for p in str(texto or "").replace(",", "-").split("-") if p.strip()]
    try:
        seq = [int(p) for p in partes]
    except ValueError:
        return None
    if len(seq) != len(MESES_PESCA) or any(c not in CONTAGENS for c in seq):
        return None
    return seq


def _pool_curto(n_pool: int) -> bool:
    """Com 4 ou 5 peixes não dá para alternar 4/5/6 sem repetir a quantidade."""
    return len(contagens_obrigatorias_para_pool(n_pool)) < len(CONTAGENS_OBRIGATORIAS)


def plano_valido(seq: Sequence[int], n_pool: int = 8) -> bool:
    if len(seq) != len(MESES_PESCA):
        return False
    if any(int(c) > int(n_pool) for c in seq):
        return False
    obr = contagens_obrigatorias_para_pool(n_pool)
    if obr and not set(obr).issubset(set(seq)):
        return False
    if _pool_curto(n_pool):
        # nunca 3 meses seguidos com a mesma quantidade (quando há escolha)
        if len(obr) > 1 and any(a == b == c for a, b, c in zip(seq, seq[1:], seq[2:])):
            return False
        return True
    if any(a == b for a, b in zip(seq, seq[1:])):
        return False
    return all(list(seq).count(c) <= lim for c, lim in CONTAGEM_MAX_ANO.items())


def _decidir_8(rng: random.Random, fixos: Dict[int, int], n_pool: int) -> bool:
    """Sorteio único por sócio: terá (ou não) um mês com 8 espécies."""
    if n_pool < 8:
        return False
    if 8 in fixos.values():
        return True
    return rng.random() < CHANCE_SOCIO_TER_8


def _sortear_sequencia(
    rng: random.Random, fixos: Dict[int, int], quer8: bool, n_pool: int = 8
) -> List[int]:
    n = len(MESES_PESCA)
    livres = [i for i in range(n) if i not in fixos]
    pesos_base = {c: p for c, p in PESO_QUANTIDADE.items() if c <= n_pool}
    if not pesos_base:
        pesos_base = {max(1, n_pool): 1.0}
    pos8 = None
    if quer8 and n_pool >= 8 and 8 not in fixos.values() and livres:
        pos8 = rng.choices(livres, weights=[PESO_POSICAO_8[i] for i in livres], k=1)[0]
    seq: List[int] = []
    for i in range(n):
        if i in fixos:
            seq.append(fixos[i])
            continue
        if i == pos8:
            seq.append(8)
            continue
        prev = seq[-1] if seq else None
        nxt = fixos.get(i + 1, 8 if pos8 == i + 1 else None)
        usados = seq + [fixos[j] for j in fixos if j > i]
        if _pool_curto(n_pool):
            opcoes = list(pesos_base)
            pesos = [
                pesos_base[c] * (0.45 if c == prev else 1.0) * (0.45 if c == nxt else 1.0)
                for c in opcoes
            ]
            seq.append(rng.choices(opcoes, weights=pesos, k=1)[0])
            continue
        opcoes = [c for c in pesos_base if c != prev and c != nxt] or [
            c for c in pesos_base if c != prev
        ] or list(pesos_base)
        pesos = [pesos_base[c] * (FATOR_REPETICAO ** usados.count(c)) for c in opcoes]
        seq.append(rng.choices(opcoes, weights=pesos, k=1)[0])
    return seq


def sortear_plano(
    rng: random.Random,
    fixos: Optional[Dict[int, int]] = None,
    evitar: Optional[Any] = None,
    tentativas: int = 600,
    n_pool: int = 8,
) -> List[int]:
    """Sorteia Mar → Out respeitando os meses já salvos (``fixos``: índice → quantidade).

    Regras: nunca a mesma quantidade em meses vizinhos, 4/5/6 aparecem no ano
    (quando o pool de peixes permitir), no máximo 3 meses com 4/5/6 e no máximo
    1 mês com 8 (só ~20% dos sócios, e só se houver ≥ 8 peixes ativos).
    ``evitar`` = planos de outros sócios (set ou dict plano → nº de sócios); tenta
    não repetir nenhum e, se o espaço esgotar, repete o plano menos usado.
    """
    fixos = {i: c for i, c in dict(fixos or {}).items() if int(c) <= int(n_pool)}
    uso: Dict[str, int] = dict(evitar) if isinstance(evitar, dict) else {k: 1 for k in (evitar or ())}
    quer8 = _decidir_8(rng, fixos, n_pool)
    reserva: Optional[List[int]] = None
    ultimo: List[int] = []
    for i in range(tentativas):
        # Só troca a decisão do 8 se não houver plano válido possível sem ela.
        seq = _sortear_sequencia(
            rng, fixos, quer8 if i < tentativas // 2 or reserva else not quer8, n_pool
        )
        ultimo = seq
        if not plano_valido(seq, n_pool):
            continue
        txt = plano_str(seq)
        if txt in uso:
            if reserva is None or uso[txt] < uso[plano_str(reserva)]:
                reserva = seq
            continue
        return seq
    return reserva or ultimo


@lru_cache(maxsize=512)
def _probabilidades_cache(
    fixos_key: Tuple[Tuple[int, int], ...], amostras: int, n_pool: int
) -> Dict[str, Any]:
    rng = random.Random(20260308)
    fixos = dict(fixos_key)
    contagens = contagens_para_pool(n_pool) or CONTAGENS
    cont = [{c: 0 for c in contagens} for _ in MESES_PESCA]
    com8 = 0
    validos = 0
    soma = 0
    for _ in range(amostras):
        quer8 = _decidir_8(rng, fixos, n_pool)
        seq = None
        for _t in range(200):
            cand = _sortear_sequencia(rng, fixos, quer8, n_pool)
            if plano_valido(cand, n_pool):
                seq = cand
                break
        if seq is None:
            continue
        validos += 1
        soma += sum(seq)
        if 8 in seq:
            com8 += 1
        for i, c in enumerate(seq):
            if c in cont[i]:
                cont[i][c] += 1
    total = max(1, validos)
    return {
        "por_mes": {
            m: {str(c): round(cont[i].get(c, 0) / total, 4) for c in contagens}
            for i, m in enumerate(MESES_PESCA)
        },
        "chance_ter_8": round(com8 / total, 4) if n_pool >= 8 else 0.0,
        "media_especies_ano": round(soma / total, 2),
        "amostras": validos,
        "n_pool": n_pool,
    }


def probabilidades_plano(
    fixos: Optional[Dict[int, int]] = None,
    amostras: int = AMOSTRAS_PROBABILIDADE,
    n_pool: int = 8,
) -> Dict[str, Any]:
    """Cálculo (Monte Carlo do próprio sorteio) da chance de cada quantidade por mês."""
    key = tuple(sorted((int(i), int(c)) for i, c in (fixos or {}).items()))
    return _probabilidades_cache(key, int(amostras), int(n_pool))


def regras_probabilidade() -> Dict[str, Any]:
    return {
        "peso_quantidade": {str(c): p for c, p in PESO_QUANTIDADE.items()},
        "fator_repeticao": FATOR_REPETICAO,
        "chance_socio_ter_8": CHANCE_SOCIO_TER_8,
        "peso_posicao_8": dict(zip(MESES_PESCA, PESO_POSICAO_8)),
        "max_por_ano": {str(c): v for c, v in CONTAGEM_MAX_ANO.items()},
    }


def plano_do_socio(salvos: Dict[str, "InformeMes"]) -> Optional[List[int]]:
    """Plano gravado nas linhas do sócio (o mais recente), com os meses salvos por cima."""
    linhas = sorted(
        (r for r in salvos.values() if plano_parse(r.plano)),
        key=lambda r: r.atualizado_em or r.gerado_em or "",
        reverse=True,
    )
    if not linhas:
        return None
    seq = list(plano_parse(linhas[0].plano) or [])
    for i, m in enumerate(MESES_PESCA):
        r = salvos.get(m)
        if r and r.houve_pesca:
            seq[i] = len(r.especies)
    return seq


def _vizinhos(mes: str, salvos: Dict[str, InformeMes]) -> List[InformeMes]:
    i = MESES_PESCA.index(mes)
    out = []
    for j in (i - 1, i + 1):
        if 0 <= j < len(MESES_PESCA):
            m = MESES_PESCA[j]
            if m in salvos and salvos[m].houve_pesca:
                out.append(salvos[m])
    return out


def _plano_para_mes(
    cpf: str,
    ano: int,
    mes: str,
    salvos: Dict[str, InformeMes],
    outros_planos: Any,
    n_pool: int = 8,
) -> List[int]:
    fixos = {
        MESES_PESCA.index(m): len(r.especies)
        for m, r in salvos.items()
        if m != mes and m in MESES_PESCA and r.houve_pesca and len(r.especies) <= n_pool
    }
    existente = plano_do_socio(salvos)
    if existente:
        candidato = list(existente)
        for i, c in fixos.items():
            candidato[i] = c
        if plano_valido(candidato, n_pool):
            return candidato
    fixos_txt = ",".join(f"{i}:{c}" for i, c in sorted(fixos.items()))
    rng = random.Random(_hash_int(f"{cpf}|{ano}|plano|{n_pool}|{fixos_txt}"))
    return sortear_plano(rng, fixos=fixos, evitar=outros_planos, n_pool=n_pool)


def _escolher_combo(
    rng: random.Random,
    mes: str,
    n_esp: int,
    salvos: Dict[str, InformeMes],
    nomes_outros_socios: set,
    perfil: Dict[str, Any],
    pool: Optional[Sequence[str]] = None,
    peixes_outros: Optional[Dict[str, int]] = None,
) -> Tuple[str, ...]:
    nomes = list(normalizar_especies_ativas(pool))
    n_esp = max(1, min(int(n_esp), len(nomes)))
    if n_esp >= len(nomes):
        return tuple(nomes)
    # quanto cada peixe já apareceu neste mês nos outros sócios (acima da média = penaliza)
    outros = {n: int((peixes_outros or {}).get(n, 0)) for n in nomes}
    tot_outros = sum(outros.values())
    excesso = {
        n: (outros[n] / tot_outros * len(nomes) - 1.0) if tot_outros else 0.0 for n in nomes
    }
    # peixe do mês "dois atrás/dois à frente": quebra o vaivém mar=mai=jul, abr=jun=ago
    idx = MESES_PESCA.index(mes) if mes in MESES_PESCA else -1
    dois: set = set()
    for j in (idx - 2, idx + 2):
        if 0 <= j < len(MESES_PESCA):
            r2 = salvos.get(MESES_PESCA[j])
            if r2 and r2.houve_pesca:
                dois.update(e.nome for e in r2.especies)
    sorte = {n: rng.uniform(0.0, 1.6) for n in nomes}
    usados_ano = {
        assinatura_nomes(e.nome for e in r.especies)
        for m, r in salvos.items()
        if m != mes and r.houve_pesca
    }
    # frequência de cada peixe no ano (evita o mesmo peixe em vários meses)
    freq_ano: Dict[str, int] = {n: 0 for n in nomes}
    for m, r in salvos.items():
        if m == mes or not r.houve_pesca:
            continue
        for e in r.especies:
            if e.nome in freq_ano:
                freq_ano[e.nome] += 1
    banidos = _especies_vizinhos(mes, salvos)
    limite = limite_comuns_vizinho(n_esp, nomes, mes, salvos)

    def score(cand: Tuple[str, ...]) -> float:
        fs = frozenset(cand)
        key = assinatura_nomes(cand)
        s = sum(_fator(mes, n, perfil) + sorte[n] for n in cand)
        s += rng.uniform(0, 1.5)
        s -= sum(max(0.0, excesso[n]) * 2.2 for n in cand)
        s -= 1.6 * len(fs & dois)
        if key in usados_ano:
            s -= 12.0
        if key in nomes_outros_socios:
            s -= 1.5
        # peixe do vizinho: no máx. ``limite`` por vizinho (kg/valor diferentes)
        overlap = len(fs & banidos)
        s -= 1.8 * overlap
        if comuns_com_vizinho(cand, mes, salvos) > limite:
            s -= 30.0
        # peixe já usado muitas vezes no ano
        s -= sum(freq_ano.get(n, 0) * 3.5 for n in cand)
        return s

    todas = list(combinations(nomes, n_esp))
    rng.shuffle(todas)
    pontos = {c: score(c) for c in todas}
    todas.sort(key=pontos.__getitem__, reverse=True)
    boas = [
        c for c in todas
        if assinatura_nomes(c) not in usados_ano and comuns_com_vizinho(c, mes, salvos) <= limite
    ] or [c for c in todas if assinatura_nomes(c) not in usados_ano] or todas
    # sorteio entre os melhores (não sempre o 1º): sócios com o mesmo histórico divergem
    top = boas[: max(3, min(12, len(boas) // 4))]
    melhor = pontos[top[0]]
    pesos = [math.exp((pontos[c] - melhor) / 1.2) for c in top]
    return rng.choices(top, weights=pesos, k=1)[0]


def comuns_com_vizinho(cand: Iterable[str], mes: str, salvos: Dict[str, InformeMes]) -> int:
    """Maior nº de peixes que ``cand`` divide com um mês vizinho."""
    fs = set(cand)
    return max((len(fs & {e.nome for e in v.especies}) for v in _vizinhos(mes, salvos)), default=0)


def limite_comuns_vizinho(
    n_esp: int, nomes: Sequence[str], mes: str, salvos: Dict[str, InformeMes]
) -> int:
    """Quantos peixes podem repetir de um mês vizinho.

    Pescador real repete alguns peixes de um mês para o outro; proibir tudo força o
    vaivém mar=mai=jul. Permite ~1/4 do mês, ou o mínimo inevitável num pool curto.
    """
    livre = 1 + int(n_esp) // 4
    forcado = max(
        (int(n_esp) + len(v.especies) - len(nomes) for v in _vizinhos(mes, salvos)), default=0
    )
    return max(livre, forcado)


def _escolher_dias(rng: random.Random, mes: str, salvos: Dict[str, InformeMes]) -> int:
    usados = {r.dias for m, r in salvos.items() if m != mes and r.houve_pesca}
    vizinhos = {v.dias for v in _vizinhos(mes, salvos)}
    opcoes = [d for d in range(DIAS_MIN, DIAS_MAX + 1) if d not in usados and d not in vizinhos]
    if not opcoes:
        opcoes = [d for d in range(DIAS_MIN, DIAS_MAX + 1) if d not in vizinhos]
    if not opcoes:
        opcoes = list(range(DIAS_MIN, DIAS_MAX + 1))
    return rng.choice(opcoes)


def _kg_base(
    rng: random.Random,
    mes: str,
    nome: str,
    perfil: Dict[str, Any],
    teto: int,
    proibidos: Optional[set] = None,
) -> int:
    # centro mais contido (antes empurrava fácil para 20–22)
    centro = 10 + int(round((_fator(mes, nome, perfil) - 1.0) * 4.5))
    centro += rng.choice([-3, -2, -1, 0, 0, 1, 2])
    kg = max(KG_MIN, min(int(teto), centro))
    proibidos = set(proibidos or ())
    if kg not in proibidos:
        return kg
    for delta in (1, -1, 2, -2, 3, -3, 4, -4):
        alt = kg + delta
        if KG_MIN <= alt <= teto and alt not in proibidos:
            return alt
    # último recurso: qualquer kg livre no intervalo
    livres = [k for k in range(KG_MIN, teto + 1) if k not in proibidos]
    return rng.choice(livres) if livres else kg


def _alvo_mes(
    rng: random.Random,
    mes: str,
    plano: Sequence[int],
    salvos: Dict[str, InformeMes],
    alvo_ano: int,
    perfil: Dict[str, Any],
) -> int:
    idx = MESES_PESCA.index(mes)
    n_esp = plano[idx]
    outros = [r for m, r in salvos.items() if m != mes and r.houve_pesca and m in MESES_PESCA]
    restante = alvo_ano - sum(r.peso_mes for r in outros)
    pendentes = [
        (i, m) for i, m in enumerate(MESES_PESCA) if m != mes and not (m in salvos and salvos[m].houve_pesca)
    ]
    ritmo = perfil["ritmo"]
    # teto médio: soft no começo; sobe quando faltam poucos meses p/ fechar 540–650
    teto_medio = KG_SOFT_MAX + 1
    if len(pendentes) <= 1:
        teto_medio = KG_MAX
    elif len(pendentes) <= 3:
        teto_medio = max(teto_medio, 20)
    if not pendentes:
        # último mês de pesca: obriga fechar o alvo anual (teto duro)
        return max(n_esp * KG_MIN + 1, min(n_esp * KG_MAX, int(restante)))
    peso_aqui = n_esp * ritmo[mes]
    peso_depois = sum(plano[i] * ritmo[m] for i, m in pendentes)
    share = peso_aqui / (peso_aqui + peso_depois)
    alvo = int(round(restante * share * rng.uniform(0.92, 1.06)))
    min_depois = sum(plano[i] * KG_MIN for i, _ in pendentes)
    max_depois = sum(plano[i] * teto_medio for i, _ in pendentes)
    alvo = max(restante - max_depois, min(alvo, restante - min_depois))
    return max(n_esp * KG_MIN + 1, min(n_esp * teto_medio, alvo))


def _distribuir_kg(
    rng: random.Random,
    mes: str,
    combo: Sequence[str],
    alvo: int,
    perfil: Dict[str, Any],
    salvos: Optional[Dict[str, InformeMes]] = None,
) -> Dict[str, int]:
    salvos = salvos or {}
    tetos = {n: _kg_teto(rng, mes, n, perfil) for n in combo}
    proib = {n: _kgs_usados_especie(salvos, mes, n) for n in combo}
    # kg do mês vizinho da mesma espécie também fica proibido
    for v in _vizinhos(mes, salvos):
        for e in v.especies:
            if e.nome in proib:
                proib[e.nome].add(int(e.kg))
    kgs = {
        n: _kg_base(rng, mes, n, perfil, tetos[n], proib[n]) for n in combo
    }

    def _pick(cands: List[str]) -> str:
        # não sempre o 1º da fila: evita todo mundo empilhar no mesmo peixe/teto
        top = cands[:3]
        return rng.choices(top, weights=[0.55, 0.3, 0.15][: len(top)], k=1)[0]

    for _ in range(800):
        total = sum(kgs.values())
        if total == alvo:
            break
        if total < alvo:
            cands = [n for n in combo if kgs[n] < tetos[n]]
            if not cands:
                # relaxa teto mole uma vez se ainda faltar peso anual
                cands = [n for n in combo if kgs[n] < KG_MAX]
                if not cands:
                    break
            def _key_up(n: str) -> Tuple[float, int]:
                nxt = kgs[n] + 1
                pen = 6.0 if nxt in proib[n] else 0.0
                return (-_fator(mes, n, perfil) + pen + rng.uniform(0, 0.3), kgs[n])
            cands.sort(key=_key_up)
            kgs[_pick(cands)] += 1
        else:
            cands = [n for n in combo if kgs[n] > KG_MIN]
            if not cands:
                break
            def _key_dn(n: str) -> Tuple[float, int]:
                nxt = kgs[n] - 1
                pen = 6.0 if nxt in proib[n] else 0.0
                return (_fator(mes, n, perfil) + pen + rng.uniform(0, 0.3), -kgs[n])
            cands.sort(key=_key_dn)
            kgs[_pick(cands)] -= 1
    # resolve kg proibidos (já usados no ano / vizinho) e diversifica no mês
    for _ in range(80):
        conflito = [n for n in combo if kgs[n] in proib[n]]
        diversificado = len(set(kgs.values())) >= min(3, len(combo))
        if not conflito and diversificado:
            break
        alvo_fix = conflito[0] if conflito else None
        if alvo_fix is None:
            ranked = sorted(combo, key=lambda n: _fator(mes, n, perfil), reverse=True)
            hi, lo = ranked[0], ranked[-1]
            if kgs[hi] < tetos[hi] and kgs[lo] > KG_MIN:
                kgs[hi] += 1
                kgs[lo] -= 1
            else:
                break
            continue
        livres = [
            k for k in range(KG_MIN, max(tetos[alvo_fix], KG_SOFT_MAX) + 1)
            if k not in proib[alvo_fix] and k not in {kgs[n] for n in combo if n != alvo_fix}
        ]
        if not livres:
            livres = [
                k for k in range(KG_MIN, KG_MAX + 1)
                if k not in proib[alvo_fix]
            ]
        if not livres:
            break
        # troca kg do conflito; compensa em outra espécie se possível
        novo = rng.choice(livres)
        delta = novo - kgs[alvo_fix]
        kgs[alvo_fix] = novo
        if delta != 0:
            outros = [n for n in combo if n != alvo_fix]
            outros.sort(key=lambda n: abs(kgs[n] - (kgs[n] - delta)))
            for n in outros:
                cand = kgs[n] - delta
                if KG_MIN <= cand <= max(tetos[n], KG_SOFT_MAX) and cand not in proib[n]:
                    kgs[n] = cand
                    break
    # fecha o alvo do mês (teto duro) sem reintroduzir kg proibido da espécie
    for _ in range(400):
        total = sum(kgs.values())
        if total == alvo:
            break
        if total < alvo:
            cands = [
                n for n in combo
                if kgs[n] < KG_MAX and (kgs[n] + 1) not in proib[n]
            ]
            if not cands:
                cands = [n for n in combo if kgs[n] < KG_MAX]
            if not cands:
                break
            cands.sort(key=lambda n: (-_fator(mes, n, perfil), kgs[n]))
            kgs[_pick(cands)] += 1
        else:
            cands = [
                n for n in combo
                if kgs[n] > KG_MIN and (kgs[n] - 1) not in proib[n]
            ]
            if not cands:
                cands = [n for n in combo if kgs[n] > KG_MIN]
            if not cands:
                break
            cands.sort(key=lambda n: (_fator(mes, n, perfil), -kgs[n]))
            kgs[_pick(cands)] -= 1
    return kgs


def _ordenar(
    rng: random.Random,
    combo: Sequence[str],
    mes: str,
    salvos: Dict[str, InformeMes],
) -> List[str]:
    """Posição dos peixes nunca repete a de outro mês nem abre com o mesmo peixe do vizinho."""
    ordens_usadas = {
        assinatura_ordem(r.especies) for m, r in salvos.items() if m != mes and r.houve_pesca
    }
    primeiros_viz = {v.especies[0].nome for v in _vizinhos(mes, salvos) if v.especies}
    ordem = list(combo)
    for _ in range(40):
        rng.shuffle(ordem)
        sig = ">".join(ordem)
        if sig in ordens_usadas:
            continue
        if len(ordem) > 1 and ordem[0] in primeiros_viz:
            continue
        return ordem
    return ordem


@dataclass
class ResultadoGeracao:
    informe: InformeMes
    alvo_ano: int
    avisos: List[str]
    tentativas: int
    plano: List[int] = field(default_factory=list)


def gerar_mes(
    *,
    person_id: str,
    cpf: str,
    nome: str,
    telefone: str,
    ano: int,
    mes: str,
    salvos: Dict[str, InformeMes],
    assinaturas_globais: Optional[set] = None,
    nomes_outros_socios: Optional[set] = None,
    outros_planos: Optional[Any] = None,
    municipio: str = "Casa Nova",
    seed: Optional[int] = None,
    ator: str = "",
    especies_ativas: Optional[Sequence[str]] = None,
    peixes_outros_socios: Optional[Dict[str, int]] = None,
    precos_outros_socios: Optional[Dict[str, Iterable[float]]] = None,
) -> ResultadoGeracao:
    """Gera o REAP de um mês de pesca, condicionado aos meses já salvos do sócio.

    ``salvos`` = meses já gravados do mesmo sócio/ano (chave = mes curto).
    ``assinaturas_globais`` = assinaturas de todos os meses de todos os sócios
    (evita gerar um mês idêntico ao de outro pescador).
    ``outros_planos`` = planos de quantidades dos outros sócios no ano
    (o plano deste sócio é sorteado para não repetir nenhum).
    ``especies_ativas`` = peixes liberados na config do Informe Mensal (universal).
    ``peixes_outros_socios`` = quantas vezes cada peixe já saiu neste mês nos
    outros sócios (os mais usados perdem prioridade).
    ``precos_outros_socios`` = preços já usados neste mês por peixe nos outros sócios.
    """
    mes = normalizar_mes(mes)
    if mes in MESES_PIRACEMA:
        raise ValueError(f"{MES_TITULO[mes]} é {PIRACEMA_LABEL} — não há REAP de pesca.")
    ano = int(ano)
    if seed is None:
        seed = secrets.randbits(48)
    pool = normalizar_especies_ativas(especies_ativas)
    n_pool = len(pool)
    chave = cpf or person_id
    globais = set(assinaturas_globais or set())
    outros_nomes = set(nomes_outros_socios or set())
    anteriores = dict(salvos or {})
    atual = anteriores.get(mes)
    if atual and atual.assinatura:
        globais.discard(atual.assinatura)
    conjuntos_ano = {
        assinatura_conjunto(r.especies)
        for m, r in anteriores.items()
        if m != mes and r.houve_pesca
    }
    alvo_ano = alvo_peso_anual(chave, ano)
    perfil = perfil_socio(chave, ano)
    plano = _plano_para_mes(chave, ano, mes, anteriores, outros_planos or {}, n_pool)
    n_esp = min(plano[MESES_PESCA.index(mes)], n_pool)
    # pool curto (ex.: só 4 peixes): o ano cabe com ~17 kg por peixe-mês
    capacidade = sum(plano) * 17
    if alvo_ano > capacidade:
        alvo_ano = max(KG_ANO_MIN + _hash_int(f"{chave}|{ano}|cap") % 12, capacidade)

    escolhido: Optional[InformeMes] = None
    tentativa = 0
    fat_usados = _valores_usados_mes(anteriores, mes)
    for tentativa in range(1, 241):
        rng = random.Random(seed + tentativa * 97)
        combo = _escolher_combo(
            rng, mes, n_esp, anteriores, outros_nomes, perfil, pool, peixes_outros_socios
        )
        dias = _escolher_dias(rng, mes, anteriores)
        alvo = _alvo_mes(rng, mes, plano, anteriores, alvo_ano, perfil)
        kgs = _distribuir_kg(rng, mes, combo, alvo, perfil, anteriores)
        ordem = _ordenar(rng, combo, mes, anteriores)
        especies = [
            Especie(n, int(kgs[n]), _preco_socio(rng, n, mes, anteriores, precos_outros_socios))
            for n in ordem
        ]
        if len({e.kg for e in especies}) < 2:
            continue
        # (peixe, kg) idêntico ao mês vizinho — nunca
        pares = {(e.nome, int(e.kg)) for e in especies}
        viz_kg = set()
        for v in _vizinhos(mes, anteriores):
            viz_kg |= {(e.nome, int(e.kg)) for e in v.especies}
        if pares & viz_kg:
            continue
        # mesmo kg da espécie em outro mês do ano — prefere evitar
        kg_ano = any(
            int(e.kg) in _kgs_usados_especie(anteriores, mes, e.nome) for e in especies
        )
        if kg_ano and tentativa < 160:
            continue
        if assinatura_conjunto(especies) in conjuntos_ano:
            continue
        sig = assinatura_mes(mes, especies, dias)
        if sig in globais:
            continue
        agora = now_stamp()
        candidato = InformeMes(
            id=(atual.id if atual else str(uuid.uuid4())),
            person_id=person_id,
            cpf=cpf,
            nome=nome,
            telefone=telefone,
            ano=ano,
            mes=mes,
            houve_pesca=True,
            dias=dias,
            especies=especies,
            municipio=normalizar_municipio(municipio),
            assinatura=sig,
            gerado_em=agora,
            gerado_por=ator,
            atualizado_em=agora,
            atualizado_por=ator,
            plano=plano_str(plano),
        )
        # evita repetir o mesmo faturamento mensal
        if round(float(candidato.faturamento_mes), 2) in fat_usados and tentativa < 140:
            continue
        escolhido = candidato
        break
    if escolhido is None:
        raise RuntimeError(
            "Não consegui gerar um mês sem repetir os anteriores. Tente gerar de novo."
        )

    simulado = dict(anteriores)
    simulado[mes] = escolhido
    avisos = validar_ano(simulado, alvo_ano=alvo_ano, n_pool=n_pool)
    return ResultadoGeracao(escolhido, alvo_ano, avisos, tentativa, list(plano))


# --------------------------------------------------------------------------
# Validação
# --------------------------------------------------------------------------


def validar_mes(mes: str, dias: Any, especies: Sequence[Especie]) -> List[str]:
    """Erros que impedem salvar (regras do cérebro)."""
    erros: List[str] = []
    mes = normalizar_mes(mes)
    if mes in MESES_PIRACEMA:
        return [f"{MES_TITULO[mes]}: {PIRACEMA_LABEL} (não houve pesca)."]
    try:
        d = int(dias)
    except (TypeError, ValueError):
        d = -1
    if not (DIAS_MIN <= d <= DIAS_MAX):
        erros.append(f"Dias de pesca devem ficar entre {DIAS_MIN} e {DIAS_MAX}.")
    n = len(especies)
    if n not in CONTAGENS:
        erros.append("Quantidade de espécies deve ser 4, 5, 6 ou 8.")
    nomes = [e.nome for e in especies]
    if len(set(nomes)) != len(nomes):
        erros.append("Espécie repetida no mesmo mês.")
    for e in especies:
        if e.nome not in PRECOS_VAREJO:
            erros.append(f"Peixe fora do catálogo: {e.nome}.")
            continue
        if not (KG_MIN <= int(e.kg) <= KG_MAX):
            erros.append(f"{e.nome}: kg deve ser inteiro entre {KG_MIN} e {KG_MAX}.")
    if n >= 2 and len({int(e.kg) for e in especies}) < 2:
        erros.append("Os kg não podem ser todos iguais (varie por espécie).")
    return erros


def peso_anual(meses: Dict[str, InformeMes]) -> int:
    return sum(r.peso_mes for m, r in meses.items() if m in MESES_PESCA and r.houve_pesca)


def faturamento_anual(meses: Dict[str, InformeMes]) -> float:
    return round(
        sum(r.faturamento_mes for m, r in meses.items() if m in MESES_PESCA and r.houve_pesca),
        2,
    )


def validar_ano(
    meses: Dict[str, InformeMes],
    *,
    alvo_ano: Optional[int] = None,
    n_pool: Optional[int] = None,
) -> List[str]:
    """Avisos do ano (não bloqueiam salvar)."""
    avisos: List[str] = []
    feitos = [m for m in MESES_PESCA if m in meses and meses[m].houve_pesca]
    contagens = [len(meses[m].especies) for m in feitos]
    conj: Dict[str, str] = {}
    for m in feitos:
        sig = assinatura_conjunto(meses[m].especies)
        if sig in conj:
            avisos.append(
                f"{MES_TITULO[m]} repete o mesmo conjunto de {MES_TITULO[conj[sig]]}."
            )
        conj[sig] = m
    # pool curto (4 ou 5 peixes): a alternância 4/5/6 é impossível
    if n_pool is not None:
        curto = _pool_curto(int(n_pool))
    else:
        curto = len(feitos) == len(MESES_PESCA) and max(contagens) < max(CONTAGENS_OBRIGATORIAS)
    if curto:
        for i in range(len(feitos) - 2):
            trio = feitos[i : i + 3]
            seguidos = MESES_PESCA.index(trio[2]) - MESES_PESCA.index(trio[0]) == 2
            c3 = {len(meses[m].especies) for m in trio}
            if seguidos and len(c3) == 1 and max(contagens) > min(contagens):
                avisos.append(
                    f"{MES_TITULO[trio[0]]} a {MES_TITULO[trio[2]]} com a mesma quantidade."
                )
    else:
        for c, lim in CONTAGEM_MAX_ANO.items():
            if contagens.count(c) > lim:
                avisos.append(f"{contagens.count(c)} meses com {c} espécies (máx. {lim}).")
    for a, b in zip(MESES_PESCA, MESES_PESCA[1:]):
        ra, rb = meses.get(a), meses.get(b)
        if (
            not curto
            and ra and rb and ra.houve_pesca and rb.houve_pesca
            and len(ra.especies) == len(rb.especies)
        ):
            avisos.append(
                f"{MES_TITULO[a]} e {MES_TITULO[b]} com a mesma quantidade ({len(ra.especies)} espécies)."
            )
        if ra and rb and ra.houve_pesca and rb.houve_pesca:
            sa = {e.nome for e in ra.especies}
            sb = {e.nome for e in rb.especies}
            comuns = sa & sb
            # aviso só quando a sobreposição era evitável (pool comporta os dois meses)
            n_pool_est = max(len(sa | sb), max((len(meses[m].especies) for m in feitos), default=8))
            evitavel = len(sa) + len(sb) <= n_pool_est
            permitido = 1 + max(len(sa), len(sb)) // 4
            if evitavel and len(comuns) > permitido:
                avisos.append(
                    f"{MES_TITULO[a]} e {MES_TITULO[b]} repetem peixe(s): {', '.join(sorted(comuns))}."
                )
            kgs_a = {(e.nome, int(e.kg)) for e in ra.especies}
            kgs_b = {(e.nome, int(e.kg)) for e in rb.especies}
            mesmos_kg = sorted(n for n, _ in (kgs_a & kgs_b))
            if mesmos_kg:
                avisos.append(
                    f"{MES_TITULO[a]} e {MES_TITULO[b]} com o mesmo kg em: {', '.join(mesmos_kg)}."
                )
    peso = peso_anual(meses)
    if len(feitos) == len(MESES_PESCA):
        # A mistura 4/5/6 só é exigida quando o pool de peixes ativos permite.
        n_pool = max((len(meses[m].especies) for m in feitos), default=8)
        # Se algum mês chegou a 8, o pool era ≥ 8; senão usamos o maior visto.
        if any(len(meses[m].especies) == 8 for m in feitos):
            n_pool = 8
        obr = contagens_obrigatorias_para_pool(max(n_pool, max(contagens) if contagens else 4))
        if obr and not set(obr).issubset(set(contagens)):
            avisos.append(
                "Ano sem a mistura " + " / ".join(str(c) for c in obr) + " espécies."
            )
        if not (KG_ANO_MIN <= peso <= KG_ANO_MAX):
            avisos.append(f"Peso anual {peso} kg fora da faixa {KG_ANO_MIN}–{KG_ANO_MAX}.")
    elif peso > KG_ANO_MAX:
        avisos.append(f"Peso acumulado {peso} kg já passou de {KG_ANO_MAX}.")
    return avisos


def especies_de_payload(raw: Any, mes: Optional[str] = None) -> List[Especie]:
    """Lista vinda da UI (edição manual).

    VALOR: mantém o preço que veio (se estiver na faixa do mês); senão usa o
    preço varejo de referência do mês (ou o do catálogo, sem mês).
    """
    out: List[Especie] = []
    for item in raw or []:
        if not isinstance(item, dict):
            continue
        nome = str(item.get("nome") or "").strip()
        if not nome:
            continue
        try:
            kg = int(round(float(str(item.get("kg") or 0).replace(",", "."))))
        except (TypeError, ValueError):
            kg = 0
        valor = float(PRECOS_VAREJO.get(nome, 0.0))
        if mes:
            ref = preco_mes(nome, mes)
            lo, hi = faixa_preco(nome, mes)
            valor = ref
            try:
                v = float(round(float(str(item.get("valor") or "").replace(",", "."))))
            except (TypeError, ValueError):
                v = 0.0
            if lo <= v <= hi:
                valor = v
        out.append(Especie(nome, kg, valor))
    return out


def resumo_socio(meses: Dict[str, InformeMes], cpf: str, ano: int) -> Dict[str, Any]:
    feitos = [m for m in MESES_PESCA if m in meses and meses[m].houve_pesca]
    perfil = perfil_socio(cpf, ano)
    favoritas = sorted(perfil["pref"], key=lambda n: perfil["pref"][n], reverse=True)
    plano = plano_do_socio(meses)
    return {
        "gerados": len(feitos),
        "total": len(MESES_PESCA),
        "peso_anual": peso_anual(meses),
        "faturamento_anual": faturamento_anual(meses),
        "alvo_peso_anual": alvo_peso_anual(cpf, ano),
        "contagens": [len(meses[m].especies) for m in feitos],
        "plano": plano or [],
        "plano_texto": plano_str(plano) if plano else "",
        "padrao_atual": padrao_quantidades(meses),
        "perfil": {
            "favoritas": favoritas[:3],
            "menos": favoritas[-2:],
            "pico": perfil["pico"],
            "ritmo": perfil["ritmo"],
        },
        "avisos": validar_ano(meses),
    }


def padrao_quantidades(meses: Dict[str, InformeMes]) -> str:
    """Ex.: '4-6-5-·-·-·-·-·' (· = mês ainda não gerado)."""
    return "-".join(
        str(len(meses[m].especies)) if m in meses and meses[m].houve_pesca else "·"
        for m in MESES_PESCA
    )


def padroes_iguais(
    por_socio: Dict[str, Dict[str, InformeMes]],
    *,
    minimo_meses: int = 4,
) -> List[Dict[str, Any]]:
    """Grupos de sócios com padrão igual (quantidades, kg por mês ou mês idêntico)."""
    grupos: List[Dict[str, Any]] = []

    def _agrupar(tipo: str, descricao, chaves: Dict[str, Any]) -> None:
        inv: Dict[Any, List[str]] = {}
        for pid, key in chaves.items():
            if key is not None:
                inv.setdefault(key, []).append(pid)
        for key, pids in inv.items():
            if len(pids) >= 2:
                grupos.append({"tipo": tipo, "descricao": descricao(key), "padrao": str(key), "socios": sorted(pids)})

    quant: Dict[str, Any] = {}
    kg: Dict[str, Any] = {}
    planos: Dict[str, Any] = {}
    for pid, meses in por_socio.items():
        feitos = [m for m in MESES_PESCA if m in meses and meses[m].houve_pesca]
        quant[pid] = padrao_quantidades(meses) if len(feitos) >= minimo_meses else None
        kg[pid] = (
            "-".join(str(meses[m].peso_mes) if m in feitos else "·" for m in MESES_PESCA)
            if len(feitos) >= 2
            else None
        )
        pl = plano_do_socio(meses)
        planos[pid] = plano_str(pl) if pl else None

    _agrupar("plano", lambda k: f"Mesmo plano anual de quantidades: {k}", planos)
    ja = {tuple(g["socios"]) for g in grupos}
    for pid in list(quant):
        if quant[pid] is not None and "·" not in quant[pid]:
            quant[pid] = None
    _agrupar("quantidades", lambda k: f"Mesma quantidade de espécies por mês: {k}", quant)
    grupos[:] = [g for g in grupos if g["tipo"] != "quantidades" or tuple(g["socios"]) not in ja]
    _agrupar("kg", lambda k: f"Mesmos kg por mês: {k}", kg)

    for m in MESES_PESCA:
        mes_key: Dict[str, Any] = {}
        for pid, meses in por_socio.items():
            r = meses.get(m)
            mes_key[pid] = assinatura_conjunto(r.especies) if r and r.houve_pesca else None
        _agrupar(
            "mes_identico",
            lambda k, m=m: f"{MES_TITULO[m]} idêntico (mesmas espécies e kg): {k.split('|', 1)[1].replace('|', ', ')}",
            mes_key,
        )
    vistos = set()
    unicos = []
    for g in grupos:
        chave = (g["tipo"], tuple(g["socios"]), g["padrao"])
        if chave not in vistos:
            vistos.add(chave)
            unicos.append(g)
    return unicos


def texto_para_site(reg: InformeMes) -> str:
    """Texto pronto para conferir/colar no Informe Mensal do gov.br."""
    linhas = [
        f"REAP — Informe Mensal {MES_TITULO.get(reg.mes, reg.mes)}/{reg.ano}",
        f"Pescador: {reg.nome} · CPF {reg.cpf}",
        "Houve pesca: SIM",
        f"Dias de pesca: {reg.dias}",
        f"Local: {reg.local} · UF {LOCAL_PADRAO['uf']} · Município {reg.municipio}",
        f"Ambiente: {reg.ambiente} · Petrecho: {reg.petrecho}",
        "Espécies (kg · valor médio R$/kg):",
    ]
    for i, e in enumerate(reg.especies, start=1):
        valor = f"{float(e.valor):.2f}".replace(".", ",")
        linhas.append(f"  {i}. {e.nome} — {int(e.kg)} kg — R$ {valor}")
    linhas.append(f"Total do mês: {reg.peso_mes} kg")
    return "\n".join(linhas)


def catalogo(ativas: Optional[Sequence[str]] = None) -> List[Dict[str, Any]]:
    """Catálogo completo; ``ativo`` indica se entra no cérebro (seleção universal)."""
    ligados = set(normalizar_especies_ativas(ativas))
    return [
        {"nome": n, "preco": p, "ativo": n in ligados, "extra": n not in PRECOS_BASE}
        for n, p in PRECOS_VAREJO.items()
    ]


def resumo_especies_ativas(ativas: Optional[Sequence[str]] = None) -> Dict[str, Any]:
    pool = normalizar_especies_ativas(ativas)
    return {
        "todas": list(ESPECIES_TODAS),
        "ativas": pool,
        "n_ativas": len(pool),
        "minimo": MIN_ESPECIES_ATIVAS,
        "contagens": list(contagens_para_pool(len(pool))),
        "permite_8": len(pool) >= 8,
    }
