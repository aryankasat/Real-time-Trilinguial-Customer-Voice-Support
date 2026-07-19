import asyncio
import aiohttp
from pipecat.processors.frame_processor import FrameProcessor, FrameDirection
from pipecat.frames.frames import (
    Frame,
    TextFrame,
    TTSAudioRawFrame,
    TTSStartedFrame,
    TTSStoppedFrame
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
            # Pass all other frames downstream
            await self.push_frame(frame, direction)


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
                        raise Exception(f"Self-hosted TTS API returned status: {response.status}")
            except Exception as e:
                print(f"[Error] Failed to connect to self-hosted TTS API at {self.api_url}: {e}")
                raise e
            finally:
                # Send TTSStoppedFrame
                await self.push_frame(TTSStoppedFrame(), direction)
        else:
            await self.push_frame(frame, direction)
