"""Funções extras da Consulta RGP — pacote organizado (não misturar no core).

Módulos:
  - vencidos.py         → atalho «Reconsultar vencidos»
  - exportar.py         → export CSV / HTML (imprimir PDF) + relatório geral
  - alertas.py          → alerta Ativo → Suspenso/Cancelado
  - fila_inteligente.py → fila com pausa após falhas seguidas + CSV de erros
  - importar_arquivo.py → parse PDF / XLS / TXT para lote (anti-cota)
  - editar_lote.py      → correção em lote (nome/CPF/tel/mun/obs)
  - excluir.py          → exclusão de sócio(s)
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
from controle.consulta_rgp_funcoes.editar_lote import normalizar_itens_edicao
from controle.consulta_rgp_funcoes.excluir import ids_para_excluir, resumo_exclusao
from controle.consulta_rgp_funcoes.importar_arquivo import (
    itens_para_dicts,
    parse_arquivo_lote,
    parse_texto_lote,
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
    "ids_para_excluir",
    "ids_vencidos",
    "itens_para_dicts",
    "listar_vencidos",
    "normalizar_itens_edicao",
    "parse_arquivo_lote",
    "parse_texto_lote",
    "resumo_exclusao",
    "rodar_fila_inteligente",
]
