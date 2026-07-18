from pipecat.processors.frame_processor import FrameProcessor, FrameDirection
from pipecat.frames.frames import (
    Frame,
    TTSAudioRawFrame,
    TTSStartedFrame,
    TTSStoppedFrame
)

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
