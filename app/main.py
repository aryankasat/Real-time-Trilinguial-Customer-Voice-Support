import os
import asyncio
import aiohttp
from contextlib import asynccontextmanager
from fastapi import FastAPI, HTTPException, WebSocket, WebSocketDisconnect
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
from app.processors.language_filter import LanguageFilter
from app.processors.output_capture import OutputCapture
from app.services.tts_factory import create_tts_service

@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup: create shared ClientSession
    app.state.session = aiohttp.ClientSession()
    yield
    # Shutdown: close session
    await app.state.session.close()

app = FastAPI(lifespan=lifespan, title="Trilingual WebSocket TTS Orchestrator API")

@app.websocket("/ws/synthesize")
async def websocket_synthesize(websocket: WebSocket):
    await websocket.accept()
    print("[WebSocket] Client connected")
    try:
        while True:
            # Receive json data from client: {"text": "..."}
            data = await websocket.receive_json()
            text = data.get("text", "").strip()
            if not text:
                continue

            print(f"[WebSocket] Received synthesis request for text: '{text}'")

            # Custom frame processor to push audio frames directly to active WebSocket connection
            class WebSocketAudioSender(FrameProcessor):
                async def process_frame(self, frame: Frame, direction: FrameDirection):
                    await super().process_frame(frame, direction)
                    if isinstance(frame, TTSAudioRawFrame):
                        # Pushes raw 16-bit PCM bytes to client
                        await websocket.send_bytes(frame.audio)
                    await self.push_frame(frame, direction)

            sender = WebSocketAudioSender()
            session = app.state.session

            # Create TTS engine instances for this request
            en_tts = create_tts_service("en_us", session)
            hi_tts = create_tts_service("hi_in", session)
            ar_tts = create_tts_service("ar_eg", session)

            # Parallel routing pipeline
            parallel = ParallelPipeline(
                [LanguageFilter("en_us"), en_tts, OutputCapture("en_us")],
                [LanguageFilter("hi_in"), hi_tts, OutputCapture("hi_in")],
                [LanguageFilter("ar_eg"), ar_tts, OutputCapture("ar_eg")]
            )
            
            pipeline = Pipeline([parallel, sender])

            # Instantiate Pipecat task and runner
            task = PipelineWorker(pipeline, params=PipelineParams())
            runner = WorkerRunner()
            await runner.add_workers(task)

            # Queue frames to start and end worker
            await task.queue_frames([TextFrame(text), EndFrame()])

            # Run pipeline synchronously for this text block
            await runner.run()

            # Notify the client that synthesis for this text is finished
            await websocket.send_json({"type": "done"})
            print(f"[WebSocket] Synthesis complete for text: '{text}'")

    except WebSocketDisconnect:
        print("[WebSocket] Client disconnected")
    except Exception as e:
        print(f"[WebSocket Error] Exception occurred: {e}")

# Serve UI static index.html at root
@app.get("/")
async def read_index():
    if not os.path.exists("static/index.html"):
        raise HTTPException(status_code=404, detail="static/index.html not found.")
    return FileResponse("static/index.html")

# Serve other static files
if os.path.exists("static"):
    app.mount("/static", StaticFiles(directory="static"), name="static")
