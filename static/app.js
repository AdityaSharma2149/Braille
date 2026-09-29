"use strict";

const question = document.getElementById("question");
const form = document.getElementById("question-form");
const errorMessage = document.getElementById("error");
const statusMessage = document.getElementById("status");
const results = document.getElementById("results");
const historyStorageKey = "sparsh-history";
const rememberStorageKey = "sparsh-remember-history";
const examples = [
  { question: "(3/4 + 1/2) * 2", title: "Make sense of fractions" },
  { question: "2x + 3 = 11", title: "Find the missing piece" },
];
let currentSteps = [];
let recognition;

function setStatus(message) {
  statusMessage.textContent = message;
}

function showError(message) {
  errorMessage.textContent = message;
  errorMessage.hidden = !message;
}

function updateCharacterCount() {
  document.getElementById("char-count").textContent = `${question.value.length} / 500`;
}

function historyEnabled() {
  return document.getElementById("remember-history").checked;
}

function readHistory() {
  if (!historyEnabled()) return [];
  try {
    return JSON.parse(localStorage.getItem(historyStorageKey) || "[]");
  } catch {
    return [];
  }
}

function renderHistory() {
  const entries = readHistory();
  const list = document.getElementById("history-list");
  document.getElementById("history-count").textContent = String(entries.length);
  list.replaceChildren();
  if (!entries.length) {
    const empty = document.createElement("p");
    empty.className = "muted";
    empty.textContent = "Your recent questions will appear here.";
    list.append(empty);
    return;
  }
  entries.forEach((entry) => {
    const item = document.createElement("article");
    item.className = "history-item";
    const prompt = document.createElement("strong");
    prompt.textContent = entry.question;
    const answer = document.createElement("span");
    answer.textContent = entry.answer;
    const reopen = document.createElement("button");
    reopen.className = "text-button";
    reopen.type = "button";
    reopen.textContent = "Explore again";
    reopen.addEventListener("click", () => {
      question.value = entry.question;
      updateCharacterCount();
      showView("learn");
      question.focus();
    });
    item.append(prompt, answer, reopen);
    list.append(item);
  });
}

function saveHistory(entry) {
  if (!historyEnabled()) return;
  const entries = [entry, ...readHistory().filter((saved) => saved.question !== entry.question)].slice(0, 30);
  localStorage.setItem(historyStorageKey, JSON.stringify(entries));
  renderHistory();
}

function showView(name) {
  document.querySelectorAll(".view").forEach((view) => {
    view.hidden = view.id !== `${name}-view`;
  });
  document.querySelectorAll("[data-view]").forEach((button) => {
    const active = button.dataset.view === name;
    button.classList.toggle("active", active);
    if (active) button.setAttribute("aria-current", "page");
    else button.removeAttribute("aria-current");
  });
  const titles = { learn: "Learning studio", practice: "Practice library", history: "My activity" };
  document.getElementById("page-name").textContent = titles[name];
  if (name === "history") renderHistory();
}

function chooseMode(name) {
  ["type", "voice", "scan"].forEach((mode) => {
    const button = document.getElementById(`${mode}-mode`);
    const selected = mode === name;
    button.classList.toggle("selected", selected);
    button.setAttribute("aria-pressed", String(selected));
  });
  document.getElementById("voice-panel").hidden = name !== "voice";
  document.getElementById("scan-panel").hidden = name !== "scan";
  if (name === "voice") document.getElementById("input-language").focus();
  if (name === "scan") document.getElementById("image-file").focus();
  if (name === "type") question.focus();
}

function speakSteps(steps = currentSteps) {
  if (!("speechSynthesis" in window)) {
    document.getElementById("audio-status").textContent = "Speech is not available in this browser.";
    return;
  }
  window.speechSynthesis.cancel();
  const rate = Number(document.getElementById("speed").value);
  const language = document.getElementById("language").value;
  const preferredVoice = document.getElementById("voice-select").value;
  steps.forEach((step) => {
    if (!step.speech) return;
    const utterance = new SpeechSynthesisUtterance(step.speech);
    utterance.rate = rate;
    utterance.lang = language === "hi" ? "hi-IN" : language === "ta" ? "ta-IN" : "en-US";
    utterance.voice = window.speechSynthesis.getVoices().find((voice) => voice.name === preferredVoice) || null;
    window.speechSynthesis.speak(utterance);
  });
  document.getElementById("audio-status").textContent = "Playing the solution.";
}

