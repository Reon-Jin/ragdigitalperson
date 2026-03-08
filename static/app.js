const fileList = document.getElementById("file-list");
const uploadForm = document.getElementById("upload-form");
const fileInput = document.getElementById("file-input");
const uploadStatus = document.getElementById("upload-status");
const chatForm = document.getElementById("chat-form");
const messageInput = document.getElementById("message-input");
const messages = document.getElementById("messages");
const template = document.getElementById("message-template");
const avatar = document.getElementById("avatar");
const avatarCaption = document.getElementById("avatar-caption");
const plannerBadge = document.getElementById("planner-badge");
const micButton = document.getElementById("mic-button");
const voiceStatus = document.getElementById("voice-status");
const autoSendToggle = document.getElementById("auto-send-toggle");
const modelProviderSelect = document.getElementById("model-provider-select");
const modelStatus = document.getElementById("model-status");

const SILENCE_WINDOW_MS = 2000;
const MIC_ACTIVITY_THRESHOLD = 0.03;
const MODEL_STORAGE_KEY = "rag-digital-person-model-provider";

let speechUtterance = null;
let recognition = null;
let recognitionRunning = false;
let recognitionPaused = false;
let voiceModeEnabled = false;
let finalTranscript = "";
let interimTranscript = "";
let silenceTimer = null;
let voiceMonitorFrame = null;
let micStream = null;
let audioContext = null;
let analyser = null;
let analyserData = null;
let hotMicFrames = 0;
let lipSyncTimer = null;
let visemeIndex = 0;
let activeChatController = null;
let requestSequence = 0;
let finalizingVoiceInput = false;
let availableProviders = [];

function escapeHtml(value) {
  return String(value)
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#39;");
}

function setAvatarState({ mood = "neutral", state = "idle", caption = "待命中，准备接收文本或语音问题。" }) {
  avatar.className = avatar.className
    .replace(/mood-\S+/g, "")
    .replace(/state-\S+/g, "")
    .trim();
  avatar.classList.add(`mood-${mood}`, `state-${state}`);
  avatarCaption.textContent = caption;
}

function setViseme(name) {
  ["rest", "a", "e", "o", "m"].forEach((item) => avatar.classList.remove(`viseme-${item}`));
  avatar.classList.add(`viseme-${name}`);
}

function visemeSequence(text) {
  const sequence = [];
  const source = text.replace(/\s+/g, "");
  for (const char of source) {
    if ("啊阿呀哇aA".includes(char)) {
      sequence.push("a");
    } else if ("诶欸eiEI".includes(char)) {
      sequence.push("e");
    } else if ("哦喔oO".includes(char)) {
      sequence.push("o");
    } else if ("嗯唔mM".includes(char)) {
      sequence.push("m");
    } else {
      sequence.push("rest");
    }
  }
  return sequence.length ? sequence : ["rest", "a", "e", "o", "m"];
}

function stopLipSync() {
  if (lipSyncTimer) {
    window.clearInterval(lipSyncTimer);
    lipSyncTimer = null;
  }
  setViseme("rest");
}

function startLipSync(text) {
  stopLipSync();
  const sequence = visemeSequence(text);
  visemeIndex = 0;
  setViseme(sequence[0]);
  lipSyncTimer = window.setInterval(() => {
    visemeIndex = (visemeIndex + 1) % sequence.length;
    setViseme(sequence[visemeIndex]);
  }, 150);
}

