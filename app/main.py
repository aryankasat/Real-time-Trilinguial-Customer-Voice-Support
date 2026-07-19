import os
import uuid
import asyncio
import aiohttp
from contextlib import asynccontextmanager
from fastapi import FastAPI, HTTPException, Response
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from pydantic import BaseModel

from livekit.api import AccessToken, VideoGrants

from pipecat.pipeline.pipeline import Pipeline
from pipecat.pipeline.parallel_pipeline import ParallelPipeline
from pipecat.pipeline.task import PipelineWorker, PipelineParams
from pipecat.pipeline.runner import WorkerRunner
from pipecat.processors.frame_processor import FrameProcessor, FrameDirection
from pipecat.frames.frames import Frame, TextFrame, EndFrame

from app.utils.language import detect_language
from app.processors.language_filter import LanguageFilter
from app.processors.output_capture import OutputCapture
from app.services.tts_factory import create_tts_service

class DelayProcessor(FrameProcessor):
    def __init__(self, delay_seconds: float):
        super().__init__()
        self.delay_seconds = delay_seconds
        self.webrtc_established = False
        self._lock = asyncio.Lock()

    async def process_frame(self, frame: Frame, direction: FrameDirection):
        await super().process_frame(frame, direction)
        
        # We only want to delay user-facing and termination frames (TextFrame/EndFrame)
        # to allow transport connection/subscription to settle first.
        if isinstance(frame, (TextFrame, EndFrame)) and not self.webrtc_established:
            async with self._lock:
                if not self.webrtc_established:
                    print(f"[Orchestrator DelayProcessor] Holding frame '{type(frame).__name__}' for {self.delay_seconds} seconds to establish WebRTC path...")
                    await asyncio.sleep(self.delay_seconds)
                    self.webrtc_established = True
                    print("[Orchestrator DelayProcessor] WebRTC negotiation window complete. Releasing frames.")
                    
        await self.push_frame(frame, direction)

class SynthesizeRequest(BaseModel):
    text: str

def generate_livekit_token(room_name: str, identity: str) -> str:
    """
    Generates a LiveKit JWT AccessToken with room join grants.
    """
    api_key = os.getenv("LIVEKIT_API_KEY", "devkey")
    api_secret = os.getenv("LIVEKIT_API_SECRET", "secret")
    
    token = AccessToken(api_key, api_secret)
    token.with_identity(identity)
    
    grants = VideoGrants(
        room_join=True,
        room=room_name
    )
    token.with_grants(grants)
    return token.to_jwt()

@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup: create shared ClientSession
    app.state.session = aiohttp.ClientSession()
    yield
    # Shutdown: close session
    await app.state.session.close()

app = FastAPI(lifespan=lifespan, title="Trilingual WebRTC TTS Orchestrator API")

async def run_pipeline(room_name: str, bot_token: str, text: str):
    """
    Asynchronous background worker that runs the Pipecat routing pipeline
    and pushes voice streams to the LiveKit room via WebRTC.
    """
    try:
        session = app.state.session
        livekit_url = os.getenv("LIVEKIT_API_URL", "ws://127.0.0.1:7880")
        
        # Instantiate local/mock TTS engine services
        en_tts = create_tts_service("en_us", session)
        hi_tts = create_tts_service("hi_in", session)
        ar_tts = create_tts_service("ar_eg", session)

        # Setup LiveKit transport with 16kHz audio out sample rate matching our synthesizers
        from pipecat.transports.livekit.transport import LiveKitTransport, LiveKitParams
        params = LiveKitParams(audio_out_sample_rate=16000)
        transport = LiveKitTransport(
            url=livekit_url,
            token=bot_token,
            room_name=room_name,
            params=params
        )

        # Build ParallelPipeline branching
        parallel = ParallelPipeline(
            [LanguageFilter("en_us"), en_tts, OutputCapture("en_us")],
            [LanguageFilter("hi_in"), hi_tts, OutputCapture("hi_in")],
            [LanguageFilter("ar_eg"), ar_tts, OutputCapture("ar_eg")]
        )
        
        # Pipe parallel outputs straight to WebRTC transport output, using DelayProcessor to hold synthesis for 2.5s
        pipeline = Pipeline([DelayProcessor(2.5), parallel, transport.output()])

        # Initialize Pipecat task and runner
        task = PipelineWorker(pipeline, params=PipelineParams())
        runner = WorkerRunner()
        await runner.add_workers(task)

        # Queue the text frame and EndFrame upfront to prevent premature worker shutdown
        await task.queue_frames([TextFrame(text), EndFrame()])

        print(f"\n[Orchestrator Backend] Bot connecting to LiveKit room '{room_name}' via WebRTC...")
        await runner.run()
        print(f"[Orchestrator Backend] Bot successfully completed playback and left room '{room_name}'")
    except Exception as e:
        print(f"[Error] Background pipeline execution failed in room '{room_name}': {e}")

@app.post("/api/synthesize")
async def api_synthesize(req: SynthesizeRequest):
    if not req.text.strip():
        raise HTTPException(status_code=400, detail="Text payload cannot be empty")

    # Pre-flight check TTS service availability
    from app.config import get_tts_config
    from app.utils.language import detect_language
    import socket
    from urllib.parse import urlparse

    lang = detect_language(req.text)
    cfg = get_tts_config(lang)
    if cfg["provider"] in ("local_api", "piper_http"):
        tts_url = cfg["url"]
        if tts_url:
            parsed = urlparse(tts_url)
            host = parsed.hostname or "localhost"
            port = parsed.port or (80 if parsed.scheme == "http" else 443)
            try:
                with socket.create_connection((host, port), timeout=1.0):
                    pass
            except Exception:
                raise HTTPException(
                    status_code=503,
                    detail=f"TTS server at {tts_url} is offline. Please make sure the model server is running."
                )

    # Generate a unique room name and tokens
    room_name = f"room_{uuid.uuid4().hex[:12]}"
    bot_token = generate_livekit_token(room_name, f"bot_{uuid.uuid4().hex[:4]}")
    user_token = generate_livekit_token(room_name, f"user_{uuid.uuid4().hex[:4]}")
    
    livekit_url = os.getenv("LIVEKIT_API_URL", "ws://127.0.0.1:7880")
    
    # Spawn Pipecat transport connection in the background
    asyncio.create_task(run_pipeline(room_name, bot_token, req.text))
    
    # Return LiveKit connection properties instantly to client
    return {
        "room": room_name,
        "token": user_token,
        "url": livekit_url,
        "language": lang,
        "provider": cfg["provider"],
        "provider_url": cfg["url"] or ("http://localhost:5000" if cfg["provider"] == "piper_http" else "mock")
    }

# Serve UI static index.html at root
@app.get("/")
async def read_index():
    if not os.path.exists("static/index.html"):
        raise HTTPException(status_code=404, detail="static/index.html not found.")
    return FileResponse("static/index.html")

# Serve other static files
if os.path.exists("static"):
    app.mount("/static", StaticFiles(directory="static"), name="static")
