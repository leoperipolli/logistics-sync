from datetime import date

from lib.normalizar import (
    converter_data,
    excel_para_data,
    normalizar_cidade,
    normalizar_status_c,
    normalizar_status_d,
    normalizar_status_e,
    normalizar_status_tms,
)


class TestConverterData:
    def test_formato_padrao(self):
        assert converter_data("15/04/2026") == date(2026, 4, 15)

    def test_ignora_hora(self):
        assert converter_data("15/04/2026 08:30:00") == date(2026, 4, 15)

    def test_none_e_vazio(self):
        assert converter_data(None) is None
        assert converter_data("") is None

    def test_formato_invalido(self):
        assert converter_data("2026-04-15") is None


class TestNormalizarCidade:
    def test_remove_acento(self):
        assert normalizar_cidade("são paulo") == "Sao Paulo"

    def test_preposicoes_minusculas(self):
        assert normalizar_cidade("BARRA DO RIBEIRO") == "Barra do Ribeiro"

    def test_ja_correto(self):
        assert normalizar_cidade("Rio de Janeiro") == "Rio de Janeiro"


class TestExcelParaData:
    def test_serial_conhecido(self):
        assert excel_para_data(45000) == date(2023, 3, 15)

    def test_ignora_fracao_de_hora(self):
        assert excel_para_data(45000.9) == date(2023, 3, 15)


class TestStatusTms:
    def test_mapeamentos(self):
        assert normalizar_status_tms("NO ARMAZEM F01") == "recebido"
        assert normalizar_status_tms("EM ENTREGA") == "em_rota"
        assert normalizar_status_tms("APONTADO PARA ROTA 01") == "em_manifesto"

    def test_desconhecido_vira_tratativa(self):
        assert normalizar_status_tms("DEVOLVIDO AO REMETENTE") == "tratativa"

    def test_case_insensitive(self):
        assert normalizar_status_tms("no armazem") == "recebido"


class TestStatusC:
    def test_mapeamentos(self):
        assert normalizar_status_c("Recebido CD") == "recebido"
        assert normalizar_status_c("Em processo de entrega") == "em_rota"
        assert normalizar_status_c("Em rota de transferencia") == "em_manifesto"
        assert normalizar_status_c("Endereco nao localizado") == "tratativa"


class TestStatusD:
    def test_mapeamentos(self):
        assert normalizar_status_d("Chegada na transportadora") == "recebido"
        assert normalizar_status_d("Saiu para entrega") == "em_rota"
        assert normalizar_status_d("Associado a roteiro") == "em_manifesto"
        assert normalizar_status_d("Entrega realizada") == "entregue"
        assert normalizar_status_d("Cliente ausente") == "tratativa"


class TestStatusE:
    def test_mapeamentos(self):
        assert normalizar_status_e("123 - ASSINATURA ANEXADA") == "entregue"
        assert normalizar_status_e("050 - SAIDA EFETIVA") == "recebido"
        assert normalizar_status_e("010 - MANIFESTADO") == "em_manifesto"
        assert normalizar_status_e("999 - AVARIA") == "tratativa"
