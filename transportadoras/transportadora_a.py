"""Transportadora A — TMS web via HTTP direto (pendências + entregas)."""

from config import settings
from lib.normalizar import normalizar_status_tms
from transportadoras.base_dupla import TransportadoraDupla


class TransportadoraA(TransportadoraDupla):
    nome = "transportadora_a"
    transportadora_id = 1
    workflow_name = "Base | Transportadora A"
    sigla_emp = settings.transportadora_a_sigla_emp
    sigla_fil = settings.transportadora_a_sigla_fil
    qtde_ctrc = "0"

    def _credenciais(self) -> tuple[str, str, str]:
        return (
            settings.transportadora_a_usuario,
            settings.transportadora_a_cpf,
            settings.transportadora_a_senha,
        )

    def _normalizar_status(self, localizacao: str) -> str:
        return normalizar_status_tms(localizacao)
