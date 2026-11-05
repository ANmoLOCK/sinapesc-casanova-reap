"""Informe Mensal — cérebro REAP (reformulação v4) adaptado para gerar mês a mês.

Regras herdadas do cérebro ``reap-informe-mensal-v1.8.0``:
  - Jan / Fev / Nov / Dez = ÉPOCA DE PIRACEMA (não houve pesca)
  - Mar → Out = pesca, 16–21 dias, 4 / 5 / 6 / 8 espécies intercaladas
  - kg inteiro (5–22) com viés sazonal por espécie
  - VALOR = preço varejo (não multiplica por kg)
  - PESO ANUAL (soma kg Mar–Out) 540–650, alvo próprio de cada sócio

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

MOTOR = "cerebro_reformulacao/v5-plano"

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
}
# ordem fixa do catálogo (configuração universal do Informe Mensal)
ESPECIES_TODAS: Tuple[str, ...] = tuple(PRECOS_VAREJO.keys())
MIN_ESPECIES_ATIVAS = 4


def normalizar_especies_ativas(raw: Any = None) -> List[str]:
    """Lista canônica dos peixes ativos no cérebro (universal para todos os sócios).

    Vazio / inválido → todos os 8. Ordem = ``ESPECIES_TODAS``.
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
PESO_QUANTIDADE = {4: 0.40, 5: 0.33, 6: 0.27}
# cada repetição da mesma quantidade no ano multiplica o peso por este fator
FATOR_REPETICAO = 0.45
CHANCE_SOCIO_TER_8 = 0.35
# mês com 8 espécies cai mais no meio da safra do que nas pontas
PESO_POSICAO_8 = [0.55, 0.8, 1.0, 1.25, 1.25, 1.0, 0.8, 0.55]
AMOSTRAS_PROBABILIDADE = 4000
MUNICIPIOS = ("Casa Nova", "Remanso")

LOCAL_PADRAO = {
    "local": "Rio",
    "uf": "BAHIA",
    "ambiente": "Água Doce",
    "petrecho": "Emalhe",
}

