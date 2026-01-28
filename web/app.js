console.log("People Counter app.js loaded");
const imageInput = document.getElementById("imageInput");
const videoInput = document.getElementById("videoInput");
const streamInput = document.getElementById("streamInput");
const startButton = document.getElementById("startButton");
const historyList = document.getElementById("historyList");
const historyEmpty = document.getElementById("historyEmpty");
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

let activeSocket = null;
let activeTab = "image";
const statusLabels = {
  idle: "ожидание",
  processing: "обработка",
  done: "готово",
  error: "ошибка",
};

function getResultsContainer(tabName) {
  const tabPanel = document.getElementById(`tab-${tabName}`);
  if (!tabPanel) {
    return null;
  }
  return tabPanel.querySelector(".results-panel");
}

function getResultEls(tabName) {
  const container = getResultsContainer(tabName);
  if (!container) {
    return null;
  }
  return {
    container,
    currentCountEl: container.querySelector('[data-field="currentCount"]'),
    maxCountEl: container.querySelector('[data-field="maxCount"]'),
    statusEl: container.querySelector('[data-field="status"]'),
    errorEl: container.querySelector('[data-field="error"]'),
    imagePreview: container.querySelector('[data-field="imagePreview"]'),
    videoPreview: container.querySelector('[data-field="videoPreview"]'),
    streamPreview: container.querySelector('[data-field="streamPreview"]'),
  };
}

function resetStatusFor(tabName) {
  const els = getResultEls(tabName);
  if (!els) {
    return;
  }
  if (els.statusEl) {
    els.statusEl.textContent = statusLabels.idle;
  }
  if (els.currentCountEl) {
    els.currentCountEl.textContent = "-";
  }
  if (els.maxCountEl) {
    els.maxCountEl.textContent = "-";
  }
  if (els.errorEl) {
    els.errorEl.textContent = "";
  }
  if (els.imagePreview) {
    els.imagePreview.src = "";
    els.imagePreview.classList.remove("visible");
  }
  if (els.videoPreview) {
    els.videoPreview.removeAttribute("src");
    els.videoPreview.load();
    const wrapper = els.videoPreview.closest(".video-preview");
    if (wrapper) {
      wrapper.classList.remove("visible");
    }
  }
  if (els.streamPreview) {
    els.streamPreview.removeAttribute("src");
    const wrapper = els.streamPreview.closest(".stream-preview");
    if (wrapper) {
      wrapper.classList.remove("visible");
    }
  }
}

function resetStatus() {
  resetStatusFor(activeTab);
}

function updateButtonState() {
  const hasImage = imageInput.files && imageInput.files.length > 0;
  const hasVideo = videoInput.files && videoInput.files.length > 0;
  const hasStream = streamInput.value.trim().length > 0;
  if (activeTab === "image") {
    startButton.disabled = !hasImage;
  } else if (activeTab === "video") {
    startButton.disabled = !hasVideo;
  } else if (activeTab === "stream") {
    startButton.disabled = !hasStream;
  } else {
    startButton.disabled = true;
  }
}

function setStatus(status, tabName = activeTab) {
  const els = getResultEls(tabName);
  if (!els || !els.statusEl) {
    return;
  }
  els.statusEl.textContent = statusLabels[status] || status;
}

function closeSocket() {
  if (activeSocket) {
    activeSocket.close();
    activeSocket = null;
  }
}

function setStreamPreview(jobId, tabName) {
  const els = getResultEls(tabName);
  if (!els || !els.streamPreview) {
    return;
  }
  els.streamPreview.src = `/api/job/${jobId}/mjpeg?ts=${Date.now()}`;
  const wrapper = els.streamPreview.closest(".stream-preview");
  if (wrapper) {
    wrapper.classList.add("visible");
  }
}

async function processImage(file) {
  setStatus("processing", "image");
  const formData = new FormData();
  formData.append("image", file);
  const conf = parseFloat(confInput.value || "0.25");
  const els = getResultEls("image");
  try {
    const response = await fetch(`/api/process/image?conf=${conf}`, {
      method: "POST",
      body: formData,
    });
    if (!response.ok) {
      throw new Error(await response.text());
    }
    const result = await response.json();
    if (els?.currentCountEl) {
      els.currentCountEl.textContent = result.count;
    }
    if (els?.maxCountEl) {
      els.maxCountEl.textContent = result.count;
    }
    if (result.image_b64 && els?.imagePreview) {
      els.imagePreview.src = `data:image/jpeg;base64,${result.image_b64}`;
      els.imagePreview.classList.add("visible");
    }
    setStatus("done", "image");
  } catch (error) {
    setStatus("error", "image");
    if (els?.errorEl) {
      els.errorEl.textContent = error.message || "Не удалось обработать изображение";
    }
  }
}

