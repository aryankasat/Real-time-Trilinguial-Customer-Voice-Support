import io
import wave

def pcm_to_wav(pcm_bytes: bytes, sample_rate: int = 16000) -> bytes:
    """
    Wraps raw 16-bit PCM bytes inside a standard WAV header so browsers can play it natively.
    """
    wav_buf = io.BytesIO()
    with wave.open(wav_buf, "wb") as wav_file:
        wav_file.setnchannels(1)       # Mono
        wav_file.setsampwidth(2)       # 16-bit (2 bytes per sample)
        wav_file.setframerate(sample_rate)
        wav_file.writeframes(pcm_bytes)
    return wav_buf.getvalue()
