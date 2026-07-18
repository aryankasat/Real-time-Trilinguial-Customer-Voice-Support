# SOLID Trilingual Customer Voice Support Web App

This repository provides an interactive web application for a real-time trilingual customer voice support system supporting three language subsets:
- **English (United States)** (`en_us`)
- **Hindi (India)** (`hi_in`)
- **Arabic (Egypt)** (`ar_eg`)

The application is refactored according to **SOLID design principles**, separating concerns into modular utilities, custom processors, service factories, and web interfaces. It uses the **Pipecat** conversational framework and **LiveKit** to stream synthesized speech back to the browser in real time via **WebRTC**.

---

## 1. WebRTC & LiveKit Orchestration Architecture

Unlike standard file-retrieval TTS APIs, this system utilizes a real-time WebRTC media connection to stream synthesized voice tracks dynamically with sub-second latency.

```
  1. [User enters text in Browser]
             │
             ▼ (HTTP POST to /api/synthesize)
  2. [FastAPI App]
             ├─► Generate a unique room name (e.g. room_<uuid>)
             ├─► Generate LiveKit Bot Token (bot identity)
             ├─► Generate LiveKit Client Token (user identity)
             ├─► Returns user token and connection URL to Browser instantly
             │
             ▼ (FastAPI launches Pipecat pipeline in background task)
  3. [Pipecat Pipeline Worker (Bot)]
             ├─► Connects to the LiveKit Room via WebRTC (LiveKitTransport)
             ├─► Routes the text frame based on language script detection
             ├─► Synthesizes speech to raw audio frames
             ├─► Feeds output to LiveKitTransport.output()
             └─► Disconnects and terminates when synthesis is complete (EndFrame)
             
  4. [Browser Frontend UI]
             ├─► Receives room token from the HTTP response
             ├─► Connects to the same LiveKit Room via the LiveKit JS client SDK
             ├─► Listens for TrackSubscribed events (audio track)
             ├─► Attaches the audio track for real-time playback
             └─► Connects the Web Audio API AnalyserNode to visually animate the waveform
```

---

## 2. Codebase Structure (SOLID Principles)

The backend is organized into decoupled modules inside the `app/` package:

```
├── app/
│   ├── config.py               # Loads configuration from .env
│   ├── main.py                 # FastAPI server (lifespans, API endpoints, static mounts)
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
- **LiveKit Server** (to run the WebRTC server locally)

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
Edit `.env` to configure your self-hosted TTS model endpoints and LiveKit server credentials:

```env
# Supported providers: mock, piper_http, local_api
TTS_PROVIDER_EN_US=mock
TTS_VOICE_EN_US=en_US-ryan-high
TTS_URL_EN_US=http://localhost:5000

# LiveKit WebRTC Configuration (Default Local Dev Server)
LIVEKIT_API_URL=ws://localhost:7880
LIVEKIT_API_KEY=devkey
LIVEKIT_API_SECRET=secret
```

### Step 3: Run the LiveKit WebRTC Server
You can start a local LiveKit instance on macOS using Homebrew:
```bash
brew install livekit
livekit-server --dev
```

### Step 4: Run the Backend Web Server
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