function renderMeta(metaNode, plan, trace = []) {
  const traceSummary = trace
    .slice(0, 6)
    .map((item) => `${item.level === "category" ? "类型" : item.level === "document" ? "资料" : item.level === "chunk" ? "小标题" : "章节"}:${item.label}`)
    .join(" | ");

  metaNode.innerHTML = `
    <span class="meta-chip">检索: ${plan.should_retrieve ? "是" : "否"}</span>
    <span class="meta-chip">模式: ${escapeHtml(plan.mode)}</span>
    <span class="meta-chip">类型: ${escapeHtml((plan.selected_categories || []).join("、") || "未限定")}</span>
    <span class="meta-chip">资料数: ${plan.selected_documents.length}</span>
    <span class="meta-chip">分段数: ${plan.selected_chunk_ids.length}</span>
    <span class="meta-chip">原因: ${escapeHtml(plan.reason)}</span>
    ${traceSummary ? `<span class="meta-chip trace-chip">${escapeHtml(traceSummary)}</span>` : ""}
  `;
}

function appendMessage(role, text = "") {
  const node = template.content.firstElementChild.cloneNode(true);
  node.classList.add(role);
  node.querySelector(".bubble").textContent = text;
  messages.appendChild(node);
  messages.scrollTop = messages.scrollHeight;
  return node;
}

function plannerText(plan) {
  if (!plan) {
    return "等待提问";
  }
  return `${plan.should_retrieve ? "专业检索" : "直接回答"} · ${plan.reason}`;
}

function selectedModelProvider() {
  return modelProviderSelect?.value || "deepseek";
}

function selectedModelLabel() {
  const provider = availableProviders.find((item) => item.id === selectedModelProvider());
  return provider?.label || (selectedModelProvider() === "qwen" ? "Qwen" : "DeepSeek");
}

function updateModelStatus() {
  const provider = availableProviders.find((item) => item.id === selectedModelProvider());
  if (!provider) {
    modelStatus.textContent = "上传和对话都会使用这里选择的模型。";
    return;
  }
  modelStatus.textContent = provider.configured
    ? `当前使用 ${provider.label} (${provider.model})，上传和对话都会跟随这个选择。`
    : `${provider.label} 当前未配置可用密钥，选择后可能无法正常生成。`;
}

function currentVoiceDraft() {
  return `${finalTranscript}${interimTranscript}`.trim();
}

function clearVoiceDraft() {
  finalTranscript = "";
  interimTranscript = "";
  finalizingVoiceInput = false;
}

function clearSilenceTimer() {
  if (silenceTimer) {
    window.clearTimeout(silenceTimer);
    silenceTimer = null;
  }
}

function scheduleSilenceTimer() {
  clearSilenceTimer();
  if (!voiceModeEnabled) {
    return;
  }
  silenceTimer = window.setTimeout(() => {
    finalizeVoiceInput();
  }, SILENCE_WINDOW_MS);
}

function stopRecognitionSession() {
  if (!recognition || !recognitionRunning) {
    return;
  }
  try {
    recognition.stop();
  } catch (error) {
    console.debug("recognition.stop ignored", error);
  }
}

function startRecognition() {
  if (!recognition || !voiceModeEnabled || recognitionRunning || recognitionPaused) {
    return;
  }
  try {
    recognition.start();
  } catch (error) {
    console.debug("recognition.start ignored", error);
  }
}

function resumeContinuousListening(caption = "持续聆听中，停顿 2 秒会自动判定一句结束。") {
  if (!voiceModeEnabled) {
    return;
  }
  recognitionPaused = false;
  startRecognition();
  voiceStatus.textContent = caption;
  setAvatarState({ mood: "thinking", state: "listening", caption: "语音模式已开启，正在持续聆听。" });
}

function cancelSpeech({ caption = "已停止播报，继续倾听中。", resumeListening = true } = {}) {
  const activeUtterance = speechUtterance;
  speechUtterance = null;
  stopLipSync();

  if ("speechSynthesis" in window && (window.speechSynthesis.speaking || activeUtterance)) {
    window.speechSynthesis.cancel();
  }

  if (resumeListening && voiceModeEnabled) {
    resumeContinuousListening("已停止当前播报，继续持续聆听。");
  } else if (!voiceModeEnabled) {
    setAvatarState({ mood: "neutral", state: "idle", caption });
  }
}

