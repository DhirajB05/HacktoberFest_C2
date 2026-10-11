import json
import os
import asyncio
import time
from datetime import datetime
import uuid
from pathlib import Path
from typing import Optional

from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse, JSONResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
import sounddevice as sd
import numpy as np

from .db import get_db, init_db

DB_PATH = os.path.join(os.path.dirname(__file__), "..", "trailear.db")

app = FastAPI(title="TrailEar Backend")
init_db()

app.mount("/static", StaticFiles(directory=os.path.join(os.path.dirname(__file__), "..", "frontend")), name="static")
templates = Jinja2Templates(directory=os.path.join(os.path.dirname(__file__), "..", "frontend"))

# In-memory state for live listening
live_state = {
    "active": False,
    "session_id": None,
    "detections": [],
    "last_detection_time": 0,
    "confidence_threshold": 0.5,
    "cooldown_until": 0,
    "cue_type": "tone",
    "gps_enabled": False,
    "gps_lat": None,
    "gps_lon": None,
}


# ── Species info (static) ──────────────────────────────────────────────
SPECIES_INFO_PATH = Path("/home/aresenic/trailear/models/species_info.json")
if SPECIES_INFO_PATH.exists():
    with open(SPECIES_INFO_PATH) as f:
        SPECIES_INFO = json.load(f)
else:
    # Default minimal species info
    SPECIES_INFO = {
        "sparrow": "Small brown bird commonly found in urban areas, known for simple chirping sounds.",
        "robin": "Robin red-breast, known for melodic song often heard in gardens and woodlands.",
        "crow": "Large all-black bird with distinctive cawing call, common in many habitats.",
        "hawk": "Bird of prey with sharp piercing screech, often seen soaring high above.",
        "finch": "Small seed-eating bird with cheerful warbling song and bright plumage.",
    }


# ── Audio capture ──────────────────────────────────────────────────────
SAMPLE_RATE = 48000
CHANNELS = 1
DURATION = 3  # seconds, per TRD: "3 second windows"


def record_audio(duration: float = DURATION) -> np.ndarray:
    """Record audio window from microphone."""
    print(f"Recording {duration}s audio window...")
    recording = sd.rec(int(duration * SAMPLE_RATE), samplerate=SAMPLE_RATE, channels=CHANNELS)
    sd.wait()  # Wait until recording is finished
    return recording


# ── Mock BirdNET detection ─────────────────────────────────────────────
BIRDNET_SPECIES = ["sparrow", "robin", "crow", "hawk", "finch", "warbler", "eagle"]


def detect_bird(audio: np.ndarray, gps_lat: Optional[float], gps_lon: Optional[float]) -> Optional[dict]:
    """Mock BirdNET analysis - returns species and confidence."""
    # In a real implementation, this would run BirdNET-Analyzer on the audio
    # For now, simulate detection based on audio energy
    audio_rms = np.sqrt(np.mean(audio ** 2))
    
    if audio_rms < 0.01:
        return None  # Too quiet, no detection
    
    # Simulate a detection (in real life, this would be BirdNET output)
    import random
    species = random.choice(BIRDNET_SPECIES)
    confidence = round(0.4 + random.random() * 0.6, 2)  # 0.4-1.0
    
    return {
        "species_common": species,
        "species_scientific": f"{species.capitalize()} species",
        "confidence": confidence,
        "timestamp": datetime.utcnow().isoformat() + "Z",
        "lat": gps_lat,
        "lon": gps_lon,
    }


# ── LLM summarization (mock) ───────────────────────────────────────────
def summarize_detections(detections: list) -> str:
    """Generate a walk summary from detections using a local LLM."""
    if not detections:
        return "No bird calls detected during this walk."
    
    unique_species = []
    seen = set()
    for d in detections:
        s = d.get("species_common", "unknown")
        if s not in seen:
            seen.add(s)
            unique_species.append(s)
    
    species_notes = []
    for species in unique_species[:6]:
        note = SPECIES_INFO.get(species, "Interesting species detected during your walk.")
        species_notes.append(note)
    
    summary = f"Heard {len(unique_species)} species: {', '.join(unique_species)}."
    if species_notes:
        summary += " " + " ".join(species_notes[:3])
    
    return summary


# ── API Routes ─────────────────────────────────────────────────────────

@app.get("/", response_class=HTMLResponse)
async def home(request: Request):
    """Home page with start button."""
    return templates.TemplateResponse("index.html", {"request": request, "last_session": None})


@app.post("/session/start")
async def session_start(request: Request):
    """Begin listening - create a new session."""
    form = await request.form()
    threshold = float(form.get("confidence_threshold", 0.5))
    cue_type = form.get("cue_type", "tone")
    gps_lat = float(form.get("gps_lat", 0)) if form.get("gps_enabled") == "on" else None
    gps_lon = float(form.get("gps_lon", 0)) if form.get("gps_enabled") == "on" else None
    
    # Update live state
    live_state["active"] = True
    live_state["confidence_threshold"] = threshold
    live_state["cue_type"] = cue_type
    live_state["gps_enabled"] = form.get("gps_enabled") == "on"
    live_state["gps_lat"] = gps_lat
    live_state["gps_lon"] = gps_lon
    
    import uuid
    session_id = str(uuid.uuid4())
    live_state["session_id"] = session_id
    live_state["detections"] = []
    live_state["last_detection_time"] = 0
    live_state["cooldown_until"] = 0
    
    # Save session to DB
    conn = get_db()
    c = conn.cursor()
    c.execute("INSERT INTO sessions (id, started_at, lat, lon) VALUES (?, ?, ?, ?)",
              (session_id, datetime.utcnow().isoformat() + "Z", gps_lat, gps_lon))
    conn.commit()
    conn.close()
    
    return JSONResponse({"session_id": session_id, "status": "started"})


