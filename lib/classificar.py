from typing import Literal

Chave2 = Literal["00", "01", "10", "11"]
Chave3 = Literal["000", "001", "010", "011", "100", "101", "110", "111"]


def chave_simples(no_bd: bool, no_relatorio: bool) -> Chave2:
    """Relatório simples (transportadoras D e E): BD | Relatório."""
    return f"{int(no_bd)}{int(no_relatorio)}"  # type: ignore[return-value]


def chave_dupla(no_bd: bool, nas_pendencias: bool, nas_entregas: bool) -> Chave3:
    """Relatório duplo (transportadoras A, B e C): BD | Pendências | Entregas."""
    return f"{int(no_bd)}{int(nas_pendencias)}{int(nas_entregas)}"  # type: ignore[return-value]
