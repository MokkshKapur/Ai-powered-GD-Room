let socket;
let mediaRecorder, audioChunks = [];
let audioQueue = [], isPlaying = false;
let micStream, audioContext, analyser;
let silenceStart = null;
let pendingUserRecording = false;
let micAlreadyQueued = false;
let gdStartTime = null;

const SILENCE_THRESHOLD = 0.01;
const SILENCE_DURATION = 2000;
const MAX_DURATION_MS = 5 * 60 * 1000; // 5 minutes

function updateStatus(status, type) {
  const statusDiv = document.getElementById('status');
  statusDiv.textContent = status;
  statusDiv.className = type;
}

function addMessage(text, type, sender = '') {
  const messages = document.getElementById('messages');
  const messageDiv = document.createElement('div');
  messageDiv.className = `message ${type}`;
  messageDiv.textContent = sender ? `${sender}: ${text}` : text;
  messages.appendChild(messageDiv);
  messages.scrollTop = messages.scrollHeight;
  return messageDiv;
}

function debug(info) {
  const debugDiv = document.getElementById('debugInfo');
  debugDiv.style.display = 'block';
  debugDiv.innerHTML += `<div>${new Date().toISOString()}: ${info}</div>`;
  debugDiv.scrollTop = debugDiv.scrollHeight;
}

async function playNextAudio() {
  if (audioQueue.length === 0 || isPlaying) return;

  isPlaying = true;
  const { audio, messageDiv, sender } = audioQueue[0];

  try {
    messageDiv.textContent = `${sender} is speaking...`;
    await audio.play();
    await new Promise(resolve => audio.onended = resolve);
    messageDiv.textContent = `${sender}: (Finished speaking)`;
  } catch (e) {
    debug(`Audio play error: ${e.message}`);
    messageDiv.textContent = `${sender}: (Audio failed to play)`;
  }

  audioQueue.shift();
  isPlaying = false;
  playNextAudio();

  if (audioQueue.length === 0 && !isPlaying && pendingUserRecording) {
    pendingUserRecording = false;
    micAlreadyQueued = false;
    startAutoRecording();
  }
}

function checkGDTimeout() {
  if (gdStartTime && Date.now() - gdStartTime > MAX_DURATION_MS) {
    debug("⏳ Time limit reached. Forcing moderator conclusion...");
    socket.send(JSON.stringify({
      type: "control",
      action: "force_conclude"
    }));
  }
}

function initWebSocket() {
  socket = new WebSocket('ws://localhost:8000/ws/gd');

  socket.onopen = () => {
    debug('WebSocket connected');
    updateStatus('Connected', 'connected');
    gdStartTime = Date.now();
    setInterval(checkGDTimeout, 10000); // check every 10 seconds
  };

  socket.onclose = () => {
    debug('WebSocket disconnected');
    updateStatus('Disconnected', 'disconnected');
    setTimeout(initWebSocket, 3000);
  };

  socket.onerror = () => {
    debug('WebSocket error');
    updateStatus('Error', 'disconnected');
  };

  socket.onmessage = event => {
    try {
      const data = JSON.parse(event.data);

      if (data.type === "control") {
        if (data.action === "start_recording") {
          if (isPlaying || audioQueue.length > 0) {
            if (!micAlreadyQueued) {
              debug("⏳ User mic queued (waiting for AI to finish)...");
              micAlreadyQueued = true;
            }
            pendingUserRecording = true;
          } else {
            startAutoRecording();
          }
        } else if (data.action === "stop_recording") {
          stopAutoRecording();
        } else if (data.action === "force_stop") {
          stopAutoRecording();
          audioQueue = []; // Clear queued agent responses
          isPlaying = false;
          micAlreadyQueued = false;
          pendingUserRecording = false;
        }
        return;
      }

      if (data.sender && data.audio) {
        const exists = audioQueue.find(a => a.sender === data.sender);
        if (!exists) {
          const msg = addMessage('Waiting to speak...', 'agent', data.sender);
          const audio = new Audio(`data:audio/mp3;base64,${data.audio}`);
          audioQueue.push({ audio, messageDiv: msg, sender: data.sender });
          playNextAudio();
        }
      } else if (data.type === "transcript") {
        const type = data.sender === "Mokksh" ? "user" : "agent";
        addMessage(data.text, type, data.sender);
        if (type === "user" && /(conclude|wrap up|summarize|end)/i.test(data.text)) {
          debug("🗣️ User attempted to conclude GD. Triggering moderator response...");
          socket.send(JSON.stringify({
            type: "control",
            action: "force_conclude"
          }));
        }
      } else {
        addMessage(event.data, 'system');
      }
    } catch (e) {
      addMessage(event.data, 'system');
    }
  };
}

