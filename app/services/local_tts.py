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
            await self.push_frame(TTSStartedFrame(), direction)
            await asyncio.sleep(0.2)

            import math
            # 1 second of 440Hz sine wave tone at 16kHz mono 16-bit PCM
            sample_rate = 16000
            num_samples = 16000
            tone_samples = bytearray()
            for i in range(num_samples):
                val = int(10000 * math.sin(2 * math.pi * 440 * i / sample_rate))
                tone_samples.extend(val.to_bytes(2, byteorder='little', signed=True))

            chunk_size = 1600
            for i in range(0, len(tone_samples), chunk_size):
                chunk = bytes(tone_samples[i:i + chunk_size])
                await self.push_frame(TTSAudioRawFrame(audio=chunk, sample_rate=16000, num_channels=1), direction)
                await asyncio.sleep(0.048)

            await self.push_frame(TTSStoppedFrame(), direction)
            await self.push_frame(EndFrame(), direction)
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
                            print(f"[{self.language.upper()} TTS] Got {len(audio_bytes)} bytes. Streaming to LiveKit...")
                            
                            # Stream in 50ms chunks (1600 bytes for 16kHz 16-bit mono PCM)
                            chunk_size = 1600
                            for i in range(0, len(audio_bytes), chunk_size):
                                chunk = audio_bytes[i:i + chunk_size]
                                await self.push_frame(
                                    TTSAudioRawFrame(
                                        audio=chunk,
                                        sample_rate=16000,
                                        num_channels=1,
                                    ),
                                    direction,
                                )
                                await asyncio.sleep(0.048)
                            print(f"[{self.language.upper()} TTS] Finished streaming audio frames.")
                        else:
                            body = await resp.text()
                            print(f"[{self.language.upper()} TTS] ERROR: HTTP {resp.status} — {body}")
                except Exception as exc:
                    print(f"[{self.language.upper()} TTS] EXCEPTION during synthesis: {exc!r}")
                    import traceback
                    traceback.print_exc()
                finally:
                    await self.push_frame(TTSStoppedFrame(), direction)
                    await self.push_frame(EndFrame(), direction)

        elif isinstance(frame, EndFrame):
            # Wait for any in-progress synthesis to finish first
            async with self._synthesis_lock:
                await self.push_frame(frame, direction)
        else:
            await self.push_frame(frame, direction)
