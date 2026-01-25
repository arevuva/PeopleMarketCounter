const imageInput = document.getElementById("imageInput");
const videoInput = document.getElementById("videoInput");
const streamInput = document.getElementById("streamInput");
const startButton = document.getElementById("startButton");
const statusEl = document.getElementById("status");
const currentCountEl = document.getElementById("currentCount");
const maxCountEl = document.getElementById("maxCount");
const errorEl = document.getElementById("error");
const imagePreview = document.getElementById("imagePreview");
const fpsInput = document.getElementById("fpsInput");
const maxSecondsInput = document.getElementById("maxSecondsInput");
const confInput = document.getElementById("confInput");
const tabs = document.querySelectorAll(".tab");
const tabPanels = document.querySelectorAll(".tab-panel");

let activeSocket = null;
let activeTab = "image";

function resetStatus() {
  statusEl.textContent = "idle";
  currentCountEl.textContent = "-";
  maxCountEl.textContent = "-";
  errorEl.textContent = "";
  imagePreview.src = "";
  imagePreview.classList.remove("visible");
}

function updateButtonState() {
  const hasImage = imageInput.files && imageInput.files.length > 0;
  const hasVideo = videoInput.files && videoInput.files.length > 0;
  const hasStream = streamInput.value.trim().length > 0;
  if (activeTab === "image") {
    startButton.disabled = !hasImage;
  } else if (activeTab === "video") {
    startButton.disabled = !hasVideo;
  } else {
    startButton.disabled = !hasStream;
  }
}

function setStatus(status) {
  statusEl.textContent = status;
}

function closeSocket() {
  if (activeSocket) {
    activeSocket.close();
    activeSocket = null;
  }
}

async function processImage(file) {
  setStatus("processing");
  const formData = new FormData();
  formData.append("image", file);
  const conf = parseFloat(confInput.value || "0.25");
  try {
    const response = await fetch(`/api/process/image?conf=${conf}`, {
      method: "POST",
      body: formData,
    });
    if (!response.ok) {
      throw new Error(await response.text());
    }
    const result = await response.json();
    currentCountEl.textContent = result.count;
    maxCountEl.textContent = result.count;
    if (result.image_b64) {
      imagePreview.src = `data:image/jpeg;base64,${result.image_b64}`;
      imagePreview.classList.add("visible");
    }
    setStatus("done");
  } catch (error) {
    setStatus("error");
    errorEl.textContent = error.message || "Failed to process image";
  }
}

function startSocket(jobId) {
  closeSocket();
  const protocol = window.location.protocol === "https:" ? "wss" : "ws";
  const wsUrl = `${protocol}://${window.location.host}/ws/job/${jobId}`;
  const socket = new WebSocket(wsUrl);
  activeSocket = socket;

  socket.onmessage = (event) => {
    const payload = JSON.parse(event.data);
    if (payload.type === "frame") {
      currentCountEl.textContent = payload.count;
      maxCountEl.textContent = payload.max_count;
      setStatus("processing");
    }
    if (payload.type === "done") {
      maxCountEl.textContent = payload.max_count;
      setStatus("done");
    }
    if (payload.type === "error") {
      setStatus("error");
      errorEl.textContent = payload.message || "Processing error";
    }
  };

  socket.onerror = () => {
    setStatus("error");
    errorEl.textContent = "WebSocket error";
  };
}

async function processVideo(file) {
  setStatus("processing");
  const formData = new FormData();
  formData.append("video", file);
  formData.append("fps", fpsInput.value || "5");
  formData.append("max_seconds", maxSecondsInput.value || "0");
  try {
    const response = await fetch("/api/process/video", {
      method: "POST",
      body: formData,
    });
    if (!response.ok) {
      throw new Error(await response.text());
    }
    const result = await response.json();
    startSocket(result.job_id);
  } catch (error) {
    setStatus("error");
    errorEl.textContent = error.message || "Failed to process video";
  }
}

async function processStream(url) {
  setStatus("processing");
  try {
    const response = await fetch("/api/process/stream", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        url,
        fps: Number(fpsInput.value || 5),
        max_seconds: Number(maxSecondsInput.value || 0),
      }),
    });
    if (!response.ok) {
      throw new Error(await response.text());
    }
    const result = await response.json();
    startSocket(result.job_id);
  } catch (error) {
    setStatus("error");
    errorEl.textContent = error.message || "Failed to process stream";
  }
}

startButton.addEventListener("click", () => {
  resetStatus();
  closeSocket();
  const hasImage = imageInput.files && imageInput.files.length > 0;
  const hasVideo = videoInput.files && videoInput.files.length > 0;
  const streamUrl = streamInput.value.trim();

  if (activeTab === "image" && hasImage) {
    processImage(imageInput.files[0]);
    return;
  }
  if (activeTab === "video" && hasVideo) {
    processVideo(videoInput.files[0]);
    return;
  }
  if (activeTab === "stream" && streamUrl) {
    processStream(streamUrl);
  }
});

function setActiveTab(tabName) {
  activeTab = tabName;
  tabs.forEach((tab) => {
    tab.classList.toggle("active", tab.dataset.tab === tabName);
  });
  tabPanels.forEach((panel) => {
    panel.classList.toggle("active", panel.id === `tab-${tabName}`);
  });
  imagePreview.src = "";
  imagePreview.classList.remove("visible");
  updateButtonState();
}

tabs.forEach((tab) => {
  tab.addEventListener("click", () => {
    setActiveTab(tab.dataset.tab);
  });
});

[imageInput, videoInput, streamInput].forEach((input) => {
  input.addEventListener("change", () => {
    updateButtonState();
  });
});

[streamInput, fpsInput, maxSecondsInput, confInput].forEach((input) => {
  input.addEventListener("input", updateButtonState);
});

updateButtonState();
setActiveTab(activeTab);
