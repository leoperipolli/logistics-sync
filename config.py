from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env", env_file_encoding="utf-8", extra="ignore"
    )

    database_url: str

    # TMS web compartilhado pelas transportadoras A e B
    tms_base_url: str = "https://tms.example.com/bin"
    tms_endpoint_login: str = "login"
    tms_endpoint_pendencias: str = "pendencias"
    tms_endpoint_entregas: str = "entregas"
    tms_endpoint_download: str = "download"

    transportadora_a_usuario: str = ""
    transportadora_a_cpf: str = ""
    transportadora_a_senha: str = ""
    transportadora_a_sigla_emp: str = "AAA"
    transportadora_a_sigla_fil: str = "F01"

    transportadora_b_usuario: str = ""
    transportadora_b_cpf: str = ""
    transportadora_b_senha: str = ""
    transportadora_b_sigla_emp: str = "BBB"
    transportadora_b_sigla_fil: str = "F02"

    # Transportadora C: pendências via API de RPA + entregas via SSRS (NTLM)
    transportadora_c_usuario: str = ""
    transportadora_c_senha: str = ""
    transportadora_c_ssrs_url: str = (
        "https://reports.example.com/ReportServer/Pages/ReportViewer.aspx"
        "?%2fReports%2fProdutividade&rc%3ashowbackbutton=true"
    )
    transportadora_c_filial: str = "BASE01"
    transportadora_c_recipe_id: str = ""

    # Transportadora D: relatório CSV via API de RPA
    transportadora_d_recipe_id: str = ""

    # Transportadora E: portal web com login + tabela HTML
    transportadora_e_url: str = "https://portal.example.com"
    transportadora_e_usuario: str = ""
    transportadora_e_senha: str = ""

    rpa_url: str = "http://localhost:3000"
    rpa_api_key: str = ""

    waha_url: str = ""
    waha_api_key: str = ""
    waha_chat_id: str = ""


settings = Settings()
