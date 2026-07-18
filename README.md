# Real-time Trilingual Customer Voice Support

This repository is designed for building a real-time trilingual customer voice support system supporting three language subsets:
- **English (United States)** (`en_us`)
- **Hindi (India)** (`hi_in`)
- **Arabic (Egypt)** (`ar_eg`)

## Google FLEURS Dataset Downloader

To get started, we have provided an optimized downloader script that downloads the first 5 audio samples and their transcriptions from the [Google FLEURS dataset](https://huggingface.co/datasets/google/fleurs) for all three subsets. 

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
│   ├── sample_1.wav
│   ├── sample_1.txt
│   ├── ...
│   ├── sample_5.wav
│   ├── sample_5.txt
│   └── transcriptions.csv
└── ar_eg/
    ├── sample_1.wav
    ├── sample_1.txt
    ├── ...
    ├── sample_5.wav
    ├── sample_5.txt
    └── transcriptions.csv
```

For each language subset:
* **`sample_N.wav`**: The original audio file.
* **`sample_N.txt`**: The ground-truth transcription.
* **`transcriptions.csv`**: A consolidated mapping matching the filenames to their transcriptions.

---

### Setup and Usage Instructions

1. **Set up Python Virtual Environment**:
   Create a virtual environment and install the required dependencies (`requests`, `certifi`, `tqdm`):
   ```bash
   python3 -m venv .venv
   source .venv/bin/activate
   pip install -r requirements.txt
   ```
   *(Note: Alternatively, you can run pip directly: `.venv/bin/pip install requests certifi tqdm`)*

2. **Run the Downloader**:
   Execute the downloader script:
   ```bash
   python3 download_fleurs.py
   ```
   *(Or using the venv binary directly: `.venv/bin/python download_fleurs.py`)*