function interruptAssistant(reason = "检测到新的说话，已停止当前回复。") {
  if (activeChatController) {
    activeChatController.abort();
    activeChatController = null;
  }

  if (speechUtterance || ("speechSynthesis" in window && window.speechSynthesis.speaking)) {
    cancelSpeech({ caption: reason, resumeListening: true });
  } else if (voiceModeEnabled) {
    resumeContinuousListening("已停止当前回复，继续持续聆听。");
  }

  plannerBadge.textContent = voiceModeEnabled ? "持续聆听中" : "当前回复已停止";
}

async function ensureVoiceMonitor() {
  if (analyser) {
    if (audioContext?.state === "suspended") {
      await audioContext.resume();
    }
    return;
  }

  if (!navigator.mediaDevices?.getUserMedia) {
    throw new Error("当前浏览器不支持麦克风持续监听");
  }

  micStream = await navigator.mediaDevices.getUserMedia({
    audio: {
      echoCancellation: true,
      noiseSuppression: true,
      autoGainControl: true,
    },
  });

  const AudioContextClass = window.AudioContext || window.webkitAudioContext;
  if (!AudioContextClass) {
    throw new Error("当前浏览器不支持音频监听");
  }

  audioContext = new AudioContextClass();
  if (audioContext.state === "suspended") {
    await audioContext.resume();
  }

  analyser = audioContext.createAnalyser();
  analyser.fftSize = 2048;
  analyserData = new Uint8Array(analyser.fftSize);

  const source = audioContext.createMediaStreamSource(micStream);
  source.connect(analyser);
}

function stopVoiceMonitor() {
  if (voiceMonitorFrame) {
    window.cancelAnimationFrame(voiceMonitorFrame);
    voiceMonitorFrame = null;
  }
  hotMicFrames = 0;

  if (audioContext) {
    audioContext.close();
    audioContext = null;
  }
  analyser = null;
  analyserData = null;

  if (micStream) {
    micStream.getTracks().forEach((track) => track.stop());
    micStream = null;
  }
}

function monitorVoiceActivity() {
  if (!voiceModeEnabled || !analyser || !analyserData) {
    voiceMonitorFrame = null;
    return;
  }

  analyser.getByteTimeDomainData(analyserData);
  let energy = 0;
  for (let index = 0; index < analyserData.length; index += 1) {
    const normalized = (analyserData[index] - 128) / 128;
    energy += normalized * normalized;
  }
  const rms = Math.sqrt(energy / analyserData.length);

  if (rms >= MIC_ACTIVITY_THRESHOLD) {
    hotMicFrames = Math.min(hotMicFrames + 1, 8);
  } else {
    hotMicFrames = Math.max(hotMicFrames - 1, 0);
  }

  if (hotMicFrames >= 3) {
    if (!recognitionPaused) {
      startRecognition();
    }
    if (!speechUtterance) {
      voiceStatus.textContent = "正在持续聆听，停顿 2 秒会自动判定一句结束。";
      setAvatarState({ mood: "thinking", state: "listening", caption: "正在倾听新的需求。" });
    }
    if (currentVoiceDraft()) {
      scheduleSilenceTimer();
    }
  }

  voiceMonitorFrame = window.requestAnimationFrame(monitorVoiceActivity);
}

async function enableVoiceMode() {
  if (!recognition) {
    return;
  }

  try {
    await ensureVoiceMonitor();
    voiceModeEnabled = true;
    recognitionPaused = false;
    micButton.textContent = "关闭语音模式";
    voiceStatus.textContent = "持续聆听中，停顿 2 秒会自动判定一句结束。";
    setAvatarState({ mood: "thinking", state: "listening", caption: "语音模式已开启，正在持续聆听。" });
    if (!voiceMonitorFrame) {
      voiceMonitorFrame = window.requestAnimationFrame(monitorVoiceActivity);
    }
    startRecognition();
  } catch (error) {
    voiceModeEnabled = false;
    voiceStatus.textContent = `无法开启语音模式：${error.message}`;
    setAvatarState({ mood: "concerned", state: "idle", caption: "语音模式开启失败了，可以继续文字对话。" });
  }
}

