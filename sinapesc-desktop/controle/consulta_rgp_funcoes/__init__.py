"""Funções extras da Consulta RGP — pacote organizado (não misturar no core).

Módulos:
  - vencidos.py         → atalho «Reconsultar vencidos»
  - exportar.py         → export CSV / HTML (imprimir PDF)
  - alertas.py          → alerta Ativo → Suspenso/Cancelado
  - fila_inteligente.py → fila com pausa após falhas seguidas + CSV de erros
"""

from __future__ import annotations

from controle.consulta_rgp_funcoes.alertas import (
    SITUACOES_ALERTA_NEGATIVA,
    detectar_alerta_situacao,
    formatar_alerta,
)
from controle.consulta_rgp_funcoes.exportar import (
    exportar_consulta_rgp,
    filtrar_registros_export,
)
from controle.consulta_rgp_funcoes.fila_inteligente import (
    ResultadoFila,
    exportar_erros_csv,
    rodar_fila_inteligente,
)
from controle.consulta_rgp_funcoes.vencidos import (
    DIAS_PADRAO_VENCIDOS,
    ids_vencidos,
    listar_vencidos,
)

__all__ = [
    "DIAS_PADRAO_VENCIDOS",
    "SITUACOES_ALERTA_NEGATIVA",
    "ResultadoFila",
    "detectar_alerta_situacao",
    "exportar_consulta_rgp",
    "exportar_erros_csv",
    "filtrar_registros_export",
    "formatar_alerta",
    "ids_vencidos",
    "listar_vencidos",
    "rodar_fila_inteligente",
]
