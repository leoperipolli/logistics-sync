"""Helper para download de relatórios via SSRS/NTLM — fluxo 3 passos."""

import asyncio
import re
from urllib.parse import urlsplit

import httpx
from bs4 import BeautifulSoup
from httpx_ntlm import HttpNtlmAuth

_HEADERS_BROWSER = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "pt-BR,pt;q=0.9,en-US;q=0.8",
}


def _urls_base(report_url: str) -> tuple[str, str]:
    """Retorna (origin, raiz do ReportServer) a partir da URL do ReportViewer."""
    partes = urlsplit(report_url)
    origin = f"{partes.scheme}://{partes.netloc}"
    raiz = partes.path.split("/Pages/")[0]
    return origin, f"{origin}{raiz}"


async def baixar_ssrs_excel(
    report_url: str,
    usuario: str,
    senha: str,
    data_inicio: str,
    data_fim: str,
    filial: str,
) -> bytes:
    """Download de relatório SSRS via NTLM — executa em thread (cliente síncrono)."""
    auth = HttpNtlmAuth(usuario, senha)
    return await asyncio.to_thread(
        _baixar_sync, report_url, auth, usuario, data_inicio, data_fim, filial
    )


def _baixar_sync(
    report_url: str,
    auth: HttpNtlmAuth,
    usuario: str,
    data_inicio: str,
    data_fim: str,
    filial: str,
) -> bytes:
    origin, raiz = _urls_base(report_url)
    with httpx.Client(auth=auth, follow_redirects=True, timeout=300, headers=_HEADERS_BROWSER) as client:
        # Passo 1: GET → campos hidden + índice dinâmico da filial
        get_resp = client.get(report_url)
        get_resp.raise_for_status()

        soup = BeautifulSoup(get_resp.text, "html.parser")
        post_data = {
            inp["name"]: inp.get("value", "")
            for inp in soup.find_all("input", type="hidden")
            if inp.get("name")
        }
        if not post_data:
            raise RuntimeError("SSRS: nenhum campo hidden encontrado — verifique credenciais NTLM")

        dropdown = soup.find("div", id=re.compile(r"ctl04_ctl09_divDropDown"))
        if not dropdown:
            raise RuntimeError("SSRS: dropdown de filial não encontrado")
        labels = dropdown.find_all("label")
        indice_filial = next(
            (str(i) for i, lbl in enumerate(labels) if lbl.get_text(strip=True) == filial),
            None,
        )
        if indice_filial is None:
            disponiveis = [lbl.get_text(strip=True) for lbl in labels]
            raise RuntimeError(f"SSRS: filial {filial!r} não encontrada. Disponíveis: {disponiveis}")

        post_data["AjaxScriptManager"] = "AjaxScriptManager|ReportViewerControl$ctl04$ctl00"
        post_data.update({
            "__EVENTTARGET": "",
            "__EVENTARGUMENT": "",
            "__ASYNCPOST": "true",
            "ReportViewerControl$ctl04$ctl03$txtValue": data_inicio,
            "ReportViewerControl$ctl04$ctl05$txtValue": data_fim,
            "ReportViewerControl$ctl04$ctl07$txtValue": usuario,
            "ReportViewerControl$ctl04$ctl09$txtValue": filial,
            "ReportViewerControl$ctl04$ctl09$divDropDown$ctl01$HiddenIndices": indice_filial,
            "ReportViewerControl$ctl04$ctl00": "Exibir Relatório",
        })

        # Passo 2: POST → ExecutionID + ControlID
        post_url = str(get_resp.url)
        post_resp = client.post(post_url, data=post_data, headers={
            "X-MicrosoftAjax": "Delta=true",
            "X-Requested-With": "XMLHttpRequest",
            "Origin": origin,
            "Referer": post_url,
        })
        if not post_resp.is_success:
            raise RuntimeError(f"SSRS POST {post_resp.status_code}: {post_resp.text[:300]}")

        execution_id = re.search(r"ExecutionID=([a-z0-9]+)", post_resp.text)
        control_id = re.search(r"ControlID=([a-f0-9\-]+)", post_resp.text)
        if not execution_id or not control_id:
            raise RuntimeError(f"SSRS: ExecutionID/ControlID não encontrados: {post_resp.text[:300]}")

        # Passo 3: GET Excel — Culture=1046 (pt-BR) obrigatório
        export_url = (
            f"{raiz}/Reserved.ReportViewerWebControl.axd"
            f"?ExecutionID={execution_id.group(1)}&ControlID={control_id.group(1)}"
            "&Culture=1046&UICulture=1046&CultureOverrides=True&UICultureOverrides=True"
            "&ReportStack=1&OpType=Export&Format=EXCEL"
            "&ContentDisposition=OnlyHtmlInline"
            "&FileName=Relatorio"
        )
        export_resp = client.get(export_url, headers={"Referer": post_url})
        export_resp.raise_for_status()
        return export_resp.content
