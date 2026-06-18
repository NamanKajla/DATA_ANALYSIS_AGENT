import os
from pydantic_settings import BaseSettings, SettingsConfigDict
from dotenv import load_dotenv

backend_env = os.path.join(os.path.dirname(__file__), "../.env")
if os.path.exists(backend_env):
    load_dotenv(dotenv_path=backend_env)
else:
    load_dotenv(dotenv_path=os.path.join(os.path.dirname(__file__), "../../.env"))

class Settings(BaseSettings):
    GROQ_API_KEY: str = os.getenv("GROQ_API_KEY", "")
    SUPABASE_URL: str = os.getenv("SUPABASE_URL", "")
    SUPABASE_KEY: str = os.getenv("SUPABASE_KEY", "")

    # Model config
    MODEL_NAME: str = "llama-3.3-70b-versatile"

    # Retry Limit Constants
    MAX_RETRIES: int = 3
    FALLBACK_ERROR_MESSAGE: str = (
        "I'm having trouble analyzing this specific dataset. "
        "Could you clarify your question or check your data format?"
    )

    # Sandbox configuration
    SANDBOX_DOCKER_IMAGE: str = "data-agent-sandbox:latest"
    SANDBOX_TIMEOUT_SECONDS: int = 30

    # Security configuration
    # Set REQUIRE_DOCKER=true in production to prevent local exec() fallback
    REQUIRE_DOCKER: bool = os.getenv("REQUIRE_DOCKER", "false").lower() == "true"

    # Max upload file size in bytes (default 100 MB)
    MAX_UPLOAD_SIZE_BYTES: int = int(os.getenv("MAX_UPLOAD_SIZE_BYTES", str(100 * 1024 * 1024)))

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore"
    )

settings = Settings()