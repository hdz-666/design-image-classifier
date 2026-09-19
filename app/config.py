from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    # Auth
    api_key: str

    # CORS - only matters for the /test sanity page and any direct browser
    # calls; normal traffic is proxied through the existing backend.
    allowed_origins: str = ""

    # Catalog / index / thumbnail locations on disk
    catalog_dir: str = "./data/catalog"
    index_dir: str = "./data/index"
    thumbs_dir: str = "./data/thumbs"

    # Embedding model. Supported: "clip-vit-b32", "dinov2-small", "dinov2-base"
    model_name: str = "dinov2-small"

    # Base URL this service is reachable at (e.g. your Cloudflare Tunnel
    # hostname, or the Railway URL). Used to build signed image URLs.
    public_base_url: str = "http://localhost:8000"

    @property
    def origins_list(self) -> list[str]:
        return [o.strip() for o in self.allowed_origins.split(",") if o.strip()]


settings = Settings()