function disableVoiceMode() {
  voiceModeEnabled = false;
  recognitionPaused = false;
  clearSilenceTimer();
  clearVoiceDraft();
  stopRecognitionSession();
  stopVoiceMonitor();
  micButton.textContent = "开启语音模式";
  voiceStatus.textContent = "语音模式已关闭，仍可正常文本对话。";
  if (!speechUtterance && !activeChatController) {
    setAvatarState({ mood: "neutral", state: "idle", caption: "语音模式已关闭，仍可继续文字对话。" });
  }
}

function toggleVoiceMode() {
  if (voiceModeEnabled) {
    disableVoiceMode();
  } else {
    enableVoiceMode();
  }
}

async function finalizeVoiceInput() {
  clearSilenceTimer();
  const utterance = currentVoiceDraft();
  if (!utterance || finalizingVoiceInput) {
    return;
  }

  finalizingVoiceInput = true;
  clearVoiceDraft();
  messageInput.value = utterance;

  if (autoSendToggle.checked) {
    voiceStatus.textContent = "检测到一句完整的话，正在发送。";
    await sendMessage();
  } else {
    finalizingVoiceInput = false;
    voiceStatus.textContent = "检测到一句完整的话，已写入输入框。";
    setAvatarState({ mood: "thinking", state: "listening", caption: "已记录一句话，继续持续聆听。" });
  }

  finalizingVoiceInput = false;
}

async function fetchFiles() {
  const response = await fetch("/api/files");
  const files = await response.json();

  if (!files.length) {
    fileList.innerHTML = `
      <div class="file-item static-card">
        <div class="file-name">知识库为空</div>
        <div class="muted small">先上传资料，系统会生成类型、大标题和分段小标题。</div>
      </div>
    `;
    return;
  }

  fileList.innerHTML = files
    .map(
      (item) => `
        <a class="file-item static-card" href="/library?doc=${encodeURIComponent(item.doc_id)}">
          <div class="file-tag-row">
            <span class="tag">${escapeHtml(item.category)}</span>
            <span class="muted small">${item.section_count} 个章节 · ${item.chunk_count} 个分段</span>
          </div>
          <div class="file-name">${escapeHtml(item.title)}</div>
          <div class="muted small">${escapeHtml(item.filename)}</div>
          <div class="file-summary">${escapeHtml(item.summary)}</div>
        </a>
      `
    )
    .join("");
}

async function fetchModelProviders() {
  try {
    const response = await fetch("/api/models");
    if (!response.ok) {
      throw new Error("模型列表加载失败");
    }

    availableProviders = await response.json();
    const storedProvider = window.localStorage.getItem(MODEL_STORAGE_KEY);
    const fallbackProvider = availableProviders.find((item) => item.id === storedProvider)?.id || availableProviders[0]?.id || "deepseek";

    modelProviderSelect.innerHTML = availableProviders
      .map((item) => `<option value="${escapeHtml(item.id)}">${escapeHtml(item.label)}${item.configured ? "" : "（未配置）"}</option>`)
      .join("");
    modelProviderSelect.value = fallbackProvider;
    updateModelStatus();
  } catch (error) {
    availableProviders = [
      { id: "deepseek", label: "DeepSeek", model: "deepseek-chat", configured: true },
      { id: "qwen", label: "Qwen", model: "qwen-plus", configured: true },
    ];
    modelProviderSelect.value = window.localStorage.getItem(MODEL_STORAGE_KEY) || "deepseek";
    updateModelStatus();
  }
}

