import asyncio
import aiohttp
from pipecat.processors.frame_processor import FrameProcessor, FrameDirection
from pipecat.frames.frames import (
    Frame,
    TextFrame,
    TTSAudioRawFrame,
    TTSStartedFrame,
    TTSStoppedFrame,
    EndFrame
)


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
            await self.push_frame(frame, direction)


class LocalHttpTTSService(FrameProcessor):
    """
    Custom FrameProcessor that calls a self-hosted TTS HTTP API and streams
    raw PCM audio bytes downstream via TTSAudioRawFrame.
    """
    def __init__(self, language: str, api_url: str, session: aiohttp.ClientSession):
        super().__init__()
        self.language = language
        self.api_url = api_url
        self.session = session
        self._synthesis_lock = asyncio.Lock()

    async def process_frame(self, frame: Frame, direction: FrameDirection):
        # Always call super() first — handles StartFrame/CancelFrame/etc lifecycle
        await super().process_frame(frame, direction)

        if isinstance(frame, TextFrame):
            async with self._synthesis_lock:
                print(f"[{self.language.upper()} TTS] Synthesizing '{frame.text}' via {self.api_url}")
                await self.push_frame(TTSStartedFrame(), direction)
                try:
                    timeout = aiohttp.ClientTimeout(total=30)
                    payload = {"text": frame.text, "language": self.language}
                    async with self.session.post(
                        self.api_url,
                        json=payload,
                        headers={"Content-Type": "application/json"},
                        timeout=timeout,
                    ) as resp:
                        if resp.status == 200:
                            audio_bytes = await resp.read()
                            print(f"[{self.language.upper()} TTS] Got {len(audio_bytes)} bytes. Pushing to LiveKit...")
                            await self.push_frame(
                                TTSAudioRawFrame(
                                    audio=audio_bytes,
                                    sample_rate=16000,
                                    num_channels=1,
                                ),
                                direction,
                            )
                            # Sleep for the duration of the audio so transport
                            # has time to send all packets before EndFrame arrives
                            duration_secs = len(audio_bytes) / 32000.0
                            print(f"[{self.language.upper()} TTS] Sleeping {duration_secs:.2f}s for playback...")
                            await asyncio.sleep(duration_secs + 1.0)
                        else:
                            body = await resp.text()
                            print(f"[{self.language.upper()} TTS] ERROR: HTTP {resp.status} — {body}")
                except Exception as exc:
                    print(f"[{self.language.upper()} TTS] EXCEPTION during synthesis: {exc!r}")
                    import traceback
                    traceback.print_exc()
                finally:
                    await self.push_frame(TTSStoppedFrame(), direction)

        elif isinstance(frame, EndFrame):
            # Wait for any in-progress synthesis to finish first
            async with self._synthesis_lock:
                await self.push_frame(frame, direction)
        else:
            await self.push_frame(frame, direction)
