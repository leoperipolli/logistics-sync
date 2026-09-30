"""Parse do CSV da transportadora D. Dados fictícios."""

from datetime import date

from transportadoras.transportadora_d import TransportadoraD

_d = TransportadoraD()


def _linha(pedido="", prazo="", ocorrencia="", dt_ocorrencia="", bairro="", cidade="") -> str:
    cols = [""] * 30
    cols[3], cols[19], cols[22] = pedido, prazo, ocorrencia
    cols[24], cols[28], cols[29] = dt_ocorrencia, bairro, cidade
    return ",".join(cols)


_CSV = "\n".join([
    ",".join(f"col{i}" for i in range(30)),
    _linha("900001", "20/04/2026", "Saiu para entrega", "18/04/2026", "Centro", "PORTO ALEGRE"),
    _linha("900002", "21/04/2026", "Entrega realizada", "19/04/2026", "Centro", "SÃO LEOPOLDO"),
    _linha("900003", "22/04/2026", "Pedido inserido", "17/04/2026", "Centro", "CANOAS"),
    _linha("", "22/04/2026", "Saiu para entrega", "17/04/2026", "Centro", "CANOAS"),
]).encode("latin-1")


class TestParseRelatorio:
    def test_ignora_pedido_vazio_e_recem_inserido(self):
        assert set(_d._parse_relatorio(_CSV)) == {"900001", "900002"}

    def test_campos(self):
        vol = _d._parse_relatorio(_CSV)["900001"]
        assert vol["cidade"] == "Porto Alegre"
        assert vol["prazo_entrega"] == date(2026, 4, 20)
        assert vol["status"] == "em_rota"

    def test_latin1_e_acentos(self):
        vol = _d._parse_relatorio(_CSV)["900002"]
        assert vol["cidade"] == "Sao Leopoldo"
        assert vol["status"] == "entregue"
        assert vol["dt_ult_ocorrencia"] == date(2026, 4, 19)
