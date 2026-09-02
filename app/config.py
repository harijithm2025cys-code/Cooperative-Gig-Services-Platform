import os
from typing import Optional
from dotenv import load_dotenv

# Load environment variables from .env if present
load_dotenv()

class Settings:
    PROJECT_NAME: str = "Cooperative Gig Services Platform API"
    PROJECT_DESCRIPTION: str = (
        "Marketplace connecting households needing services with verified "
        "workers through Labour Cooperative Societies."
    )
    VERSION: str = "1.0.0"
    API_V1_STR: str = ""

    SUPABASE_URL: str = os.getenv("SUPABASE_URL", "")
    SUPABASE_KEY: str = os.getenv("SUPABASE_KEY", "")
    JWT_SECRET: str = os.getenv("JWT_SECRET", "super_secret_cooperative_gig_platform_key_2026_sih")
    ALGORITHM: str = os.getenv("ALGORITHM", "HS256")
    ACCESS_TOKEN_EXPIRE_MINUTES: int = int(os.getenv("ACCESS_TOKEN_EXPIRE_MINUTES", "1440"))

    def validate_config(self):
        if not self.SUPABASE_URL or not self.SUPABASE_KEY:
            raise ValueError(
                "Missing critical environment variables: SUPABASE_URL and/or SUPABASE_KEY. "
                "Please configure them in your .env file or environment."
            )

settings = Settings()
