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
import random
import secrets
import uuid
from dataclasses import dataclass, field
from datetime import datetime
from itertools import combinations
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple

MOTOR = "cerebro_reformulacao/v4-mensal"

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

KG_MIN = 5
KG_MAX = 22
KG_ANO_MIN = 540
KG_ANO_MAX = 650
ALVOS_KG_ANO = [540, 548, 555, 565, 575, 585, 595, 605, 615, 625, 635, 645, 650]
DIAS_MIN = 16
DIAS_MAX = 21
CONTAGENS = (4, 5, 6, 8)
# máximo de meses por contagem no ano (evita "4,4,4,4,4,4,6,8")
CONTAGEM_MAX_ANO = {4: 3, 5: 3, 6: 3, 8: 2}
CONTAGEM_PESO = {4: 3.0, 5: 2.2, 6: 2.2, 8: 1.3}
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
]
INFORME_HEADER_RANGE = "A1:X1"
INFORME_DATA_RANGE = "A2:X"


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


def alvo_peso_anual(cpf: str, ano: int) -> int:
    """Alvo próprio (estável) do sócio no ano — cada sócio fecha num total diferente."""
    h = int(hashlib.sha256(f"{cpf}|{ano}|alvo".encode("utf-8")).hexdigest(), 16)
    base = ALVOS_KG_ANO[h % len(ALVOS_KG_ANO)]
    jitter = (-6, -3, 0, 2, 5)[(h >> 8) % 5]
    return max(KG_ANO_MIN, min(KG_ANO_MAX, base + jitter))


def _vizinhos(mes: str, salvos: Dict[str, InformeMes]) -> List[InformeMes]:
    i = MESES_PESCA.index(mes)
    out = []
    for j in (i - 1, i + 1):
        if 0 <= j < len(MESES_PESCA):
            m = MESES_PESCA[j]
            if m in salvos and salvos[m].houve_pesca:
                out.append(salvos[m])
    return out


def _escolher_contagem(rng: random.Random, mes: str, salvos: Dict[str, InformeMes]) -> int:
    usados = [len(r.especies) for m, r in salvos.items() if m != mes and r.houve_pesca]
    faltam = [c for c in CONTAGENS if c not in usados]
    slots = len([m for m in MESES_PESCA if m not in salvos or m == mes])
    vizinhos = {len(v.especies) for v in _vizinhos(mes, salvos)}

    candidatos = [c for c in CONTAGENS if usados.count(c) < CONTAGEM_MAX_ANO[c]]
    if faltam and len(faltam) >= slots:
        candidatos = [c for c in faltam] or candidatos
    if not candidatos:
        candidatos = list(CONTAGENS)

    pesos = []
    for c in candidatos:
        w = CONTAGEM_PESO[c]
        if c in faltam:
            w *= 1.7
        if c in vizinhos:
            w *= 0.15
        pesos.append(w)
    return rng.choices(candidatos, weights=pesos, k=1)[0]


def _escolher_combo(
    rng: random.Random,
    mes: str,
    n_esp: int,
    salvos: Dict[str, InformeMes],
    nomes_outros_socios: set,
) -> Tuple[str, ...]:
    nomes = list(PRECOS_VAREJO.keys())
    if n_esp >= len(nomes):
        return tuple(nomes)
    atv = ATIVIDADE.get(mes) or {}
    usados_ano = {
        assinatura_nomes(e.nome for e in r.especies)
        for m, r in salvos.items()
        if m != mes and r.houve_pesca
    }
    vizinhos = [frozenset(e.nome for e in v.especies) for v in _vizinhos(mes, salvos)]

    def score(cand: Tuple[str, ...]) -> float:
        fs = frozenset(cand)
        key = assinatura_nomes(cand)
        s = sum(atv.get(n, 1.0) for n in cand) * 1.8
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


def _kg_base(rng: random.Random, mes: str, nome: str) -> int:
    atv = (ATIVIDADE.get(mes) or {}).get(nome, 1.0)
    centro = 11 + int(round((atv - 1.0) * 6))
    centro += rng.choice([-2, -1, 0, 0, 1, 2])
    return max(KG_MIN, min(KG_MAX, centro))


