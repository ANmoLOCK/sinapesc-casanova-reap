"""Usuários online (aba Usuarios) — login, papéis e senha PBKDF2."""

from __future__ import annotations

import base64
import hashlib
import hmac
import secrets
import uuid
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple

USUARIOS_TAB = "Usuarios"
USUARIOS_HEADER = [
    "id",
    "email",
    "nome",
    "senhaHash",
    "ativo",
    "papel",
    "modulos",
    "criadoEm",
    "ultimoLogin",
    "atualizadoEm",
]

PAPEIS = ("admin", "operador", "leitura")
PAPEL_ADMIN = "admin"
PAPEL_OPERADOR = "operador"
PAPEL_LEITURA = "leitura"

MODULOS_TODOS = ("reap", "defeso", "informe", "consulta_rgp", "lista")
PBKDF2_ROUNDS = 200_000
PBKDF2_PREFIX = "pbkdf2_sha256"


def now_stamp() -> str:
    return datetime.now().astimezone().strftime("%Y-%m-%d %H:%M:%S")


def normalizar_email(valor: Any) -> str:
    return str(valor or "").strip().lower()


def normalizar_papel(valor: Any) -> str:
    p = str(valor or "").strip().lower()
    if p in ("administrador", "adm"):
        return PAPEL_ADMIN
    if p in ("operadora", "secretaria", "user", "usuario"):
        return PAPEL_OPERADOR
    if p in ("somente_leitura", "read", "viewer", "consulta"):
        return PAPEL_LEITURA
    if p in PAPEIS:
        return p
    return PAPEL_OPERADOR


def normalizar_ativo(valor: Any) -> bool:
    s = str(valor or "").strip().lower()
    return s in ("sim", "true", "1", "yes", "ativo", "on")


def ativo_para_celula(ativo: bool) -> str:
    return "sim" if ativo else "nao"


def normalizar_modulos(raw: Any = None) -> List[str]:
    """Vazio = todos os módulos. Ordem canônica."""
    if raw is None or raw == "" or raw == []:
        return []
    if isinstance(raw, str):
        partes = [p.strip().lower() for p in raw.replace(";", ",").split(",") if p.strip()]
    elif isinstance(raw, (list, tuple, set)):
        partes = [str(p).strip().lower() for p in raw if str(p).strip()]
    else:
        return []
    out: List[str] = []
    for m in MODULOS_TODOS:
        if m in partes and m not in out:
            out.append(m)
    # aliases
    for p in partes:
        if p in ("rgp", "consulta") and "consulta_rgp" not in out:
            out.append("consulta_rgp")
        if p == "informe_mensal" and "informe" not in out:
            out.append("informe")
    return out


def modulos_para_celula(modulos: Sequence[str]) -> str:
    return ",".join(normalizar_modulos(modulos))


def hash_senha(senha: str) -> str:
    """PBKDF2-SHA256 com salt aleatório (nativo, sem dependência)."""
    plain = str(senha or "")
    if not plain:
        raise ValueError("Senha vazia.")
    salt = secrets.token_bytes(16)
    dk = hashlib.pbkdf2_hmac("sha256", plain.encode("utf-8"), salt, PBKDF2_ROUNDS)
    return (
        f"{PBKDF2_PREFIX}${PBKDF2_ROUNDS}$"
        f"{base64.b64encode(salt).decode('ascii')}$"
        f"{base64.b64encode(dk).decode('ascii')}"
    )


def verificar_senha(senha: str, stored: str) -> bool:
    raw = str(stored or "").strip()
    plain = str(senha or "")
    if not raw or not plain:
        return False
    # legado: senha em texto puro (só bootstrap / migração)
    if not raw.startswith(PBKDF2_PREFIX + "$"):
        return hmac.compare_digest(plain, raw)
    try:
        _pref, rounds_s, salt_b64, hash_b64 = raw.split("$", 3)
        rounds = int(rounds_s)
        salt = base64.b64decode(salt_b64.encode("ascii"))
        expected = base64.b64decode(hash_b64.encode("ascii"))
    except (ValueError, TypeError):
        return False
    got = hashlib.pbkdf2_hmac("sha256", plain.encode("utf-8"), salt, rounds)
    return hmac.compare_digest(got, expected)


def senha_precisa_rehash(stored: str) -> bool:
    return not str(stored or "").strip().startswith(PBKDF2_PREFIX + "$")


