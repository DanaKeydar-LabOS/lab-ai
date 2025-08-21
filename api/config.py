import os
from typing import List
from pathlib import Path

# Load environment variables from .env file
try:
    from dotenv import load_dotenv

    # Look for .env file in the current directory (api/) or parent directory
    env_file = Path(__file__).parent / '.env'
    if env_file.exists():
        load_dotenv(env_file)
        print(f"Loaded environment from: {env_file}")
    else:
        parent_env = Path(__file__).parent.parent / '.env'
        if parent_env.exists():
            load_dotenv(parent_env)
            print(f"Loaded environment from: {parent_env}")
        else:
            print("No .env file found, using system environment variables")
except ImportError:
    print("python-dotenv not installed, using system environment variables only")


class Settings:
    """Application settings and configuration"""

    # Qdrant Configuration
    QDRANT_HOST: str = os.getenv("QDRANT_HOST", "qdrant")
    QDRANT_PORT: int = int(os.getenv("QDRANT_PORT", "6333"))

    # Ollama Configuration
    OLLAMA_HOST: str = os.getenv("OLLAMA_HOST", "ollama")
    OLLAMA_PORT: int = int(os.getenv("OLLAMA_PORT", "11434"))

    # Model Configuration
    EMBEDDING_MODEL: str = os.getenv("EMBEDDING_MODEL", "nomic-embed-text")
    CHAT_MODEL: str = os.getenv("CHAT_MODEL", "llama3.2")

    # Vector Store Configuration
    COLLECTION_NAME: str = "lab_schema"
    VECTOR_SIZE: int = 768  # nomic-embed-text vector size

    # Knowledge Base Configuration - handle both local and Docker paths
    KB_PATH: str = os.getenv("KB_PATH", "/app/kb")

    # If running locally and KB_PATH is relative, make it absolute
    if not Path(KB_PATH).is_absolute():
        KB_PATH = str(Path(__file__).parent.parent / KB_PATH.lstrip('../'))

    # POC Tables - only these are available for queries
    POC_TABLES: List[str] = [
        "o", "r", "sa", "rr", "ep", "tat", "c", "cti",
        "m", "i", "mc", "mac", "ao", "ar", "asa", "arr", "aep"
    ]

    # Database Configuration
    DB_CONFIG = {
        "host": os.getenv("LAB_DB_HOST", "localhost"),
        "port": int(os.getenv("LAB_DB_PORT", "5432")),
        "database": os.getenv("LAB_DB_NAME", "lab_db"),
        "user": os.getenv("LAB_DB_USER", "lab_user"),
        "password": os.getenv("LAB_DB_PASSWORD", "lab_password"),
        "driver": os.getenv("LAB_DB_DRIVER", "postgresql")
    }

    # API Configuration
    LOG_LEVEL: str = os.getenv("LOG_LEVEL", "INFO")

    # Query Configuration
    MAX_QUERY_LIMIT: int = int(os.getenv("MAX_QUERY_LIMIT", "1000"))
    DEFAULT_QUERY_LIMIT: int = int(os.getenv("DEFAULT_QUERY_LIMIT", "100"))
    QUERY_TIMEOUT_SECONDS: int = int(os.getenv("QUERY_TIMEOUT_SECONDS", "60"))

    # Cache Configuration
    CACHE_TTL_SECONDS: int = int(os.getenv("CACHE_TTL_SECONDS", "300"))
    CACHE_MAX_SIZE: int = int(os.getenv("CACHE_MAX_SIZE", "50"))


# Create global settings instance
settings = Settings()

# Debug: Print current configuration (remove in production)
if __name__ == "__main__" or os.getenv("LOG_LEVEL") == "DEBUG":
    print("=== Current Configuration ===")
    print(f"QDRANT_HOST: {settings.QDRANT_HOST}")
    print(f"QDRANT_PORT: {settings.QDRANT_PORT}")
    print(f"OLLAMA_HOST: {settings.OLLAMA_HOST}")
    print(f"OLLAMA_PORT: {settings.OLLAMA_PORT}")
    print(f"KB_PATH: {settings.KB_PATH}")
    print(f"KB_PATH exists: {Path(settings.KB_PATH).exists()}")
    print("==========================")