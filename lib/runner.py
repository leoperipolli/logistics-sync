"""Lógica compartilhada de execução de transportadora (usada por CLI e scheduler)."""

import traceback
import uuid
from datetime import datetime, timezone

import asyncpg

from lib.db import get_pool, inserir_log_execucao
from lib.logger import logger, set_correlation_id
from lib.notificar import notificar_erro, notificar_sucesso

_TRANSPORTADORAS = {
    "transportadora_a": lambda: _importar("transportadoras.transportadora_a", "TransportadoraA"),
    "transportadora_b": lambda: _importar("transportadoras.transportadora_b", "TransportadoraB"),
    "transportadora_c": lambda: _importar("transportadoras.transportadora_c", "TransportadoraC"),
    "transportadora_d": lambda: _importar("transportadoras.transportadora_d", "TransportadoraD"),
    "transportadora_e": lambda: _importar("transportadoras.transportadora_e", "TransportadoraE"),
}


def _importar(modulo: str, classe: str):
    import importlib
    mod = importlib.import_module(modulo)
    return getattr(mod, classe)()


async def executar_transportadora(
    nome: str,
    pool: asyncpg.Pool | None = None,
    dry_run: bool = False,
) -> None:
    """Executa uma transportadora com log, notificação e registro no banco.

    Se `pool` for None, obtém o pool global (modo scheduler, pool compartilhado).
    O pool NÃO é fechado aqui — responsabilidade de quem chama.
    """
    cid = str(uuid.uuid4())[:8]
    set_correlation_id(cid)

    if nome not in _TRANSPORTADORAS:
        raise ValueError(f"Transportadora desconhecida: {nome!r}. Opções: {list(_TRANSPORTADORAS)}")

    transportadora = _TRANSPORTADORAS[nome]()
    logger.info("execucao_iniciada", transportadora=nome, dry_run=dry_run)

    if pool is None:
        pool = await get_pool()

    started_at = datetime.now(timezone.utc)
    status_final = "sucesso"
    status_msg = None
    resultado = None

    try:
        resultado = await transportadora.executar(pool)
        logger.info(
            "execucao_concluida",
            transportadora=nome,
            volumes_lidos=resultado.volumes_lidos,
            contadores=resultado.contadores,
        )
        if not dry_run:
            await notificar_sucesso(
                nome,
                resultado.volumes_lidos,
                resultado.contadores,
                int((datetime.now(timezone.utc) - started_at).total_seconds() * 1000),
            )
    except Exception as exc:
        status_final = "erro"
        status_msg = str(exc)
        logger.error("execucao_falhou", transportadora=nome, erro=status_msg)
        logger.debug("traceback", detalhe=traceback.format_exc())
        if not dry_run:
            await notificar_erro(nome, status_msg)
    finally:
        finished_at = datetime.now(timezone.utc)
        if not dry_run:
            try:
                await inserir_log_execucao(
                    pool,
                    workflow_name=transportadora.workflow_name,
                    started_at=started_at,
                    finished_at=finished_at,
                    volumes_lidos=resultado.volumes_lidos if resultado else 0,
                    status=status_final,
                    status_message=status_msg,
                    contadores=resultado.contadores if resultado else {},
                )
            except Exception as log_exc:
                logger.warning("falha_log_execucao", erro=str(log_exc))
