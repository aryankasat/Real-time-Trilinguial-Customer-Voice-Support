import os
import sys
import asyncio
import certifi
import aiohttp

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
# 2.5 Local HTTP TTS Service (Self-Hosted Model Endpoint)
# ------------------------------------------------------------------------------
class LocalHttpTTSService(FrameProcessor):
    """
    Custom FrameProcessor to communicate with any self-hosted TTS engine exposing an HTTP API.
    Sends raw text and returns audio bytes, which are then passed downstream.
    """
    def __init__(self, language: str, api_url: str, session: aiohttp.ClientSession):
        super().__init__()
        self.language = language
        self.api_url = api_url
        self.session = session

    async def process_frame(self, frame: Frame, direction: FrameDirection):
        await super().process_frame(frame, direction)
        
        if isinstance(frame, TextFrame):
            print(f"[{self.language.upper()} Local HTTP TTS] Requesting speech from self-hosted endpoint: {self.api_url} for: '{frame.text}'")
            # Send TTSStartedFrame to downstream transport/sink
            await self.push_frame(TTSStartedFrame(), direction)
            
            try:
                headers = {"Content-Type": "application/json"}
                data = {"text": frame.text, "language": self.language}
                
                async with self.session.post(self.api_url, json=data, headers=headers, timeout=10) as response:
                    if response.status == 200:
                        audio_bytes = await response.read()
                        print(f"[{self.language.upper()} Local HTTP TTS] Synthesized {len(audio_bytes)} bytes.")
                        await self.push_frame(
                            TTSAudioRawFrame(audio=audio_bytes, sample_rate=16000, num_channels=1),
                            direction
                        )
                    else:
                        print(f"[Error] Self-hosted TTS API returned status: {response.status}")
                        # Fallback mock
                        mock_audio = b"\x00" * 32000
                        await self.push_frame(
                            TTSAudioRawFrame(audio=mock_audio, sample_rate=16000, num_channels=1),
                            direction
                        )
            except Exception as e:
                print(f"[Error] Failed to connect to self-hosted TTS API at {self.api_url}: {e}")
                # Fallback mock
                mock_audio = b"\x00" * 32000
                await self.push_frame(
                    TTSAudioRawFrame(audio=mock_audio, sample_rate=16000, num_channels=1),
                    direction
                )
                
            # Send TTSStoppedFrame
            await self.push_frame(TTSStoppedFrame(), direction)
        else:
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
def create_tts_service(language_code: str, session: aiohttp.ClientSession) -> TTSService:
    """
    Dynamically loads TTS configurations from .env.
    Instantiates self-hosted local services (piper_http, local_api) or falls back to MockTTSService.
    """
    provider_key = f"TTS_PROVIDER_{language_code.upper()}"
    model_key = f"TTS_MODEL_{language_code.upper()}"
    voice_key = f"TTS_VOICE_{language_code.upper()}"
    url_key = f"TTS_URL_{language_code.upper()}"
    
    provider = os.getenv(provider_key, "mock").lower()
    model = os.getenv(model_key, "")
    voice = os.getenv(voice_key, "")
    url = os.getenv(url_key, "")
    
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
    async with aiohttp.ClientSession() as session:
        # 1. Initialize language-specific TTS services
        en_tts = create_tts_service("en_us", session)
        hi_tts = create_tts_service("hi_in", session)
        ar_tts = create_tts_service("ar_eg", session)
        
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
