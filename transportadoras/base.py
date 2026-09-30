from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any

import asyncpg


@dataclass
class ResultadoExecucao:
    volumes_lidos: int = 0
    contadores: dict[str, int] = field(default_factory=dict)
    status: str = "sucesso"
    status_message: str | None = None

    @property
    def total_processado(self) -> int:
        return sum(v for k, v in self.contadores.items() if k != "erro")

    @property
    def total_erro(self) -> int:
        return self.contadores.get("erro", 0)


class Transportadora(ABC):
    nome: str
    transportadora_id: int
    workflow_name: str

    @abstractmethod
    async def buscar_dados(self) -> Any:
        """
        Autentica e baixa os relatórios.
        Simples (D, E): retorna bytes do relatório único.
        Duplo (A, B, C): retorna tuple (pendencias_bytes, entregas_bytes).
        """
        ...

    @abstractmethod
    async def processar(
        self, pool: asyncpg.Pool, dados: Any
    ) -> ResultadoExecucao:
        """Parseia dados, classifica e persiste no banco."""
        ...

    async def executar(self, pool: asyncpg.Pool) -> ResultadoExecucao:
        dados = await self.buscar_dados()
        return await self.processar(pool, dados)
