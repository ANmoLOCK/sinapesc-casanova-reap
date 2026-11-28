"""Conexão HTTP do Google por thread.

O httplib2 não pode ser usado por duas threads ao mesmo tempo: o socket SSL
compartilhado corrompe e o processo fecha sem aviso. Cada thread do programa
(chamadas do pywebview, tarefas em segundo plano) ganha a sua própria conexão,
com tempo limite para não travar a tela.
"""

from __future__ import annotations

import threading
from typing import Any

TIMEOUT_SEGUNDOS = 90

_local = threading.local()
_instalado = False
_instalar_lock = threading.Lock()


def _http_da_thread(http_original: Any) -> Any:
    credenciais = getattr(http_original, "credentials", None)
    if credenciais is None:
        return http_original
    import httplib2
    from google_auth_httplib2 import AuthorizedHttp

    cache = getattr(_local, "por_credencial", None)
    if cache is None:
        cache = {}
        _local.por_credencial = cache
    chave = id(credenciais)
    http = cache.get(chave)
    if http is None:
        http = AuthorizedHttp(credenciais, http=httplib2.Http(timeout=TIMEOUT_SEGUNDOS))
        cache[chave] = http
    return http


def instalar() -> None:
    """Faz todo ``execute()`` / ``next_chunk()`` usar a conexão da thread atual."""
    global _instalado
    with _instalar_lock:
        if _instalado:
            return
        from googleapiclient.http import HttpRequest

        execute_original = HttpRequest.execute
        next_chunk_original = HttpRequest.next_chunk

        def execute(self, http=None, num_retries=0):  # type: ignore[no-untyped-def]
            if http is None:
                http = _http_da_thread(self.http)
            return execute_original(self, http=http, num_retries=num_retries)

        def next_chunk(self, http=None, num_retries=0):  # type: ignore[no-untyped-def]
            if http is None:
                http = _http_da_thread(self.http)
            return next_chunk_original(self, http=http, num_retries=num_retries)

        HttpRequest.execute = execute  # type: ignore[assignment]
        HttpRequest.next_chunk = next_chunk  # type: ignore[assignment]
        _instalado = True
