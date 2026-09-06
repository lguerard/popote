from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    database_url: str = "postgresql+asyncpg://popote:popote@db:5432/popote"
    ollama_base_url: str = "http://ollama:11434"
    ollama_model: str = "qwen2.5:14b"
    claude_api_key: str = ""
    secret_key: str = "changeme"
    whisper_model: str = "large-v3"
    whisper_device: str = "cuda"
    media_dir: str = "/app/media"
    # URL publique réelle de l'app, utilisée pour construire les liens de
    # réinitialisation. Derrière un tunnel Cloudflare, l'URL vue par le backend
    # n'est pas celle que la personne ouvrira.
    public_url: str = ""
    # Cookie de session en Secure : à laisser à True dès que l'app est servie
    # en HTTPS. Mettre à False pour un accès en http:// sur le LAN.
    cookie_secure: bool = True

    @property
    def use_claude(self) -> bool:
        return bool(self.claude_api_key)

    class Config:
        env_file = ".env"


settings = Settings()
