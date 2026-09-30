import asyncio

from lib.pipeline import processar_linhas


async def _ok():
    await asyncio.sleep(0)


async def _falha():
    raise ValueError("erro simulado")


def test_conta_por_chave_e_isola_erros():
    tarefas = [(_ok(), "010"), (_ok(), "010"), (_ok(), "101"), (_falha(), "110")]
    contadores = asyncio.run(processar_linhas(tarefas))
    assert contadores == {"010": 2, "101": 1, "erro": 1}


def test_respeita_limite_de_paralelismo():
    ativos = 0
    pico = 0

    async def tarefa():
        nonlocal ativos, pico
        ativos += 1
        pico = max(pico, ativos)
        await asyncio.sleep(0.01)
        ativos -= 1

    tarefas = [(tarefa(), "010") for _ in range(20)]
    asyncio.run(processar_linhas(tarefas, max_paralelo=5))
    assert pico == 5
