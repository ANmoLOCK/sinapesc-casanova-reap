"""Consulta RGP — planilha exclusiva + status MPA / importação REAP·Defeso."""

from __future__ import annotations

import uuid
from dataclasses import asdict, dataclass, field
from datetime import datetime
from typing import Any, Dict, List, Optional, Sequence

from ui.formatters import display_nome, format_cpf, format_nome, normalize_cpf, only_digits


CONSULTA_RGP_TAB = "ConsultaRGP"
CONSULTA_RGP_CONFIG_TAB = "Config"
CONSULTA_RGP_AUDITORIA_TAB = "Auditoria"
CONSULTA_RGP_CONFIG_HEADER = ["chave", "valor"]
CONSULTA_RGP_PREF_GOVBR_SENHA = "govbr_senha"
CONSULTA_RGP_HEADER = [
    "id",
    "personId",
    "nome",
    "cpf",
    "telefone",
    "municipio",
    "uf",
    "situacaoRgp",
    "observacao",
    "ultimaConsultaEm",
    "codigoRgp",
    "categoria",
    "email",
    "importadoReapEm",
    "importadoDefesoEm",
    "cadastroReapEm",
    "atualizadoEm",
    "criadoEm",
    "timeline",
]

# Estimativa de UX: ~20 min para 500 consultas sequenciais (~2,4 s/CPF).
# O site MPA pode demorar mais; a UI mostra progresso real.
SEGUNDOS_POR_CONSULTA_EST = 2.4

# Situações retornadas / normalizadas do site MPA
SITUACAO_ATIVO = "Ativo"
SITUACAO_AGUARDANDO_ANALISE = "Aguardando análise"
SITUACAO_EM_ANALISE = "Em análise"
SITUACAO_RASCUNHO = "Rascunho"
SITUACAO_FINALIZADA = "Finalizada"
SITUACAO_AGUARDANDO_ATUALIZACAO = "Aguardando atualização do interessado"
SITUACAO_SUSPENSO = "Suspenso"
SITUACAO_CANCELADO = "Cancelado"
SITUACAO_INATIVO = "Inativo"
SITUACAO_PEND_REG = "Pend. regularização"
SITUACAO_NAO_CONSULTADO = "Não consultado"
SITUACAO_NAO_ENCONTRADO = "Não encontrado"

# Só Ativo entra nas planilhas REAP e Defeso
SITUACOES_APTAS_IMPORT = frozenset(
    {
        SITUACAO_ATIVO.lower(),
    }
)

_SITUACAO_ALIASES = {
    "ativo": SITUACAO_ATIVO,
    "aguardando analise": SITUACAO_AGUARDANDO_ANALISE,
    "aguardando análise": SITUACAO_AGUARDANDO_ANALISE,
    "aguardando analise consulta publica": SITUACAO_AGUARDANDO_ANALISE,
    "aguardando análise consulta pública": SITUACAO_AGUARDANDO_ANALISE,
    "aguardando analise consulta pública": SITUACAO_AGUARDANDO_ANALISE,
    "em analise": SITUACAO_EM_ANALISE,
    "em análise": SITUACAO_EM_ANALISE,
    "rascunho": SITUACAO_RASCUNHO,
    "finalizada": SITUACAO_FINALIZADA,
    "finalizado": SITUACAO_FINALIZADA,
    "deferida": SITUACAO_ATIVO,
    "deferido": SITUACAO_ATIVO,
    "indeferida": SITUACAO_PEND_REG,
    "indeferido": SITUACAO_PEND_REG,
    "aguardando atualizacao": SITUACAO_AGUARDANDO_ATUALIZACAO,
    "aguardando atualização": SITUACAO_AGUARDANDO_ATUALIZACAO,
    "aguardando atualizacao de informacoes do(a) interessado(a)": SITUACAO_AGUARDANDO_ATUALIZACAO,
    "aguardando atualização de informações do(a) interessado(a)": SITUACAO_AGUARDANDO_ATUALIZACAO,
    "aguardando atualizacao do interessado": SITUACAO_AGUARDANDO_ATUALIZACAO,
    "aguardando atualização do interessado": SITUACAO_AGUARDANDO_ATUALIZACAO,
    "suspenso": SITUACAO_SUSPENSO,
    "cancelado": SITUACAO_CANCELADO,
    "inativo": SITUACAO_INATIVO,
    "pend. regularizacao": SITUACAO_PEND_REG,
    "pend. regularização": SITUACAO_PEND_REG,
    "pendente regularizacao": SITUACAO_PEND_REG,
    "pendente regularização": SITUACAO_PEND_REG,
    "em correção": SITUACAO_PEND_REG,
    "em correçao": SITUACAO_PEND_REG,
    "em correcao": SITUACAO_PEND_REG,
    "nao consultado": SITUACAO_NAO_CONSULTADO,
    "não consultado": SITUACAO_NAO_CONSULTADO,
    "nao encontrado": SITUACAO_NAO_ENCONTRADO,
    "não encontrado": SITUACAO_NAO_ENCONTRADO,
    "nao encontrado no mpa": SITUACAO_NAO_ENCONTRADO,
    "não encontrado no mpa": SITUACAO_NAO_ENCONTRADO,
    "": SITUACAO_NAO_CONSULTADO,
}