# Atividade sazonal humanizada (São Francisco / BA) — só viés de kg e escolha
ATIVIDADE: Dict[str, Dict[str, float]] = {
    "mar": {"Curimatã": 1.35, "Tilápia": 1.25, "Piau": 1.15, "Tucunaré": 1.10,
            "Piranha": 1.00, "Pescada": 0.90, "Tambaqui": 0.80, "Dourado-de-água-doce": 0.65},
    "abr": {"Curimatã": 1.30, "Tilápia": 1.20, "Piau": 1.15, "Tucunaré": 1.15,
            "Piranha": 1.05, "Pescada": 0.95, "Tambaqui": 0.85, "Dourado-de-água-doce": 0.70},
    "mai": {"Tilápia": 1.25, "Piau": 1.20, "Curimatã": 1.10, "Pescada": 1.10,
            "Tucunaré": 1.00, "Piranha": 0.95, "Tambaqui": 0.95, "Dourado-de-água-doce": 0.75},
    "jun": {"Tambaqui": 1.30, "Tilápia": 1.15, "Pescada": 1.15, "Piau": 1.05,
            "Curimatã": 0.95, "Tucunaré": 0.95, "Piranha": 0.85, "Dourado-de-água-doce": 0.90},
    "jul": {"Tambaqui": 1.35, "Pescada": 1.20, "Tilápia": 1.10, "Piau": 1.00,
            "Dourado-de-água-doce": 1.00, "Curimatã": 0.90, "Tucunaré": 0.90, "Piranha": 0.80},
    "ago": {"Tambaqui": 1.25, "Pescada": 1.15, "Tilápia": 1.10, "Dourado-de-água-doce": 1.05,
            "Piau": 1.00, "Tucunaré": 0.95, "Curimatã": 0.85, "Piranha": 0.85},
    "set": {"Tucunaré": 1.35, "Piranha": 1.25, "Tilápia": 1.15, "Piau": 1.05,
            "Pescada": 1.00, "Tambaqui": 0.95, "Curimatã": 0.90, "Dourado-de-água-doce": 0.80},
    "out": {"Tucunaré": 1.40, "Piranha": 1.30, "Tilápia": 1.15, "Piau": 1.10,
            "Pescada": 0.95, "Tambaqui": 0.90, "Curimatã": 0.85, "Dourado-de-água-doce": 0.75},
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


def plano_valido(seq: Sequence[int], n_pool: int = 8) -> bool:
    if len(seq) != len(MESES_PESCA):
        return False
    if any(a == b for a, b in zip(seq, seq[1:])):
        return False
    if any(int(c) > int(n_pool) for c in seq):
        return False
    obr = contagens_obrigatorias_para_pool(n_pool)
    if obr and not set(obr).issubset(set(seq)):
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
    1 mês com 8 (só ~35% dos sócios, e só se houver ≥ 8 peixes ativos).
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
) -> Tuple[str, ...]:
    nomes = list(normalizar_especies_ativas(pool))
    n_esp = max(1, min(int(n_esp), len(nomes)))
    if n_esp >= len(nomes):
        return tuple(nomes)
    usados_ano = {
        assinatura_nomes(e.nome for e in r.especies)
        for m, r in salvos.items()
        if m != mes and r.houve_pesca
    }
    vizinhos = [frozenset(e.nome for e in v.especies) for v in _vizinhos(mes, salvos)]

    def score(cand: Tuple[str, ...]) -> float:
        fs = frozenset(cand)
        key = assinatura_nomes(cand)
        s = sum(_fator(mes, n, perfil) for n in cand) * 1.8
        s += rng.uniform(0, 1.5)
        if key in usados_ano:
            s -= 8.0
        if key in nomes_outros_socios:
            s -= 1.2
        for v in vizinhos:
            s -= len(fs & v) * 2.5 / max(1, len(vizinhos))
        return s

    todas = list(combinations(nomes, n_esp))
    rng.shuffle(todas)
    todas.sort(key=score, reverse=True)
    for cand in todas:
        if assinatura_nomes(cand) not in usados_ano:
            return cand
    return todas[0]


def _escolher_dias(rng: random.Random, mes: str, salvos: Dict[str, InformeMes]) -> int:
    usados = {r.dias for m, r in salvos.items() if m != mes and r.houve_pesca}
    vizinhos = {v.dias for v in _vizinhos(mes, salvos)}
    opcoes = [d for d in range(DIAS_MIN, DIAS_MAX + 1) if d not in usados and d not in vizinhos]
    if not opcoes:
        opcoes = [d for d in range(DIAS_MIN, DIAS_MAX + 1) if d not in vizinhos]
    if not opcoes:
        opcoes = list(range(DIAS_MIN, DIAS_MAX + 1))
    return rng.choice(opcoes)


def _kg_base(rng: random.Random, mes: str, nome: str, perfil: Dict[str, Any]) -> int:
    centro = 11 + int(round((_fator(mes, nome, perfil) - 1.0) * 6))
    centro += rng.choice([-2, -1, 0, 0, 1, 2])
    return max(KG_MIN, min(KG_MAX, centro))


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
    if not pendentes:
        alvo = restante
    else:
        peso_aqui = n_esp * ritmo[mes]
        peso_depois = sum(plano[i] * ritmo[m] for i, m in pendentes)
        share = peso_aqui / (peso_aqui + peso_depois)
        alvo = int(round(restante * share * rng.uniform(0.92, 1.08)))
        min_depois = sum(plano[i] * KG_MIN for i, _ in pendentes)
        max_depois = sum(plano[i] * KG_MAX for i, _ in pendentes)
        alvo = max(restante - max_depois, min(alvo, restante - min_depois))
    return max(n_esp * KG_MIN + 1, min(n_esp * KG_MAX - 1, alvo))


