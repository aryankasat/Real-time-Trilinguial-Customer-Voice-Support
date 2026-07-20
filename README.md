# SOLID Trilingual Customer Voice Support Web App

This repository provides a production-grade, interactive web application for a **real-time trilingual customer voice support system** supporting three language subsets:
- **English (United States)** (`en_us`)
- **Hindi (India)** (`hi_in`)
- **Arabic (Egypt)** (`ar_eg`)

The system follows **SOLID design principles** (decoupled processors, service factories, modular utilities, and UI components) and combines **Pipecat**, **FastAPI**, **LiveKit WebRTC**, and **Hugging Face MMS / VITS TTS models** to stream synthesized voice tracks back to the browser dynamically with sub-second latency.

---

## 1. Architecture & End-to-End Workflow

Unlike standard static audio file downloads, this application streams raw 16-bit 16kHz PCM audio frames over a live WebRTC media transport channel using LiveKit and Pipecat.

```
┌────────────────────────┐         HTTP POST /api/synthesize          ┌──────────────────────────────────┐
│  Browser Frontend UI   ├───────────────────────────────────────────►│ FastAPI Orchestrator (Port 8000) │
└───────────┬────────────┘                                            └────────────────┬─────────────────┘
            │                                                                          │
            │ (1) Receive room token & URL                                             │ (2) Launch Pipecat
            │                                                                          │     Background Pipeline
            ▼                                                                          ▼
┌────────────────────────┐            WebRTC Media Transport          ┌──────────────────────────────────┐
│ LiveKit JS Client SDK  │◄══════════════════════════════════════════►│ Pipecat Pipeline Worker (Bot)    │
└────────────────────────┘                                            └────────────────┬─────────────────┘
                                                                                       │
                                                                                       │ (3) HTTP POST /tts/{lang}
                                                                                       ▼
                                                                      ┌──────────────────────────────────┐
                                                                      │ Local TTS Model Server (Port 5000)│
                                                                      └──────────────────────────────────┘
```

### Complete Step-by-Step Flow:
1. **User Request**: User enters text in the web interface (e.g. English, Hindi script, or Arabic script).
2. **Language Detection**: The system analyzes character script Unicode ranges (`app/utils/language.py`) to classify the language (`en_us`, `hi_in`, `ar_eg`).
3. **Session Initialization**: `POST /api/synthesize` generates a unique room name and JWT tokens for both the user client and the bot identity, then spawns the Pipecat background pipeline.
4. **Synchronization Guard**: `WaitForParticipantProcessor` holds frame execution until the user client connects to the LiveKit room, ensuring WebRTC audio track subscriptions are ready.
5. **Model Inference**: `LocalHttpTTSService` calls the local model server (`http://127.0.0.1:5000/tts/{lang}`) which runs VITS inference and returns raw 16kHz mono 16-bit PCM audio bytes.
6. **Real-time Streaming**: Audio is chunked into 50ms segments (`1600` bytes) and pushed downstream to `LiveKitOutputTransport` with real-time frame pacing.
7. **Playback & Visualization**: The frontend receives the audio track, plays it out loud via an HTML5 `<audio>` element, and passes the media stream to a WebAudio `AnalyserNode` to render a dynamic canvas waveform.
8. **Graceful Teardown**: Upon completion, `LocalHttpTTSService` pushes an `EndFrame` downstream, closing the WebRTC session cleanly.

---

## 2. Hosted Endpoints & Models

The self-hosted TTS Model Server (`model_server.py`) hosts high-quality speech synthesis models locally on `http://127.0.0.1:5000`:

| Language Subset | API Endpoint | Model / Engine | Provider Key in `.env` |
| :--- | :--- | :--- | :--- |
| **English (US)** (`en_us`) | `POST /tts/en` | `facebook/mms-tts-eng` *(Fallback: CosyVoice2)* | `local_api` |
| **Hindi (IN)** (`hi_in`) | `POST /tts/hi` | `facebook/mms-tts-hin` *(Fallback: IndicF5)* | `local_api` |
| **Arabic (EG)** (`ar_eg`) | `POST /tts/ar` | `facebook/mms-tts-ara` | `local_api` |

### API Payload Schema:
```json
{
  "text": "Your customer support text string here",
  "language": "en_us"
}
```

---

## 3. Codebase Structure (SOLID Principles)

