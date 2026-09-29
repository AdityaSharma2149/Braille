"use strict";

// ---------------------------------------------------------------------------
// Offline shell caching -- helps this page keep loading reliably on a weak
// or intermittent connection (the project's "off-grid, low-resource" goal).
// Solving still needs the local server; only the page shell is cached.
// ---------------------------------------------------------------------------
if ("serviceWorker" in navigator) {
  window.addEventListener("load", () => {
    navigator.serviceWorker.register("sw.js").catch(() => {});
  });
}

// ---------------------------------------------------------------------------
// GanitDrishti engine status -- a real health check against the running
// backend, not a decorative indicator.
// ---------------------------------------------------------------------------
(function initEngineStatus() {
  const el = document.getElementById("engine-status");
  if (!el) return;
  fetch("/api/health")
    .then((res) => {
      if (!res.ok) throw new Error("bad response");
      return res.json();
    })
    .then((data) => {
      el.dataset.tone = "ok";
      el.textContent =
        data.status === "ok"
          ? "GanitDrishti Engine: Online" + (data.groq_key_present ? "" : " (offline math solving only)")
          : "GanitDrishti Engine: Unavailable";
    })
    .catch(() => {
      el.dataset.tone = "error";
      el.textContent = "GanitDrishti Engine: Offline — check that the server is running";
    });
})();

// ---------------------------------------------------------------------------
// Live audio waveform -- decorative visual confirmation that the microphone
// is picking up sound. The text status next to it is the real a11y signal;
// this canvas is aria-hidden.
// ---------------------------------------------------------------------------
function startWaveform(stream, canvas) {
  const AudioCtx = window.AudioContext || window.webkitAudioContext;
  if (!AudioCtx || !canvas) return () => {};
  const ctx = new AudioCtx();
  const source = ctx.createMediaStreamSource(stream);
  const analyser = ctx.createAnalyser();
  analyser.fftSize = 256;
  source.connect(analyser);
  const data = new Uint8Array(analyser.frequencyBinCount);
  const canvasCtx = canvas.getContext("2d");
  canvas.classList.remove("hidden");
  let running = true;

  function draw() {
    if (!running) return;
    requestAnimationFrame(draw);
    analyser.getByteFrequencyData(data);
    const styles = getComputedStyle(document.documentElement);
    canvasCtx.clearRect(0, 0, canvas.width, canvas.height);
    canvasCtx.fillStyle = styles.getPropertyValue("--primary").trim() || "#063a8a";
    const barWidth = canvas.width / data.length;
    for (let i = 0; i < data.length; i++) {
      const barHeight = (data[i] / 255) * canvas.height;
      canvasCtx.fillRect(i * barWidth, canvas.height - barHeight, barWidth - 1, barHeight);
    }
  }
  draw();

  return function stopWaveform() {
    running = false;
    canvas.classList.add("hidden");
    canvasCtx.clearRect(0, 0, canvas.width, canvas.height);
    try { source.disconnect(); } catch (e) {}
    ctx.close().catch(() => {});
  };
}

// ---------------------------------------------------------------------------
// Display settings: theme + text size, persisted so a returning user does
// not have to reconfigure every visit.
// ---------------------------------------------------------------------------
const root = document.documentElement;

function applyTheme(theme) {
  root.setAttribute("data-theme", theme);
  const btn = document.getElementById("theme-toggle");
  if (btn) {
    btn.textContent = theme === "dark" ? "Switch to Light Mode" : "Switch to Dark Mode";
    btn.setAttribute("aria-pressed", theme === "dark" ? "true" : "false");
  }
  localStorage.setItem("theme", theme);
}

function applyFontScale(scale) {
  scale = Math.min(1.6, Math.max(0.8, scale));
  root.style.setProperty("--font-scale", scale);
  localStorage.setItem("fontScale", String(scale));
}