def _distribuir_kg(
    rng: random.Random,
    mes: str,
    combo: Sequence[str],
    alvo: int,
    perfil: Dict[str, Any],
) -> Dict[str, int]:
    kgs = {n: _kg_base(rng, mes, n, perfil) for n in combo}
    for _ in range(600):
        total = sum(kgs.values())
        if total == alvo:
            break
        if total < alvo:
            cands = [n for n in combo if kgs[n] < KG_MAX]
            if not cands:
                break
            cands.sort(key=lambda n: (-_fator(mes, n, perfil) + rng.uniform(0, 0.35), kgs[n]))
            kgs[cands[0]] += 1
        else:
            cands = [n for n in combo if kgs[n] > KG_MIN]
            if not cands:
                break
            cands.sort(key=lambda n: (_fator(mes, n, perfil) + rng.uniform(0, 0.35), -kgs[n]))
            kgs[cands[0]] -= 1
    if len(set(kgs.values())) < 2 and len(combo) >= 2:
        ranked = sorted(combo, key=lambda n: _fator(mes, n, perfil), reverse=True)
        hi, lo = ranked[0], ranked[-1]
        if kgs[hi] < KG_MAX and kgs[lo] > KG_MIN:
            kgs[hi] += 1
            kgs[lo] -= 1
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
) -> ResultadoGeracao:
    """Gera o REAP de um mês de pesca, condicionado aos meses já salvos do sócio.

    ``salvos`` = meses já gravados do mesmo sócio/ano (chave = mes curto).
    ``assinaturas_globais`` = assinaturas de todos os meses de todos os sócios
    (evita gerar um mês idêntico ao de outro pescador).
    ``outros_planos`` = planos de quantidades dos outros sócios no ano
    (o plano deste sócio é sorteado para não repetir nenhum).
    ``especies_ativas`` = peixes liberados na config do Informe Mensal (universal).
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

    escolhido: Optional[InformeMes] = None
    tentativa = 0
    for tentativa in range(1, 121):
        rng = random.Random(seed + tentativa * 97)
        combo = _escolher_combo(rng, mes, n_esp, anteriores, outros_nomes, perfil, pool)
        dias = _escolher_dias(rng, mes, anteriores)
        alvo = _alvo_mes(rng, mes, plano, anteriores, alvo_ano, perfil)
        kgs = _distribuir_kg(rng, mes, combo, alvo, perfil)
        ordem = _ordenar(rng, combo, mes, anteriores)
        especies = [Especie(n, int(kgs[n]), float(PRECOS_VAREJO[n])) for n in ordem]
        if len({e.kg for e in especies}) < 2:
            continue
        if assinatura_conjunto(especies) in conjuntos_ano:
            continue
        sig = assinatura_mes(mes, especies, dias)
        if sig in globais:
            continue
        agora = now_stamp()
        escolhido = InformeMes(
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
        break
    if escolhido is None:
        raise RuntimeError(
            "Não consegui gerar um mês sem repetir os anteriores. Tente gerar de novo."
        )

    simulado = dict(anteriores)
    simulado[mes] = escolhido
    avisos = validar_ano(simulado, alvo_ano=alvo_ano)
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


def validar_ano(meses: Dict[str, InformeMes], *, alvo_ano: Optional[int] = None) -> List[str]:
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
    for c, lim in CONTAGEM_MAX_ANO.items():
        if contagens.count(c) > lim:
            avisos.append(f"{contagens.count(c)} meses com {c} espécies (máx. {lim}).")
    for a, b in zip(MESES_PESCA, MESES_PESCA[1:]):
        ra, rb = meses.get(a), meses.get(b)
        if ra and rb and ra.houve_pesca and rb.houve_pesca and len(ra.especies) == len(rb.especies):
            avisos.append(
                f"{MES_TITULO[a]} e {MES_TITULO[b]} com a mesma quantidade ({len(ra.especies)} espécies)."
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


def especies_de_payload(raw: Any) -> List[Especie]:
    """Lista vinda da UI (edição manual). VALOR sempre = preço varejo."""
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
        out.append(Especie(nome, kg, float(PRECOS_VAREJO.get(nome, 0.0))))
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
        {"nome": n, "preco": p, "ativo": n in ligados}
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
