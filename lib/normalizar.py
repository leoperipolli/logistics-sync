import unicodedata
from datetime import date, timedelta

PREPOSICOES = {"de", "do", "da", "dos", "das", "e"}


def converter_data(valor: str | None) -> date | None:
    """DD/MM/YYYY → date. Ignora parte de hora se presente."""
    if not valor:
        return None
    parte = str(valor).strip().split(" ")[0]
    try:
        dia, mes, ano = parte.split("/")
        return date(int(ano), int(mes), int(dia))
    except (ValueError, AttributeError):
        return None


def normalizar_cidade(nome: str) -> str:
    """Remove acentos, capitaliza palavras, preposições em minúsculo."""
    sem_acento = unicodedata.normalize("NFD", nome)
    sem_acento = "".join(c for c in sem_acento if unicodedata.category(c) != "Mn")
    palavras = sem_acento.strip().lower().split()
    return " ".join(
        p if (i > 0 and p in PREPOSICOES) else p.capitalize()
        for i, p in enumerate(palavras)
    )


def excel_para_data(serial: float) -> date:
    """Converte serial Excel para date."""
    return date(1899, 12, 30) + timedelta(days=int(serial))


def normalizar_status_tms(localizacao: str) -> str:
    """TMS web das transportadoras A e B — campo de localização do volume."""
    loc = localizacao.lower()
    if "no armazem" in loc:
        return "recebido"
    if "em entrega" in loc:
        return "em_rota"
    if "apontado para" in loc:
        return "em_manifesto"
    return "tratativa"


def normalizar_status_c(desc_status: str) -> str:
    """Relatório de pendências da transportadora C — coluna Desc_Ultimo_Status."""
    s = desc_status.lower()
    if "recebido cd" in s:
        return "recebido"
    if "processo de entrega" in s:
        return "em_rota"
    if "em rota" in s or "manifesto" in s:
        return "em_manifesto"
    return "tratativa"


def normalizar_status_d(ocorrencia: str) -> str:
    """CSV via RPA — mapeamento baseado no campo Última Ocorrência."""
    oc = ocorrencia.lower()
    if "chegada na transportadora" in oc:
        return "recebido"
    if "saiu para entrega" in oc:
        return "em_rota"
    if "associado a roteiro" in oc:
        return "em_manifesto"
    if "entrega realizada" in oc:
        return "entregue"
    return "tratativa"


def normalizar_status_e(status: str) -> str:
    """Tabela HTML do portal — campo ÚLTIMO STATUS. Mapeamento por contains."""
    s = status.lower()
    if "assinatura anexada" in s or "entrega realizada" in s:
        return "entregue"
    if "saida efetiva" in s:
        return "recebido"
    if "manifestado" in s:
        return "em_manifesto"
    return "tratativa"
