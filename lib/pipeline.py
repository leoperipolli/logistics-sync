import asyncio
from collections.abc import Coroutine
from typing import Any

from lib.logger import logger


async def processar_linha_segura(
    coro: Coroutine,
    chave: str,
) -> str:
    """Executa a coroutine do handler e retorna a chave. Loga erros sem propagar."""
    try:
        await coro
        return chave
    except Exception as exc:
        logger.error("erro_linha", chave=chave, erro=str(exc))
        return "erro"


async def processar_linhas(
    tarefas: list[tuple[Coroutine, str]],
    max_paralelo: int = 20,
) -> dict[str, int]:
    """
    Processa todas as tarefas em paralelo limitado por semáforo.

    tarefas: lista de (coroutine_do_handler, chave)
    Retorna contadores por chave (incluindo 'erro' para falhas).
    """
    semaforo = asyncio.Semaphore(max_paralelo)

    async def com_semaforo(coro: Coroutine, chave: str) -> str:
        async with semaforo:
            return await processar_linha_segura(coro, chave)

    coroutines = [com_semaforo(coro, chave) for coro, chave in tarefas]
    resultados: list[str | BaseException] = await asyncio.gather(
        *coroutines, return_exceptions=True
    )

    contadores: dict[str, int] = {}
    for r in resultados:
        chave = r if isinstance(r, str) else "erro"
        contadores[chave] = contadores.get(chave, 0) + 1

    return contadores
