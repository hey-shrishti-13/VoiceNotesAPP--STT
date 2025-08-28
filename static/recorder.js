let recordBtn = document.getElementById("recordBtn");
let stopBtn = document.getElementById("stopBtn");
let origTextEl = document.getElementById("origText");
let enTextEl = document.getElementById("enText");
let statusEl = document.getElementById("status");

let mediaRecorder;
let audioChunks = [];

let recognition;
if ("webkitSpeechRecognition" in window || "SpeechRecognition" in window) {
  const SpeechRecognition = window.SpeechRecognition || window.webkitSpeechRecognition;
  recognition = new SpeechRecognition();
  recognition.continuous = true;
  recognition.interimResults = true;
  recognition.lang = 'hi-IN'; // Set to Hindi, but will work for English too
  recognition.onresult = (event) => {
    let interim = "";
    let final = "";
    for (let i = event.resultIndex; i < event.results.length; ++i) {
      let text = event.results[i][0].transcript;
      if (event.results[i].isFinal) final += text;
      else interim += text;
    }
    origTextEl.textContent = final + " " + interim;
  };
  recognition.onerror = (e) => {
    console.warn("SpeechRecognition error", e);
  };
}

recordBtn.onclick = async () => {
  recordBtn.disabled = true;
  stopBtn.disabled = false;
  origTextEl.textContent = "(listening... please speak in Hindi or English)";
  enTextEl.textContent = "(waiting...)";
  statusEl.textContent = "Recording... (Hindi/English only)";

  if (recognition) {
    try { recognition.start(); } catch(e) {}
  }

  const stream = await navigator.mediaDevices.getUserMedia({audio: true});
  mediaRecorder = new MediaRecorder(stream);
  audioChunks = [];
  mediaRecorder.ondataavailable = e => {
    if (e.data && e.data.size > 0) audioChunks.push(e.data);
  };
  mediaRecorder.start();
};

stopBtn.onclick = async () => {
  stopBtn.disabled = true;
  recordBtn.disabled = false;
  statusEl.textContent = "Processing... (checking language)";
  if (recognition) {
    try { recognition.stop(); } catch(e) {}
  }

  mediaRecorder.stop();
  mediaRecorder.onstop = async () => {
    statusEl.textContent = "Uploading and transcribing...";
    const blob = new Blob(audioChunks, { type: "audio/webm" });
    const fd = new FormData();
    fd.append("audio_data", blob, "note.webm");

    try {
      const resp = await fetch("/upload_audio", { method: "POST", body: fd });
      const j = await resp.json();
      if (j.error) {
        statusEl.textContent = "Error: " + j.error;
        statusEl.style.color = "#dc3545";
        origTextEl.textContent = "(Please try again with Hindi or English)";
        enTextEl.textContent = "(Please try again with Hindi or English)";
      } else {
        statusEl.style.color = "#28a745";
        origTextEl.textContent = j.orig_text || "(no text)";
        enTextEl.textContent = j.en_text || "(no translation)";
        statusEl.innerHTML = `Saved successfully! Language: ${j.language} | <a href="${j.txt_file}">.txt</a> | <a href="${j.docx_file}">.docx</a>`;
      }
    } catch (err) {
      console.error(err);
      statusEl.textContent = "Upload/processing failed. Please try again.";
      statusEl.style.color = "#dc3545";
    }
  };
};