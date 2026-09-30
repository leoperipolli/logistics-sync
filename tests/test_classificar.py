from lib.classificar import chave_dupla, chave_simples


def test_chave_simples():
    # BD | Relatório
    assert chave_simples(False, True) == "01"   # novo no relatório → insere
    assert chave_simples(True, False) == "10"   # sumiu do relatório → atenção
    assert chave_simples(True, True) == "11"    # nos dois → atualiza status


def test_chave_dupla():
    # BD | Pendências | Entregas
    assert chave_dupla(False, True, False) == "010"  # pendência nova
    assert chave_dupla(True, False, True) == "101"   # volume conhecido foi entregue
    assert chave_dupla(True, True, True) == "111"    # conflito: pendente e entregue


def test_chave_dupla_cobre_os_8_casos():
    chaves = {
        chave_dupla(bool(b), bool(p), bool(e))
        for b in range(2) for p in range(2) for e in range(2)
    }
    assert chaves == {"000", "001", "010", "011", "100", "101", "110", "111"}
