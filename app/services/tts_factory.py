import aiohttp
from pipecat.processors.frame_processor import FrameProcessor
from app.config import get_tts_config
from app.services.local_tts import MockTTSService, LocalHttpTTSService

def create_tts_service(language_code: str, session: aiohttp.ClientSession) -> FrameProcessor:
    """
    Dynamically loads TTS configurations from env and instantiates
    local/self-hosted TTS engines or fallbacks.
    """
    cfg = get_tts_config(language_code)
    provider = cfg["provider"]
    model = cfg["model"]
    voice = cfg["voice"]
    url = cfg["url"]
    
    print(f"[Init] Creating TTS Service for {language_code} (Provider: {provider}, Model: '{model}', Voice: '{voice}', URL: '{url}')")
    
    if provider == "piper_http":
        from pipecat.services.piper.tts import PiperHttpTTSService
        server_url = url or "http://localhost:5000"
        settings = PiperHttpTTSService.Settings(
            voice=voice or "en_US-ryan-high"
        )
        return PiperHttpTTSService(base_url=server_url, aiohttp_session=session, settings=settings)
        
    elif provider == "local_api":
        server_url = url or "http://localhost:8000/tts"
        return LocalHttpTTSService(language_code, server_url, session)
        
    else:
        return MockTTSService(language_code)
