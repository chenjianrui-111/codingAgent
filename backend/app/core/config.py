from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    app_name: str = "coding-agent"
    env: str = "development"
    api_prefix: str = "/api/v1"

    oceanbase_host: str = "127.0.0.1"
    oceanbase_port: int = 2881
    oceanbase_user: str = "root@test"
    oceanbase_password: str = ""
    oceanbase_database: str = "coding_agent"

    run_workspace: str = "/tmp"
    run_test_command: str = "pytest -q"
    context_repo_name: str = "codingAgent"
    context_branch_name: str = "main"
    memory_max_items_per_session: int = 80
    memory_keep_recent_items: int = 36
    memory_summary_batch_size: int = 16
    memory_context_char_budget: int = 5000
    project_vector_dim: int = 64
    project_context_max_items: int = 12
    deep_agent_persona_name: str = "coding_deep_agent"
    deep_agent_max_steps: int = 16
    deep_agent_default_retry_budget: int = 2
    deep_agent_artifact_dir: str = ".deepagent/runs"

    # LLM (ZhiPu AI – OpenAI-compatible)
    llm_api_key: str = ""
    llm_base_url: str = "https://open.bigmodel.cn/api/paas/v4"
    llm_model: str = "glm-4-plus"
    llm_vision_model: str = "glm-4v-plus"
    llm_max_tokens: int = 4096

    # Auth / Tenant
    auth_required: bool = False
    auth_access_token_ttl_hours: int = 24
    auth_google_verify_mode: str = "tokeninfo"  # tokeninfo | dev_unverified
    auth_google_client_ids: str = ""
    auth_default_tenant_prefix: str = "personal"
    invite_accept_url_base: str = "http://127.0.0.1:5173"
    invite_email_enabled: bool = False
    invite_email_provider: str = "noop"  # noop | resend | sendgrid
    invite_email_required: bool = False
    invite_email_from: str = ""
    invite_email_reply_to: str = ""
    invite_email_subject_prefix: str = "[Coding Agent]"
    resend_api_key: str = ""
    sendgrid_api_key: str = ""

    # Sandbox
    sandbox_workspace_root: str = "/tmp/codex-sandbox"
    allowed_shell_commands: str = "git,ls,find,grep,python,node,npm,pip,pytest,make,cat,head,tail"

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    @property
    def sqlalchemy_database_url(self) -> str:
        return (
            f"mysql+pymysql://{self.oceanbase_user}:{self.oceanbase_password}"
            f"@{self.oceanbase_host}:{self.oceanbase_port}/{self.oceanbase_database}?charset=utf8mb4"
        )


settings = Settings()
