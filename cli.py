"""CLI para execução manual das transportadoras.

Uso:
    python cli.py run transportadora_a
    python cli.py run transportadora_a --dry-run
"""

import argparse
import asyncio

from lib.db import fechar_pool
from lib.runner import executar_transportadora, _TRANSPORTADORAS


async def _run(nome: str, dry_run: bool) -> None:
    try:
        await executar_transportadora(nome, dry_run=dry_run)
    finally:
        await fechar_pool()


def main() -> None:
    parser = argparse.ArgumentParser(description="logistics-sync CLI")
    sub = parser.add_subparsers(dest="cmd", required=True)

    run_p = sub.add_parser("run", help="Executa uma transportadora")
    run_p.add_argument("transportadora", choices=list(_TRANSPORTADORAS))
    run_p.add_argument(
        "--dry-run",
        action="store_true",
        help="Busca e processa dados mas não persiste no banco nem notifica",
    )

    args = parser.parse_args()

    if args.cmd == "run":
        asyncio.run(_run(args.transportadora, args.dry_run))


if __name__ == "__main__":
    main()
