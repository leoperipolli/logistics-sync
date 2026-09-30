"""Base para transportadoras com fluxo duplo: pendências + entregas → dispatch 8 casos."""

import time
from abc import abstractmethod
from datetime import date, timedelta

import asyncpg

from lib.classificar import chave_dupla
from lib.db import buscar_ou_criar_cidade_id, buscar_volumes_bd
from lib.normalizar import converter_data, normalizar_cidade
from lib.pipeline import processar_linhas
from config import settings
from lib.tms_client import TmsHttpClient
from transportadoras.base import ResultadoExecucao, Transportadora

_CONFLITO_MSG = (
    "Conflito: volume consta simultaneamente como pendente e entregue. "
    "Conferir no sistema da transportadora."
)


class TransportadoraDupla(Transportadora):
    """Transportadora com dois relatórios (pendências + entregas) e dispatch de 8 casos.

    Subclasses do TMS web (A, B) usam buscar_dados() herdado via TmsHttpClient.
    Subclasses com outra autenticação (C) sobrescrevem buscar_dados() e _credenciais().
    """

    # Atributos usados pelo buscar_dados() do TMS — definir nas subclasses do TMS
    sigla_emp: str
    sigla_fil: str
    qtde_ctrc: str
    janela_dias: int = 6

    @abstractmethod
    def _credenciais(self) -> tuple[str, str, str]:
        """Retorna (usuario, cpf, senha). Usado pelo buscar_dados() do TMS."""
        ...

    @abstractmethod
    def _normalizar_status(self, localizacao: str) -> str: ...

    async def buscar_dados(self) -> tuple[bytes, bytes]:
        today = date.today()
        inicio = today - timedelta(days=self.janela_dias)
        dummy = int(time.time() * 1000)
        usuario, cpf, senha = self._credenciais()

        async with TmsHttpClient(
            sigla_emp=self.sigla_emp,
            usuario=usuario,
            cpf=cpf,
            senha=senha,
        ) as tms:
            await tms.login()

            pend_bytes = await tms.baixar_relatorio(
                settings.tms_endpoint_pendencias,
                {
                    "act": "CSV",
                    "qtde_ctrc": self.qtde_ctrc,
                    "nro_romaneio": "",
                    "seq_romaneio": "",
                    "dummy": dummy,
                },
            )

            ent_bytes = await tms.baixar_relatorio(
                settings.tms_endpoint_entregas,
                {
                    "act": "ENV_EXCEL",
                    "t_sigla_fil": self.sigla_fil,
                    "t_data_busca": inicio.strftime("%d%m%y"),
                    "t_data_busca2": today.strftime("%d%m%y"),
                    "dummy": dummy,
                },
            )

        return pend_bytes, ent_bytes

    def _parse_pendencias(self, data: bytes) -> dict[str, dict]:
        result: dict[str, dict] = {}
        for line in data.decode("utf-8-sig").splitlines()[2:]:
            if not line.strip():
                continue
            row = line.split(";")
            ctrc = row[1].strip() if len(row) > 1 else ""
            if not ctrc:
                continue
            ultima_oc = row[15].strip() if len(row) > 15 else ""
            oc_lower = ultima_oc.lower()
            obs = (
                None
                if (
                    "separado para processo de entrega" in oc_lower
                    or "recebido no centro" in oc_lower
                )
                else (ultima_oc or None)
            )
            cidade_raw = row[6].strip() if len(row) > 6 else ""
            localizacao = row[16].strip() if len(row) > 16 else ""
            result[ctrc] = {
                "cidade": normalizar_cidade(cidade_raw) if cidade_raw else "Desconhecida",
                "bairro": row[7].strip() if len(row) > 7 else None,
                "prazo_entrega": converter_data(row[13].strip() if len(row) > 13 else None),
                "observacao_cliente": obs,
                "localizacao": localizacao,
                "status": self._normalizar_status(localizacao),
            }
        return result

    def _aceita_entrega(self, ocorrencia: str) -> bool:
        return "nome do recebedor" in ocorrencia.lower()

    def _parse_entregas(self, data: bytes) -> dict[str, dict]:
        result: dict[str, dict] = {}
        for line in data.decode("utf-8-sig").splitlines()[1:]:
            if not line.strip():
                continue
            row = line.split(";")
            ocorrencia = row[12].strip() if len(row) > 12 else ""
            if not self._aceita_entrega(ocorrencia):
                continue
            ctrc = row[1].strip() if len(row) > 1 else ""
            if not ctrc:
                continue
            cidade_raw = row[8].strip() if len(row) > 8 else ""
            if "/" in cidade_raw:
                cidade_raw = cidade_raw.split("/", 1)[1]
            result[ctrc] = {
                "cidade": normalizar_cidade(cidade_raw) if cidade_raw else "Desconhecida",
                "prazo_entrega": converter_data(row[11].strip() if len(row) > 11 else None),
                "data_entrega": converter_data(row[2].strip() if len(row) > 2 else None),
                "ocorrencia": ocorrencia[:45],
            }
        return result

    async def processar(
        self, pool: asyncpg.Pool, dados: tuple[bytes, bytes]
    ) -> ResultadoExecucao:
        pend_bytes, ent_bytes = dados
        pendencias = self._parse_pendencias(pend_bytes)
        entregas = self._parse_entregas(ent_bytes)
        bd = await buscar_volumes_bd(pool, self.transportadora_id)

        todos_ctrcs = set(pendencias) | set(entregas) | set(bd)

        tarefas: list[tuple] = []
        for ctrc in todos_ctrcs:
            p = pendencias.get(ctrc)
            e = entregas.get(ctrc)
            v = bd.get(ctrc)
            chave = chave_dupla(v is not None, p is not None, e is not None)

            if chave.startswith("1") and v and v.get("resolvido"):
                continue

            coro = self._despachar(chave, ctrc, p, e, v, pool)
            if coro is not None:
                tarefas.append((coro, chave))

        contadores = await processar_linhas(tarefas)
        return ResultadoExecucao(volumes_lidos=len(todos_ctrcs), contadores=contadores)

    def _despachar(self, chave, ctrc, p, e, v, pool):
        match chave:
            case "000":
                return self._h000(pool, ctrc)
            case "001":
                return self._h001(pool, ctrc, e)
            case "010":
                return self._h010(pool, ctrc, p)
            case "011":
                return self._h011(pool, ctrc, p, e)
            case "100":
                return self._h100(pool, v)
            case "101":
                return self._h101(pool, v, e)
            case "110":
                return self._h110(pool, v, p)
            case "111":
                return self._h111(pool, v)
        return None

    async def _h000(self, pool: asyncpg.Pool, ctrc: str) -> None:
        await pool.execute(
            """
            INSERT INTO volumes (cod_transportadora, transportadora_id, atencao, observacao_interna)
            VALUES ($1, $2, TRUE, 'Erro de classificação 000')
            """,
            ctrc,
            self.transportadora_id,
        )

    async def _h001(self, pool: asyncpg.Pool, ctrc: str, e: dict) -> None:
        cidade_id = await buscar_ou_criar_cidade_id(pool, e.get("cidade") or "Desconhecida")
        await pool.execute(
            """
            INSERT INTO volumes (
                cod_transportadora, transportadora_id, cidade_id,
                data_vencimento, data_entrega, status, resolvido
            ) VALUES ($1, $2, $3, $4, $5, 'entregue', TRUE)
            """,
            ctrc,
            self.transportadora_id,
            cidade_id,
            e.get("prazo_entrega"),
            e.get("data_entrega"),
        )

    async def _h010(self, pool: asyncpg.Pool, ctrc: str, p: dict) -> None:
        cidade_id = await buscar_ou_criar_cidade_id(pool, p.get("cidade") or "Desconhecida")
        await pool.execute(
            """
            INSERT INTO volumes (
                cod_transportadora, transportadora_id, cidade_id, bairro,
                data_vencimento, status, observacao_cliente
            ) VALUES ($1, $2, $3, $4, $5, $6, $7)
            """,
            ctrc,
            self.transportadora_id,
            cidade_id,
            p.get("bairro"),
            p.get("prazo_entrega"),
            p["status"],
            p.get("observacao_cliente"),
        )

    async def _h011(self, pool: asyncpg.Pool, ctrc: str, p: dict, e: dict) -> None:
        cidade = p.get("cidade") or (e.get("cidade") if e else None) or "Desconhecida"
        cidade_id = await buscar_ou_criar_cidade_id(pool, cidade)
        prazo = p.get("prazo_entrega") or (e.get("prazo_entrega") if e else None)
        await pool.execute(
            """
            INSERT INTO volumes (
                cod_transportadora, transportadora_id, cidade_id, bairro,
                data_vencimento, status, observacao_cliente, observacao_interna
            ) VALUES ($1, $2, $3, $4, $5, 'entregue', $6, $7)
            """,
            ctrc,
            self.transportadora_id,
            cidade_id,
            p.get("bairro"),
            prazo,
            p.get("observacao_cliente"),
            _CONFLITO_MSG,
        )

    async def _h100(self, pool: asyncpg.Pool, v: dict) -> None:
        if v.get("atencao"):
            return
        await pool.execute(
            """
            UPDATE volumes
            SET atencao = TRUE,
                observacao_interna = 'Conflito: nao esta na lista de entregues e nem nas pendencias'
            WHERE doc_interno = $1
              AND status != 'entregue'
              AND resolvido = FALSE
            """,
            v["doc_interno"],
        )

    async def _h101(self, pool: asyncpg.Pool, v: dict, e: dict) -> None:
        ocorrencia = (e.get("ocorrencia") or "").lower()
        if "observa" in ocorrencia:
            await pool.execute(
                """
                UPDATE volumes
                SET atencao = TRUE
                WHERE doc_interno = $1
                  AND status != 'entregue'
                  AND resolvido = FALSE
                """,
                v["doc_interno"],
            )
        else:
            await pool.execute(
                """
                UPDATE volumes
                SET status = 'entregue',
                    resolvido = TRUE,
                    data_entrega = $2
                WHERE doc_interno = $1
                  AND status != 'entregue'
                """,
                v["doc_interno"],
                e.get("data_entrega"),
            )

    async def _h110(self, pool: asyncpg.Pool, v: dict, p: dict) -> None:
        novo_status = self._normalizar_status(p.get("localizacao", ""))
        if novo_status == v.get("status"):
            return
        await pool.execute(
            """
            UPDATE volumes
            SET status = $2,
                atencao = CASE
                    WHEN data_vencimento::DATE = CURRENT_DATE THEN TRUE
                    ELSE atencao
                END
            WHERE doc_interno = $1
            """,
            v["doc_interno"],
            novo_status,
        )

    async def _h111(self, pool: asyncpg.Pool, v: dict) -> None:
        await pool.execute(
            """
            UPDATE volumes
            SET status = 'entregue',
                observacao_interna = $2
            WHERE doc_interno = $1
              AND status != 'entregue'
            """,
            v["doc_interno"],
            _CONFLITO_MSG,
        )