# Códigos numéricos vistos nos enums do front MPA (consulta pública / solicitação)
_SITUACAO_NUMERIC = {
    "0": SITUACAO_NAO_CONSULTADO,
    "1": SITUACAO_RASCUNHO,
    "2": SITUACAO_AGUARDANDO_ANALISE,
    "3": SITUACAO_EM_ANALISE,
    "4": SITUACAO_ATIVO,  # deferido / deferida em alguns enums
    "5": SITUACAO_FINALIZADA,
    "6": SITUACAO_AGUARDANDO_ANALISE,
    "7": SITUACAO_EM_ANALISE,
}


def new_id() -> str:
    return uuid.uuid4().hex[:12]


def now_stamp() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def normalize_situacao(raw: Any) -> str:
    if raw is None:
        return SITUACAO_NAO_CONSULTADO
    if isinstance(raw, bool):
        return SITUACAO_NAO_CONSULTADO
    if isinstance(raw, (int, float)) and not isinstance(raw, bool):
        key = str(int(raw))
        if key in _SITUACAO_NUMERIC:
            return _SITUACAO_NUMERIC[key]
        raw = str(int(raw))
    text = " ".join(str(raw or "").strip().split())
    if not text:
        return SITUACAO_NAO_CONSULTADO
    if text.isdigit() and text in _SITUACAO_NUMERIC:
        return _SITUACAO_NUMERIC[text]
    key = text.lower()
    if key in _SITUACAO_ALIASES:
        return _SITUACAO_ALIASES[key]
    for alias, label in _SITUACAO_ALIASES.items():
        if alias and alias in key:
            return label
    return text


def flatten_mpa_payload(data: Dict[str, Any] | None) -> Dict[str, Any]:
    """Normaliza envelope da API MPA (objeto plano, content[], data{}, etc.)."""
    if not isinstance(data, dict):
        return {}
    out = dict(data)
    if out.get("sem_registros") or out.get("not_found"):
        out.setdefault("situacao", SITUACAO_NAO_ENCONTRADO)
        return out
    for key in ("resultado", "content", "data", "items", "registros", "resultados"):
        val = out.get(key)
        if isinstance(val, list):
            if len(val) == 0:
                out["sem_registros"] = True
                out["situacao"] = SITUACAO_NAO_ENCONTRADO
                return out
            if isinstance(val[0], dict):
                merged = {**out, **val[0]}
                return merged
        if isinstance(val, dict):
            return {**out, **val}
    return out


