import os
import sys
import asyncio
import certifi

# Bypass macOS SSL certificate verification issues globally for requests/urllib/nltk
os.environ["SSL_CERT_FILE"] = certifi.where()
os.environ["REQUESTS_CA_BUNDLE"] = certifi.where()

from dotenv import load_dotenv
load_dotenv()

from pipecat.pipeline.pipeline import Pipeline
from pipecat.pipeline.parallel_pipeline import ParallelPipeline
from pipecat.pipeline.task import PipelineWorker, PipelineParams
from pipecat.pipeline.runner import WorkerRunner
from pipecat.processors.frame_processor import FrameProcessor, FrameDirection
from pipecat.frames.frames import (
    Frame,
    TextFrame,
    EndFrame,
    SystemFrame,
    TTSAudioRawFrame,
    TTSStartedFrame,
    TTSStoppedFrame
)
from pipecat.services.tts_service import TTSService, TTSSettings

# ------------------------------------------------------------------------------
# 1. Script-based Language Detector
# ------------------------------------------------------------------------------
def detect_language(text: str) -> str:
    """
    Detects language based on character set analysis:
    - Devanagari script mapping -> hi_in (Hindi)
    - Arabic script mapping -> ar_eg (Arabic)
    - Latin alphabet mapping -> en_us (English)
    """
    counts = {"en_us": 0, "hi_in": 0, "ar_eg": 0}
    for char in text:
        cp = ord(char)
        if 0x0900 <= cp <= 0x097F:
            counts["hi_in"] += 1
        elif 0x0600 <= cp <= 0x06FF:
            counts["ar_eg"] += 1
        elif (0x0041 <= cp <= 0x005A) or (0x0061 <= cp <= 0x007A):
            counts["en_us"] += 1
            
    max_lang = max(counts, key=counts.get)
    if counts[max_lang] > 0:
        return max_lang
    return "en_us"  # Fallback default

# ------------------------------------------------------------------------------
# 2. Mock TTS Service
# ------------------------------------------------------------------------------
class MockTTSService(FrameProcessor):
    def __init__(self, language: str, **kwargs):
        super().__init__(**kwargs)
        self.language = language

    async def process_frame(self, frame: Frame, direction: FrameDirection):
        await super().process_frame(frame, direction)
        
        if isinstance(frame, TextFrame):
            print(f"[{self.language.upper()} Mock TTS] Synthesizing speech for text: '{frame.text}'")
            # 1. Send TTSStartedFrame
            await self.push_frame(TTSStartedFrame(), direction)
            
            # 2. Simulate synthesis delay
            await asyncio.sleep(0.4)
            
            # 3. Send TTSAudioRawFrame (1 second of 16kHz mono 16-bit PCM silence)
            mock_audio_bytes = b"\x00" * 32000
            await self.push_frame(TTSAudioRawFrame(audio=mock_audio_bytes, sample_rate=16000, num_channels=1), direction)
            
            # 4. Send TTSStoppedFrame
            await self.push_frame(TTSStoppedFrame(), direction)
        else:
            # Pass all other frames downstream
            await self.push_frame(frame, direction)

# ------------------------------------------------------------------------------
# 3. Custom Language Filter Frame Processor
# ------------------------------------------------------------------------------
class LanguageFilter(FrameProcessor):
    def __init__(self, target_lang: str):
        super().__init__()
        self.target_lang = target_lang

    async def process_frame(self, frame: Frame, direction: FrameDirection):
        await super().process_frame(frame, direction)
        if isinstance(frame, TextFrame):
            lang = detect_language(frame.text)
            if lang != self.target_lang:
                # Discard the text frame if it belongs to a different pipeline branch
                return
            else:
                print(f"\n[LanguageFilter - {self.target_lang.upper()}] Match! Processing TextFrame: '{frame.text}'")
        
        # Pass the matching TextFrame, and all other control/system frames downstream
        await self.push_frame(frame, direction)

# ------------------------------------------------------------------------------
# 4. Custom Output Capture Frame Processor
# ------------------------------------------------------------------------------
class OutputCapture(FrameProcessor):
    def __init__(self, language: str):
        super().__init__()
        self.language = language

    async def process_frame(self, frame: Frame, direction: FrameDirection):
        await super().process_frame(frame, direction)
        if isinstance(frame, TTSAudioRawFrame):
            print(f"[OutputCapture - {self.language.upper()}] Captured TTS audio frame ({len(frame.audio)} bytes, sample rate: {frame.sample_rate}Hz)")
        elif isinstance(frame, TTSStartedFrame):
            print(f"[OutputCapture - {self.language.upper()}] Received TTSStartedFrame")
        elif isinstance(frame, TTSStoppedFrame):
            print(f"[OutputCapture - {self.language.upper()}] Received TTSStoppedFrame")
            
        await self.push_frame(frame, direction)