@dataclass
class Usuario:
    id: str
    email: str
    nome: str
    senha_hash: str
    ativo: bool = True
    papel: str = PAPEL_OPERADOR
    modulos: List[str] = field(default_factory=list)
    criado_em: str = ""
    ultimo_login: str = ""
    atualizado_em: str = ""

    def __post_init__(self) -> None:
        self.email = normalizar_email(self.email)
        self.nome = str(self.nome or "").strip() or self.email
        self.papel = normalizar_papel(self.papel)
        self.modulos = normalizar_modulos(self.modulos)
        self.ativo = bool(self.ativo)

    @property
    def pode_admin_usuarios(self) -> bool:
        return self.papel == PAPEL_ADMIN and self.ativo

    @property
    def pode_escrever(self) -> bool:
        return self.ativo and self.papel in (PAPEL_ADMIN, PAPEL_OPERADOR)

    def permite_modulo(self, modulo: str) -> bool:
        if not self.ativo:
            return False
        if self.papel == PAPEL_ADMIN:
            return True
        mods = self.modulos
        if not mods:
            return True
        m = str(modulo or "").strip().lower()
        if m == "informe_mensal":
            m = "informe"
        return m in mods

    def to_row(self) -> List[str]:
        return [
            self.id,
            self.email,
            self.nome,
            self.senha_hash,
            ativo_para_celula(self.ativo),
            self.papel,
            modulos_para_celula(self.modulos),
            self.criado_em,
            self.ultimo_login,
            self.atualizado_em,
        ]

    def to_public_dict(self) -> Dict[str, Any]:
        """Sem hash — para UI."""
        return {
            "id": self.id,
            "email": self.email,
            "nome": self.nome,
            "ativo": self.ativo,
            "papel": self.papel,
            "modulos": list(self.modulos),
            "modulos_texto": modulos_para_celula(self.modulos) or "(todos)",
            "criado_em": self.criado_em,
            "ultimo_login": self.ultimo_login,
            "atualizado_em": self.atualizado_em,
            "pode_escrever": self.pode_escrever,
            "pode_admin_usuarios": self.pode_admin_usuarios,
        }

    def sessao_dict(self) -> Dict[str, Any]:
        d = self.to_public_dict()
        d["admin_user"] = self.email
        return d


def row_to_usuario(row: Sequence[Any] | None) -> Optional[Usuario]:
    if not row:
        return None
    cells = [str(c) if c is not None else "" for c in row]
    while len(cells) < len(USUARIOS_HEADER):
        cells.append("")
    uid = cells[0].strip()
    email = normalizar_email(cells[1])
    if not uid or uid.lower() == "id" or not email:
        return None
    return Usuario(
        id=uid,
        email=email,
        nome=cells[2].strip(),
        senha_hash=cells[3].strip(),
        ativo=normalizar_ativo(cells[4]),
        papel=normalizar_papel(cells[5]),
        modulos=normalizar_modulos(cells[6]),
        criado_em=cells[7].strip(),
        ultimo_login=cells[8].strip(),
        atualizado_em=cells[9].strip(),
    )


def novo_usuario(
    *,
    email: str,
    senha: str,
    nome: str = "",
    papel: str = PAPEL_OPERADOR,
    ativo: bool = True,
    modulos: Any = None,
) -> Usuario:
    agora = now_stamp()
    return Usuario(
        id=str(uuid.uuid4()),
        email=normalizar_email(email),
        nome=(nome or "").strip() or normalizar_email(email),
        senha_hash=hash_senha(senha),
        ativo=ativo,
        papel=papel,
        modulos=normalizar_modulos(modulos),
        criado_em=agora,
        ultimo_login="",
        atualizado_em=agora,
    )


def validar_senha_nova(senha: Any) -> List[str]:
    s = str(senha or "")
    erros: List[str] = []
    if len(s) < 6:
        erros.append("Senha deve ter pelo menos 6 caracteres.")
    return erros


def validar_payload_usuario(
    payload: Dict[str, Any],
    *,
    exige_senha: bool = False,
    emails_ocupados: Optional[Iterable[str]] = None,
    email_atual: str = "",
) -> List[str]:
    erros: List[str] = []
    email = normalizar_email(payload.get("email"))
    if not email or "@" not in email:
        erros.append("E-mail inválido.")
    ocupados = {normalizar_email(e) for e in (emails_ocupados or [])}
    if email and email in ocupados and email != normalizar_email(email_atual):
        erros.append("Já existe usuário com este e-mail.")
    if "papel" in payload or exige_senha:
        papel = normalizar_papel(payload.get("papel"))
        if papel not in PAPEIS:
            erros.append("Papel inválido (use admin, operador ou leitura).")
    if exige_senha or payload.get("senha"):
        erros.extend(validar_senha_nova(payload.get("senha")))
    return erros


def autenticar(
    usuarios: Sequence[Usuario],
    email: str,
    senha: str,
) -> Tuple[Optional[Usuario], str]:
    """Retorna (usuario, erro). erro vazio = ok."""
    alvo = normalizar_email(email)
    if not alvo or not str(senha or ""):
        return None, "E-mail ou senha incorretos."
    hit = next((u for u in usuarios if u.email == alvo), None)
    if hit is None:
        return None, "E-mail ou senha incorretos."
    if not verificar_senha(senha, hit.senha_hash):
        return None, "E-mail ou senha incorretos."
    if not hit.ativo:
        return None, "Acesso bloqueado. Fale com a secretaria."
    return hit, ""
