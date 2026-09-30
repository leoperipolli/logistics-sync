"""Parse dos relatórios Excel da transportadora C. Dados fictícios."""

import io
from datetime import date, datetime

import openpyxl

from transportadoras.transportadora_c import TransportadoraC

_c = TransportadoraC(filial="BASE01")


def _xlsx(linhas: list[list]) -> bytes:
    wb = openpyxl.Workbook()
    for linha in linhas:
        wb.active.append(linha)
    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()


_COLS_PEND = ["Awb", "Cidade", "Bairro", "Dt_Vencimento_LM", "Status_Ultima_NC",
              "Desc_Ultimo_Status", "Base_Status", "Base_Ultima_NC"]

_PEND = _xlsx([
    _COLS_PEND,
    ["AWB0001", "PORTO ALEGRE", "Centro", datetime(2026, 4, 20), None, "Recebido CD", "BASE01", None],
    ["AWB0002", "CANOAS", "Bairro Teste", datetime(2026, 4, 21), "Cliente ausente", "Em processo de entrega", "BASE01", "BASE01"],
    ["AWB0003", "SAO PAULO", "x", datetime(2026, 4, 22), None, "Recebido CD", "OUTRA", None],     # outra filial
    ["AWB0004", "SAO PAULO", "x", datetime(2026, 4, 22), None, "Recebido CD", "BASE01", "OUTRA"], # ocorrência em outra filial
])

# O relatório SSRS tem 3 linhas de título antes do cabeçalho (header=3 no pandas)
_ENT = _xlsx([
    ["Relatorio de produtividade"], [], [],
    ["Awb", "DT HR", "PRAZO", "cidade"],
    ["AWB0001", datetime(2026, 4, 18, 14, 30), "DENTRO", "PORTO ALEGRE"],
    ["AWB0002", datetime(2026, 4, 25, 9, 0), "FORA", "CANOAS"],
    ["AWB0005", None, "DENTRO", "CANOAS"],  # sem data de entrega
])


class TestPendencias:
    def test_filtra_pela_filial(self):
        assert set(_c._parse_pendencias(_PEND)) == {"AWB0001", "AWB0002"}

    def test_campos(self):
        vol = _c._parse_pendencias(_PEND)["AWB0002"]
        assert vol["cidade"] == "Canoas"
        assert vol["prazo_entrega"] == date(2026, 4, 21)
        assert vol["status"] == "em_rota"
        assert vol["observacao_cliente"] == "Cliente ausente"


class TestEntregas:
    def test_ignora_linha_sem_data(self):
        assert set(_c._parse_entregas(_ENT)) == {"AWB0001", "AWB0002"}

    def test_prazo_estimado_pelo_campo_dentro_fora(self):
        result = _c._parse_entregas(_ENT)
        assert result["AWB0001"]["data_entrega"] == date(2026, 4, 18)
        assert result["AWB0001"]["prazo_entrega"] == date(2026, 4, 19)  # dentro → prazo depois da entrega
        assert result["AWB0002"]["prazo_entrega"] == date(2026, 4, 24)  # fora → prazo antes da entrega