def _alvo_mes(
    rng: random.Random,
    mes: str,
    n_esp: int,
    salvos: Dict[str, InformeMes],
    alvo_ano: int,
) -> int:
    outros = [r for m, r in salvos.items() if m != mes and r.houve_pesca and m in MESES_PESCA]
    acumulado = sum(r.peso_mes for r in outros)
    restante = alvo_ano - acumulado
    slots_depois = len([m for m in MESES_PESCA if m != mes and m not in salvos])
    media_n = 5.6
    if slots_depois == 0:
        alvo = restante
    else:
        share = n_esp / (n_esp + media_n * slots_depois)
        alvo = int(round(restante * share * rng.uniform(0.9, 1.1)))
        # deixa espaço viável para os meses que faltam (4–8 spp × 5–22 kg)
        min_depois = slots_depois * 4 * KG_MIN
        max_depois = slots_depois * 8 * KG_MAX
        alvo = max(restante - max_depois, min(alvo, restante - min_depois))
    return max(n_esp * KG_MIN + 1, min(n_esp * KG_MAX - 1, alvo))


def _distribuir_kg(
    rng: random.Random,
    mes: str,
    combo: Sequence[str],
    alvo: int,
) -> Dict[str, int]:
    kgs = {n: _kg_base(rng, mes, n) for n in combo}
    atv = ATIVIDADE.get(mes) or {}
    for _ in range(600):
        total = sum(kgs.values())
        if total == alvo:
            break
        if total < alvo:
            cands = [n for n in combo if kgs[n] < KG_MAX]
            if not cands:
                break
            cands.sort(key=lambda n: (-atv.get(n, 1.0) + rng.uniform(0, 0.35), kgs[n]))
            kgs[cands[0]] += 1
        else:
            cands = [n for n in combo if kgs[n] > KG_MIN]
            if not cands:
                break
            cands.sort(key=lambda n: (atv.get(n, 1.0) + rng.uniform(0, 0.35), -kgs[n]))
            kgs[cands[0]] -= 1
    if len(set(kgs.values())) < 2 and len(combo) >= 2:
        ranked = sorted(combo, key=lambda n: atv.get(n, 1.0), reverse=True)
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
    municipio: str = "Casa Nova",
    seed: Optional[int] = None,
    ator: str = "",
) -> ResultadoGeracao:
    """Gera o REAP de um mês de pesca, condicionado aos meses já salvos do sócio.

    ``salvos`` = meses já gravados do mesmo sócio/ano (chave = mes curto).
    ``assinaturas_globais`` = assinaturas de todos os meses de todos os sócios
    (evita gerar um mês idêntico ao de outro pescador).
    """
    mes = normalizar_mes(mes)
    if mes in MESES_PIRACEMA:
        raise ValueError(f"{MES_TITULO[mes]} é {PIRACEMA_LABEL} — não há REAP de pesca.")
    ano = int(ano)
    if seed is None:
        seed = secrets.randbits(48)
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
    alvo_ano = alvo_peso_anual(cpf or person_id, ano)

    escolhido: Optional[InformeMes] = None
    tentativa = 0
    for tentativa in range(1, 121):
        rng = random.Random(seed + tentativa * 97)
        n_esp = _escolher_contagem(rng, mes, anteriores)
        combo = _escolher_combo(rng, mes, n_esp, anteriores, outros_nomes)
        dias = _escolher_dias(rng, mes, anteriores)
        alvo = _alvo_mes(rng, mes, n_esp, anteriores, alvo_ano)
        kgs = _distribuir_kg(rng, mes, combo, alvo)
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
        )
        break
    if escolhido is None:
        raise RuntimeError(
            "Não consegui gerar um mês sem repetir os anteriores. Tente gerar de novo."
        )

    simulado = dict(anteriores)
    simulado[mes] = escolhido
    avisos = validar_ano(simulado, alvo_ano=alvo_ano)
    return ResultadoGeracao(escolhido, alvo_ano, avisos, tentativa)


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
    peso = peso_anual(meses)
    if len(feitos) == len(MESES_PESCA):
        if not set(CONTAGENS).issubset(set(contagens)):
            avisos.append("Ano sem a mistura 4 / 5 / 6 / 8 espécies.")
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
    return {
        "gerados": len(feitos),
        "total": len(MESES_PESCA),
        "peso_anual": peso_anual(meses),
        "faturamento_anual": faturamento_anual(meses),
        "alvo_peso_anual": alvo_peso_anual(cpf, ano),
        "contagens": [len(meses[m].especies) for m in feitos],
        "avisos": validar_ano(meses),
    }


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


def catalogo() -> List[Dict[str, Any]]:
    return [{"nome": n, "preco": p} for n, p in PRECOS_VAREJO.items()]