def extract_situacao_from_mpa(data: Dict[str, Any] | None) -> str:
    """Extrai situação RGP de formatos variados da API pública MPA."""
    if not isinstance(data, dict):
        return SITUACAO_NAO_CONSULTADO
    flat = flatten_mpa_payload(data)
    if flat.get("sem_registros") or flat.get("not_found"):
        return SITUACAO_NAO_ENCONTRADO
    candidates = [
        flat.get("situacao"),
        flat.get("situacaoRgp"),
        flat.get("situacao_rgp"),
        flat.get("situacaoRGP"),
        flat.get("status"),
        flat.get("label"),
    ]
    pescador = flat.get("pescador")
    if isinstance(pescador, dict):
        candidates.extend(
            [
                pescador.get("situacao"),
                pescador.get("situacaoRgp"),
                pescador.get("status"),
            ]
        )
    for raw in candidates:
        if raw is None or raw == "":
            continue
        sit = normalize_situacao(raw)
        if sit and sit != SITUACAO_NAO_CONSULTADO:
            return sit
        if sit == SITUACAO_NAO_CONSULTADO and str(raw).strip() not in ("", "0", "Nenhum"):
            return sit
    return SITUACAO_NAO_CONSULTADO


def situacao_apta_import(situacao: str) -> bool:
    return normalize_situacao(situacao).lower() in SITUACOES_APTAS_IMPORT


def situacao_badge_class(situacao: str) -> str:
    s = normalize_situacao(situacao)
    if s == SITUACAO_ATIVO:
        return "rgp-badge-ativo"
    if s in (SITUACAO_AGUARDANDO_ANALISE, SITUACAO_EM_ANALISE):
        return "rgp-badge-analise"
    if s in (SITUACAO_PEND_REG, SITUACAO_AGUARDANDO_ATUALIZACAO, SITUACAO_RASCUNHO):
        return "rgp-badge-pend"
    if s in (SITUACAO_SUSPENSO, SITUACAO_CANCELADO, SITUACAO_INATIVO):
        return "rgp-badge-inativo"
    if s == SITUACAO_FINALIZADA:
        return "rgp-badge-final"
    return "rgp-badge-neutro"


@dataclass
class RegistroConsultaRgp:
    id: str = ""
    person_id: str = ""
    nome: str = ""
    cpf: str = ""
    telefone: str = ""
    municipio: str = ""
    uf: str = ""
    situacao_rgp: str = SITUACAO_NAO_CONSULTADO
    observacao: str = ""
    ultima_consulta_em: str = ""
    codigo_rgp: str = ""
    categoria: str = ""
    email: str = ""
    importado_reap_em: str = ""
    importado_defeso_em: str = ""
    cadastro_reap_em: str = ""
    atualizado_em: str = ""
    criado_em: str = ""
    timeline: str = ""  # linhas "data|ator|evento" separadas por \n

    def to_row(self) -> List[str]:
        return [
            self.id,
            self.person_id,
            self.nome,
            normalize_cpf(self.cpf) or self.cpf,
            self.telefone,
            self.municipio,
            self.uf,
            self.situacao_rgp,
            self.observacao,
            self.ultima_consulta_em,
            self.codigo_rgp,
            self.categoria,
            self.email,
            self.importado_reap_em,
            self.importado_defeso_em,
            self.cadastro_reap_em,
            self.atualizado_em,
            self.criado_em,
            self.timeline,
        ]

    def timeline_items(self) -> List[Dict[str, str]]:
        items: List[Dict[str, str]] = []
        for line in (self.timeline or "").split("\n"):
            line = line.strip()
            if not line:
                continue
            parts = line.split("|", 2)
            if len(parts) < 3:
                continue
            items.append({"em": parts[0], "ator": parts[1], "evento": parts[2]})
        return items

    def append_timeline(self, evento: str, *, ator: str = "Sistema") -> None:
        stamp = now_stamp()
        line = f"{stamp}|{ator}|{evento}"
        if self.timeline.strip():
            self.timeline = line + "\n" + self.timeline.strip()
        else:
            self.timeline = line

    def to_dict(self) -> Dict[str, Any]:
        d = asdict(self)
        d["nome_display"] = display_nome(self.nome)
        d["cpf"] = normalize_cpf(self.cpf) or self.cpf
        d["cpf_formatado"] = format_cpf(self.cpf)
        d["situacao_rgp"] = normalize_situacao(self.situacao_rgp)
        d["badge_class"] = situacao_badge_class(self.situacao_rgp)
        d["apta_import"] = situacao_apta_import(self.situacao_rgp)
        d["timeline_items"] = self.timeline_items()
        d["iniciais"] = _iniciais(self.nome)
        return d


