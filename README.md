# Real-time Trilingual Customer Voice Support

This repository provides an orchestration and data-acquisition solution for building a real-time trilingual customer voice support system supporting three language subsets:
- **English (United States)** (`en_us`)
- **Hindi (India)** (`hi_in`)
- **Arabic (Egypt)** (`ar_eg`)

It utilizes the **Pipecat** orchestration framework to dynamically route inputs to distinct processing pipelines based on language.

---

## 1. Pipecat Orchestration Pipeline

We use the [Pipecat framework](https://github.com/pipecat-ai/pipecat) to define a parallel processing pipeline that dynamically detects input language and routes text frames to their respective language TTS pipelines.

### Pipeline Architecture

```mermaid
graph TD
    Input[Test Feeder / Text Input] --> Pipeline[Pipecat PipelineWorker]
    Pipeline --> Parallel[ParallelPipeline]
    
    subgraph Parallel Branches
        Parallel --> FilterEN[LanguageFilter en_us]
        FilterEN --> TTS_EN[English TTS Service]
        TTS_EN --> CaptureEN[OutputCapture en_us]
        
        Parallel --> FilterHI[LanguageFilter hi_in]
        FilterHI --> TTS_HI[Hindi TTS Service]
        TTS_HI --> CaptureHI[OutputCapture hi_in]
        
        Parallel --> FilterAR[LanguageFilter ar_eg]
        FilterAR --> TTS_AR[Arabic TTS Service]
        TTS_AR --> CaptureAR[OutputCapture ar_eg]
    end
```

### Components

1. **Language Detection**: Custom Unicode block analyzer that identifies character ranges:
   - Devanagari script range (`U+0900` to `U+097F`) maps to **Hindi** (`hi_in`).
   - Arabic script range (`U+0600` to `U+06FF`) maps to **Arabic** (`ar_eg`).
   - Latin range maps to **English** (`en_us`).
2. **`LanguageFilter`**: A custom Pipecat `FrameProcessor` placed at the start of each language branch. It evaluates incoming `TextFrame`s and discards them if they don't match the target language, while letting control frames (like `StartFrame`/`EndFrame`) pass through to keep pipeline state synced.
3. **TTS Services Factory**: Reads `.env` configuration and instantiates the chosen provider for each language, falling back to a lightweight custom `MockTTSService` (which simulates voice synthesis and generates mock frames) when API credentials or models are not configured.
4. **`OutputCapture`**: A custom `FrameProcessor` placed at the end of each pipeline branch to intercept and verify the generated `TTSAudioRawFrame`s and speak events.

### Running the Orchestrator

Run the pipeline:
```bash
python3 trilingual_orchestrator.py
```
*(Or via the virtual environment binary directly: `.venv/bin/python trilingual_orchestrator.py`)*

### Configuring Self-Hosted Models via `.env`

To connect the orchestrator to your self-hosted model instances, edit the variables in `.env`:

```env
# TTS Configuration for en_us (English - US)
# Supported providers: mock, piper_http, local_api
TTS_PROVIDER_EN_US=piper_http
TTS_VOICE_EN_US=en_US-ryan-high
TTS_URL_EN_US=http://localhost:5000
```

1. **`piper_http`**: Connects to a locally running Piper HTTP server (e.g. started via `python -m piper.http_server -m en_US-ryan-high`).
2. **`local_api`**: Connects to a custom generic HTTP API endpoint of a self-hosted model wrapper (receives a JSON payload `{"text": "...", "language": "..."}` and returns raw audio bytes).

---

## 2. Google FLEURS Dataset Downloader

To download sample voice data for validation, we have provided an optimized downloader script that downloads the first 5 audio samples and their transcriptions from the [Google FLEURS dataset](https://huggingface.co/datasets/google/fleurs) for all three subsets. 

Unlike standard loading methods which download multi-gigabyte archives, this script streams the archives directly over HTTP and terminates the connection immediately after extracting the first 5 samples. This keeps the network footprint extremely small (~10-12 MB total) and uses zero disk cache.

### Dataset Directory Structure

Running the downloader script creates a `fleurs_dataset` directory with the following structure:

```
fleurs_dataset/
├── en_us/
│   ├── sample_1.wav
│   ├── sample_1.txt
│   ├── ...
│   ├── sample_5.wav
│   ├── sample_5.txt
│   └── transcriptions.csv
├── hi_in/
│   └── ...
└── ar_eg/
    └── ...
```

### Running the Downloader

```bash
python3 download_fleurs.py
```

---

## Setup and Installation

1. **Create and Activate Virtual Environment**:
   ```bash
   python3 -m venv .venv
   source .venv/bin/activate
   ```
2. **Install Dependencies**:
   ```bash
   pip install -r requirements.txt
   ```