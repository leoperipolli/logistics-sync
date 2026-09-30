"""Parse da tabela HTML da transportadora E. Dados fictícios."""

from datetime import date

import pytest

from transportadoras.transportadora_e import TransportadoraE, _extrair_token_csrf

_e = TransportadoraE()


def _linha(cod="", dest="", prazo="", status="") -> str:
    cells = [""] * 17
    cells[1], cells[12], cells[13], cells[16] = cod, dest, prazo, status
    return "<tr>" + "".join(f"<td>{c}</td>" for c in cells) + "</tr>"


def _html(*linhas: str) -> bytes:
    header = "<tr>" + "".join(f"<th>c{i}</th>" for i in range(17)) + "</tr>"
    return f'<table id="printExcel">{header}{"".join(linhas)}</table>'.encode("utf-8")


class TestParseRelatorio:
    def test_ignora_codigo_vazio(self):
        assert _e._parse_relatorio(_html(_linha(cod=""))) == {}

    def test_entregue(self):
        html = _html(_linha(
            cod="500001",
            dest="CLIENTE TESTE<br/>PORTO ALEGRE - RS",
            prazo="10/04/2026 18:00<br/>AGENTE TESTE",
            status="09/04/2026<br/>123 - ENTREGA REALIZADA",
        ))
        vol = _e._parse_relatorio(html)["500001"]
        assert vol["cidade"] == "Porto Alegre"
        assert vol["prazo_entrega"] == date(2026, 4, 10)
        assert vol["status"] == "entregue"
        assert vol["data_entrega"] == date(2026, 4, 9)

    def test_nao_entregue_sem_data_de_entrega(self):
        html = _html(_linha(cod="500002", dest="CANOAS - RS", status="09/04/2026<br/>010 - MANIFESTADO"))
        vol = _e._parse_relatorio(html)["500002"]
        assert vol["status"] == "em_manifesto"
        assert vol["data_entrega"] is None

    def test_tabela_ausente_gera_erro(self):
        with pytest.raises(RuntimeError):
            _e._parse_relatorio(b"<html></html>")


class TestTokenCsrf:
    def test_hidden_input(self):
        assert _extrair_token_csrf('<input name="token" value="abc">') == "abc"

    def test_variavel_js(self):
        token = "0123456789abcdef0123456789abcdef"
        assert _extrair_token_csrf(f'<script>var token = "{token}";</script>') == token