async function uploadFiles(event) {
  event.preventDefault();
  if (!fileInput.files.length) {
    uploadStatus.textContent = "请选择要上传的资料。";
    return;
  }

  const formData = new FormData();
  const providerLabel = selectedModelLabel();
  for (const file of fileInput.files) {
    formData.append("files", file);
  }
  formData.append("model_provider", selectedModelProvider());

  uploadStatus.textContent = `正在使用 ${providerLabel} 分析资料类型、生成大标题和分段小标题...`;
  setAvatarState({ mood: "thinking", state: "thinking", caption: "正在理解资料内容并建立专业元数据。" });

  try {
    const response = await fetch("/api/upload", { method: "POST", body: formData });
    const result = await response.json();
    if (!response.ok) {
      throw new Error(result.detail || "上传失败");
    }

    uploadStatus.textContent = [
      result.added.length ? `已加入：${result.added.map((item) => `${item.category}-${item.title}`).join("，")}` : "",
      result.skipped.length ? `跳过：${result.skipped.join("，")}` : "",
    ]
      .filter(Boolean)
      .join("；");
    fileInput.value = "";
    await fetchFiles();
    setAvatarState({ mood: "happy", state: "idle", caption: "资料已整理完成，现在可以提问或打开分段浏览器查看详情。" });
  } catch (error) {
    uploadStatus.textContent = error.message;
    setAvatarState({ mood: "concerned", state: "idle", caption: "资料处理失败了，请检查文件后重试。" });
  }
}

function speakAnswer(text, mood) {
  if (!("speechSynthesis" in window) || !text) {
    stopLipSync();
    if (voiceModeEnabled) {
      resumeContinuousListening("回答完成，继续持续聆听。");
    } else {
      setAvatarState({ mood, state: "idle", caption: "回答已完成。你可以继续追问或使用语音输入。" });
    }
    return;
  }

  if (speechUtterance) {
    cancelSpeech({ resumeListening: false });
  }

  const utterance = new SpeechSynthesisUtterance(text);
  speechUtterance = utterance;
  utterance.lang = "zh-CN";
  utterance.rate = 1;
  utterance.pitch = mood === "happy" ? 1.08 : 1.0;

  utterance.onstart = () => {
    if (speechUtterance !== utterance) {
      return;
    }
    recognitionPaused = true;
    stopRecognitionSession();
    setAvatarState({ mood, state: "speaking", caption: "正在播报回答，你可以直接开口打断我。" });
    if (voiceModeEnabled) {
      voiceStatus.textContent = "数字人正在说话，你可以直接开口打断它。";
    }
    startLipSync(text);
  };

  utterance.onboundary = () => {
    if (speechUtterance !== utterance) {
      return;
    }
    setViseme(["a", "e", "o", "m"][visemeIndex % 4]);
    visemeIndex += 1;
  };

  utterance.onend = () => {
    if (speechUtterance !== utterance) {
      return;
    }
    speechUtterance = null;
    stopLipSync();
    if (voiceModeEnabled) {
      resumeContinuousListening("回答完成，继续持续聆听。");
    } else {
      setAvatarState({ mood, state: "idle", caption: "回答完成，可以继续提问。" });
    }
  };

  utterance.onerror = () => {
    if (speechUtterance !== utterance) {
      return;
    }
    speechUtterance = null;
    stopLipSync();
    if (voiceModeEnabled) {
      resumeContinuousListening("回答已生成，语音播报失败，继续持续聆听。");
    } else {
      setAvatarState({ mood, state: "idle", caption: "回答已生成，但语音播报失败了。" });
    }
  };

  window.speechSynthesis.cancel();
  window.speechSynthesis.speak(utterance);
}

