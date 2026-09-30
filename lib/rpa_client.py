"""Cliente fino para a API RPA."""

import asyncio
import time

import httpx

from config import settings


async def chamar_rpa(
    recipe_id: str,
    inputs: dict,
    key: str | None = None,
    timeout: int | None = None,
    max_wait: int = 600,
    retry_delay: float = 60.0,
) -> bytes:
    """POST /api/executions?format=file. Retorna bytes brutos.

    Cap sincrono do servidor e 300s. Se a execucao exceder `timeout` (ou 290s default),
    cai para polling em GET /api/executions/:id ate `max_wait` segundos no total.
    Falhas transientes (ex: login timeout no portal) ganham um retry apos `retry_delay` segundos.
    """
    try:
        return await _chamar_rpa_once(recipe_id, inputs, key, timeout, max_wait)
    except RuntimeError:
        await asyncio.sleep(retry_delay)
        return await _chamar_rpa_once(recipe_id, inputs, key, timeout, max_wait)


async def _chamar_rpa_once(
    recipe_id: str,
    inputs: dict,
    key: str | None,
    timeout: int | None,
    max_wait: int,
) -> bytes:
    sync_timeout = min(timeout or 290, 290)
    params: dict = {"format": "file", "timeout": sync_timeout}
    if key is not None:
        params["key"] = key

    auth = {"X-Api-Key": settings.rpa_api_key}
    async with httpx.AsyncClient(timeout=sync_timeout + 70) as client:
        resp = await client.post(
            f"{settings.rpa_url}/api/executions",
            params=params,
            headers={**auth, "Content-Type": "application/json"},
            json={"recipe_id": recipe_id, "inputs": inputs},
        )

        if resp.status_code < 400:
            if "application/json" in resp.headers.get("content-type", ""):
                raise RuntimeError(f"RPA retornou JSON (esperado binário): {resp.text[:300]}")
            return resp.content

        if resp.status_code == 408:
            try:
                exec_id = resp.json()["execution_id"]
            except (ValueError, KeyError):
                raise RuntimeError(f"RPA 408 sem execution_id: {resp.text[:500]}")
            return await _aguardar_e_baixar(client, exec_id, key, auth, max_wait)

        raise RuntimeError(f"RPA {resp.status_code}: {resp.text[:500]}")


async def _aguardar_e_baixar(
    client: httpx.AsyncClient,
    exec_id: str,
    key: str | None,
    auth: dict,
    max_wait: int,
    poll_interval: float = 5.0,
) -> bytes:
    if key is None:
        raise RuntimeError(f"RPA polling de {exec_id} requer 'key' para baixar resultado")

    status_url = f"{settings.rpa_url}/api/executions/{exec_id}"
    deadline = time.monotonic() + max_wait

    while True:
        await asyncio.sleep(poll_interval)
        resp = await client.get(status_url, headers=auth)
        if resp.status_code >= 400:
            raise RuntimeError(f"RPA {resp.status_code} (polling {exec_id}): {resp.text[:500]}")

        status = resp.json().get("status")
        if status == "success":
            break
        if status == "failed":
            erro = resp.json().get("error") or "?"
            raise RuntimeError(f"RPA execucao {exec_id} falhou: {erro}")
        if time.monotonic() >= deadline:
            raise RuntimeError(f"RPA polling timeout para {exec_id} apos {max_wait}s")

    download_url = f"{settings.rpa_url}/api/executions/{exec_id}/download/{key}"
    file_resp = await client.get(download_url, headers=auth)
    if file_resp.status_code >= 400:
        raise RuntimeError(f"RPA download {file_resp.status_code}: {file_resp.text[:500]}")
    return file_resp.content
