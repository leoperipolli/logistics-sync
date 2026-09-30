"""Entry point do scheduler logistics-sync.

Dispara cada transportadora nos horários configurados (Mon-Sat, America/Sao_Paulo).
Shutdown gracioso via SIGINT/SIGTERM.
"""

import asyncio
import signal

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger

from lib.db import fechar_pool, get_pool
from lib.logger import logger
from lib.runner import executar_transportadora

# Mon-Sat, America/Sao_Paulo — mesmos horários dos antigos workflows n8n
AGENDAMENTOS = [
    ("transportadora_a", [(7,  4), (14,  4), (20, 34)]),
    ("transportadora_b", [(7,  2), (14,  2), (20, 32)]),
    ("transportadora_c", [(7, 10), (14, 10), (22, 36)]),
    ("transportadora_d", [(7,  0), (14,  0), (22, 30)]),
    ("transportadora_e", [(7,  8), (14,  8), (22, 34)]),
]


async def main() -> None:
    await get_pool()

    scheduler = AsyncIOScheduler(timezone="America/Sao_Paulo")

    for nome, horarios in AGENDAMENTOS:
        for hora, minuto in horarios:
            scheduler.add_job(
                executar_transportadora,
                CronTrigger(
                    day_of_week="mon-sat",
                    hour=hora,
                    minute=minuto,
                    timezone="America/Sao_Paulo",
                ),
                args=[nome],
                id=f"{nome}_{hora:02d}{minuto:02d}",
                misfire_grace_time=300,
                coalesce=True,
                max_instances=1,
            )

    scheduler.start()
    logger.info("scheduler_iniciado", jobs=len(scheduler.get_jobs()))

    stop = asyncio.Event()
    loop = asyncio.get_running_loop()
    for sig in (signal.SIGINT, signal.SIGTERM):
        loop.add_signal_handler(sig, stop.set)

    await stop.wait()

    logger.info("scheduler_encerrando")
    scheduler.shutdown(wait=True)
    await fechar_pool()


if __name__ == "__main__":
    asyncio.run(main())
