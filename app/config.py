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
    ENVIRONMENT: str = os.getenv("ENVIRONMENT", "development")

    SUPABASE_URL: str = os.getenv(
        "SUPABASE_URL",
        "https://fwfurlmpbtkxpkigiupi.supabase.co"
    )
    SUPABASE_KEY: str = os.getenv(
        "SUPABASE_KEY",
        "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6ImZ3ZnVybG1wYnRreHBraWdpdXBpIiwicm9sZSI6InNlcnZpY2Vfcm9sZSIsImlhdCI6MTc4ODI4MjM4NSwiZXhwIjoyMTAzODU4Mzg1fQ.epwXW8dTejjscvG6fVnRe3qsAodBhL_4c0QH2pDGe-8"
    )
    JWT_SECRET: str = os.getenv(
        "JWT_SECRET",
        "super_secret_cooperative_gig_platform_key_2026_sih"
    )
    ALGORITHM: str = os.getenv("ALGORITHM", "HS256")
    ACCESS_TOKEN_EXPIRE_MINUTES: int = int(os.getenv("ACCESS_TOKEN_EXPIRE_MINUTES", "1440"))

    # Google Maps Integration Key for Location & Proximity Tracking
    GOOGLE_MAPS_API_KEY: str = os.getenv("GOOGLE_MAPS_API_KEY", "AIzaSyCo_8I7zNvhpBL2KUYzqCGhueJl0B6Gl6Y")

    # Razorpay Payment Gateway (Test Mode / Environment Secrets)
    RAZORPAY_KEY_ID: str = os.getenv("RAZORPAY_KEY_ID", "rzp_test_coop_gig_2026")
    RAZORPAY_KEY_SECRET: str = os.getenv("RAZORPAY_KEY_SECRET", "test_secret_coop_gig_2026")
    RAZORPAY_WEBHOOK_SECRET: str = os.getenv("RAZORPAY_WEBHOOK_SECRET", "test_webhook_secret_coop_gig_2026")

    # CORS Allowed Origins
    ALLOWED_ORIGINS: str = os.getenv("ALLOWED_ORIGINS", "*")

    @property
    def cors_origins(self) -> list:
        if self.ALLOWED_ORIGINS == "*":
            return ["*"]
        return [origin.strip() for origin in self.ALLOWED_ORIGINS.split(",") if origin.strip()]

    def validate_config(self):
        if not self.SUPABASE_URL or not self.SUPABASE_KEY:
            raise ValueError(
                "Missing critical environment variables: SUPABASE_URL and/or SUPABASE_KEY."
            )

settings = Settings()
