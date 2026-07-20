import os
import io
import torch
import numpy as np
import scipy.signal
from fastapi import FastAPI, HTTPException, Response
from pydantic import BaseModel
import uvicorn

from contextlib import asynccontextmanager

@asynccontextmanager
async def lifespan(app: FastAPI):
    print("[Model Server Startup] Pre-warming speech models (English, Hindi, Arabic)...")
    try:
        english_fallback_model.load()
        hindi_fallback_model.load()
        arabic_mms_model.load()
        print("[Model Server Startup] All trilingual speech models pre-warmed successfully!")
    except Exception as e:
        print(f"[Model Server Startup Warning] Model pre-warming notice: {e}")
    yield

# Initialize FastAPI App
app = FastAPI(title="Trilingual TTS Model Hosting Server", lifespan=lifespan)

# Pydantic schema matching Pipecat's LocalHttpTTSService payload
class TTSRequest(BaseModel):
    text: str
    language: str

# ------------------------------------------------------------------------------
# Reusable VITS Model Class for Hugging Face Fallbacks
# ------------------------------------------------------------------------------
class VitsTTSModel:
    def __init__(self, model_id: str):
        self.model_id = model_id
        self.tokenizer = None
        self.model = None

    def load(self):
        if self.model is None:
            from transformers import VitsModel, AutoTokenizer
            print(f"[Model Server] Loading VITS model from HF: {self.model_id}...")
            self.tokenizer = AutoTokenizer.from_pretrained(self.model_id)
            self.model = VitsModel.from_pretrained(self.model_id)
            print(f"[Model Server] VITS model {self.model_id} loaded successfully.")

    def synthesize(self, text: str) -> bytes:
        self.load()
        inputs = self.tokenizer(text=text, return_tensors="pt")
        with torch.no_grad():
            outputs = self.model(**inputs)
        
        # Extract raw audio floats (shape: 1, num_samples)
        waveform = outputs.waveform[0].cpu().numpy()
        sampling_rate = self.model.config.sampling_rate
        
        # Resample to 16000Hz mono PCM if required by Pipecat
        if sampling_rate != 16000:
            num_samples = int(len(waveform) * 16000 / sampling_rate)
            waveform = scipy.signal.resample(waveform, num_samples)
            
        # Normalize signal to avoid clipping/distortion
        if len(waveform) > 0:
            max_val = np.abs(waveform).max()
            if max_val > 0:
                waveform = waveform / max_val
                
        # Convert to 16-bit PCM bytes
        pcm_wave = (waveform * 32767).astype(np.int16)
        return pcm_wave.tobytes()

# Pre-instantiate HF fallbacks/models
arabic_mms_model = VitsTTSModel("facebook/mms-tts-ara")
hindi_fallback_model = VitsTTSModel("facebook/mms-tts-hin")
english_fallback_model = VitsTTSModel("facebook/mms-tts-eng")

# ------------------------------------------------------------------------------
# 1. English Endpoint (CosyVoice2 / Fallback VITS)
# ------------------------------------------------------------------------------
cosyvoice_instance = None
try:
    # Attempt to import CosyVoice if installed
    import cosyvoice
    print("[Model Server] CosyVoice package found. Initializing...")
    # cosyvoice_instance = cosyvoice.CosyVoice(...)
except ImportError:
    print("[Model Server] CosyVoice2 package not found. Using Meta MMS-TTS English as fallback.")

@app.post("/tts/en")
async def tts_english(req: TTSRequest):
    if not req.text.strip():
        raise HTTPException(status_code=400, detail="Text cannot be empty")
        
    print(f"[Model Server] English TTS requested: '{req.text}'")
    try:
        if cosyvoice_instance:
            # Placeholder: run real CosyVoice2 inference code if package is available
            # output = cosyvoice_instance.inference_sft(req.text, ...)
            # return audio bytes
            pass
        else:
            # Run high-quality HF MMS fallback
            audio_bytes = english_fallback_model.synthesize(req.text)
            return Response(content=audio_bytes, media_type="audio/pcm")
    except Exception as e:
        print(f"[Model Server Error] English synthesis failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))

# ------------------------------------------------------------------------------
# 2. Hindi Endpoint (IndicF5 / Fallback VITS)
# ------------------------------------------------------------------------------
f5_tts_instance = None
try:
    # Attempt to import F5-TTS / IndicF5 if installed
    import f5_tts
    print("[Model Server] IndicF5 / F5-TTS package found. Initializing...")
except ImportError:
    print("[Model Server] IndicF5 / F5-TTS package not found. Using Meta MMS-TTS Hindi as fallback.")

@app.post("/tts/hi")
async def tts_hindi(req: TTSRequest):
    if not req.text.strip():
        raise HTTPException(status_code=400, detail="Text cannot be empty")
        
    print(f"[Model Server] Hindi TTS requested: '{req.text}'")
    try:
        if f5_tts_instance:
            # Placeholder: run IndicF5 inference
            pass
        else:
            # Run high-quality HF MMS Hindi fallback
            audio_bytes = hindi_fallback_model.synthesize(req.text)
            return Response(content=audio_bytes, media_type="audio/pcm")
    except Exception as e:
        print(f"[Model Server Error] Hindi synthesis failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))

# ------------------------------------------------------------------------------
# 3. Arabic Endpoint (Meta MMS-TTS)
# ------------------------------------------------------------------------------
@app.post("/tts/ar")
async def tts_arabic(req: TTSRequest):
    if not req.text.strip():
        raise HTTPException(status_code=400, detail="Text cannot be empty")
        
    print(f"[Model Server] Arabic TTS requested: '{req.text}'")
    try:
        audio_bytes = arabic_mms_model.synthesize(req.text)
        return Response(content=audio_bytes, media_type="audio/pcm")
    except Exception as e:
        print(f"[Model Server Error] Arabic synthesis failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))

# ------------------------------------------------------------------------------
# Server Entry Point
# ------------------------------------------------------------------------------
if __name__ == "__main__":
    # Host on port 5000, which matches the .env local_api configuration
    uvicorn.run(app, host="127.0.0.1", port=5000)