async function startAutoRecording() {
  if (isPlaying || audioQueue.length > 0) {
    if (!micAlreadyQueued) {
      debug("⏳ User mic queued (waiting for AI to finish)...");
      micAlreadyQueued = true;
    }
    pendingUserRecording = true;
    return;
  }

  micAlreadyQueued = false;
  addMessage("🎙️ Your turn to speak...", "system");
  debug("🎤 Mic starting...");

  const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
  micStream = stream;
  mediaRecorder = new MediaRecorder(stream, { mimeType: 'audio/webm;codecs=opus' });
  audioChunks = [];
  silenceStart = null;

  mediaRecorder.ondataavailable = e => {
    if (e.data.size > 0) audioChunks.push(e.data);
  };

  mediaRecorder.onstop = () => {
    const blob = new Blob(audioChunks, { type: 'audio/webm' });
    const reader = new FileReader();
    reader.onloadend = () => {
      const base64Audio = reader.result.split(',')[1];

      socket.send(JSON.stringify({
        type: "audio_chunk",
        data: base64Audio
      }));
      debug(`✅ Sent audio_chunk (${blob.size} bytes)`);

      socket.send(JSON.stringify({
        type: "control",
        action: "end_turn"
      }));
      debug("📩 Sent end_turn control message to backend");
    };
    reader.readAsDataURL(blob);
    audioChunks = [];
  };

  mediaRecorder.start();

  audioContext = new AudioContext();
  const source = audioContext.createMediaStreamSource(stream);
  analyser = audioContext.createAnalyser();
  analyser.fftSize = 2048;
  source.connect(analyser);

  detectSilenceLoop();
}

function detectSilenceLoop() {
  const buffer = new Uint8Array(analyser.fftSize);
  analyser.getByteTimeDomainData(buffer);

  let rms = 0;
  for (let i = 0; i < buffer.length; i++) {
    const norm = (buffer[i] - 128) / 128;
    rms += norm * norm;
  }
  rms = Math.sqrt(rms / buffer.length);

  document.getElementById('mic-bar').style.width = `${Math.min(rms * 500, 100)}%`;

  if (rms < SILENCE_THRESHOLD) {
    if (!silenceStart) silenceStart = Date.now();
    else if (Date.now() - silenceStart > SILENCE_DURATION) {
      debug("🛑 Silence detected: stopping recording...");
      stopAutoRecording();
      return;
    }
  } else {
    silenceStart = null;
  }

  requestAnimationFrame(detectSilenceLoop);
}

function stopAutoRecording() {
  if (mediaRecorder && mediaRecorder.state === "recording") mediaRecorder.stop();
  if (micStream) micStream.getTracks().forEach(track => track.stop());
  if (audioContext) audioContext.close();
}

window.onload = () => {
  initWebSocket();
  document.addEventListener('click', function unlockOnce() {
    new Audio();
    const prompt = document.getElementById("unlock-prompt");
    if (prompt) prompt.style.display = "none";
    document.removeEventListener('click', unlockOnce);
    console.log("🔓 Audio playback unlocked");
  });
};
