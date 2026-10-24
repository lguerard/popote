from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    database_url: str = "postgresql+asyncpg://popote:popote@db:5432/popote"
    ollama_base_url: str = "http://ollama:11434"
    ollama_model: str = "gemma4:12b"
    # Fenêtre de contexte d'Ollama (tokens) : le défaut du serveur (2048-4096)
    # tronque les pages longues. Plus grand = plus de VRAM.
    ollama_num_ctx: int = 8192
    # Modèle qui lit les photos (recettes photographiées, texte des images).
    # Vide : OLLAMA_MODEL, à condition qu'il accepte les images (gemma4).
    # Un modèle à part double la VRAM nécessaire s'ils tournent ensemble.
    ollama_vision_model: str = ""
    # Si définie, Claude REMPLACE Ollama pour toutes les tâches IA.
    claude_api_key: str = ""
    # Extraction des recettes et lecture des photos.
    claude_model: str = "claude-sonnet-5-5"
    # Tâches courtes (nutrition, description du plat pour l'image) : plus
    # rapide et bien moins cher, largement suffisant pour quelques lignes.
    claude_fast_model: str = "claude-haiku-5-5"
    secret_key: str = "changeme"
    # large-v3-turbo : décodeur réduit (4 couches au lieu de 32), plusieurs
    # fois plus rapide que large-v3 pour une précision très proche, ~1 Go
    # de VRAM en int8_float16.
    whisper_model: str = "large-v3-turbo"
    whisper_device: str = "cuda"
    # Précision sur GPU : int8_float16 (moitié moins de VRAM) ou float16.
    whisper_compute_type: str = "int8_float16"
    # Utilisé seulement si le GPU est indisponible : large-v3 sur CPU est
    # trop lent pour tenir dans le délai d'extraction.
    whisper_cpu_model: str = "small"
    # Modèle CPU gardé en mémoire ce temps (s) après la dernière vidéo, puis
    # libéré ; 0 = libéré après chaque vidéo. Sur GPU, Whisper est toujours
    # libéré dès la fin de la transcription (VRAM rendue à Ollama).
    whisper_idle_unload_seconds: int = 300
    # Décharge le modèle Ollama du GPU avant une transcription Whisper.
    whisper_free_gpu: bool = True
    media_dir: str = "/app/media"
    # Cookies d'un compte (format Netscape, exportés du navigateur) pour les
    # vidéos qui exigent une connexion, Instagram surtout. Ignoré si absent.
    ytdlp_cookies_file: str = "/app/cookies/cookies.txt"
    imagegen_base_url: str = "http://imagegen:8001"
    # Décharge le modèle Ollama du GPU avant chaque génération d'image : sans
    # ça, il n'y a pas la place de générer sur le GPU (repli CPU très lent).
    image_gen_free_gpu: bool = True
    # Le premier compte s'inscrit toujours (amorcage). Les suivants
    # seulement si ceci est vrai : Popote est publie sur un domaine
    # public, une inscription libre laisserait n'importe qui entrer.
    allow_signup: bool = False

    @property
    def vision_model(self) -> str:
        return self.ollama_vision_model or self.ollama_model

    @property
    def use_claude(self) -> bool:
        return bool(self.claude_api_key)

    class Config:
        env_file = ".env"


settings = Settings()