# ------------------------------------------------------------------------------
# 5. Factory Function for TTS Services
# ------------------------------------------------------------------------------
def create_tts_service(language_code: str) -> TTSService:
    """
    Dynamically loads TTS configurations from .env.
    Instantiates actual Pipecat services if configured, otherwise falls back to MockTTSService.
    """
    provider_key = f"TTS_PROVIDER_{language_code.upper()}"
    model_key = f"TTS_MODEL_{language_code.upper()}"
    voice_key = f"TTS_VOICE_{language_code.upper()}"
    
    provider = os.getenv(provider_key, "mock").lower()
    model = os.getenv(model_key, "")
    voice = os.getenv(voice_key, "")
    
    print(f"[Init] Creating TTS Service for {language_code} (Provider: {provider}, Model: '{model}', Voice: '{voice}')")
    
    if provider == "elevenlabs":
        from pipecat.services.elevenlabs.tts import ElevenLabsTTSService
        api_key = os.getenv("ELEVENLABS_API_KEY", "")
        if not api_key:
            print(f"[Warning] ELEVENLABS_API_KEY not found in .env. Falling back to Mock TTS.")
            return MockTTSService(language_code)
        settings = ElevenLabsTTSService.Settings(
            model=model or "eleven_multilingual_v2",
            voice=voice or "21m00Tcm4TlvDq8ikWAM"
        )
        return ElevenLabsTTSService(api_key=api_key, settings=settings)
        
    elif provider == "cartesia":
        from pipecat.services.cartesia.tts import CartesiaTTSService
        api_key = os.getenv("CARTESIA_API_KEY", "")
        if not api_key:
            print(f"[Warning] CARTESIA_API_KEY not found in .env. Falling back to Mock TTS.")
            return MockTTSService(language_code)
        settings = CartesiaTTSService.Settings(
            model=model or "sonic-english",
            voice=voice or "c16198f2-850d-400a-b286-6c7038e219aa"
        )
        return CartesiaTTSService(api_key=api_key, settings=settings)
        
    elif provider == "openai":
        from pipecat.services.openai.tts import OpenAITTSService
        api_key = os.getenv("OPENAI_API_KEY", "")
        if not api_key:
            print(f"[Warning] OPENAI_API_KEY not found in .env. Falling back to Mock TTS.")
            return MockTTSService(language_code)
        settings = OpenAITTSService.Settings(
            model=model or "tts-1",
            voice=voice or "alloy"
        )
        return OpenAITTSService(api_key=api_key, settings=settings)
        
    else:
        return MockTTSService(language_code)

# ------------------------------------------------------------------------------
# 6. Main Runner & Testing Loop
# ------------------------------------------------------------------------------
async def feed_inputs(task: PipelineWorker):
    """
    Feeds test text inputs of different languages into the pipeline task.
    """
    # Wait for the pipeline runner to fully initialize and StartFrame to propagate
    await asyncio.sleep(2.0)
    
    samples = [
        # English
        "Hello, how can I help you today?",
        # Hindi
        "नमस्ते, आज मैं आपकी क्या सहायता कर सकता हूँ?",
        # Arabic
        "مرحباً، كيف يمكنني مساعدتك اليوم؟",
        # English fallback
        "Thank you for calling. Have a great day!"
    ]
    
    for text in samples:
        print(f"\n[Test Feeder] Injecting TextFrame: '{text}'")
        await task.queue_frame(TextFrame(text))
        # Give enough time for the mock TTS to synthesize audio and log outputs
        await asyncio.sleep(2.0)
        
    print("\n[Test Feeder] Completed feeding all test samples. Signaling pipeline task shutdown...")
    await task.queue_frame(EndFrame())

async def main():
    # 1. Initialize language-specific TTS services
    en_tts = create_tts_service("en_us")
    hi_tts = create_tts_service("hi_in")
    ar_tts = create_tts_service("ar_eg")
    
    # 2. Setup orchestrator routing pipeline using ParallelPipeline
    parallel = ParallelPipeline(
        [LanguageFilter("en_us"), en_tts, OutputCapture("en_us")],
        [LanguageFilter("hi_in"), hi_tts, OutputCapture("hi_in")],
        [LanguageFilter("ar_eg"), ar_tts, OutputCapture("ar_eg")]
    )
    main_pipeline = Pipeline([parallel])
    
    # 4. Initialize Pipecat task and runner
    runner = WorkerRunner()
    task = PipelineWorker(main_pipeline, params=PipelineParams())
    
    # Register the worker task with the runner
    await runner.add_workers(task)
    
    # 5. Create background task to feed test frames
    feeder_task = asyncio.create_task(feed_inputs(task))
    
    # 6. Execute pipeline
    print("\n[Orchestrator] Starting Pipecat Pipeline runner...")
    await runner.run()
    
    # Wait for feeder background task to wrap up
    await feeder_task
    print("[Orchestrator] Pipeline execution completed successfully.")

if __name__ == "__main__":
    asyncio.run(main())
