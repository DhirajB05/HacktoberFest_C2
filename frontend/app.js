/* TrailEar Frontend - app.js */
document.addEventListener("DOMContentLoaded", () => {
  const views = {
    home: document.getElementById("home"),
    setup: document.getElementById("setup"),
    live: document.getElementById("live"),
    summary: document.getElementById("summary"),
    history: document.getElementById("history"),
    about: document.getElementById("about"),
  };

  const screens = Object.values(views);

  // Show a view, hide others
  function showView(name) {
    screens.forEach((v) => v.classList.remove("active"));
    if (views[name]) views[name].classList.add("active");
  }

  // --- Home ---
  const startBtn = document.getElementById("startBtn");
  startBtn.addEventListener("click", () => showView("setup"));

  // Load last session on home
  async function loadLastSession() {
    try {
      const res = await fetch("/sessions");
      const sessions = await res.json();
      const last = sessions[0];
      const lastSessionContent = document.getElementById("lastSessionContent");
      if (last) {
        lastSessionContent.innerHTML = `
          <div class="session-info">
            <div>Duration: <span>${formatDuration(last.ended_at, last.started_at)}</span></div>
            <div>Species heard: ${last.summary_text || "None"}</div>
            <div class="small">${last.lat && last.lon ? `Location: ${last.lat.toFixed(4)}, ${last.lon.toFixed(4)}` : ""}</div>
          </div>
        `;
      } else {
        lastSessionContent.innerHTML = "<p>No previous walks. Start your first walk!</p>";
      }
    } catch (e) {
      console.error("Failed to load last session:", e);
    }
  }
  loadLastSession();

  // --- Setup ---
  const startWalkBtn = document.getElementById("startWalkBtn");
  const confidenceRadios = document.querySelectorAll('input[name="confidence"]');
  const cueRadios = document.querySelectorAll('input[name="cue"]');
  const useGPSBtn = document.getElementById("useGPSBtn");
  const manualLat = document.getElementById("manualLat");
  const manualLon = document.getElementById("manualLon");
  const micBtn = document.getElementById("micBtn");

  let gpsEnabled = false;
  let gpsLat = null;
  let gpsLon = null;

  // GPS (simulated - in real app would use browser GPS)
  useGPSBtn.addEventListener("click", () => {
    gpsEnabled = !gpsEnabled;
    useGPSBtn.textContent = gpsEnabled ? "GPS active" : "Use GPS location";
    if (gpsEnabled) {
      // Simulated GPS - in real app would use navigator.geolocation
      gpsLat = 37.7749;  // San Francisco as example
      gpsLon = -122.4194;
      manualLat.value = gpsLat.toFixed(4);
      manualLon.value = gpsLon.toFixed(4);
      showStatus("GPS location set", "success");
    } else {
      gpsLat = null;
      gpsLon = null;
      manualLat.value = "";
      manualLon.value = "";
      showStatus("GPS disabled", "info");
    }
  });

  // Manual location
  [manualLat, manualLon].forEach(input => {
    input.addEventListener("change", () => {
      gpsLat = parseFloat(manualLat.value) || null;
      gpsLon = parseFloat(manualLon.value) || null;
    });
  });

  // Confidence level
  confidenceRadios.forEach(radio => {
    radio.addEventListener("change", (e) => {
      const level = e.target.value;
      const labels = {
        relaxed: "Relaxed (0.3)",
        balanced: "Balanced (0.5)",
        strict: "Strict (0.7)",
      };
      showStatus(`Confidence set to ${level}`, "info");
    });
  });

  // Cue type
  cueRadios.forEach(radio => {
    radio.addEventListener("change", (e) => {
      showStatus(`Cue type: ${e.target.value}`, "info");
    });
  });

  function showStatus(msg, type) {
    // Simple status feedback
    const existing = document.querySelector(".status-msg");
    if (existing) existing.remove();
    const div = document.createElement("div");
    div.className = `status-msg ${type}`;
    div.textContent = msg;
    document.querySelector(".setup-grid").insertBefore(div, document.querySelector(".start-btn"));
    setTimeout(() => div.remove(), 3000);
  }

  startWalkBtn.addEventListener("click", async () => {
    const threshold = parseFloat(
      document.querySelector('input[name="confidence"]:checked')?.value || "0.5"
    );
    const cueType = document.querySelector('input[name="cue"]:checked')?.value || "tone";

    // Send setup to backend
    const res = await fetch("/session/start", {
      method: "POST",
      headers: { "Content-Type": "application/x-www-form-urlencoded" },
      body: new URLSearchParams({
        confidence_threshold: threshold,
        cue_type: cueType,
        gps_enabled: gpsEnabled ? "on" : "off",
        gps_lat: gpsLat || "",
        gps_lon: gpsLon || "",
      }),
    });
    const data = await res.json();

    if (data.status === "started") {
      showView("live");
      startLiveListening(data.session_id);
    }
  });

  function formatDuration(endedAt, startedAt) {
    if (!startedAt) return "00:00";
    const start = new Date(startedAt);
    const end = new Date(endedAt || Date.now());
    const diffMs = end - start;
    const mins = Math.floor((diffMs / 1000) / 60);
    const secs = Math.floor((diffMs / 1000) % 60);
    return `${mins.toString().padStart(2, "0")}:${secs.toString().padStart(2, "0")}`;
  }

  // --- Live listening ---
  async function startLiveListening(sessionId) {
    // Start periodic detection
    liveInterval = setInterval(async () => {
      if (!liveState.active) return;
      
      try {
        const audio = recordAudioWindow();
        const detection = await detectBird(audio, gpsLat, gpsLon);
        
        if (detection) {
          // Update UI
          updateLatestSpecies(detection.species_common);
          
          // Fire to backend
          await fetch("/detection", {
            method: "POST",
            headers: { "Content-Type": "application/x-www-form-urlencoded" },
            body: new URLSearchParams({
              species: detection.species_common,
              confidence: detection.confidence,
              timestamp: detection.timestamp,
              lat: detection.lat || 0,
              lon: detection.lon || 0,
              session_id: sessionId,
            }),
          });
        }
      } catch (e) {
        console.error("Live detection error:", e);
      }
    }, 1500); // 1-2 second overlap per TRD

    // Start timer
    startTimer();
  }

  function recordAudioWindow() {
    // Record 3-second audio window
    return recordAudio(SAMPLE_RATE, DURATION);
  }

  function updateLatestSpecies(species) {
    const el = document.getElementById("latestSpecies");
    el.textContent = species || "--";
    el.classList.remove("empty");
  }

  function startTimer() {
    let seconds = 0;
    const timerEl = document.querySelector(".timer");
    timerEl.textContent = "00:00";
    
    const timerId = setInterval(() => {
      seconds++;
      const mins = Math.floor(seconds / 60);
      const secs = seconds % 60;
      timerEl.textContent = `${mins.toString().padStart(2, "0")}:${secs.toString().padStart(2, "0")}`;
    }, 1000);

    // Stop timer when session stops (will be cleared in stop handler)
    window._timerId = timerId;
  }

  // --- Stop ---
  const stopBtn = document.getElementById("stopBtn");
  stopBtn.addEventListener("click", async () => {
    clearInterval(window._timerId);
    
    const res = await fetch("/session/stop", { method: "POST" });
    const data = await res.json();
    
    showView("summary");
    document.getElementById("duration").textContent = data.summary ? formatDuration(data.ended_at) : "00:00";
    document.getElementById("location").textContent = gpsLat && gpsLon ? `${gpsLat.toFixed(4)}, ${gpsLon.toFixed(4)}` : "--";
    
    // Populate species list
    renderSpeciesList(data.detections || []);
    
    // LLM summary already in data.summary
    const summaryEl = document.getElementById("llmSummary");
    summaryEl.textContent = data.summary || "Generating summary...";
  });

  function renderSpeciesList(detections) {
    const listEl = document.getElementById("speciesList");
    
    if (!detections || detections.length === 0) {
      listEl.innerHTML = "<p>No species detected.</p>";
      return;
    }
    
    let html = "";
    detections.forEach(d => {
      const conf = (d.confidence || 0.5).toFixed(2);
      html += `
        <div class="species-item">
          <span>${d.species_common || "unknown"}</span>
          <span class="confidence">${conf}</span>
        </div>
      `;
    });
    listEl.innerHTML = html;
  }

  // --- Export / Delete ---
  window.exportSession = async () => {
    if (confirm("Export session data as JSON?")) {
      const res = await fetch("/sessions");
      const sessions = await res.json();
      const data = JSON.stringify(sessions, null, 2);
      const blob = new Blob([data], { type: "application/json" });
      const url = URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = url;
      a.download = "trailear-session.json";
      a.click();
      URL.revokeObjectURL(url);
    }
  };

  window.deleteCurrentSession = async () => {
    if (confirm("Delete this walk session?")) {
      const sessionId = /* get current session id */;
      await fetch(`/session/${sessionId}`, { method: "DELETE" });
      showView("home");
      loadLastSession();
    }
  };

  // --- History ---
  async function loadHistory() {
    try {
      const res = await fetch("/sessions");
      const sessions = await res.json();
      const listEl = document.getElementById("historyList");
      
      if (sessions.length === 0) {
        listEl.innerHTML = "<p>No walks yet. Start your first walk!</p>";
        return;
      }
      
      let html = "";
      sessions.forEach(s => {
        const duration = formatDuration(s.ended_at, s.started_at);
        html += `
          <div class="history-item" onclick="showView('summary')">
            <div class="date">${new Date(s.started_at).toLocaleDateString()}</div>
            <div class="species">${s.summary_text || "Unknown species"}</div>
          </div>
        `;
      });
      listEl.innerHTML = html;
    } catch (e) {
      console.error("Failed to load history:", e);
    }
  }

  // Initial history load on home
  if (document.getElementById("history")) {
    loadHistory();
  }

  // --- About ---
  const aboutBtn = document.querySelector('button.close-btn');
  aboutBtn.addEventListener("click", () => showView("home"));

  // Initialize live state
  let liveInterval = null;
});