function initSpeechRecognition() {
  const SpeechRecognition = window.SpeechRecognition || window.webkitSpeechRecognition;
  if (!SpeechRecognition) {
    voiceStatus.textContent = "当前浏览器不支持实时语音识别，仍可正常文本对话。";
    micButton.disabled = true;
    return;
  }

  recognition = new SpeechRecognition();
  recognition.lang = "zh-CN";
  recognition.continuous = true;
  recognition.interimResults = true;

  recognition.onstart = () => {
    recognitionRunning = true;
    if (voiceModeEnabled && !speechUtterance) {
      micButton.textContent = "关闭语音模式";
      voiceStatus.textContent = "持续聆听中，停顿 2 秒会自动判定一句结束。";
      setAvatarState({ mood: "thinking", state: "listening", caption: "语音模式已开启，正在持续聆听。" });
    }
  };

  recognition.onresult = (event) => {
    let nextInterim = "";
    let heardSomething = false;

    for (let index = event.resultIndex; index < event.results.length; index += 1) {
      const transcript = event.results[index][0].transcript;
      if (!transcript.trim()) {
        continue;
      }
      heardSomething = true;
      if (event.results[index].isFinal) {
        finalTranscript += transcript;
      } else {
        nextInterim += transcript;
      }
    }

    if (!heardSomething) {
      return;
    }

    const recognizedText = `${finalTranscript}${nextInterim}`.trim();
    if (recognizedText && (speechUtterance || activeChatController)) {
      interruptAssistant("检测到你开始说话，已停止当前回复。");
    }

    interimTranscript = nextInterim;
    const draft = currentVoiceDraft();
    if (!draft) {
      return;
    }

    messageInput.value = draft;
    scheduleSilenceTimer();
    voiceStatus.textContent = "正在记录你的说话，停顿 2 秒会自动判定一句结束。";
    setAvatarState({ mood: "thinking", state: "listening", caption: "正在倾听并实时记录你的问题。" });
  };

  recognition.onend = () => {
    recognitionRunning = false;
    if (voiceModeEnabled && !recognitionPaused) {
      window.setTimeout(() => {
        startRecognition();
      }, 240);
      return;
    }

    if (!voiceModeEnabled) {
      micButton.textContent = "开启语音模式";
      voiceStatus.textContent = "语音模式已关闭，仍可正常文本对话。";
    }
  };

  recognition.onerror = (event) => {
    recognitionRunning = false;
    if (event.error === "not-allowed" || event.error === "service-not-allowed") {
      disableVoiceMode();
      voiceStatus.textContent = "浏览器未授权麦克风或语音识别。";
      return;
    }

    if (voiceModeEnabled && !recognitionPaused) {
      voiceStatus.textContent = "语音识别短暂中断，正在恢复持续聆听。";
      window.setTimeout(() => {
        startRecognition();
      }, 500);
      return;
    }

    voiceStatus.textContent = "语音识别出错了，请重试。";
    setAvatarState({ mood: "concerned", state: "idle", caption: "这次没听清，你可以再试一次。" });
  };
}

function renderSources(sourcesNode, sources) {
  if (!sources || !sources.length) {
    sourcesNode.remove();
    return;
  }

  sourcesNode.innerHTML = sources
    .map(
      (item) => `
        <a class="source-chip" href="/library?doc=${encodeURIComponent(item.doc_id)}&chunk=${encodeURIComponent(item.chunk_id)}">
          ${escapeHtml(item.category)} · ${escapeHtml(item.title)} · ${escapeHtml(item.chunk_title)}
        </a>
      `
    )
    .join("");
}

