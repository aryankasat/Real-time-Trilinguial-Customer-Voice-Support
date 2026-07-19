import os
import uuid
import asyncio
import aiohttp
from contextlib import asynccontextmanager
from fastapi import FastAPI, HTTPException
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from pydantic import BaseModel

from livekit.api import AccessToken, VideoGrants

from pipecat.pipeline.pipeline import Pipeline
from pipecat.pipeline.task import PipelineWorker, PipelineParams
from pipecat.workers.runner import WorkerRunner
from pipecat.frames.frames import TextFrame, EndFrame

from app.processors.output_capture import OutputCapture
from app.services.tts_factory import create_tts_service


class SynthesizeRequest(BaseModel):
    text: str


def generate_livekit_token(room_name: str, identity: str) -> str:
    api_key = os.getenv("LIVEKIT_API_KEY", "devkey")
    api_secret = os.getenv("LIVEKIT_API_SECRET", "secret")
    token = AccessToken(api_key, api_secret)
    token.with_identity(identity)
    token.with_grants(VideoGrants(room_join=True, room=room_name))
    return token.to_jwt()


@asynccontextmanager
async def lifespan(app: FastAPI):
    app.state.session = aiohttp.ClientSession()
    yield
    await app.state.session.close()


app = FastAPI(lifespan=lifespan, title="Trilingual WebRTC TTS Orchestrator API")


async def run_pipeline(room_name: str, bot_token: str, text: str, lang: str):
    """
    Runs the TTS→LiveKit pipeline. Polls the underlying LiveKit room object
    directly to detect when the user participant joins, then queues frames.
    """
    try:
        session = app.state.session
        livekit_url = os.getenv("LIVEKIT_API_URL", "ws://127.0.0.1:7880")

        tts = create_tts_service(lang, session)

        from pipecat.transports.livekit.transport import LiveKitTransport, LiveKitParams
        params = LiveKitParams(audio_out_sample_rate=16000)
        transport = LiveKitTransport(
            url=livekit_url,
            token=bot_token,
            room_name=room_name,
            params=params
        )

        pipeline = Pipeline([
            tts,
            OutputCapture(lang),
            transport.output(),
        ])

        task = PipelineWorker(
            pipeline,
            params=PipelineParams(),
            enable_rtvi=False,          # No RTVI protocol — plain TextFrame passthrough
            enable_turn_tracking=False, # No user/bot turn tracking needed
            idle_timeout_secs=None,     # No idle timeout — pipeline runs until EndFrame
        )
        runner = WorkerRunner(handle_sigint=False)
        await runner.add_workers(task)

        print(f"\n[Orchestrator] Bot joining room '{room_name}'...")

        async def wait_then_queue():
            """
            Poll transport._client.room.remote_participants directly — no event system.
            This is the most reliable way to detect user join in output-only mode.
            """
            print(f"[Orchestrator] Polling for user participant in room '{room_name}'...")
            elapsed = 0.0
            timeout = 15.0
            poll_interval = 0.2

            # Wait for transport client to be initialized (setup() called by StartFrame)
            while elapsed < 2.0:
                try:
                    _ = transport._client.room
                    break  # room object exists
                except Exception:
                    await asyncio.sleep(0.1)
                    elapsed += 0.1

            # Reset elapsed for participant polling
            elapsed = 0.0
            while elapsed < timeout:
                try:
                    participants = transport._client.room.remote_participants
                    if participants:
                        identity = list(participants.values())[0].identity
                        print(f"[Orchestrator] Participant '{identity}' detected in room '{room_name}'!")
                        # Give WebRTC audio subscription 1.5s to fully settle
                        await asyncio.sleep(1.5)
                        break
                except Exception as e:
                    pass  # room not ready yet

                await asyncio.sleep(poll_interval)
                elapsed += poll_interval

            if elapsed >= timeout:
                print(f"[Orchestrator] No user joined after {timeout}s — sending anyway.")

            print(f"[Orchestrator] Queuing TextFrame + EndFrame for '{room_name}'...")
            await task.queue_frames([TextFrame(text), EndFrame()])

        await asyncio.gather(runner.run(), wait_then_queue())
        print(f"[Orchestrator] Pipeline finished for room '{room_name}'")

    except Exception as e:
        import traceback
        print(f"[Error] Pipeline failed for room '{room_name}': {e}")
        traceback.print_exc()


@app.post("/api/synthesize")
async def api_synthesize(req: SynthesizeRequest):
    if not req.text.strip():
        raise HTTPException(status_code=400, detail="Text payload cannot be empty")

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

    room_name = f"room_{uuid.uuid4().hex[:12]}"
    bot_token = generate_livekit_token(room_name, f"bot_{uuid.uuid4().hex[:4]}")
    user_token = generate_livekit_token(room_name, f"user_{uuid.uuid4().hex[:4]}")
    livekit_url = os.getenv("LIVEKIT_API_URL", "ws://127.0.0.1:7880")

    asyncio.create_task(run_pipeline(room_name, bot_token, req.text, lang))

    return {
        "room": room_name,
        "token": user_token,
        "url": livekit_url,
        "language": lang,
        "provider": cfg["provider"],
        "provider_url": cfg["url"] or ("http://localhost:5000" if cfg["provider"] == "piper_http" else "mock")
    }


@app.get("/")
async def read_index():
    if not os.path.exists("static/index.html"):
        raise HTTPException(status_code=404, detail="static/index.html not found.")
    return FileResponse("static/index.html")


if os.path.exists("static"):
    app.mount("/static", StaticFiles(directory="static"), name="static")
