console.log("People Counter app.js loaded");
const imageInput = document.getElementById("imageInput");
const videoInput = document.getElementById("videoInput");
const streamInput = document.getElementById("streamInput");
const startButton = document.getElementById("startButton");
const statusEl = document.getElementById("status");
const currentCountEl = document.getElementById("currentCount");
const maxCountEl = document.getElementById("maxCount");
const errorEl = document.getElementById("error");
const imagePreview = document.getElementById("imagePreview");
const videoPreview = document.getElementById("videoPreview");
const videoPreviewContainer = document.getElementById("videoPreviewContainer");
const streamPreview = document.getElementById("streamPreview");
const historyList = document.getElementById("historyList");
const fpsInput = document.getElementById("fpsInput");
const maxSecondsInput = document.getElementById("maxSecondsInput");
const confInput = document.getElementById("confInput");
const tabs = document.querySelectorAll(".tab");
const tabPanels = document.querySelectorAll(".tab-panel");
const controlLabels = {
  fps: document.querySelector('[data-control="fps"]'),
  maxSeconds: document.querySelector('[data-control="max-seconds"]'),
  conf: document.querySelector('[data-control="conf"]'),
};
const controlsPanel = document.getElementById("controlsPanel");
const resultsPanel = document.getElementById("resultsPanel");

let activeSocket = null;
let activeTab = "image";
const statusLabels = {
  idle: "ожидание",
  processing: "обработка",
  done: "готово",
  error: "ошибка",
};

function resetStatus() {
  statusEl.textContent = statusLabels.idle;
  currentCountEl.textContent = "-";
  maxCountEl.textContent = "-";
  errorEl.textContent = "";
  imagePreview.src = "";
  imagePreview.classList.remove("visible");
  if (videoPreview) {
    videoPreview.removeAttribute("src");
    videoPreview.load();
  }
  if (videoPreviewContainer) {
    videoPreviewContainer.classList.remove("visible");
  }
  if (streamPreview) {
    streamPreview.removeAttribute("src");
  }
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
  statusEl.textContent = statusLabels[status] || status;
}

function closeSocket() {
  if (activeSocket) {
    activeSocket.close();
    activeSocket = null;
  }
}

function setStreamPreview(jobId) {
  if (!streamPreview) {
    return;
  }
  streamPreview.src = `/api/job/${jobId}/mjpeg?ts=${Date.now()}`;
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
    errorEl.textContent = error.message || "Не удалось обработать изображение";
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
      if (payload.video_url && activeTab === "video" && videoPreview) {
        videoPreview.src = payload.video_url;
        videoPreview.load();
        if (videoPreviewContainer) {
          videoPreviewContainer.classList.add("visible");
        }
      }
      setStatus("done");
    }
    if (payload.type === "error") {
      setStatus("error");
      errorEl.textContent = payload.message || "Ошибка обработки";
    }
  };

  socket.onerror = () => {
    setStatus("error");
    errorEl.textContent = "Ошибка WebSocket";
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
    errorEl.textContent = error.message || "Не удалось обработать видео";
  }
}

async function processStream(url) {
  setStatus("processing");
  const streamWindow = window.open("", "_blank");
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
    setStreamPreview(result.job_id);
    if (streamWindow) {
      streamWindow.location = `/api/job/${result.job_id}/mjpeg`;
    }
  } catch (error) {
    setStatus("error");
    errorEl.textContent = error.message || "Не удалось обработать поток";
    if (streamWindow) {
      streamWindow.close();
    }
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
  if (videoPreview) {
    videoPreview.removeAttribute("src");
    videoPreview.load();
  }
  if (videoPreviewContainer) {
    videoPreviewContainer.classList.remove("visible");
  }

  updateControlsVisibility();
  updateButtonState();
  if (activeTab === "history") {
    loadHistory();
  }
  const showProcessingPanels = activeTab !== "history";
  if (controlsPanel) {
    controlsPanel.style.display = showProcessingPanels ? "" : "none";
  }
  if (resultsPanel) {
    resultsPanel.style.display = showProcessingPanels ? "" : "none";
  }
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

function updateControlsVisibility() {
  const showImageControls = activeTab === "image";
  if (controlLabels.fps) {
    controlLabels.fps.style.display = activeTab === "video" || activeTab === "stream" ? "none" : "";
  }
  if (controlLabels.maxSeconds) {
    controlLabels.maxSeconds.style.display =
      activeTab === "video" || activeTab === "stream" ? "none" : "";
  }
  if (controlLabels.conf) {
    controlLabels.conf.style.display = showImageControls ? "" : "none";
  }
}

async function loadHistory() {
  if (!historyList) {
    return;
  }
  try {
    const response = await fetch("/api/history");
    if (!response.ok) {
      throw new Error(await response.text());
    }
    const items = await response.json();
    if (!items || items.length === 0) {
      historyList.textContent = "Нет данных";
      return;
    }
    historyList.innerHTML = "";
    items
      .slice()
      .reverse()
      .forEach((item) => {
        const wrapper = document.createElement("div");
        wrapper.className = "history-item";
        const filename = item.filename || "—";
        const duration =
          item.duration_seconds !== null && item.duration_seconds !== undefined
            ? `${item.duration_seconds} сек`
            : "—";
        const count =
          item.count !== null && item.count !== undefined ? item.count : "—";
        const timestamp = item.timestamp || "—";
        wrapper.innerHTML = `
          <span><strong>Тип:</strong> ${item.type || "—"}</span>
          <span><strong>Файл:</strong> ${filename}</span>
          <span><strong>Длительность:</strong> ${duration}</span>
          <span><strong>Количество людей:</strong> ${count}</span>
          <span><strong>Время:</strong> ${timestamp}</span>
        `;
        historyList.appendChild(wrapper);
      });
  } catch (error) {
    historyList.textContent = "Не удалось загрузить историю";
  }
}