def _iniciais(nome: str) -> str:
    parts = [p for p in display_nome(nome).split() if p]
    if not parts:
        return "?"
    if len(parts) == 1:
        return parts[0][:2].upper()
    return (parts[0][0] + parts[-1][0]).upper()


def row_to_registro(row: Sequence[Any] | None) -> Optional[RegistroConsultaRgp]:
    if not row or not str(row[0]).strip():
        return None
    cells = [str(c) if c is not None else "" for c in row]
    while len(cells) < len(CONSULTA_RGP_HEADER):
        cells.append("")
    return RegistroConsultaRgp(
        id=cells[0].strip(),
        person_id=cells[1].strip(),
        nome=cells[2].strip(),
        cpf=normalize_cpf(cells[3]),
        telefone=cells[4].strip(),
        municipio=cells[5].strip(),
        uf=cells[6].strip().upper()[:2],
        situacao_rgp=normalize_situacao(cells[7]),
        observacao=cells[8].strip(),
        ultima_consulta_em=cells[9].strip(),
        codigo_rgp=cells[10].strip(),
        categoria=cells[11].strip(),
        email=cells[12].strip(),
        importado_reap_em=cells[13].strip(),
        importado_defeso_em=cells[14].strip(),
        cadastro_reap_em=cells[15].strip(),
        atualizado_em=cells[16].strip(),
        criado_em=cells[17].strip(),
        timeline=cells[18].strip() if len(cells) > 18 else "",
    )


def payload_to_registro(
    payload: Dict[str, Any], *, existing: Optional[RegistroConsultaRgp] = None
) -> RegistroConsultaRgp:
    base = existing or RegistroConsultaRgp()
    agora = now_stamp()
    nome = format_nome(str(payload.get("nome") or base.nome or ""))
    cpf = normalize_cpf(payload.get("cpf") or base.cpf or "")
    situacao = normalize_situacao(str(payload.get("situacao_rgp") or base.situacao_rgp or ""))
    reg = RegistroConsultaRgp(
        id=(str(payload.get("id") or base.id or "").strip() or new_id()),
        person_id=str(payload.get("person_id") or base.person_id or "").strip(),
        nome=nome,
        cpf=cpf,
        telefone=str(payload.get("telefone") or base.telefone or "").strip(),
        municipio=str(payload.get("municipio") or base.municipio or "").strip(),
        uf=str(payload.get("uf") or base.uf or "").strip().upper()[:2],
        situacao_rgp=situacao,
        observacao=str(payload.get("observacao") if "observacao" in payload else base.observacao or "").strip(),
        ultima_consulta_em=str(
            payload.get("ultima_consulta_em") or base.ultima_consulta_em or ""
        ).strip(),
        codigo_rgp=str(payload.get("codigo_rgp") or base.codigo_rgp or "").strip(),
        categoria=str(payload.get("categoria") or base.categoria or "").strip(),
        email=str(payload.get("email") or base.email or "").strip(),
        importado_reap_em=str(payload.get("importado_reap_em") or base.importado_reap_em or "").strip(),
        importado_defeso_em=str(
            payload.get("importado_defeso_em") or base.importado_defeso_em or ""
        ).strip(),
        cadastro_reap_em=str(payload.get("cadastro_reap_em") or base.cadastro_reap_em or "").strip(),
        atualizado_em=agora,
        criado_em=base.criado_em or agora,
        timeline=str(payload.get("timeline") or base.timeline or "").strip(),
    )
    return reg


