# SOLID Trilingual Customer Voice Support Web App

This repository provides an interactive web application for a real-time trilingual customer voice support system supporting three language subsets:
- **English (United States)** (`en_us`)
- **Hindi (India)** (`hi_in`)
- **Arabic (Egypt)** (`ar_eg`)

The application is refactored according to **SOLID design principles**, separating concerns into modular utilities, custom processors, service factories, and web interfaces. It uses the **Pipecat** conversational framework and **FastAPI WebSockets** to stream synthesized speech back to the browser in real time.

---

## 1. Native WebSocket Orchestration Architecture

Unlike standard file-retrieval TTS APIs, this system utilizes a native WebSocket connection to stream synthesized voice tracks dynamically with low latency, removing any external dependencies.

```
  1. [User enters text in Browser]
             │
             ▼ (WebSocket sends text JSON: {"text": "..."})
  2. [FastAPI WebSocket Endpoint /ws/synthesize]
             ├─► Receives text message
             ├─► Dynamically compiles the Pipecat routing pipeline
             ├─► Pipes output to WebSocketAudioSender custom FrameProcessor
             │
             ▼ (Pipecat pipeline runs asynchronously)
  3. [Pipecat Parallel Routing & Synthesis]
             ├─► LanguageFilter routes text to correct TTS service
             ├─► TTS service synthesizes speech to raw audio frames
             ├─► WebSocketAudioSender pushes raw 16-bit PCM bytes via websocket
             └─► Sends completion signal {"type": "done"} when pipeline stops
             
  4. [Browser Frontend UI]
             ├─► Establishes persistent WebSocket connection to /ws/synthesize
             ├─► Receives binary message (arrayBuffer of 16-bit PCM)
             ├─► Decodes PCM data to Float32 [-1.0, 1.0]
             ├─► Schedules back-to-back smooth playback using Web Audio API buffer scheduling
             └─► Routes the audio nodes to AnalyserNode to animate the canvas visualizer
```

---

## 2. Codebase Structure (SOLID Principles)

The backend is organized into decoupled modules inside the `app/` package:

```
├── app/
│   ├── config.py               # Loads configuration from .env
│   ├── main.py                 # FastAPI server (lifespans, WebSocket endpoints, static mounts)
│   ├── processors/
│   │   ├── language_filter.py  # LanguageFilter custom FrameProcessor
│   │   └── output_capture.py   # OutputCapture custom FrameProcessor
│   ├── services/
│   │   ├── local_tts.py        # Custom self-hosted MockTTSService & LocalHttpTTSService
│   │   └── tts_factory.py      # Factory to build the proper TTS service instance
│   └── utils/
│       ├── audio.py            # Audio utility functions (PCM to WAV conversion)
│       └── language.py         # Script-based language/character set detector
├── static/
│   └── index.html              # Premium dark-mode glassmorphism frontend
├── trilingual_orchestrator.py   # Minimal root uvicorn entry point launcher
├── download_fleurs.py          # Hugging Face Fleurs metadata & audio downloader
├── requirements.txt
└── .env
```

---

## 3. Getting Started

### Prerequisites
- **Python 3.10+**

### Step 1: Install Dependencies
1. Create and activate a virtual environment:
   ```bash
   python3 -m venv .venv
   source .venv/bin/activate
   ```
2. Install dependencies:
   ```bash
   pip install -r requirements.txt
   ```

### Step 2: Configure Environment
Edit `.env` to configure your self-hosted TTS model endpoints:

```env
# Supported providers: mock, piper_http, local_api
TTS_PROVIDER_EN_US=mock
TTS_VOICE_EN_US=en_US-ryan-high
TTS_URL_EN_US=http://localhost:5000
```

### Step 3: Run the Backend Web Server
Start the FastAPI server:
```bash
python trilingual_orchestrator.py
```
Open **`http://localhost:8000`** in your browser to interact with the application.

---

## 4. Google FLEURS Downloader

To acquire trilingual audio samples for dataset verification, run the optimized downloader:
```bash
python download_fleurs.py
```
This script streams archives in memory and extracts only the first 5 WAV audio samples and their ground-truth transcriptions per subset, terminating the connection instantly to save disk space and network bandwidth (~10-12 MB total data transfer).