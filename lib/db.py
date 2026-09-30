import uuid
from datetime import datetime

import asyncpg

from config import settings

_pool: asyncpg.Pool | None = None


async def get_pool() -> asyncpg.Pool:
    global _pool
    if _pool is None:
        _pool = await asyncpg.create_pool(
            dsn=settings.database_url,
            min_size=2,
            max_size=20,
            command_timeout=60,
            statement_cache_size=0,  # compatível com PgBouncer em transaction mode
        )
    return _pool


async def fechar_pool() -> None:
    global _pool
    if _pool is not None:
        await _pool.close()
        _pool = None


async def buscar_volumes_bd(
    pool: asyncpg.Pool, transportadora_id: int
) -> dict[str, dict]:
    """Retorna dict keyed by cod_transportadora com volumes dos últimos 60 dias."""
    rows = await pool.fetch(
        """
        SELECT doc_interno, cod_transportadora, status, data_vencimento,
               atencao, resolvido, observacao_interna
        FROM volumes
        WHERE transportadora_id = $1
          AND data_insercao >= NOW() - INTERVAL '60 days'
        """,
        transportadora_id,
    )
    return {r["cod_transportadora"]: dict(r) for r in rows}


async def buscar_cidade_id(pool: asyncpg.Pool, nome: str) -> int | None:
    row = await pool.fetchrow(
        "SELECT id FROM cidades WHERE LOWER(nome) = LOWER($1)", nome
    )
    return row["id"] if row else None


async def buscar_ou_criar_cidade_id(pool: asyncpg.Pool, nome: str) -> int:
    """Retorna id da cidade, criando-a se não existir."""
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            "SELECT id FROM cidades WHERE LOWER(nome) = LOWER($1)", nome
        )
        if row:
            return row["id"]
        novo = await conn.fetchrow(
            "INSERT INTO cidades (nome) VALUES ($1) RETURNING id", nome
        )
        return novo["id"]


async def inserir_log_execucao(
    pool: asyncpg.Pool,
    *,
    workflow_name: str,
    started_at: datetime,
    finished_at: datetime,
    volumes_lidos: int,
    status: str,
    status_message: str | None = None,
    contadores: dict[str, int],
) -> str:
    execucao_id = str(uuid.uuid4())
    execution_ms = int((finished_at - started_at).total_seconds() * 1000)

    async with pool.acquire() as conn:
        async with conn.transaction():
            await conn.execute(
                """
                INSERT INTO log_execucoes
                    (id, workflow_name, started_at, finished_at,
                     execution_ms, volumes_lidos, status, status_message)
                VALUES ($1, $2, $3, $4, $5, $6, $7, $8)
                """,
                execucao_id,
                workflow_name,
                started_at,
                finished_at,
                execution_ms,
                volumes_lidos,
                status,
                status_message,
            )
            for caso, quantidade in contadores.items():
                await conn.execute(
                    """
                    INSERT INTO log_execucoes_detalhes (id, execucao_id, caso, quantidade)
                    VALUES ($1, $2, $3, $4)
                    """,
                    str(uuid.uuid4()),
                    execucao_id,
                    caso,
                    quantidade,
                )

    return execucao_id
