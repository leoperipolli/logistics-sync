"""Transportadora C — API de RPA (pendências) + SSRS/NTLM (entregas)."""

import io
from datetime import date, timedelta

import pandas as pd

from config import settings
from lib.normalizar import normalizar_cidade, normalizar_status_c
from lib.rpa_client import chamar_rpa
from lib.ssrs import baixar_ssrs_excel
from transportadoras.base_dupla import TransportadoraDupla

_OLE2_MAGIC = b"\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1"


def _s(val) -> str:
    """str seguro para valores pandas — trata NaN/None como ''."""
    try:
        if pd.isna(val):
            return ""
    except (TypeError, ValueError):
        pass
    return str(val).strip()


def _ler_excel(data: bytes, **kwargs) -> pd.DataFrame:
    engine = "xlrd" if data[:8] == _OLE2_MAGIC else "openpyxl"
    return pd.read_excel(io.BytesIO(data), engine=engine, **kwargs)


class TransportadoraC(TransportadoraDupla):
    nome = "transportadora_c"
    transportadora_id = 3
    workflow_name = "Base | Transportadora C"

    def __init__(self, filial: str | None = None):
        self.filial = filial or settings.transportadora_c_filial

    def _credenciais(self) -> tuple[str, str, str]:
        # Não usada — buscar_dados é sobrescrito
        return settings.transportadora_c_usuario, "", settings.transportadora_c_senha

    def _normalizar_status(self, localizacao: str) -> str:
        return normalizar_status_c(localizacao)

    async def buscar_dados(self) -> tuple[bytes, bytes]:
        today = date.today()
        inicio = today - timedelta(days=6)

        pend_bytes = await chamar_rpa(
            key="relatorioPendencias",
            recipe_id=settings.transportadora_c_recipe_id,
            inputs={},
            timeout=299,
        )
        ent_bytes = await baixar_ssrs_excel(
            report_url=settings.transportadora_c_ssrs_url,
            usuario=settings.transportadora_c_usuario,
            senha=settings.transportadora_c_senha,
            data_inicio=inicio.strftime("%d/%m/%Y"),
            data_fim=today.strftime("%d/%m/%Y"),
            filial=self.filial,
        )
        return pend_bytes, ent_bytes

    def _parse_pendencias(self, data: bytes) -> dict[str, dict]:
        df = _ler_excel(data)
        result: dict[str, dict] = {}
        for _, row in df.iterrows():
            awb = _s(row.get("Awb"))
            if not awb:
                continue
            base_status = _s(row.get("Base_Status"))
            if base_status != self.filial:
                continue
            base_ultima_nc = _s(row.get("Base_Ultima_NC"))
            if base_ultima_nc and base_ultima_nc != self.filial:
                continue
            prazo_dt = row.get("Dt_Vencimento_LM")
            prazo = prazo_dt.date() if not pd.isna(prazo_dt) and hasattr(prazo_dt, "date") else None
            desc_status = _s(row.get("Desc_Ultimo_Status"))
            obs = _s(row.get("Status_Ultima_NC")) or None
            cidade_raw = _s(row.get("Cidade"))
            result[awb] = {
                "cidade": normalizar_cidade(cidade_raw) if cidade_raw else "Desconhecida",
                "bairro": _s(row.get("Bairro")) or None,
                "prazo_entrega": prazo,
                "observacao_cliente": obs,
                "localizacao": desc_status,
                "status": self._normalizar_status(desc_status),
            }
        return result

    def _parse_entregas(self, data: bytes) -> dict[str, dict]:
        df = _ler_excel(data, header=3)
        result: dict[str, dict] = {}
        for _, row in df.iterrows():
            awb = _s(row.get("Awb"))
            if not awb:
                continue
            dt_hr = row.get("DT HR")
            if pd.isna(dt_hr):
                continue
            data_entrega = dt_hr.date()
            prazo_campo = _s(row.get("PRAZO")).lower()
            delta = timedelta(days=1 if prazo_campo == "dentro" else -1)
            prazo_dt = dt_hr.date() + delta
            cidade_raw = _s(row.get("cidade"))
            result[awb] = {
                "cidade": normalizar_cidade(cidade_raw) if cidade_raw else "Desconhecida",
                "prazo_entrega": prazo_dt,
                "data_entrega": data_entrega,
            }
        return result