function startSocket(jobId, tabName) {
  closeSocket();
  const protocol = window.location.protocol === "https:" ? "wss" : "ws";
  const wsUrl = `${protocol}://${window.location.host}/ws/job/${jobId}`;
  const socket = new WebSocket(wsUrl);
  activeSocket = socket;

  socket.onmessage = (event) => {
    const payload = JSON.parse(event.data);
    const els = getResultEls(tabName);
    if (!els) {
      return;
    }
    if (payload.type === "frame") {
      if (els.currentCountEl) {
        els.currentCountEl.textContent = payload.count;
      }
      if (els.maxCountEl) {
        els.maxCountEl.textContent = payload.max_count;
      }
      setStatus("processing", tabName);
    }
    if (payload.type === "done") {
      if (els.maxCountEl) {
        els.maxCountEl.textContent = payload.max_count;
      }
      if (payload.video_url && tabName === "video" && els.videoPreview) {
        els.videoPreview.src = payload.video_url;
        els.videoPreview.load();
        const wrapper = els.videoPreview.closest(".video-preview");
        if (wrapper) {
          wrapper.classList.add("visible");
        }
      }
      setStatus("done", tabName);
    }
    if (payload.type === "error") {
      setStatus("error", tabName);
      if (els.errorEl) {
        els.errorEl.textContent = payload.message || "Ошибка обработки";
      }
    }
  };

  socket.onerror = () => {
    const els = getResultEls(tabName);
    setStatus("error", tabName);
    if (els?.errorEl) {
      els.errorEl.textContent = "Ошибка WebSocket";
    }
  };
}

async function processVideo(file) {
  setStatus("processing", "video");
  const formData = new FormData();
  formData.append("video", file);
  formData.append("fps", fpsInput.value || "5");
  formData.append("max_seconds", maxSecondsInput.value || "0");
  const els = getResultEls("video");
  try {
    const response = await fetch("/api/process/video", {
      method: "POST",
      body: formData,
    });
    if (!response.ok) {
      throw new Error(await response.text());
    }
    const result = await response.json();
    startSocket(result.job_id, "video");
    setStreamPreview(result.job_id, "video");
  } catch (error) {
    setStatus("error", "video");
    if (els?.errorEl) {
      els.errorEl.textContent = error.message || "Не удалось обработать видео";
    }
  }
}

async function processStream(url) {
  setStatus("processing", "stream");
  const streamWindow = window.open("", "_blank");
  const els = getResultEls("stream");
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
    startSocket(result.job_id, "stream");
    setStreamPreview(result.job_id, "stream");
    if (streamWindow) {
      streamWindow.location = `/api/job/${result.job_id}/mjpeg`;
    }
  } catch (error) {
    setStatus("error", "stream");
    if (els?.errorEl) {
      els.errorEl.textContent = error.message || "Не удалось обработать поток";
    }
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
  updateControlsVisibility();
  updateButtonState();
  if (activeTab === "history") {
    loadHistory();
  }
  if (controlsPanel) {
    controlsPanel.style.display = activeTab === "history" ? "none" : "";
  }
}

tabs.forEach((tab) => {
  tab.addEventListener("click", () => {
    if (tab.disabled || tab.classList.contains("disabled")) {
      return;
    }
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
    controlLabels.fps.style.display = "none";
  }
  if (controlLabels.maxSeconds) {
    controlLabels.maxSeconds.style.display = "none";
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
      historyList.innerHTML = "";
      if (historyEmpty) {
        historyEmpty.style.display = "block";
      }
      return;
    }
    historyList.innerHTML = "";
    if (historyEmpty) {
      historyEmpty.style.display = "none";
    }
    items
      .slice()
      .reverse()
      .forEach((item) => {
        const filename = item.filename || "—";
        const duration =
          item.duration_seconds !== null && item.duration_seconds !== undefined
            ? `${item.duration_seconds} сек`
            : "—";
        const count =
          item.count !== null && item.count !== undefined ? item.count : "—";
        const timestamp = item.timestamp || "—";
        const row = document.createElement("tr");
        row.innerHTML = `
          <td>${item.type || "—"}</td>
          <td>${filename}</td>
          <td>${duration}</td>
          <td>${count}</td>
          <td>${timestamp}</td>
        `;
        historyList.appendChild(row);
      });
  } catch (error) {
    historyList.innerHTML = "";
    if (historyEmpty) {
      historyEmpty.textContent = "Не удалось загрузить историю";
      historyEmpty.style.display = "block";
    }
  }
}
