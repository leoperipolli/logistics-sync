import httpx

from config import settings
from lib.logger import logger


async def notificar_sucesso(
    transportadora: str,
    volumes_lidos: int,
    contadores: dict[str, int],
    execution_ms: int,
) -> None:
    linhas = [
        f"✅ *{transportadora}* concluído",
        f"Volumes lidos: {volumes_lidos}",
        f"Tempo: {execution_ms / 1000:.1f}s",
        "",
        *[f"  {caso}: {qtd}" for caso, qtd in sorted(contadores.items())],
    ]
    await _enviar("\n".join(linhas))


async def notificar_erro(transportadora: str, erro: str) -> None:
    await _enviar(f"❌ *{transportadora}* falhou\n{erro}")


async def _enviar(texto: str) -> None:
    if not settings.waha_url or not settings.waha_chat_id:
        logger.warning("waha_nao_configurado")
        return
    try:
        async with httpx.AsyncClient() as client:
            resp = await client.post(
                f"{settings.waha_url}/api/sendText",
                json={
                    "chatId": settings.waha_chat_id,
                    "text": texto,
                    "session": "default",
                },
                headers={"X-Api-Key": settings.waha_api_key},
                timeout=10,
            )
            resp.raise_for_status()
    except Exception as exc:
        logger.warning("falha_notificacao_waha", erro=str(exc))
