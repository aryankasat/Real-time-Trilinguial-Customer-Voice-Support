from pipecat.processors.frame_processor import FrameProcessor, FrameDirection
from pipecat.frames.frames import Frame, TextFrame
from app.utils.language import detect_language

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
