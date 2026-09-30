"""Transportadora E — portal web: token CSRF + login JSON + parse da tabela HTML."""

import asyncio
import re
from datetime import date, timedelta

import asyncpg
import httpx
from bs4 import BeautifulSoup

from config import settings
from lib.classificar import chave_simples
from lib.db import buscar_ou_criar_cidade_id, buscar_volumes_bd
from lib.normalizar import converter_data, normalizar_cidade, normalizar_status_e
from lib.pipeline import processar_linhas
from transportadoras.base import ResultadoExecucao, Transportadora

# URL base vem da configuração; os caminhos abaixo são do portal de exemplo
_BASE_URL   = settings.transportadora_e_url.rstrip("/")
_LOGIN_PAGE = f"{_BASE_URL}/login"
_LOGIN_URL  = f"{_BASE_URL}/api/login"
_LIST_URL   = f"{_BASE_URL}/volumes/lista"

_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/147.0.0.0 Safari/537.36"
    ),
    "Accept-Language": "pt-BR,pt;q=0.9",
}

# Índices 0-based das colunas na tabela HTML (col 0 é checkbox vazio)
_COL_COD    = 1   # B — "MD"
_COL_DEST   = 12  # M — "DESTINATÁRIO" (HTML: NOME<br/>CIDADE - UF)
_COL_PRAZO  = 13  # N — "PREV. ENTREGA" (HTML: DD/MM/YYYY HH:MM<br/>NOME DO AGENTE)
_COL_STATUS = 16  # Q — "ÚLTIMO STATUS" (HTML: DATA<br/>CÓDIGO - TEXTO)


def _extrair_cidade(campo: str) -> str:
    """Extrai cidade de 'CIDADE - UF' (segunda linha da célula, após o <br/>)."""
    cidade = campo.split(" -")[0].strip()
    return normalizar_cidade(cidade) if cidade else "Desconhecida"


def _extrair_token_csrf(html: str) -> str:
    """Extrai token CSRF da página de login (hidden input ou variável JS)."""
    soup = BeautifulSoup(html, "html.parser")
    inp = soup.find("input", {"name": "token"})
    if inp and inp.get("value"):
        return inp["value"]
    # fallback: variável JS  var token = "abc123";
    m = re.search(r'var\s+token\s*=\s*["\']([a-f0-9]{32})["\']', html)
    if m:
        return m.group(1)
    raise RuntimeError("Transportadora E: token CSRF não encontrado na página de login")


def _download_sync(data_inicio: str, data_fim: str) -> bytes:
    with httpx.Client(follow_redirects=True, timeout=60, headers=_HEADERS) as client:
        # 1. GET login page → token CSRF
        resp = client.get(_LOGIN_PAGE)
        resp.raise_for_status()
        token = _extrair_token_csrf(resp.text)

        # 2. POST autenticação
        resp = client.post(
            _LOGIN_URL,
            json={"user": settings.transportadora_e_usuario, "password": settings.transportadora_e_senha, "token": token},
            headers={"X-Requested-With": "XMLHttpRequest"},
        )
        resp.raise_for_status()
        data = resp.json()
        if not (data.get("success") or data.get("logado") or data.get("status") == "ok"):
            # o portal pode retornar HTTP 200 com erro no JSON
            if "erro" in str(data).lower() or "error" in str(data).lower():
                raise RuntimeError(f"Transportadora E: login falhou: {data}")

        # 3. POST lista de volumes com filtro de data
        resp = client.post(
            _LIST_URL,
            params={"acao": "1", "pagina": "0"},
            data={
                "tipo_cadastro": "id_cliente",
                "tipoNota": "nf",
                "tipoCampo": "id_manifesto",
                "tipo_coluna": "fantasia",
                "minuta": "",
                "notaFiscal": "",
                "cte": "",
                "buscaGeral": "",
                "unidade": "0",
                "cliente_nome": "",
                "tipo_data": "data",
                "data_1": data_inicio,
                "data_2": data_fim,
                "ordem": "id_minuta",
                "situacao": "0",
                "rota": "0",
                "PESQUISAR": " PESQUISAR ",
            },
            headers={"Referer": _LIST_URL},
        )
        resp.raise_for_status()
        return resp.content


class TransportadoraE(Transportadora):
    nome = "transportadora_e"
    transportadora_id = 5
    workflow_name = "Base | Transportadora E"

    async def buscar_dados(self) -> bytes:
        today = date.today()
        inicio = today - timedelta(days=10)
        return await asyncio.to_thread(
            _download_sync,
            inicio.strftime("%d/%m/%Y"),
            today.strftime("%d/%m/%Y"),
        )

    def _parse_relatorio(self, data: bytes) -> dict[str, dict]:
        html = data.decode("utf-8", errors="replace")
        soup = BeautifulSoup(html, "html.parser")
        tabela = soup.find(id="printExcel")
        if tabela is None:
            raise RuntimeError("Transportadora E: tabela #printExcel não encontrada no HTML")

        result: dict[str, dict] = {}
        linhas = tabela.find_all("tr")
        for linha in linhas[1:]:  # pula header
            cells = linha.find_all(["td", "th"])
            if len(cells) <= _COL_STATUS:
                continue

            cod = cells[_COL_COD].get_text(strip=True)
            if not cod:
                continue

            # DEST: "NOME<br/>CIDADE - UF" → pega a última linha (após o <br/>)
            dest_linhas = cells[_COL_DEST].get_text(separator="\n", strip=True).split("\n")
            cidade_raw = dest_linhas[-1] if len(dest_linhas) > 1 else dest_linhas[0]

            # PRAZO: "DD/MM/YYYY HH:MM<br/>NOME DO AGENTE" → pega a primeira linha
            prazo_linhas = cells[_COL_PRAZO].get_text(separator="\n", strip=True).split("\n")
            prazo_raw = prazo_linhas[0] if prazo_linhas else ""

            # STATUS: "DATA<br/>CÓDIGO - TEXTO" → data na primeira linha, texto na última
            status_linhas = cells[_COL_STATUS].get_text(separator="\n", strip=True).split("\n")
            status_data_raw = status_linhas[0] if status_linhas else ""
            status_raw = status_linhas[-1] if len(status_linhas) > 1 else status_linhas[0]

            status = normalizar_status_e(status_raw)
            result[cod] = {
                "cidade": _extrair_cidade(cidade_raw),
                "prazo_entrega": converter_data(prazo_raw),
                "status": status,
                "data_entrega": converter_data(status_data_raw) if status == "entregue" else None,
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
        await pool.execute(
            """
            INSERT INTO volumes (
                cod_transportadora, transportadora_id, cidade_id,
                data_vencimento, data_entrega, status, atencao, resolvido
            ) VALUES ($1, $2, $3, $4::DATE, $5::DATE, $6, $7, $8)
            ON CONFLICT (doc_interno) DO NOTHING
            """,
            pedido,
            self.transportadora_id,
            cidade_id,
            r.get("prazo_entrega"),
            r.get("data_entrega"),
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
        await pool.execute(
            """
            UPDATE volumes
            SET status          = $2,
                data_vencimento = $3::DATE,
                data_entrega    = $4::DATE,
                atencao         = $5,
                resolvido       = $6
            WHERE doc_interno = $1
              AND resolvido = FALSE
            """,
            v["doc_interno"],
            status,
            r.get("prazo_entrega"),
            r.get("data_entrega"),
            atencao,
            entregue,
        )
