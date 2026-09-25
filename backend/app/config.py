from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    database_url: str = "postgresql+asyncpg://popote:popote@db:5432/popote"
    ollama_base_url: str = "http://ollama:11434"
    ollama_model: str = "qwen2.5:14b"
    # Fenêtre de contexte d'Ollama (tokens) : le défaut du serveur (2048-4096)
    # tronque les pages longues. Plus grand = plus de VRAM.
    ollama_num_ctx: int = 8192
    claude_api_key: str = ""
    secret_key: str = "changeme"
    whisper_model: str = "large-v3"
    whisper_device: str = "cuda"
    media_dir: str = "/app/media"
    imagegen_base_url: str = "http://imagegen:8001"
    # Décharge le modèle Ollama du GPU avant chaque génération d'image : sans
    # ça, il n'y a pas la place de générer sur le GPU (repli CPU très lent).
    image_gen_free_gpu: bool = True
    # Le premier compte s'inscrit toujours (amorcage). Les suivants
    # seulement si ceci est vrai : Popote est publie sur un domaine
    # public, une inscription libre laisserait n'importe qui entrer.
    allow_signup: bool = False

    @property
    def use_claude(self) -> bool:
        return bool(self.claude_api_key)

    class Config:
        env_file = ".env"


settings = Settings()
