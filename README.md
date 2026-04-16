<div align="center">

# AURIX

<img src="docs/assets/banner.png" alt="AURIX banner" width="720" onerror="this.style.display='none'" />

**JARVIS-style AI voice assistant powered by Ollama**

[![Python](https://img.shields.io/badge/python-3.12%2B-blue.svg)](https://www.python.org/)
[![Node](https://img.shields.io/badge/node-18%2B-43853d.svg)](https://nodejs.org/)
[![Ollama](https://img.shields.io/badge/LLM-Ollama-000000.svg)](https://ollama.com/)
[![Platform](https://img.shields.io/badge/platform-Windows%20%7C%20Linux%20%7C%20macOS-lightgrey.svg)]()
[![License](https://img.shields.io/badge/license-MIT-green.svg)](#-license)
[![PRs Welcome](https://img.shields.io/badge/PRs-welcome-brightgreen.svg)](#-contributing)

</div>

AURIX is a fully local, voice-first personal assistant. It listens for a wake word, understands natural language through a local Ollama LLM, executes real OS-level actions, learns from your habits through a graph-based memory system, and visualizes everything through a holographic HUD and audio-reactive 3D sphere. No API keys, no cloud inference, no telemetry.

---

## ✨ Features

- 🎤 **Voice control with wake-word detection** — hands-free activation via openWakeWord, no push-to-talk needed
- 🧠 **Local LLM via Ollama** — zero API cost, zero data leaving your machine, hybrid fast/smart model routing (`llama3.2:3b` → `llama3.2:1b`)
- 💾 **Graph-based memory system** — NetworkX-backed semantic memory that learns shortcuts from repeated command sequences
- 🎨 **Holographic GUI** — audio-reactive 3D Electron sphere + translucent Tkinter HUD with live transcript, summary, and memory stats
- 🔧 **20+ built-in tools** — apps, media, Gmail, weather, web search, file search, timers, notes, macros, system info, reminders
- 💬 **Silent mode** — text-only chat in the HUD for quiet environments or meetings
- 🗣️ **Speech mode** — full voice interaction with gTTS and Google Speech Recognition
- ⚡ **Instant fast-path** — arithmetic and direct app launches skip the LLM entirely for zero-latency responses
- 🔁 **Macro recording & replay** — record keyboard/mouse sequences, replay as named shortcuts

---

## 📸 Screenshots

<div align="center">

| Holographic HUD | Audio-reactive Sphere | Silent Mode |
|:---:|:---:|:---:|
| *(coming soon)* | *(coming soon)* | *(coming soon)* |

</div>

---

## 🚀 Installation

### Prerequisites

- **Python 3.12+**
- **Node.js 18+** (for the Electron sphere overlay)
- **[Ollama](https://ollama.com/download)** installed and running

### Step-by-step

```bash
# 1. Clone the repository
git clone https://github.com/YOUR_USERNAME/AURIX.git
cd AURIX

# 2. Create and activate a virtual environment
python -m venv venv
# Windows:
venv\Scripts\activate
# Linux/macOS:
source venv/bin/activate

# 3. Install Python dependencies
pip install -r requirements.txt

# 4. Install Electron dependencies for the 3D sphere
cd gui/electron-sphere
npm install
cd ../..

# 5. Pull the Ollama models
ollama pull llama3.2:3b
ollama pull llama3.2:1b

# 6. (Optional) Copy the env template
cp .env.example .env

# 7. (Optional) Enable Gmail integration
# See docs/GMAIL_SETUP.md
```

---

## 🎮 Usage

```bash
# Launch with the full experience (sphere + HUD + mode picker)
python main.py --sphere

# Or jump straight into a mode:
python main.py --silent     # Text-only chat in the HUD
python main.py --speech     # Voice interaction

# Useful flags:
python main.py --sphere --verbose     # Show DEBUG logs
python main.py --reset-memory         # Clear the graph before starting
```

On start you'll be prompted to pick **Speech Mode** (voice) or **Silent Mode** (typed) unless you passed `--silent` / `--speech`.

### Example interactions

| You say / type                     | AURIX does                                           |
|------------------------------------|------------------------------------------------------|
| "Hey AURIX, open Brave"            | Launches the Brave browser                           |
| "What's the weather in Hagen?"     | Fetches wttr.in, shows result in the Summary tab     |
| "What is 2 + 2?"                   | Answers instantly (fast-path, no LLM call)           |
| "Check my emails"                  | Returns unread count + top senders                   |
| "Search online for Python 3.13"    | Google + DuckDuckGo fallback, top 3 snippets         |
| "Set a timer for 5 minutes"        | Schedules a timer with alert                         |
| "Take a note: buy milk"            | Saves to `notes/`                                    |
| "System info"                      | CPU / RAM / disk / battery snapshot                  |
| "Record macro" / "Play macro X"    | Records and replays keyboard/mouse sequences         |
| "Goodnight, AURIX"                 | Graceful shutdown (saves memory graph)               |

---

## 📋 Available Commands

### Tool categories

| Category       | Tools                                                                          |
|----------------|---------------------------------------------------------------------------------|
| **Apps**       | `open_application`, `close_application`                                         |
| **Media**      | `control_media` (play/pause/skip/volume), `search_youtube`                      |
| **Files**      | `file_search`, `local_file_search`, `delete_file`                               |
| **Web**        | `web_search` (Google + DuckDuckGo fallback)                                     |
| **Weather**    | `get_weather` (wttr.in, auto-location)                                          |
| **System**     | `get_system_info`, `shutdown_aurix`                                             |
| **Gmail**      | `check_unread_count`, `get_recent_emails`, `send_email`, `search_emails`        |
| **Notes**      | `create_note`, `read_note`, `list_notes`                                        |
| **Timers**     | `set_timer`, `cancel_timer`                                                     |
| **Reminders**  | `create_reminder`                                                                |
| **Macros**     | `start_recording`, `stop_recording`, `play_macro`, `list_macros`, `delete_macro` |

### Built-in control phrases

- **Wake**: "Hey AURIX" (or your configured wake word)
- **Shutdown**: "Goodnight AURIX", "shut down AURIX"
- **Pause listening**: "Hold on", "wait", "never mind"
- **HUD visibility**: "Show the HUD", "hide the HUD"

---

## ⚙️ Configuration

All runtime settings live in `config/settings.yaml`:

```yaml
# Wake word
wake_word: hey_aurix
wakeword_model_path: ""        # custom .onnx/.tflite path (optional)
wakeword_threshold: 0.5        # higher = stricter, fewer false triggers

# Voice
stt_language: en-US
stt_mic_index: 4               # run list_microphones() to find yours
tts_rate: 175
tts_volume: 0.9

# Memory
graph_path: data/graph.pkl
max_context_nodes: 10
similarity_threshold: 0.7
shortcut_frequency_threshold: 3   # how often before a pattern becomes a macro

# GUI
gui_enabled: true
fps: 60

# Logging
log_level: INFO                # INFO | DEBUG | WARNING
log_path: logs/aurix.log
```

### Changing the wake word

`wake_word` accepts any openWakeWord built-in: `hey_aurix`, `jarvis`, `alexa`, `mycroft`, `rhasspy`. For a custom model, point `wakeword_model_path` at your `.onnx` / `.tflite` file.

### Custom app paths

`tools/app_control.py` defines `APP_ALIASES`. Add entries per platform:

```python
APP_ALIASES = {
    "myapp": {
        "win32": [r"C:\Path\To\MyApp.exe"],
        "linux": ["myapp"],
        "darwin": ["MyApp"],
    },
    ...
}
```

`APP_NAME_ALIASES` maps natural phrases ("brave browser", "task manager") to canonical keys.

---

## 🏗️ Architecture

```
┌────────────────────────────────────────────────────────────────┐
│  Wake Word  ──►  STT  ──►  Engine  ──►  LLM (Ollama)           │
│  (openWW)       (Google)    │            │                     │
│                             ▼            ▼                     │
│                        Graph Memory  Tool Executor             │
│                        (NetworkX)    (20+ handlers)            │
│                             │            │                     │
│                             ▼            ▼                     │
│                         TTS (gTTS)   OS / APIs                 │
│                             │                                  │
│                             ▼                                  │
│                    Sphere (Electron) + HUD (Tkinter)           │
└────────────────────────────────────────────────────────────────┘
```

### Key components

| Module                       | Purpose                                                        |
|------------------------------|----------------------------------------------------------------|
| `core/engine.py`             | Main orchestrator and event loop                               |
| `core/state_manager.py`      | System state + active-window tracking                          |
| `llm/claude_interface.py`    | Ollama client + fast/smart model routing                       |
| `llm/prompt_builder.py`      | System prompt assembly with memory context                     |
| `memory/graph_memory.py`     | NetworkX-backed semantic memory with shortcut learning         |
| `tools/executor.py`          | Tool dispatcher with param sanitization                        |
| `tools/*.py`                 | Individual tool implementations                                |
| `voice/`                     | Wake word, STT, TTS                                            |
| `gui/sphere_controller.py`   | Electron process + WebSocket bridge                            |
| `gui/hud_panel.py`           | Translucent Tkinter HUD                                        |
| `gui/electron-sphere/`       | 3D audio-reactive sphere (Three.js)                            |

---

## 🛠️ Technologies

- **[Ollama](https://ollama.com/)** — local LLM inference (llama3.2:3b + llama3.2:1b)
- **[openWakeWord](https://github.com/dscripka/openWakeWord)** — offline wake-word detection
- **[SpeechRecognition](https://github.com/Uberi/speech_recognition)** — speech-to-text
- **[gTTS](https://github.com/pndurette/gTTS)** + **[pygame](https://www.pygame.org/)** — text-to-speech synthesis + playback
- **[Electron](https://www.electronjs.org/)** + **Three.js** — 3D audio-reactive sphere overlay
- **[NetworkX](https://networkx.org/)** — graph-based memory backbone
- **[sentence-transformers](https://www.sbert.net/)** — semantic similarity for context retrieval
- **[Tkinter](https://docs.python.org/3/library/tkinter.html)** — holographic HUD
- **[BeautifulSoup](https://www.crummy.com/software/BeautifulSoup/)** — web search parsing
- **[Google API Client](https://github.com/googleapis/google-api-python-client)** — Gmail integration
- **[psutil](https://github.com/giampaolo/psutil)** + **[pyautogui](https://github.com/asweigart/pyautogui)** — OS automation

---

## 📖 Documentation

- [`docs/GMAIL_SETUP.md`](docs/GMAIL_SETUP.md) — Gmail OAuth setup walkthrough
- [`SETUP_GUIDE.md`](../SETUP_GUIDE.md) — extended install notes
- [`QUICK_REFERENCE.md`](../QUICK_REFERENCE.md) — cheatsheet of commands
- [`aurix-voice-assistant-architecture.md`](../aurix-voice-assistant-architecture.md) — design deep-dive
- [`graph-memory-systems.md`](../graph-memory-systems.md) — memory internals
- [`os-automation-safety.md`](../os-automation-safety.md) — tool safety model
- [`real-time-gui-rendering.md`](../real-time-gui-rendering.md) — HUD + sphere rendering
- [`voice-ai-integration.md`](../voice-ai-integration.md) — voice stack walkthrough

---

## 🤝 Contributing

Contributions are very welcome.

1. Fork the repo and create a feature branch: `git checkout -b feat/my-feature`
2. Follow existing code style: **PEP 8**, type hints where practical, docstrings on public functions
3. Add a tool? Register it in `tools/executor.py` and expose a schema in `llm/claude_interface.py`
4. Run existing tests (`test_*.py`) before opening a PR
5. Open a pull request with a clear description of the change and its motivation

**Never commit secrets.** `.gitignore` already excludes `.env`, `config/gmail_credentials.json`, and `config/gmail_token.json` — keep it that way.

---

## 📝 License

Released under the **MIT License**. See [`LICENSE`](LICENSE) for the full text.

---

## 🙏 Acknowledgments

- **Ollama** — for making local LLMs effortless
- **openWakeWord** — for a free, offline, actually-good wake-word engine
- **The JARVIS concept** (Marvel / Iron Man) — for the vision that started it all
- Everyone contributing to the open-source voice-AI ecosystem: SpeechRecognition, gTTS, sentence-transformers, NetworkX, Three.js, and the many others this project stands on

<div align="center">

*Built for people who want an assistant that runs on their own hardware, on their own terms.*

</div>
