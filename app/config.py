import os
from dotenv import load_dotenv

# Construct absolute path to the root .env file
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DOTENV_PATH = os.path.join(BASE_DIR, ".env")

# Load environment variables at package startup
load_dotenv(DOTENV_PATH)

def get_tts_config(language_code: str) -> dict:
    """
    Retrieves the provider, model, voice, and URL configurations for a given language code.
    """
    # Reload environment variables from .env dynamically
    load_dotenv(DOTENV_PATH, override=True)
    
    lang_upper = language_code.upper()
    return {
        "provider": os.getenv(f"TTS_PROVIDER_{lang_upper}", "local_api").lower(),
        "model": os.getenv(f"TTS_MODEL_{lang_upper}", ""),
        "voice": os.getenv(f"TTS_VOICE_{lang_upper}", ""),
        "url": os.getenv(f"TTS_URL_{lang_upper}", "")
    }
