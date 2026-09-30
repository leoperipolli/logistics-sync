"""Cliente HTTP para o TMS web usado pelas transportadoras A e B.

O fluxo é idêntico para as duas transportadoras. O que muda:
- credenciais (usuário, CPF, senha)
- sigla da empresa e sigla da filial nas entregas

Fluxo de download:
- endpoint de login: POST → cookie `token` (JWT)
- endpoint de pendências / entregas: POST → HTML com hidden `web_body`
  contendo abrir('ARQUIVO','SCRIPT')
- endpoint de download: GET com act=ARQUIVO, filename=SCRIPT → arquivo CSV/XLSX real

URLs e nomes de endpoint vêm da configuração (.env).
"""

import re
import time
from urllib.parse import unquote, urlsplit

import httpx

from config import settings

USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/147.0.0.0 Safari/537.36"
)


def _origin(url: str) -> str:
    partes = urlsplit(url)
    return f"{partes.scheme}://{partes.netloc}"


class TmsHttpClient:
    """Session HTTP para o TMS. Use como async context manager."""

    def __init__(self, sigla_emp: str, usuario: str, cpf: str, senha: str):
        self.sigla_emp = sigla_emp
        self.usuario = usuario
        self.cpf = cpf
        self.senha = senha
        self.base_url = settings.tms_base_url.rstrip("/")
        self._client: httpx.AsyncClient | None = None

    async def __aenter__(self) -> "TmsHttpClient":
        self._client = httpx.AsyncClient(
            follow_redirects=True,
            headers={
                "Accept": "*/*",
                "Accept-Language": "pt-BR,pt;q=0.9",
                "Connection": "keep-alive",
                "Content-type": "application/x-www-form-urlencoded",
                "Origin": _origin(self.base_url),
                "User-Agent": USER_AGENT,
            },
            cookies={
                "useri": "",
                "remember": "0",
                "sigla_emp": self.sigla_emp,
            },
            timeout=60,
        )
        return self

    async def __aexit__(self, *_) -> None:
        if self._client is not None:
            await self._client.aclose()
            self._client = None

    @property
    def client(self) -> httpx.AsyncClient:
        if self._client is None:
            raise RuntimeError("TmsHttpClient fora de contexto — use `async with`")
        return self._client

    def _url(self, endpoint: str) -> str:
        return f"{self.base_url}/{endpoint}"

    async def login(self) -> None:
        dummy = int(time.time() * 1000)
        url = self._url(settings.tms_endpoint_login)
        resp = await self.client.post(
            url,
            data={
                "act": "L",
                "f1": self.sigla_emp,
                "f2": self.cpf,
                "f3": self.usuario,
                "f4": self.senha,
                "dummy": dummy,
            },
            headers={"Referer": url},
        )
        resp.raise_for_status()
        if "token" not in self.client.cookies:
            raise RuntimeError(f"login no TMS falhou (sigla_emp={self.sigla_emp})")

    async def baixar_relatorio(self, endpoint: str, data: dict) -> bytes:
        """POST em endpoint → extrai abrir('arq','script') → GET no endpoint de download."""
        url = self._url(endpoint)
        post = await self.client.post(url, data=data, headers={"Referer": url})
        post.raise_for_status()

        body_match = re.search(r'name=web_body[^>]+value="([^"]+)"', post.text)
        if not body_match:
            raise RuntimeError(
                f"web_body não encontrado em {endpoint} — resposta: {post.text[:400]}"
            )
        web_body = unquote(body_match.group(1))

        args_match = re.search(r"abrir\s*\('([^']+)',\s*'([^']+)'", web_body)
        if not args_match:
            raise RuntimeError(f"argumentos abrir() não encontrados em {endpoint}")
        arq, script = args_match.group(1), args_match.group(2)

        resp = await self.client.get(
            self._url(settings.tms_endpoint_download),
            params={
                "act": arq,
                "filename": script,
                "path": "",
                "down": "1",
                "nw": "1",
            },
            headers={"Referer": url},
        )
        resp.raise_for_status()
        return resp.content
