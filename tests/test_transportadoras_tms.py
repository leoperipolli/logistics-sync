"""Parse dos relatórios do TMS web (transportadoras A e B). Dados fictícios."""

from datetime import date

from transportadoras.transportadora_a import TransportadoraA
from transportadoras.transportadora_b import TransportadoraB

_a = TransportadoraA()
_b = TransportadoraB()

# Pendências: 2 linhas de cabeçalho, separador ";"
# col 1 = código, 6 = cidade, 7 = bairro, 13 = prazo, 15 = última ocorrência, 16 = localização
_PEND_CSV = (
    "﻿"
    "relatorio de pendencias\n"
    "c0;codigo;c2;c3;c4;c5;cidade;bairro;c8;c9;c10;c11;c12;prazo;c14;ultima_oc;localizacao\n"
    "x;100001;x;x;x;x;PORTO ALEGRE;Centro;x;x;x;x;x;15/04/2026;x;SEPARADO PARA PROCESSO DE ENTREGA;NO ARMAZEM F01\n"
    "x;100002;x;x;x;x;SAO PAULO;Bairro Teste;x;x;x;x;x;20/04/2026;x;EM TRANSITO;EM ENTREGA\n"
    "x;;x;x;x;x;CIDADE TESTE;x;x;x;x;x;x;x;x;;APONTADO PARA ROTA 01\n"
).encode("utf-8")

# Entregas: 1 linha de cabeçalho
# col 1 = código, 2 = data de entrega, 8 = UF/cidade, 11 = prazo, 12 = ocorrência
_ENT_CSV = (
    "﻿"
    "c0;codigo;data_entrega;c3;c4;c5;c6;c7;cidade_uf;c9;c10;prazo;ocorrencia\n"
    "x;100002;14/04/2026;x;x;x;x;x;RS/PORTO ALEGRE;x;x;18/04/2026;NOME DO RECEBEDOR: CLIENTE TESTE\n"
    "x;100003;13/04/2026;x;x;x;x;x;SP/SAO PAULO;x;x;19/04/2026;ENTREGUE SEM ASSINATURA\n"
).encode("utf-8")


class TestPendencias:
    def test_ignora_codigo_vazio(self):
        assert set(_a._parse_pendencias(_PEND_CSV)) == {"100001", "100002"}

    def test_campos_normalizados(self):
        vol = _a._parse_pendencias(_PEND_CSV)["100001"]
        assert vol["cidade"] == "Porto Alegre"
        assert vol["prazo_entrega"] == date(2026, 4, 15)
        assert vol["status"] == "recebido"

    def test_ocorrencia_rotineira_nao_vira_observacao(self):
        result = _a._parse_pendencias(_PEND_CSV)
        assert result["100001"]["observacao_cliente"] is None
        assert result["100002"]["observacao_cliente"] == "EM TRANSITO"


class TestEntregas:
    def test_a_so_aceita_com_nome_do_recebedor(self):
        assert set(_a._parse_entregas(_ENT_CSV)) == {"100002"}

    def test_b_aceita_tambem_entregue(self):
        assert set(_b._parse_entregas(_ENT_CSV)) == {"100002", "100003"}

    def test_remove_uf_da_cidade_e_converte_datas(self):
        vol = _a._parse_entregas(_ENT_CSV)["100002"]
        assert vol["cidade"] == "Porto Alegre"
        assert vol["data_entrega"] == date(2026, 4, 14)
        assert vol["prazo_entrega"] == date(2026, 4, 18)
