"""Transportadora D — relatório CSV (latin-1) baixado pela API de RPA."""

import csv
import io
from datetime import date, timedelta

import asyncpg

from config import settings
from lib.classificar import chave_simples
from lib.db import buscar_ou_criar_cidade_id, buscar_volumes_bd
from lib.normalizar import converter_data, normalizar_cidade, normalizar_status_d
from lib.pipeline import processar_linhas
from lib.rpa_client import chamar_rpa
from transportadoras.base import ResultadoExecucao, Transportadora


# Índices das colunas no CSV (layout do relatório exportado)
_COL_PEDIDO   = 3
_COL_PRAZO    = 19
_COL_OCORR    = 22
_COL_DT_OCORR = 24
_COL_BAIRRO   = 28
_COL_CIDADE   = 29


class TransportadoraD(Transportadora):
    nome = "transportadora_d"
    transportadora_id = 4
    workflow_name = "Base | Transportadora D"

    async def buscar_dados(self) -> bytes:
        today = date.today()
        inicio = today - timedelta(days=10)
        return await chamar_rpa(
            key="relatorio",
            recipe_id=settings.transportadora_d_recipe_id,
            inputs={
                "dataInicio": inicio.strftime("%d/%m/%Y"),
                "dataFinal":  today.strftime("%d/%m/%Y"),
            },
            timeout=310,
        )

    def _parse_relatorio(self, data: bytes) -> dict[str, dict]:
        texto = data.decode("latin-1").lstrip("\ufeff")
        result: dict[str, dict] = {}
        reader = csv.reader(io.StringIO(texto))
        next(reader, None)  # pula header
        for row in reader:
            if not row:
                continue
            pedido = row[_COL_PEDIDO].strip() if len(row) > _COL_PEDIDO else ""
            if not pedido:
                continue
            ocorrencia = row[_COL_OCORR].strip() if len(row) > _COL_OCORR else ""
            # Volumes só inseridos no sistema ainda sem status real de transporte
            if "inserido" in ocorrencia.lower() or "integrado" in ocorrencia.lower():
                continue
            cidade_raw = row[_COL_CIDADE].strip() if len(row) > _COL_CIDADE else ""
            result[pedido] = {
                "cidade": normalizar_cidade(cidade_raw) if cidade_raw else "Desconhecida",
                "bairro": row[_COL_BAIRRO].strip() if len(row) > _COL_BAIRRO else None,
                "prazo_entrega": converter_data(row[_COL_PRAZO].strip() if len(row) > _COL_PRAZO else None),
                "dt_ult_ocorrencia": converter_data(row[_COL_DT_OCORR].strip() if len(row) > _COL_DT_OCORR else None),
                "status": normalizar_status_d(ocorrencia),
            }
        return result

    async def processar(self, pool: asyncpg.Pool, dados: bytes) -> ResultadoExecucao:
        relatorio = self._parse_relatorio(dados)
        bd = await buscar_volumes_bd(pool, self.transportadora_id)

        todos = set(relatorio) | set(bd)
        tarefas: list[tuple] = []
        for pedido in todos:
            r = relatorio.get(pedido)
            v = bd.get(pedido)
            chave = chave_simples(v is not None, r is not None)

            if chave.startswith("1") and v and v.get("resolvido"):
                continue

            coro = self._despachar(chave, pedido, r, v, pool)
            if coro is not None:
                tarefas.append((coro, chave))

        contadores = await processar_linhas(tarefas)
        return ResultadoExecucao(volumes_lidos=len(todos), contadores=contadores)

    def _despachar(self, chave, pedido, r, v, pool):
        match chave:
            case "00":
                return self._h00(pool, pedido)
            case "01":
                return self._h01(pool, pedido, r)
            case "10":
                return self._h10(pool, v)
            case "11":
                return self._h11(pool, v, r)
        return None

    async def _h00(self, pool: asyncpg.Pool, pedido: str) -> None:
        await pool.execute(
            """
            INSERT INTO volumes (cod_transportadora, transportadora_id, atencao, observacao_interna)
            VALUES ($1, $2, TRUE, 'Erro de classificação 000')
            ON CONFLICT (doc_interno) DO UPDATE
            SET atencao = TRUE, observacao_interna = 'Erro de classificação 000'
            """,
            pedido,
            self.transportadora_id,
        )

    async def _h01(self, pool: asyncpg.Pool, pedido: str, r: dict) -> None:
        cidade_id = await buscar_ou_criar_cidade_id(pool, r.get("cidade") or "Desconhecida")
        status = r["status"]
        entregue = status == "entregue"
        atencao = status == "tratativa"
        data_entrega = r.get("dt_ult_ocorrencia") if entregue else None
        await pool.execute(
            """
            INSERT INTO volumes (
                cod_transportadora, transportadora_id, cidade_id, bairro,
                data_vencimento, data_entrega, status, atencao, resolvido
            ) VALUES ($1, $2, $3, $4, $5::DATE, $6::DATE, $7, $8, $9)
            ON CONFLICT (doc_interno) DO NOTHING
            """,
            pedido,
            self.transportadora_id,
            cidade_id,
            r.get("bairro") or None,
            r.get("prazo_entrega"),
            data_entrega,
            status,
            atencao,
            entregue,
        )

    async def _h10(self, pool: asyncpg.Pool, v: dict) -> None:
        await pool.execute(
            """
            UPDATE volumes
            SET atencao = TRUE,
                observacao_interna = 'Nao consta em relatorio do cliente. Verificar situacao'
            WHERE doc_interno = $1
              AND resolvido = FALSE
            """,
            v["doc_interno"],
        )

    async def _h11(self, pool: asyncpg.Pool, v: dict, r: dict) -> None:
        status = r["status"]
        if status == v.get("status"):
            return
        entregue = status == "entregue"
        atencao = status == "tratativa"
        data_entrega = r.get("dt_ult_ocorrencia") if entregue else None
        await pool.execute(
            """
            UPDATE volumes
            SET status          = $2,
                data_vencimento = $3::DATE,
                atencao         = $4,
                resolvido       = $5,
                data_entrega    = CASE WHEN $5 THEN $6::DATE ELSE data_entrega END
            WHERE doc_interno = $1
              AND resolvido = FALSE
            """,
            v["doc_interno"],
            status,
            r.get("prazo_entrega"),
            atencao,
            entregue,
            data_entrega,
        )
