"""Transportadora B — mesmo TMS web da A, só muda configuração e filtro de entregas."""

from config import settings
from lib.normalizar import normalizar_status_tms
from transportadoras.base_dupla import TransportadoraDupla


class TransportadoraB(TransportadoraDupla):
    nome = "transportadora_b"
    transportadora_id = 2
    workflow_name = "Base | Transportadora B"
    sigla_emp = settings.transportadora_b_sigla_emp
    sigla_fil = settings.transportadora_b_sigla_fil
    qtde_ctrc = "9999"

    def _credenciais(self) -> tuple[str, str, str]:
        return (
            settings.transportadora_b_usuario,
            settings.transportadora_b_cpf,
            settings.transportadora_b_senha,
        )

    def _aceita_entrega(self, ocorrencia: str) -> bool:
        oc = ocorrencia.lower()
        return "nome do recebedor" in oc or "entregue" in oc

    def _normalizar_status(self, localizacao: str) -> str:
        return normalizar_status_tms(localizacao)
