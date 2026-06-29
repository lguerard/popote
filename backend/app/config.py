from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    database_url: str = "postgresql+asyncpg://kitchenai:kitchenai@db:5432/kitchenai"
    ollama_base_url: str = "http://ollama:11434"
    ollama_model: str = "qwen2.5:14b"
    claude_api_key: str = ""
    secret_key: str = "changeme"
    whisper_model: str = "large-v3"
    whisper_device: str = "cuda"
    media_dir: str = "/app/media"

    @property
    def use_claude(self) -> bool:
        return bool(self.claude_api_key)

    class Config:
        env_file = ".env"


settings = Settings()