async function sendMessage(event) {
  if (event) {
    event.preventDefault();
  }

  const message = messageInput.value.trim();
  if (!message) {
    return;
  }
  const modelProvider = selectedModelProvider();

  clearSilenceTimer();
  clearVoiceDraft();

  if (activeChatController || speechUtterance) {
    interruptAssistant("已停止上一轮回复，准备处理新的问题。");
  }

  appendMessage("user", message);
  messageInput.value = "";
  plannerBadge.textContent = "规划中...";
  setAvatarState({ mood: "thinking", state: "thinking", caption: "正在让模型判断是否需要检索专业资料。" });

  const assistantNode = appendMessage("assistant", "");
  const bubbleNode = assistantNode.querySelector(".bubble");
  const metaNode = assistantNode.querySelector(".meta");
  const sourcesNode = assistantNode.querySelector(".sources");

  const controller = new AbortController();
  const requestId = ++requestSequence;
  activeChatController = controller;

  try {
    const response = await fetch("/api/chat/stream", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ message, model_provider: modelProvider }),
      signal: controller.signal,
    });

    if (!response.ok || !response.body) {
      throw new Error("流式对话失败");
    }

    const reader = response.body.getReader();
    const decoder = new TextDecoder("utf-8");
    let buffer = "";
    let finalPayload = null;

    while (true) {
      const { value, done } = await reader.read();
      if (done) {
        break;
      }
      buffer += decoder.decode(value, { stream: true });
      const events = buffer.split("\n\n");
      buffer = events.pop() || "";

      for (const eventText of events) {
        if (requestId !== requestSequence) {
          return;
        }

        const dataLine = eventText.split("\n").find((line) => line.startsWith("data: "));
        if (!dataLine) {
          continue;
        }
        const payload = JSON.parse(dataLine.slice(6));
        if (payload.type === "plan") {
          plannerBadge.textContent = plannerText(payload.plan);
          renderMeta(metaNode, payload.plan, payload.trace || []);
          setAvatarState({ mood: "thinking", state: "thinking", caption: "正在按类型、资料和小标题逐层筛选证据。" });
        } else if (payload.type === "token") {
          bubbleNode.textContent += payload.delta;
          messages.scrollTop = messages.scrollHeight;
          setAvatarState({ mood: "neutral", state: "speaking", caption: "正在流式生成回答。" });
          setViseme(["a", "e", "o", "m"][Math.floor(Math.random() * 4)]);
        } else if (payload.type === "final") {
          finalPayload = payload;
        } else if (payload.type === "error") {
          throw new Error(payload.detail || "请求失败");
        }
      }
    }

    if (requestId !== requestSequence) {
      return;
    }

    if (finalPayload) {
      plannerBadge.textContent = plannerText(finalPayload.plan);
      renderMeta(metaNode, finalPayload.plan, finalPayload.trace || []);
      renderSources(sourcesNode, finalPayload.sources || []);
      speakAnswer(finalPayload.answer, finalPayload.emotion || "neutral");
    } else {
      stopLipSync();
      if (voiceModeEnabled) {
        resumeContinuousListening("回答生成完毕，继续持续聆听。");
      } else {
        setAvatarState({ mood: "neutral", state: "idle", caption: "回答生成完毕。" });
      }
    }
  } catch (error) {
    stopLipSync();
    if (error.name === "AbortError") {
      if (requestId === requestSequence) {
        bubbleNode.textContent = bubbleNode.textContent || "当前回复已停止。";
        metaNode.remove();
        sourcesNode.remove();
        plannerBadge.textContent = voiceModeEnabled ? "持续聆听中" : "当前回复已停止";
        if (voiceModeEnabled) {
          resumeContinuousListening("已停止当前回复，继续持续聆听。");
        } else {
          setAvatarState({ mood: "neutral", state: "idle", caption: "当前回复已停止。" });
        }
      }
      return;
    }

    bubbleNode.textContent = `当前请求失败：${error.message}`;
    metaNode.remove();
    sourcesNode.remove();
    plannerBadge.textContent = "请求失败";
    setAvatarState({ mood: "concerned", state: "idle", caption: "这次回答没有成功，请稍后再试。" });
  } finally {
    if (activeChatController === controller) {
      activeChatController = null;
    }
  }
}

uploadForm.addEventListener("submit", uploadFiles);
chatForm.addEventListener("submit", sendMessage);
micButton.addEventListener("click", toggleVoiceMode);
modelProviderSelect.addEventListener("change", () => {
  window.localStorage.setItem(MODEL_STORAGE_KEY, selectedModelProvider());
  updateModelStatus();
});

initSpeechRecognition();
fetchModelProviders();
fetchFiles();