function displayResult(data) {
  document.getElementById("answer").textContent = data.answer;
  document.getElementById("result-kind").textContent = data.kind;
  const steps = document.getElementById("steps");
  steps.replaceChildren();
  currentSteps = data.steps || [];
  currentSteps.forEach((step) => {
    const item = document.createElement("li");
    const title = document.createElement("strong");
    title.textContent = step.title;
    const text = document.createElement("p");
    text.textContent = step.text;
    item.append(title, text);
    steps.append(item);
  });
  document.getElementById("braille").textContent = data.braille?.text || "";
  document.getElementById("braille-note").textContent = "English letters and digits preview only. This is not a certified mathematical Braille translation.";
  document.getElementById("braille-unsupported").textContent = data.braille?.unsupported?.length
    ? `Not represented in the preview: ${data.braille.unsupported.join(" ")}`
    : "";
  results.hidden = false;
  document.getElementById("result-heading").focus();
  saveHistory({ question: data.question || question.value, answer: data.answer });
  if (document.getElementById("auto-read").checked) speakSteps();
}

async function requestJson(url, payload) {
  const response = await fetch(url, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
  const data = await response.json();
  if (!response.ok) throw new Error(data.error || `Request failed (${response.status}).`);
  return data;
}

form.addEventListener("submit", async (event) => {
  event.preventDefault();
  showError("");
  const button = document.getElementById("solve-button");
  button.disabled = true;
  setStatus("Working through your question.");
  try {
    const data = await requestJson("/api/solve", {
      question: question.value,
      language: document.getElementById("language").value,
    });
    displayResult(data);
    setStatus("Solution ready.");
  } catch (error) {
    showError(error.message || "Could not reach the local math service.");
    setStatus("The question could not be solved.");
  } finally {
    button.disabled = false;
  }
});

question.addEventListener("input", updateCharacterCount);
document.querySelectorAll("[data-example]").forEach((button) => {
  button.addEventListener("click", () => {
    question.value = button.dataset.example;
    updateCharacterCount();
    question.focus();
  });
});

document.querySelectorAll("[data-view]").forEach((button) => {
  button.addEventListener("click", () => showView(button.dataset.view));
});
document.getElementById("type-mode").addEventListener("click", () => chooseMode("type"));
document.getElementById("voice-mode").addEventListener("click", () => chooseMode("voice"));
document.getElementById("scan-mode").addEventListener("click", () => chooseMode("scan"));

document.getElementById("scan").addEventListener("click", async () => {
  const file = document.getElementById("image-file").files[0];
  const scanStatus = document.getElementById("scan-status");
  scanStatus.textContent = "";
  if (!file) {
    scanStatus.textContent = "Choose a PNG or JPEG image first.";
    return;
  }
  if (file.size > 6 * 1024 * 1024) {
    scanStatus.textContent = "Choose an image smaller than 6 MB.";
    return;
  }
  try {
    const encoded = await new Promise((resolve, reject) => {
      const reader = new FileReader();
      reader.onload = () => resolve(String(reader.result).split(",")[1]);
      reader.onerror = () => reject(new Error("This image could not be read."));
      reader.readAsDataURL(file);
    });
    const data = await requestJson("/api/ocr", { image: encoded });
    question.value = data.text;
    updateCharacterCount();
    scanStatus.textContent = data.notice;
    question.focus();
  } catch (error) {
    scanStatus.textContent = error.message || "Could not scan this image.";
  }
});

document.getElementById("record").addEventListener("click", () => {
  const Recognition = window.SpeechRecognition || window.webkitSpeechRecognition;
  const voiceStatus = document.getElementById("voice-status");
  if (!Recognition) {
    voiceStatus.textContent = "Speech recognition is not available in this browser.";
    return;
  }
  if (!recognition) {
    recognition = new Recognition();
    recognition.interimResults = false;
    recognition.onresult = (event) => {
      question.value = event.results[0][0].transcript;
      updateCharacterCount();
      voiceStatus.textContent = "Speech recognized. Review the question before solving.";
    };
    recognition.onerror = () => { voiceStatus.textContent = "Speech recognition failed. Try typing your question."; };
    recognition.onend = () => { document.getElementById("record").textContent = "Start listening"; };
  }
  recognition.lang = document.getElementById("input-language").value;
  recognition.start();
  document.getElementById("record").textContent = "Listening…";
  voiceStatus.textContent = "Listening. Speak your math question.";
});

document.getElementById("listen-all").addEventListener("click", () => speakSteps());
document.getElementById("stop-audio").addEventListener("click", () => {
  if ("speechSynthesis" in window) window.speechSynthesis.cancel();
  document.getElementById("audio-status").textContent = "Speech stopped.";
});
document.getElementById("download").addEventListener("click", () => {
  const lines = [question.value, `Result: ${document.getElementById("answer").textContent}`, ...currentSteps.map((step) => `${step.title}: ${step.text}`)];
  const url = URL.createObjectURL(new Blob([lines.join("\n\n")], { type: "text/plain;charset=utf-8" }));
  const link = document.createElement("a");
  link.href = url;
  link.download = "sparsh-study-notes.txt";
  link.click();
  URL.revokeObjectURL(url);
});

document.getElementById("clear-history").addEventListener("click", () => {
  localStorage.removeItem(historyStorageKey);
  renderHistory();
});
const rememberHistory = document.getElementById("remember-history");
rememberHistory.checked = localStorage.getItem(rememberStorageKey) !== "false";
rememberHistory.addEventListener("change", () => {
  localStorage.setItem(rememberStorageKey, String(rememberHistory.checked));
  if (!rememberHistory.checked) localStorage.removeItem(historyStorageKey);
  renderHistory();
});
document.getElementById("history-count").textContent = String(readHistory().length);

const practiceList = document.getElementById("practice-list");
examples.forEach((example) => {
  const button = document.createElement("button");
  button.className = "starter";
  button.type = "button";
  button.textContent = `${example.title}: ${example.question}`;
  button.addEventListener("click", () => {
    question.value = example.question;
    updateCharacterCount();
    showView("learn");
    question.focus();
  });
  practiceList.append(button);
});

function openDialog(id) {
  const dialog = document.getElementById(id);
  if (!dialog.open) dialog.showModal();
}

document.getElementById("open-settings").addEventListener("click", () => openDialog("settings-dialog"));
document.getElementById("open-help").addEventListener("click", () => openDialog("help-dialog"));
document.getElementById("shortcuts-link").addEventListener("click", () => openDialog("help-dialog"));
document.querySelectorAll(".close-dialog").forEach((button) => {
  button.addEventListener("click", () => button.closest("dialog").close());
});
document.getElementById("settings-done").addEventListener("click", () => document.getElementById("settings-dialog").close());

document.getElementById("contrast-toggle").addEventListener("click", (event) => {
  const enabled = event.currentTarget.getAttribute("aria-pressed") !== "true";
  event.currentTarget.setAttribute("aria-pressed", String(enabled));
  document.documentElement.classList.toggle("high-contrast", enabled);
});
document.getElementById("large-text").addEventListener("change", (event) => {
  document.documentElement.classList.toggle("large-text", event.currentTarget.checked);
});

document.addEventListener("keydown", (event) => {
  if ((event.ctrlKey || event.metaKey) && event.key === "Enter") {
    event.preventDefault();
    form.requestSubmit();
  } else if (event.altKey && event.key.toLowerCase() === "q") {
    event.preventDefault();
    showView("learn");
    question.focus();
  } else if (event.altKey && event.key.toLowerCase() === "l") {
    event.preventDefault();
    speakSteps();
  } else if (event.key === "Escape" && "speechSynthesis" in window) {
    window.speechSynthesis.cancel();
  }
});

document.querySelectorAll("dialog").forEach((dialog) => {
  dialog.addEventListener("click", (event) => {
    if (event.target === dialog) dialog.close();
  });
});