(function initDisplaySettings() {
  applyTheme(localStorage.getItem("theme") || "light");
  applyFontScale(parseFloat(localStorage.getItem("fontScale") || "1"));

  const themeToggle = document.getElementById("theme-toggle");
  if (themeToggle) {
    themeToggle.addEventListener("click", () => {
      const current = root.getAttribute("data-theme") === "dark" ? "dark" : "light";
      applyTheme(current === "dark" ? "light" : "dark");
    });
  }
  const smaller = document.getElementById("font-smaller");
  const bigger = document.getElementById("font-bigger");
  const reset = document.getElementById("font-reset");
  if (smaller) smaller.addEventListener("click", () => applyFontScale(parseFloat(localStorage.getItem("fontScale") || "1") - 0.1));
  if (bigger) bigger.addEventListener("click", () => applyFontScale(parseFloat(localStorage.getItem("fontScale") || "1") + 0.1));
  if (reset) reset.addEventListener("click", () => applyFontScale(1));

  const readBtn = document.getElementById("read-page");
  if (readBtn) {
    readBtn.addEventListener("click", () => {
      if (!("speechSynthesis" in window)) {
        alert("Your browser does not support reading text aloud.");
        return;
      }
      const main = document.getElementById("main");
      const text = main ? main.innerText : document.body.innerText;
      window.speechSynthesis.cancel();
      const utterance = new SpeechSynthesisUtterance(text);
      utterance.rate = 0.9;
      window.speechSynthesis.speak(utterance);
    });
  }
})();

(function initVoiceGuide() {
  const toggle = document.getElementById("voice-guide-toggle");
  if (!toggle) return;
  const audioContext = window.AudioContext || window.webkitAudioContext;
  let context = null;
  let lastBeepAt = 0;

  function beep(count) {
    if (!toggle.checked || !audioContext || Date.now() - lastBeepAt < 160) return;
    lastBeepAt = Date.now();
    context ||= new audioContext();
    context.resume().catch(() => {});
    for (let index = 0; index < count; index += 1) {
      const start = context.currentTime + index * 0.12;
      const oscillator = context.createOscillator();
      const gain = context.createGain();
      oscillator.type = "sine";
      oscillator.frequency.value = 540 + count * 55;
      gain.gain.setValueAtTime(0.0001, start);
      gain.gain.exponentialRampToValueAtTime(0.045, start + 0.01);
      gain.gain.exponentialRampToValueAtTime(0.0001, start + 0.07);
      oscillator.connect(gain).connect(context.destination);
      oscillator.start(start);
      oscillator.stop(start + 0.08);
    }
  }

  function beepCountFor(element) {
    if (element.matches("input[type=file], .material-button")) return 4;
    if (element.matches("#quick-ask-btn, #record-start, #record-stop") || element.closest("#panel-voice")) return 3;
    if (element.matches("input, select, textarea, .choice-card")) return 2;
    return 1;
  }

  toggle.addEventListener("change", () => {
    if (!toggle.checked && "speechSynthesis" in window) window.speechSynthesis.cancel();
  });
  document.querySelectorAll("button, a, select, textarea, input[type=file], .choice-card").forEach((element) => {
    if (element === toggle || element.classList.contains("voice-guide-control")) return;
    const playBeep = () => beep(beepCountFor(element));
    element.addEventListener("mouseenter", playBeep);
    element.addEventListener("focus", playBeep);
  });
})();

