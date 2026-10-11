# TrailEar

Offline birding companion for the Touch Grass challenge. Identifies bird calls on-device with no internet. Keeps audio, location and sighting data local.

## Goals

- Identify bird calls on-device with no internet
- Keep screen time to start/end of walk only
- Keep all data local (no outbound network calls)
- Cost nothing to run (no per-call fees)

## Non-goals (v1)

- Plant, mushroom or animal identification
- User accounts, cloud sync, social features
- Commercial use (BirdNET model weights carry a non-commercial license)

## Tech Stack

| Layer | Choice |
| --- | --- |
| Audio capture | sounddevice (PortAudio), 3s windows, 48kHz mono |
| Bird detection | BirdNET-Analyzer (local inference) |
| Local LLM | Gemma/Qwen/Llama via Ollama or llama.cpp |
| Backend | FastAPI, serves UI and local API |
| Storage | SQLite, one file, all sessions |
| Frontend | Static HTML/JS, phone-browser compatible |
| Location | Device GPS or manual lat/lon |
| Cues | Earbud tone through audio output, or phone vibration |

## User Flow

```
Home → Setup → Live listening → Stop → Summary → History
```

## Setup

1. Clone the repository
2. Install dependencies: `pip install -r requirements.txt`
3. Run: `uvicorn trailear.backend.api:app --host 127.0.0.1 --port 8000`
4. Open http://127.0.0.1:8000 in a browser

## Key Endpoints

| Endpoint | Purpose |
| --- | --- |
| `GET /` | Home page |
| `POST /session/start` | Begin listening, create session |
| `POST /session/stop` | Stop listening, trigger summary |
| `POST /detection` | Bird detected, fire cue, store detection |
| `GET /session/{id}` | Session details and detections |
| `GET /sessions` | History of all sessions |
| `DELETE /session/{id}` | Delete a session |
| `GET /live` | Server-sent events stream for latest detection |

## Development

- `backend/db.py` — Database initialization and CRUD
- `backend/api.py` — FastAPI app with all routes
- `frontend/` — Static HTML, CSS, and JS for the UI

## License

Personal, non-commercial use only. BirdNET model weights carry a non-commercial license.