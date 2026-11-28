"""
Pacote de integração com o Google Sheets (planilha).

Como usar (visão geral didática):
1. Configure as credenciais em Configurações do programa (ou arquivo config.json).
2. O módulo `client` autentica com uma Conta de Serviço do Google.
3. O módulo `service` lê/grava as abas "Pessoas", "Reap", "Auditoria" e "Config".
"""

from .http_seguro import instalar as _instalar_http_seguro

_instalar_http_seguro()

from .models import MESES, MESES_LABEL, MesKey, Pessoa, PessoaComReap, ReapAno  # noqa: E402
from .service import SheetsService, SheetsConfigError  # noqa: E402

__all__ = [
    "MESES",
    "MESES_LABEL",
    "MesKey",
    "Pessoa",
    "PessoaComReap",
    "ReapAno",
    "SheetsService",
    "SheetsConfigError",
]