```
├── app/
│   ├── config.py                       # Config loader reading parameters from .env
│   ├── main.py                         # FastAPI web server, lifecycle management & API routing
│   ├── processors/
│   │   ├── language_filter.py          # LanguageFilter custom FrameProcessor
│   │   ├── output_capture.py           # OutputCapture custom FrameProcessor for metrics & logging
│   │   └── wait_for_participant.py     # Synchronization processor delaying synthesis until WebRTC join
│   ├── services/
│   │   ├── local_tts.py                # Self-hosted LocalHttpTTSService & MockTTSService implementations
│   │   └── tts_factory.py              # Service factory creating TTS instances based on config
│   └── utils/
│       ├── audio.py                    # Audio utilities (PCM conversion, resample helpers)
│       └── language.py                 # Unicode character-set script detector
├── static/
│   └── index.html                      # Premium dark-mode glassmorphism Web UI & visualizer
├── model_server.py                     # Self-hosted PyTorch/Transformers VITS model hosting server
├── trilingual_orchestrator.py           # Web application launcher entrypoint
├── download_fleurs.py                  # Google FLEURS dataset downloader script
├── requirements.txt                    # Project Python dependencies
└── .env                                # System configuration & server endpoints
```

---

## 4. Reproducibility Guide

Follow these step-by-step instructions to reproduce and run the entire trilingual voice application locally from scratch.

### Step 1: Environment Setup
1. **Clone the repository and create a virtual environment**:
   ```bash
   python3 -m venv .venv
   source .venv/bin/activate
   ```

2. **Install dependencies**:
   ```bash
   pip install -r requirements.txt
   ```

### Step 2: Environment Configuration
Ensure `.env` contains the local model server endpoints and LiveKit dev server settings:

```env
# TTS Configuration for English
TTS_PROVIDER_EN_US=local_api
TTS_URL_EN_US=http://localhost:5000/tts/en

# TTS Configuration for Hindi
TTS_PROVIDER_HI_IN=local_api
TTS_URL_HI_IN=http://localhost:5000/tts/hi

# TTS Configuration for Arabic
TTS_PROVIDER_AR_EG=local_api
TTS_URL_AR_EG=http://localhost:5000/tts/ar

# LiveKit WebRTC Server Configuration
LIVEKIT_API_URL=ws://127.0.0.1:7880
LIVEKIT_API_KEY=devkey
LIVEKIT_API_SECRET=secret
```

### Step 3: Run the Services (3 Terminal Commands)

To run the complete system, start the three required background services:

#### Terminal 1: LiveKit WebRTC Media Server
```bash
livekit-server --dev
```
*Listens on `ws://127.0.0.1:7880`.*

#### Terminal 2: Local Speech Model Hosting Server
```bash
source .venv/bin/activate
python model_server.py
```
*Listens on `http://127.0.0.1:5000`. On startup, it automatically pre-warms all 3 VITS speech models (English, Hindi, and Arabic) in memory.*

#### Terminal 3: UI & Web Application Orchestrator
```bash
source .venv/bin/activate
python trilingual_orchestrator.py
```
*Listens on `http://127.0.0.1:8000`.*

---

## 5. Verification & Testing

### Testing via Web Browser
1. Open **[http://127.0.0.1:8000](http://127.0.0.1:8000)**.
2. Enter text in English, Hindi (e.g. `नमस्ते, आपका स्वागत है`), or Arabic (e.g. `مرحباً بك في الدعم الصوتي`).
3. Click **Generate Speech**.
4. Observe the live system data flow pipeline step indicators, listen to the speech output, and view the animated waveform canvas.

### Testing Endpoints via Terminal (`curl`)

- **English Synthesis**:
  ```bash
  curl -X POST http://127.0.0.1:8000/api/synthesize \
    -H "Content-Type: application/json" \
    -d '{"text": "Hello, thank you for calling customer voice support!"}'
  ```

- **Hindi Synthesis**:
  ```bash
  curl -X POST http://127.0.0.1:8000/api/synthesize \
    -H "Content-Type: application/json" \
    -d '{"text": "नमस्ते, आपका स्वागत है"}'
  ```

- **Arabic Synthesis**:
  ```bash
  curl -X POST http://127.0.0.1:8000/api/synthesize \
    -H "Content-Type: application/json" \
    -d '{"text": "مرحباً بك في الدعم الصوتي"}'
  ```