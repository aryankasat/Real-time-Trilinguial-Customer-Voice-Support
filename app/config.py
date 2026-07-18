import os
from dotenv import load_dotenv

# Load environment variables at package startup
load_dotenv()

def get_tts_config(language_code: str) -> dict:
    """
    Retrieves the provider, model, voice, and URL configurations for a given language code.
    """
    lang_upper = language_code.upper()
    return {
        "provider": os.getenv(f"TTS_PROVIDER_{lang_upper}", "mock").lower(),
        "model": os.getenv(f"TTS_MODEL_{lang_upper}", ""),
        "voice": os.getenv(f"TTS_VOICE_{lang_upper}", ""),
        "url": os.getenv(f"TTS_URL_{lang_upper}", "")
    }