@app.post("/session/stop")
async def session_stop(request: Request):
    """Stop listening, trigger summary."""
    live_state["active"] = False
    session_id = live_state.get("session_id")
    
    # Generate summary
    detections = live_state.get("detections", [])
    summary = summarize_detections(detections)
    
    # Save to DB
    conn = get_db()
    c = conn.cursor()
    c.execute("UPDATE sessions SET ended_at = ?, summary_text = ? WHERE id = ?",
              (datetime.utcnow().isoformat() + "Z", summary, session_id))
    conn.commit()
    conn.close()
    
    # Save detections
    for d in detections:
        conn = get_db()
        c = conn.cursor()
        c.execute("INSERT OR IGNORE INTO detections (id, session_id, timestamp, species_common, species_scientific, confidence, lat, lon) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                  (d.get("id"), session_id, d.get("timestamp"), d.get("species_common"), d.get("species_scientific"), d.get("confidence"), d.get("lat"), d.get("lon")))
        conn.commit()
        conn.close()
    
    return JSONResponse({"summary": summary, "session_id": session_id, "detections_count": len(detections)})


@app.post("/detection")
async def detection_endpoint(request: Request):
    """Called when BirdNET detects a bird - fire cue and store detection."""
    form = await request.form()
    species = form.get("species", "unknown")
    confidence = float(form.get("confidence", 0.5))
    timestamp = form.get("timestamp", "")
    lat = float(form.get("lat", 0))
    lon = float(form.get("lon", 0))
    session_id = form.get("session_id", live_state.get("session_id"))
    
    # Cooldown check (60 seconds per TRD)
    import time
    current_time = time.time()
    if current_time < live_state.get("cooldown_until", 0):
        return JSONResponse({"status": "cooldown", "message": "Suppressing same species for cooldown"}, status_code=200)
    
    # Create detection
    detection = {
        "id": str(uuid4()) if 'uuid4' in dir() else str(hash((species, timestamp))),
        "session_id": session_id,
        "timestamp": timestamp,
        "species_common": species,
        "species_scientific": f"{species.capitalize()} species",
        "confidence": confidence,
        "lat": lat,
        "lon": lon,
    }
    
    # Check for duplicate suppression (TRD: suppress same species for cooldown)
    # If same species detected within 60s, suppress
    last_time = live_state.get("last_detection_time", 0)
    if species in [x.get("species_common") for x in live_state.get("detections", [])]:
        live_state["cooldown_until"] = current_time + 60
        return JSONResponse({"status": "suppressed", "message": f"{species} suppressed (cooldown)"}, status_code=200)
    
    live_state["detections"].append(detection)
    live_state["last_detection_time"] = current_time
    
    # Fire cue
    await fire_cue(species, confidence, live_state["cue_type"])
    
    # Persist detection to DB
    conn = get_db()
    c = conn.cursor()
    c.execute("INSERT INTO detections (id, session_id, timestamp, species_common, species_scientific, confidence, lat, lon) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
              (detection["id"], session_id, timestamp, species, f"{species.capitalize()} species", confidence, lat, lon))
    conn.commit()
    conn.close()
    
    return JSONResponse({"status": "detected", "detection": detection, "cue_fired": True})


async def fire_cue(species: str, confidence: float, cue_type: str):
    """Fire audio or haptic cue."""
    print(f"🔊 CUE: {species} detected (confidence: {confidence:.2f}) - {cue_type}")
    # In a real implementation, this would play a tone through earbuds or trigger vibration


@app.get("/session/{session_id}")
async def session_detail(session_id: str):
    """Get session details and detections."""
    conn = get_db()
    c = conn.cursor()
    c.execute("SELECT * FROM sessions WHERE id = ?", (session_id,))
    session = c.fetchone()
    c.execute("SELECT * FROM detections WHERE session_id = ? ORDER BY timestamp", (session_id,))
    detections = c.fetchall()
    db.close()
    
    return {"session": dict(session) if session else None, "detections": [dict(d) for d in detections]}


@app.get("/sessions")
async def list_sessions():
    """Get history of all sessions."""
    conn = get_db()
    c = conn.cursor()
    c.execute("SELECT id, started_at, ended_at, summary_text, lat, lon FROM sessions ORDER BY started_at DESC")
    rows = c.fetchall()
    conn.close()
    return [dict(r) for r in rows]


@app.delete("/session/{session_id}")
async def delete_session(session_id: str):
    """Delete a session and its data."""
    conn = get_db()
    c = conn.cursor()
    c.execute("DELETE FROM detections WHERE session_id = ?", (session_id,))
    c.execute("DELETE FROM sessions WHERE id = ?", (session_id,))
    conn.commit()
    conn.close()
    return {"status": "deleted"}


@app.get("/live")
async def live_detection():
    """Server-sse events stream for latest detection."""
    async def event_stream():
        while True:
            if live_state.get("active") and live_state.get("detections"):
                last = live_state["detections"][-1]
                yield f"data: {json.dumps(last)}\n\n"
            await asyncio.sleep(0.5)
    
    from fastapi.responses import StreamingResponse
    return StreamingResponse(event_stream(), media_type="text/event-stream")