def resumo_kpis(registros: List[RegistroConsultaRgp]) -> Dict[str, Any]:
    total = len(registros)
    ativos = 0
    analise = 0
    pendentes = 0
    for r in registros:
        s = normalize_situacao(r.situacao_rgp)
        if s == SITUACAO_ATIVO:
            ativos += 1
        elif s in (SITUACAO_AGUARDANDO_ANALISE, SITUACAO_EM_ANALISE):
            analise += 1
        elif s in (
            SITUACAO_PEND_REG,
            SITUACAO_AGUARDANDO_ATUALIZACAO,
            SITUACAO_RASCUNHO,
            SITUACAO_SUSPENSO,
            SITUACAO_CANCELADO,
            SITUACAO_INATIVO,
        ):
            pendentes += 1
    def pct(n: int) -> float:
        return round((100.0 * n / total), 1) if total else 0.0

    return {
        "total": total,
        "ativos": ativos,
        "ativos_pct": pct(ativos),
        "aguardando_analise": analise,
        "aguardando_analise_pct": pct(analise),
        "pendentes": pendentes,
        "pendentes_pct": pct(pendentes),
    }


def aplicar_resultado_mpa(
    reg: RegistroConsultaRgp,
    data: Dict[str, Any],
    *,
    ator: str = "Sistema",
) -> RegistroConsultaRgp:
    """Atualiza registro com payload JSON da API pública MPA."""
    flat = flatten_mpa_payload(data if isinstance(data, dict) else {})
    situacao = extract_situacao_from_mpa(flat)
    nome_api = " ".join(
        p
        for p in (
            str(flat.get("nome") or "").strip(),
            str(flat.get("sobrenome") or "").strip(),
        )
        if p
    )
    if nome_api and (not reg.nome or reg.nome.lower() == "sem nome"):
        reg.nome = format_nome(nome_api)
    elif nome_api and len(nome_api) > len(reg.nome or ""):
        reg.nome = format_nome(nome_api)

    if flat.get("cpf"):
        reg.cpf = normalize_cpf(flat.get("cpf")) or only_digits(str(flat.get("cpf")))
    tel = flat.get("telefone") or flat.get("celular") or flat.get("fone")
    if tel:
        reg.telefone = str(tel).strip() or reg.telefone
    mun = flat.get("municipio") or flat.get("municipioPescador")
    if mun:
        reg.municipio = str(mun).strip() or reg.municipio
    uf = flat.get("uf") or flat.get("ufPescador")
    if uf:
        reg.uf = str(uf).strip().upper()[:2] or reg.uf
    if flat.get("codigoRGP") or flat.get("codigo_rgp") or flat.get("rgp"):
        reg.codigo_rgp = str(
            flat.get("codigoRGP") or flat.get("codigo_rgp") or flat.get("rgp") or ""
        ).strip()
    if flat.get("categoria"):
        reg.categoria = str(flat.get("categoria") or "").strip()
    if flat.get("email"):
        reg.email = str(flat.get("email") or "").strip() or reg.email

    old = normalize_situacao(reg.situacao_rgp)
    if situacao and situacao != SITUACAO_NAO_CONSULTADO:
        reg.situacao_rgp = situacao
    elif not reg.situacao_rgp:
        reg.situacao_rgp = SITUACAO_NAO_CONSULTADO
    reg.ultima_consulta_em = now_stamp()
    reg.atualizado_em = reg.ultima_consulta_em
    reg.append_timeline(f"Consulta realizada → {reg.situacao_rgp}", ator=ator)
    if old != reg.situacao_rgp and old != SITUACAO_NAO_CONSULTADO:
        reg.append_timeline(f"Situação: {old} → {reg.situacao_rgp}", ator=ator)
    return reg
