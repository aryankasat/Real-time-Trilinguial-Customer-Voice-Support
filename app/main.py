import os
import aiohttp
from contextlib import asynccontextmanager
from fastapi import FastAPI, HTTPException, Response
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from pydantic import BaseModel

from pipecat.pipeline.pipeline import Pipeline
from pipecat.pipeline.parallel_pipeline import ParallelPipeline
from pipecat.pipeline.task import PipelineWorker, PipelineParams
from pipecat.pipeline.runner import WorkerRunner
from pipecat.processors.frame_processor import FrameProcessor, FrameDirection
from pipecat.frames.frames import Frame, TextFrame, EndFrame, TTSAudioRawFrame

from app.utils.language import detect_language
from app.utils.audio import pcm_to_wav
from app.processors.language_filter import LanguageFilter
from app.processors.output_capture import OutputCapture
from app.services.tts_factory import create_tts_service

class SynthesizeRequest(BaseModel):
    text: str

@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup: create shared ClientSession
    app.state.session = aiohttp.ClientSession()
    yield
    # Shutdown: close session
    await app.state.session.close()

app = FastAPI(lifespan=lifespan, title="Trilingual TTS Orchestrator API")

@app.post("/api/synthesize")
async def api_synthesize(req: SynthesizeRequest):
    if not req.text.strip():
        raise HTTPException(status_code=400, detail="Text payload cannot be empty")

    audio_chunks = []
    sample_rate = 16000

    # Custom processor to collect raw audio output frames from the pipeline
    class AudioCollector(FrameProcessor):
        async def process_frame(self, frame: Frame, direction: FrameDirection):
            await super().process_frame(frame, direction)
            nonlocal sample_rate
            if isinstance(frame, TTSAudioRawFrame):
                audio_chunks.append(frame.audio)
                sample_rate = frame.sample_rate
            await self.push_frame(frame, direction)

    collector = AudioCollector()

    # Create TTS engine instances for this request using shared aiohttp session
    en_tts = create_tts_service("en_us", app.state.session)
    hi_tts = create_tts_service("hi_in", app.state.session)
    ar_tts = create_tts_service("ar_eg", app.state.session)

    # Setup ParallelPipeline routing
    parallel = ParallelPipeline(
        [LanguageFilter("en_us"), en_tts, OutputCapture("en_us")],
        [LanguageFilter("hi_in"), hi_tts, OutputCapture("hi_in")],
        [LanguageFilter("ar_eg"), ar_tts, OutputCapture("ar_eg")]
    )
    # Assemble full pipeline, capturing all outputs downstream of the parallel merger
    pipeline = Pipeline([parallel, collector])

    # Instantiate Pipecat task and runner
    task = PipelineWorker(pipeline, params=PipelineParams())
    runner = WorkerRunner()
    await runner.add_workers(task)

    # Inject the TextFrame and signaling EndFrame into the task queue
    await task.queue_frames([TextFrame(req.text), EndFrame()])

    # Run pipeline to completion
    print(f"\n[Orchestrator Backend] Running trilingual routing pipeline for text: '{req.text}'")
    await runner.run()

    if not audio_chunks:
        raise HTTPException(status_code=500, detail="TTS pipeline yielded no audio output")

    # Wrap raw PCM frames into browser-playable WAV
    wav_bytes = pcm_to_wav(b"".join(audio_chunks), sample_rate)
    print(f"[Orchestrator Backend] Synthesis completed. Yielded {len(wav_bytes)} WAV bytes.")

    return Response(content=wav_bytes, media_type="audio/wav")

# Serve UI static index.html at root
@app.get("/")
async def read_index():
    if not os.path.exists("static/index.html"):
        raise HTTPException(status_code=404, detail="static/index.html not found. Build frontend first.")
    return FileResponse("static/index.html")

# Serve other static files
if os.path.exists("static"):
    app.mount("/static", StaticFiles(directory="static"), name="static")
