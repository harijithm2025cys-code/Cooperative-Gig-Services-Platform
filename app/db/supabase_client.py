from functools import lru_cache
from supabase import create_client, Client
from app.config import settings

_client_instance: Client = None

def init_supabase() -> Client:
    global _client_instance
    if _client_instance is None:
        if not settings.SUPABASE_URL or not settings.SUPABASE_KEY:
            raise RuntimeError(
                "Cannot initialize Supabase client: SUPABASE_URL or SUPABASE_KEY is missing."
            )
        _client_instance = create_client(settings.SUPABASE_URL, settings.SUPABASE_KEY)
    return _client_instance

# Global client access
try:
    supabase_client: Client = init_supabase()
except Exception as e:
    # Allow import during testing or build phases where env might not be loaded yet
    supabase_client = None

def get_supabase_client() -> Client:
    """Dependency injection provider for FastAPI endpoints."""
    global _client_instance
    if _client_instance is None:
        return init_supabase()
    return _client_instance