// ---------------------------------------------------------------------------
// API helper
// ---------------------------------------------------------------------------
async function api(path, body) {
  const res = await fetch(path, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  const data = await res.json();
  if (!res.ok) {
    throw new Error(data.error || "Something went wrong.");
  }
  return data;
}

function fileToBase64(file) {
  return new Promise((resolve, reject) => {
    const reader = new FileReader();
    reader.onload = () => resolve(reader.result.split(",")[1]);
    reader.onerror = reject;
    reader.readAsDataURL(file);
  });
}

function blobToBase64(blob) {
  return new Promise((resolve, reject) => {
    const reader = new FileReader();
    reader.onload = () => resolve(reader.result.split(",")[1]);
    reader.onerror = reject;
    reader.readAsDataURL(blob);
  });
}

// ---------------------------------------------------------------------------
// Solve page logic (only runs if the page has these elements)
// ---------------------------------------------------------------------------
(function initSolvePage() {
  const solveBtn = document.getElementById("solve-btn");
  if (!solveBtn) return; // not on this page

  const panels = {
    type: document.getElementById("panel-type"),
    voice: document.getElementById("panel-voice"),
    image: document.getElementById("panel-image"),
  };
  const modeRadios = document.querySelectorAll('input[name="input-mode"]');
  const recognizedWrap = document.getElementById("recognized-wrap");
  const recognizedText = document.getElementById("recognized-text");

  function currentMode() {
    return document.querySelector('input[name="input-mode"]:checked').value;
  }

  function setMode(mode) {
    const radio = document.querySelector(`input[name="input-mode"][value="${mode}"]`);
    if (radio) radio.checked = true;
    showPanel(mode);
  }

  function showPanel(mode) {
    Object.entries(panels).forEach(([key, el]) => el.classList.toggle("hidden", key !== mode));
    recognizedWrap.classList.toggle("hidden", mode === "type");
    if (mode !== "image") stopCamera();
  }
  modeRadios.forEach((r) => r.addEventListener("change", () => showPanel(currentMode())));
  // NOTE: the initial showPanel() call happens at the end of this function,
  // once `stopCamera` (which it may call) is safely declared -- calling it
  // here would throw (const TDZ) since camera setup is declared further down.

  // -- Remember language choices between visits ---------------------------
  const voiceLanguageSelect = document.getElementById("voice-language");
  const targetLanguageSelect = document.getElementById("target-language");
  const savedVoiceLang = localStorage.getItem("voiceLanguage");
  const savedTargetLang = localStorage.getItem("targetLanguage");
  if (savedVoiceLang) voiceLanguageSelect.value = savedVoiceLang;
  if (savedTargetLang) targetLanguageSelect.value = savedTargetLang;
  voiceLanguageSelect.addEventListener("change", () => localStorage.setItem("voiceLanguage", voiceLanguageSelect.value));
  targetLanguageSelect.addEventListener("change", () => localStorage.setItem("targetLanguage", targetLanguageSelect.value));

  const voiceLanguageNames = Object.fromEntries(
    Array.from(voiceLanguageSelect.options).map((option) => [option.value, option.textContent])
  );

  function parseVoiceRequest(text) {
    const names = Array.from(targetLanguageSelect.options)
      .map((option) => option.textContent)
      .sort((left, right) => right.length - left.length)
      .map((name) => name.replace(/[.*+?^${}()|[\]\\]/g, "\\$&"));
    const languageCommand = new RegExp(
      `(?:please\\s+)?(?:solve|answer|explain|teach)\\s+(?:it\\s+)?(?:in|using)\\s+(${names.join("|")})\\b`,
      "i"
    );
    const match = text.match(languageCommand);
    const language = match
      ? Array.from(targetLanguageSelect.options).find(
          (option) => option.textContent.toLowerCase() === match[1].toLowerCase()
        )?.value
      : voiceLanguageNames[voiceLanguageSelect.value] || "English";
    const question = match ? text.replace(match[0], " ").replace(/\s+/g, " ").trim() : text.trim();
    return { question, language };
  }

  function speakConversation(text) {
    if (!("speechSynthesis" in window)) return;
    window.speechSynthesis.cancel();
    const utterance = new SpeechSynthesisUtterance(text);
    utterance.rate = 0.9;
    utterance.volume = 0.8;
    window.speechSynthesis.speak(utterance);
  }

  // -- Voice recording ----------------------------------------------------
  const recordStart = document.getElementById("record-start");
  const recordStop = document.getElementById("record-stop");
  const voiceStatus = document.getElementById("voice-status");
  const voicePlayback = document.getElementById("voice-playback");
  let mediaRecorder = null;
  let audioChunks = [];

  function setStatus(el, kind, message) {
    el.dataset.kind = kind;
    el.textContent = message;
    el.classList.remove("hidden");
    // Errors must interrupt immediately; success/info can wait politely.
    el.setAttribute("aria-live", kind === "error" ? "assertive" : "polite");
  }

  const voiceWaveform = document.getElementById("voice-waveform");
  let stopVoiceWaveform = () => {};

  recordStart.addEventListener("click", async () => {
    try {
      const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
      audioChunks = [];
      mediaRecorder = new MediaRecorder(stream);
      stopVoiceWaveform = startWaveform(stream, voiceWaveform);
      mediaRecorder.ondataavailable = (e) => audioChunks.push(e.data);
      mediaRecorder.onstop = async () => {
        stream.getTracks().forEach((t) => t.stop());
        stopVoiceWaveform();
        const blob = new Blob(audioChunks, { type: "audio/webm" });
        voicePlayback.src = URL.createObjectURL(blob);
        voicePlayback.classList.remove("hidden");
        setStatus(voiceStatus, "info", "Transcribing your recording (this runs offline on this computer)...");
        try {
          const base64 = await blobToBase64(blob);
          const lang = document.getElementById("voice-language").value;
          const result = await api("/api/voice", { audio: base64, language: lang });
          recognizedText.value = result.text;
          recognizedWrap.classList.remove("hidden");
          setStatus(voiceStatus, "success", `Heard: "${result.text}". Check the text below and edit it if needed.`);
        } catch (err) {
          setStatus(voiceStatus, "error", "Could not transcribe: " + err.message);
        }
      };
      mediaRecorder.start();
      recordStart.disabled = true;
      recordStop.disabled = false;
      setStatus(voiceStatus, "info", "Recording... speak your question, then press Stop Recording.");
    } catch (err) {
      setStatus(voiceStatus, "error", "Could not access the microphone: " + err.message);
    }
  });

  recordStop.addEventListener("click", () => {
    if (mediaRecorder && mediaRecorder.state !== "inactive") {
      mediaRecorder.stop();
    }
    recordStart.disabled = false;
    recordStop.disabled = true;
  });

  // -- Image OCR (file upload + live camera) --------------------------------
  const imageInput = document.getElementById("image-input");
  const imagePreview = document.getElementById("image-preview");
  const ocrStatus = document.getElementById("ocr-status");
  const materialInput = document.getElementById("material-input");
  const materialStatus = document.getElementById("material-status");
  let lastOcrConfident = null; // null = no photo used this question

  if (materialInput && materialStatus) {
    materialInput.addEventListener("change", () => {
      const file = materialInput.files[0];
      if (!file) return;
      const sizeMb = (file.size / (1024 * 1024)).toFixed(1);
      materialStatus.textContent = `Selected: ${file.name} (${sizeMb} MB). Ready for a guided lesson.`;
    });
  }

  async function processImageBlob(blob, previewUrl) {
    imagePreview.src = previewUrl;
    imagePreview.classList.remove("hidden");
    setStatus(ocrStatus, "info", "Reading the photo (this runs on this computer)...");
    try {
      const base64 = await blobToBase64(blob);
      const result = await api("/api/ocr", { image: base64 });
      lastOcrConfident = result.confident;
      if (result.confident) {
        recognizedText.value = result.text;
        recognizedWrap.classList.remove("hidden");
        setStatus(ocrStatus, "success", `Read: "${result.text}". Check the text below and edit it if needed.`);
      } else {
        setStatus(ocrStatus, "error", "Could not read this photo clearly. Try better lighting, or type the question instead.");
      }
    } catch (err) {
      lastOcrConfident = false;
      setStatus(ocrStatus, "error", "Could not read the image: " + err.message);
    }
  }

  imageInput.addEventListener("change", () => {
    const file = imageInput.files[0];
    if (!file) return;
    stopCamera();
    processImageBlob(file, URL.createObjectURL(file));
  });

  // -- Live camera viewfinder (desktop webcam or a phone browser) -----------
  const cameraStart = document.getElementById("camera-start");
  const cameraCapture = document.getElementById("camera-capture");
  const cameraStop = document.getElementById("camera-stop");
  const cameraPreview = document.getElementById("camera-preview");
  let cameraStream = null;

  function stopCamera() {
    if (cameraStream) {
      cameraStream.getTracks().forEach((t) => t.stop());
      cameraStream = null;
    }
    cameraPreview.classList.add("hidden");
    cameraPreview.srcObject = null;
    cameraCapture.classList.add("hidden");
    cameraStop.classList.add("hidden");
    cameraStart.classList.remove("hidden");
  }

  cameraStart.addEventListener("click", async () => {
    try {
      cameraStream = await navigator.mediaDevices.getUserMedia({
        video: { facingMode: "environment" },
      });
      cameraPreview.srcObject = cameraStream;
      cameraPreview.classList.remove("hidden");
      cameraStart.classList.add("hidden");
      cameraCapture.classList.remove("hidden");
      cameraStop.classList.remove("hidden");
      setStatus(ocrStatus, "info", "Camera is on. Line up the page, then press Capture Photo.");
    } catch (err) {
      setStatus(ocrStatus, "error", "Could not access the camera: " + err.message);
    }
  });

  cameraCapture.addEventListener("click", () => {
    const canvas = document.createElement("canvas");
    canvas.width = cameraPreview.videoWidth || 640;
    canvas.height = cameraPreview.videoHeight || 480;
    canvas.getContext("2d").drawImage(cameraPreview, 0, 0, canvas.width, canvas.height);
    canvas.toBlob((blob) => {
      if (blob) processImageBlob(blob, canvas.toDataURL("image/png"));
    }, "image/png");
  });

  cameraStop.addEventListener("click", stopCamera);

  // -- Solve ----------------------------------------------------
  const resultStatus = document.getElementById("result-status");
  const resultBlock = document.getElementById("result-block");
  const engineBadge = document.getElementById("engine-badge");
  const resultText = document.getElementById("result-text");
  const brailleText = document.getElementById("braille-text");
  const brailleFidelityCaption = document.getElementById("braille-fidelity-caption");
  const resultAudio = document.getElementById("result-audio");

  const ENGINE_LABELS = {
    "local-deterministic": ["Verified — Solved Locally, Offline", "ok"],
    "local+llm-translation": ["Math Verified — Translated by AI", "ok"],
    "llm-fallback (unverified)": ["Unverified — Solved by AI", "warn"],
    "local-offline": ["Solved Locally — Translation Unavailable Offline", "muted"],
    "error": ["Error", "warn"],
  };

  function questionForCurrentMode() {
    const mode = currentMode();
    if (mode === "type") return document.getElementById("question-text").value.trim();
    return recognizedText.value.trim();
  }

  // -- Step wizard: one screen at a time, fits the viewport ----------------
  const steps = {
    1: document.getElementById("step-1"),
    2: document.getElementById("step-2"),
    3: document.getElementById("step-3"),
  };
  const stepIndicator = document.getElementById("step-indicator");
  const mechanismStatus = document.getElementById("mechanism-status");
  const mechanismStages = document.querySelectorAll("[data-mechanism-stage]");
  const STEP_TITLES = {
    1: "Step 1 of 3: Ask Your Question",
    2: "Step 2 of 3: Choose the Answer Language",
    3: "Step 3 of 3: Your Result",
  };
  let activeStep = 1;

  function setMechanismStage(stage, message) {
    const order = ["hear", "understand", "solve", "respond"];
    const stageIndex = order.indexOf(stage);
    mechanismStages.forEach((item) => {
      const itemIndex = order.indexOf(item.dataset.mechanismStage);
      item.classList.toggle("is-done", itemIndex < stageIndex);
      item.classList.toggle("is-active", itemIndex === stageIndex);
    });
    if (mechanismStatus && message) mechanismStatus.textContent = message;
  }

  function showStep(n, focusEl) {
    activeStep = n;
    Object.entries(steps).forEach(([key, el]) => {
      if (Number(key) === n) el.removeAttribute("hidden");
      else el.setAttribute("hidden", "");
    });
    stepIndicator.textContent = STEP_TITLES[n];
    const target = focusEl || steps[n].querySelector("h2");
    if (target) {
      target.setAttribute("tabindex", "-1");
      target.focus();
    }
  }

  function goToStep1() {
    const errorBox = document.getElementById("step1-error");
    errorBox.classList.add("hidden");
    showStep(1);
  }

  function tryContinueFromStep1() {
    const question = questionForCurrentMode();
    const errorBox = document.getElementById("step1-error");
    if (!question) {
      errorBox.textContent = "Please type, speak, or photograph a question before continuing.";
      errorBox.classList.remove("hidden"); // role="alert" announces this immediately, no focus() needed
      return;
    }
    errorBox.classList.add("hidden");
    setMechanismStage("understand", "Question received. I am understanding the maths now.");
    showStep(2);
  }

  document.getElementById("step1-continue").addEventListener("click", tryContinueFromStep1);
  document.getElementById("step2-back").addEventListener("click", goToStep1);

  document.getElementById("ask-another-btn").addEventListener("click", () => {
    document.getElementById("question-text").value = "";
    recognizedText.value = "";
    recognizedWrap.classList.add("hidden");
    document.getElementById("image-preview").classList.add("hidden");
    document.getElementById("ocr-status").classList.add("hidden");
    voicePlayback.classList.add("hidden");
    stopCamera();
    lastOcrConfident = null;
    setMode("type");
    document.getElementById("question-text").focus();
    goToStep1();
  });

  const toggleHistoryBtn = document.getElementById("toggle-history-btn");
  toggleHistoryBtn.addEventListener("click", () => {
    const panel = document.getElementById("history-panel");
    const willShow = panel.classList.contains("hidden");
    panel.classList.toggle("hidden", !willShow);
    toggleHistoryBtn.setAttribute("aria-expanded", String(willShow));
    toggleHistoryBtn.textContent = willShow ? "Hide Previous Questions" : "View Previous Questions";
  });

  // -- Read Answer Again ---------------------------------------------------
  const readAgainBtn = document.getElementById("read-again-btn");
  let lastAudioDataUrl = null;
  let lastSolutionText = "";

  function readAnswerAgain() {
    if (lastAudioDataUrl) {
      resultAudio.currentTime = 0;
      resultAudio.play().catch(() => {});
    } else if (lastSolutionText && "speechSynthesis" in window) {
      window.speechSynthesis.cancel();
      const utterance = new SpeechSynthesisUtterance(lastSolutionText);
      utterance.rate = 0.85;
      window.speechSynthesis.speak(utterance);
    }
  }
  readAgainBtn.addEventListener("click", readAnswerAgain);

  // -- History of answers this visit --------------------------------------
  const historyList = document.getElementById("history-list");
  const historyEmpty = document.getElementById("history-empty");
  const history = [];

  function addToHistory(question, data) {
    history.unshift({ question, ...data });
    if (history.length > 20) history.pop();
    renderHistory();
  }

  function renderHistory() {
    historyEmpty.classList.toggle("hidden", history.length > 0);
    historyList.innerHTML = "";
    history.forEach((entry, i) => {
      const [label] = ENGINE_LABELS[entry.engine] || [entry.engine];
      const li = document.createElement("li");
      li.className = "history-item";
      const qId = `hist-q-${i}`;
      li.innerHTML = `
        <div class="history-q" id="${qId}">${escapeHtml(entry.question)}</div>
        <div class="caption">${escapeHtml(label)}</div>
        <div class="result-text" style="margin-top:0.5rem">${escapeHtml(entry.solution_text)}</div>
        <div class="btn-row">
          <button type="button" class="btn" data-action="replay" data-index="${i}" aria-describedby="${qId}">🔊 Read This Answer Aloud</button>
        </div>
      `;
      historyList.appendChild(li);
    });
  }

  historyList.addEventListener("click", (e) => {
    const btn = e.target.closest('button[data-action="replay"]');
    if (!btn) return;
    const entry = history[parseInt(btn.dataset.index, 10)];
    if (!entry || !("speechSynthesis" in window)) return;
    window.speechSynthesis.cancel();
    const utterance = new SpeechSynthesisUtterance(entry.solution_text);
    utterance.rate = 0.85;
    window.speechSynthesis.speak(utterance);
  });

  function escapeHtml(str) {
    const div = document.createElement("div");
    div.textContent = str;
    return div.innerHTML;
  }

  // -- Solve ----------------------------------------------------
  const engineProgress = document.getElementById("engine-progress");
  const engineProgressStages = engineProgress.querySelectorAll("li");

  function resetEngineProgress() {
    engineProgressStages.forEach((li) => li.removeAttribute("data-done"));
    engineProgress.classList.add("hidden");
  }

  function markStageDone(stage) {
    const li = engineProgress.querySelector(`[data-stage="${stage}"]`);
    if (li) li.setAttribute("data-done", "true");
  }

  const statBrailleFidelity = document.getElementById("stat-braille-fidelity");
  const statOcrTile = document.getElementById("stat-ocr-tile");
  const statOcrConfidence = document.getElementById("stat-ocr-confidence");

  async function solve(questionOverride) {
    const question = questionOverride !== undefined ? questionOverride : questionForCurrentMode();
    if (!question) {
      setStatus(resultStatus, "error", "Please provide a question first.");
      return;
    }
    solveBtn.disabled = true;
    setStatus(resultStatus, "info", "Solving your question...");
    setMechanismStage("solve", "Math engine is solving locally before translation.");
    resultStatus.setAttribute("aria-busy", "true");
    resetEngineProgress();
    engineProgress.classList.remove("hidden");
    markStageDone("read"); // reading the already-captured question is instant
    try {
      const targetLanguage = document.getElementById("target-language").value;
      const data = await api("/api/solve", {
        question,
        target_language: targetLanguage,
        make_audio: true,
      });
      markStageDone("solve");

      const [label, tone] = ENGINE_LABELS[data.engine] || [data.engine, "muted"];
      engineBadge.textContent = label;
      engineBadge.dataset.tone = tone;
      resultText.textContent = data.solution_text;
      brailleText.textContent = data.braille_text;
      brailleFidelityCaption.textContent =
        `Braille fidelity: ${data.braille_fidelity.accuracy_pct}% ` +
        `(${data.braille_fidelity.mapped_symbol_count}/${data.braille_fidelity.input_symbol_count} symbols). ` +
        "This is an uncontracted preview, not certified Nemeth/UEB math Braille.";

      statBrailleFidelity.textContent = `${data.braille_fidelity.accuracy_pct}%`;
      if (lastOcrConfident !== null) {
        statOcrTile.hidden = false;
        statOcrConfidence.textContent = lastOcrConfident ? "High" : "Low";
      } else {
        statOcrTile.hidden = true;
      }

      lastSolutionText = data.solution_text;
      lastAudioDataUrl = data.audio_data_url || null;

      if (data.audio_data_url) {
        resultAudio.src = data.audio_data_url;
        resultAudio.classList.remove("hidden");
        if (document.getElementById("auto-play").checked) {
          resultAudio.play().catch(() => {});
        }
      } else {
        resultAudio.classList.add("hidden");
      }

      setMechanismStage("respond", "Answer ready. Reading it aloud and showing Braille.");

      let statusMsg = "Your answer is ready. " + (data.notice || "");
      setStatus(resultStatus, "success", statusMsg.trim());
      addToHistory(question, data);
      showStep(3, resultBlock);
      return data;
    } catch (err) {
      setStatus(resultStatus, "error", "Could not solve this question: " + err.message);
      throw err;
    } finally {
      solveBtn.disabled = false;
      resultStatus.removeAttribute("aria-busy");
      setTimeout(resetEngineProgress, 600); // let the user see the completed steps briefly
    }
  }

  solveBtn.addEventListener("click", () => solve());

  // -- Quick Ask: one button, hands-free (record -> transcribe -> solve -> speak) --
  const quickAskBtn = document.getElementById("quick-ask-btn");
  const quickAskLabel = document.getElementById("quick-ask-label");
  const quickAskStatus = document.getElementById("quick-ask-status");
  const quickAskWaveform = document.getElementById("quick-ask-waveform");
  let quickAskRecorder = null;
  let quickAskChunks = [];
  let quickAskRecording = false;
  let stopQuickAskWaveform = () => {};

  async function quickAskToggle() {
    if (!quickAskRecording) {
      try {
        const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
        quickAskChunks = [];
        quickAskRecorder = new MediaRecorder(stream);
        stopQuickAskWaveform = startWaveform(stream, quickAskWaveform);
        quickAskRecorder.ondataavailable = (e) => quickAskChunks.push(e.data);
        quickAskRecorder.onstop = async () => {
          stream.getTracks().forEach((t) => t.stop());
          stopQuickAskWaveform();
          quickAskStatus.textContent = "Understanding your question...";
          try {
            const blob = new Blob(quickAskChunks, { type: "audio/webm" });
            const base64 = await blobToBase64(blob);
            const lang = voiceLanguageSelect.value;
            const heard = await api("/api/voice", { audio: base64, language: lang });
            if (!heard.text || !heard.text.trim()) {
              quickAskStatus.textContent = "I didn't catch that. Please press the button and try again.";
              speakConversation("I did not catch that. Please try once more.");
              return;
            }
            const request = parseVoiceRequest(heard.text);
            if (!request.question) {
              quickAskStatus.textContent = "Please include a maths question, for example: solve 2 plus 2 in Hindi.";
              speakConversation("Please include a maths question, then tell me the answer language.");
              return;
            }
            targetLanguageSelect.value = request.language;
            localStorage.setItem("targetLanguage", request.language);
            setMode("voice");
            recognizedText.value = request.question;
            recognizedWrap.classList.remove("hidden");
            setMechanismStage("understand", "I heard your question. Checking the maths now.");
            quickAskStatus.textContent = `I heard your question. Solving it in ${request.language}...`;
            speakConversation(`I heard your question. I will solve it in ${request.language}.`);
            await solve(request.question);
            quickAskStatus.textContent = `Your answer is ready in ${request.language}. I am reading it aloud now.`;
          } catch (err) {
            quickAskStatus.textContent = "Something went wrong: " + err.message;
          }
        };
        quickAskRecorder.start();
        quickAskRecording = true;
        setMechanismStage("hear", "Listening. Ask one maths question, then press again.");
        quickAskBtn.setAttribute("aria-pressed", "true");
        quickAskLabel.textContent = "Listening... Press again when you're done speaking";
        quickAskStatus.textContent = "Listening. Ask your question, then press the button again.";
      } catch (err) {
        quickAskStatus.textContent = "Could not access the microphone: " + err.message;
      }
    } else {
      if (quickAskRecorder && quickAskRecorder.state !== "inactive") {
        quickAskRecorder.stop();
      }
      quickAskRecording = false;
      quickAskBtn.setAttribute("aria-pressed", "false");
      quickAskLabel.textContent = "Press to Ask a Question by Voice";
    }
  }
  quickAskBtn.addEventListener("click", quickAskToggle);

  // -- Keyboard shortcuts ----------------------------------------------------
  document.addEventListener("keydown", (e) => {
    if (!e.altKey) {
      if (e.key === "Escape") {
        if ("speechSynthesis" in window) window.speechSynthesis.cancel();
        document.querySelectorAll("audio").forEach((a) => a.pause());
      }
      return;
    }
    const key = e.key.toLowerCase();
    if (key === "s") {
      e.preventDefault();
      if (activeStep === 1) tryContinueFromStep1();
      else if (activeStep === 2) solve().catch(() => {});
    } else if (key === "b") {
      e.preventDefault();
      if (activeStep === 2) goToStep1();
    } else if (key === "q" && activeStep === 1) {
      e.preventDefault();
      quickAskToggle();
    } else if (key === "r" && activeStep === 3) {
      e.preventDefault();
      readAnswerAgain();
    } else if (key === "1" && activeStep === 1) {
      e.preventDefault();
      setMode("type");
      document.getElementById("question-text").focus();
    } else if (key === "2" && activeStep === 1) {
      e.preventDefault();
      setMode("voice");
      recordStart.focus();
    } else if (key === "3" && activeStep === 1) {
      e.preventDefault();
      setMode("image");
      imageInput.focus();
    }
  });

  // Now that every const above (including stopCamera) is initialized, set
  // the actual initial panel state.
  showPanel(currentMode());
})();

// ---------------------------------------------------------------------------
// Worksheet page logic (only runs if the page has these elements)
// ---------------------------------------------------------------------------
(function initWorksheetPage() {
  const worksheetBtn = document.getElementById("worksheet-btn");
  if (!worksheetBtn) return; // not on this page

  const ENGINE_LABELS = {
    "local-deterministic": ["Verified — Solved Locally, Offline", "ok"],
    "local+llm-translation": ["Math Verified — Translated by AI", "ok"],
    "llm-fallback (unverified)": ["Unverified — Solved by AI", "warn"],
    "local-offline": ["Solved Locally — Translation Unavailable Offline", "muted"],
    "error": ["Error", "warn"],
  };

  const statusBox = document.getElementById("worksheet-status");
  const summaryBox = document.getElementById("worksheet-summary");
  const resultsWrap = document.getElementById("worksheet-results");

  worksheetBtn.addEventListener("click", async () => {
    const lines = document.getElementById("worksheet-questions").value
      .split("\n").map((l) => l.trim()).filter(Boolean);
    if (lines.length === 0) {
      statusBox.dataset.kind = "error";
      statusBox.textContent = "Please enter at least one question.";
      return;
    }
    worksheetBtn.disabled = true;
    statusBox.dataset.kind = "info";
    statusBox.textContent = `Solving ${lines.length} question(s)...`;
    summaryBox.classList.add("hidden");
    resultsWrap.innerHTML = "";

    try {
      const targetLanguage = document.getElementById("worksheet-language").value;
      const data = await api("/api/worksheet", { questions: lines, target_language: targetLanguage });

      statusBox.dataset.kind = "success";
      statusBox.textContent = "Done.";
      summaryBox.classList.remove("hidden");
      summaryBox.textContent =
        `${data.total_questions} question(s) solved. ` +
        `${data.solved_without_llm_math_risk_pct}% solved with zero AI-math risk.`;

      data.results.forEach((r, i) => {
        const [label, tone] = ENGINE_LABELS[r.engine] || [r.engine, "muted"];
        const card = document.createElement("fieldset");
        card.innerHTML = `
          <legend>Question ${i + 1}: ${escapeHtml(r.question)}</legend>
          <div class="engine-badge" data-tone="${tone}">${label}</div>
          <div class="result-text">${escapeHtml(r.solution_text)}</div>
          <div class="braille-box" style="font-size:1.8rem;margin-top:0.75rem">${escapeHtml(r.braille_text)}</div>
        `;
        resultsWrap.appendChild(card);
      });
    } catch (err) {
      statusBox.dataset.kind = "error";
      statusBox.textContent = "Could not solve the worksheet: " + err.message;
    } finally {
      worksheetBtn.disabled = false;
    }
  });

  function escapeHtml(str) {
    const div = document.createElement("div");
    div.textContent = str;
    return div.innerHTML;
  }
})();
