import { useEffect, useMemo, useRef, useState } from "react";

import type { LocalAvatarProfile } from "../types";

type AvatarPresence = "idle" | "listening" | "thinking" | "speaking" | "warn";
type RuntimeState = "idle" | "loading" | "warn";

interface SpeechRecognitionResultLike {
  transcript: string;
}

interface SpeechRecognitionLike extends EventTarget {
  continuous: boolean;
  interimResults: boolean;
  lang: string;
  onresult: ((event: { results: ArrayLike<ArrayLike<SpeechRecognitionResultLike>> }) => void) | null;
  onerror: ((event: { error?: string }) => void) | null;
  onend: (() => void) | null;
  start: () => void;
  stop: () => void;
}

interface AvatarPanelProps {
  profile: LocalAvatarProfile | null;
  voiceEnabled: boolean;
  agentTitle: string;
  agentCaption: string;
  routeBadge: string;
  runtimeState: RuntimeState;
  lastAssistantMessage: string;
  onTranscript: (text: string) => void;
  onToggleVoice: () => void;
  onSaveProfile: (profile: LocalAvatarProfile) => Promise<void>;
}

const DEFAULT_PROFILE: LocalAvatarProfile = {
  avatar_id: "local-avatar",
  display_name: "FinAvatar Analyst",
  greeting: "你好，我会结合你的长期偏好、实时行情和私有知识库给出分析。",
  persona: "专业、克制、可解释的金融研究助理。",
  default_language: "zh-CN",
  voice_name: "default",
  portrait_data_url: null,
  motion_mode: "portrait_motion",
  tts_backend: "browser",
  asr_backend: "browser",
  note: "当前为本地自建头像模式。",
  updated_at: "",
};

function getSpeechRecognitionCtor(): (new () => SpeechRecognitionLike) | null {
  const candidate = (window as Window & { SpeechRecognition?: new () => SpeechRecognitionLike; webkitSpeechRecognition?: new () => SpeechRecognitionLike }).SpeechRecognition
    || (window as Window & { SpeechRecognition?: new () => SpeechRecognitionLike; webkitSpeechRecognition?: new () => SpeechRecognitionLike }).webkitSpeechRecognition;
  return candidate || null;
}

export function AvatarPanel(props: AvatarPanelProps) {
  const [draftProfile, setDraftProfile] = useState<LocalAvatarProfile>(props.profile || DEFAULT_PROFILE);
  const [subtitle, setSubtitle] = useState("");
  const [error, setError] = useState("");
  const [isRecording, setIsRecording] = useState(false);
  const [isSaving, setIsSaving] = useState(false);
  const [isSpeaking, setIsSpeaking] = useState(false);
  const speechRef = useRef<SpeechSynthesisUtterance | null>(null);
  const recognitionRef = useRef<SpeechRecognitionLike | null>(null);
  const lastSpokenRef = useRef("");

  useEffect(() => {
    setDraftProfile(props.profile || DEFAULT_PROFILE);
  }, [props.profile]);

  useEffect(() => {
    if (!props.lastAssistantMessage.trim()) return;
    if (!props.voiceEnabled || draftProfile.tts_backend !== "browser") return;
    if (props.lastAssistantMessage === lastSpokenRef.current) return;
    lastSpokenRef.current = props.lastAssistantMessage;

    window.speechSynthesis.cancel();
    const utterance = new SpeechSynthesisUtterance(props.lastAssistantMessage);
    utterance.lang = draftProfile.default_language || "zh-CN";
    const voices = window.speechSynthesis.getVoices();
    const matchedVoice = voices.find((voice) => draftProfile.voice_name !== "default" && voice.name === draftProfile.voice_name)
      || voices.find((voice) => voice.lang?.toLowerCase().startsWith((draftProfile.default_language || "zh-CN").toLowerCase().slice(0, 2)));
    if (matchedVoice) utterance.voice = matchedVoice;
    utterance.onstart = () => {
      setIsSpeaking(true);
      setSubtitle(props.lastAssistantMessage);
      setError("");
    };
    utterance.onend = () => {
      setIsSpeaking(false);
      setSubtitle("");
    };
    utterance.onerror = () => {
      setIsSpeaking(false);
      setError("浏览器语音播报失败，请检查系统语音引擎。");
    };
    speechRef.current = utterance;
    window.speechSynthesis.speak(utterance);
  }, [draftProfile.default_language, draftProfile.tts_backend, draftProfile.voice_name, props.lastAssistantMessage, props.voiceEnabled]);

  useEffect(() => {
    return () => {
      recognitionRef.current?.stop();
      window.speechSynthesis.cancel();
    };
  }, []);

  const presence: AvatarPresence = useMemo(() => {
    if (isSpeaking) return "speaking";
    if (isRecording) return "listening";
    if (props.runtimeState === "warn") return "warn";
    if (props.runtimeState === "loading") return "thinking";
    return "idle";
  }, [isRecording, isSpeaking, props.runtimeState]);

  const presenceLabel = useMemo(() => {
    switch (presence) {
      case "listening":
        return "聆听中";
      case "thinking":
        return "思考中";
      case "speaking":
        return "播报中";
      case "warn":
        return "注意";
      default:
        return "待命";
    }
  }, [presence]);

  const runtimeCaption = useMemo(() => {
    if (subtitle) return subtitle;
    if (error) return error;
    return props.agentCaption;
  }, [error, props.agentCaption, subtitle]);

  const recognitionAvailable = typeof window !== "undefined" && !!getSpeechRecognitionCtor();

  const handleRecordToggle = (): void => {
    if (draftProfile.asr_backend !== "browser") {
      setError("当前头像方案设置为手动输入模式，未启用浏览器语音识别。");
      return;
    }
    const Ctor = getSpeechRecognitionCtor();
    if (!Ctor) {
      setError("当前浏览器不支持语音识别，请直接使用文字输入。");
      return;
    }
    if (isRecording) {
      recognitionRef.current?.stop();
      return;
    }
    setError("");
    const recognition = new Ctor();
    recognition.lang = draftProfile.default_language || "zh-CN";
    recognition.interimResults = false;
    recognition.continuous = false;
    recognition.onresult = (event) => {
      const transcript = Array.from(event.results)
        .flatMap((item) => Array.from(item))
        .map((item) => item.transcript)
        .join(" ")
        .trim();
      if (transcript) {
        props.onTranscript(transcript);
      }
    };
    recognition.onerror = (event) => {
      setError(event.error ? `语音识别失败：${event.error}` : "语音识别失败。");
      setIsRecording(false);
    };
    recognition.onend = () => {
      setIsRecording(false);
    };
    recognitionRef.current = recognition;
    setIsRecording(true);
    recognition.start();
  };

  const handleInterruptSpeech = (): void => {
    window.speechSynthesis.cancel();
    setIsSpeaking(false);
    setSubtitle("");
  };

  const handleImageFile = async (file: File | null): Promise<void> => {
    if (!file) {
      setDraftProfile((current) => ({ ...current, portrait_data_url: null }));
      return;
    }
    const dataUrl = await new Promise<string>((resolve, reject) => {
      const reader = new FileReader();
      reader.onload = () => resolve(String(reader.result || ""));
      reader.onerror = () => reject(new Error("图片读取失败"));
      reader.readAsDataURL(file);
    });
    setDraftProfile((current) => ({ ...current, portrait_data_url: dataUrl }));
  };

  const handleSave = async (): Promise<void> => {
    setIsSaving(true);
    setError("");
    try {
      await props.onSaveProfile(draftProfile);
    } catch (saveError) {
      setError(saveError instanceof Error ? saveError.message : "头像配置保存失败。");
    } finally {
      setIsSaving(false);
    }
  };

  const faceClass = `local-face local-face-${presence} ${draftProfile.motion_mode === "studio_card" ? "is-card" : ""}`;

  return (
    <section className="panel avatar-panel">
      <div className="panel-heading avatar-panel-heading">
        <div>
          <p className="section-kicker">Local Avatar Desk</p>
          <h2>本地自建数字人席位</h2>
        </div>
        <div className="pill-row compact">
          <span className="status-pill status-good">离线优先</span>
          <span className="status-pill status-neutral">{props.routeBadge}</span>
        </div>
      </div>

      <div className="avatar-stage-wrap">
        <div className="avatar-stage-surface is-live">
          <div className={faceClass}>
            {draftProfile.portrait_data_url ? (
              <img className="local-face-image" src={draftProfile.portrait_data_url} alt={draftProfile.display_name} />
            ) : (
              <div className="avatar-placeholder">
                <div className="avatar-placeholder-face" />
                <div>
                  <strong>{draftProfile.display_name}</strong>
                  <p>{draftProfile.persona || props.agentCaption}</p>
                </div>
              </div>
            )}
            <div className="local-face-aura" />
            <div className="local-face-shimmer" />
            <div className="local-face-frame" />
            <div className="local-face-features" aria-hidden="true">
              <span className="local-face-brow left" />
              <span className="local-face-brow right" />
              <span className="local-face-eye left" />
              <span className="local-face-eye right" />
              <span className="local-face-cheek left" />
              <span className="local-face-cheek right" />
            </div>
            <div className="local-face-mouth" />
          </div>
        </div>
        <div className="avatar-stage-sidebar">
          <div className="signal-card">
            <span>头像状态</span>
            <strong>{presenceLabel}</strong>
          </div>
          <div className="signal-card">
            <span>语音播报</span>
            <strong>{props.voiceEnabled ? "开启" : "关闭"}</strong>
          </div>
          <div className="signal-card signal-card-wide">
            <span>字幕</span>
            <strong>{runtimeCaption || props.agentTitle}</strong>
          </div>
        </div>
      </div>

      <div className="toolbar-row">
        <button className="button secondary" type="button" onClick={props.onToggleVoice}>
          {props.voiceEnabled ? "关闭播报" : "开启播报"}
        </button>
        <button className="button primary" type="button" onClick={handleRecordToggle}>
          {isRecording ? "结束语音输入" : recognitionAvailable ? "语音提问" : "浏览器不支持语音识别"}
        </button>
        <button className="button ghost" type="button" onClick={handleInterruptSpeech}>
          停止播报
        </button>
      </div>

      {error ? <div className="inline-banner inline-banner-error">{error}</div> : null}
      {draftProfile.note ? <div className="inline-banner">{draftProfile.note}</div> : null}

      <div className="avatar-lab-grid">
        <article className="subpanel">
          <div className="subpanel-head">
            <div>
              <p className="section-kicker">Avatar Profile</p>
              <h3>头像素材与设定</h3>
            </div>
            <span className="status-pill status-neutral">{draftProfile.updated_at ? "已持久化" : "未保存"}</span>
          </div>
          <div className="form-grid two-col">
            <label className="field">
              <span>头像名称</span>
              <input value={draftProfile.display_name} onChange={(event) => setDraftProfile((current) => ({ ...current, display_name: event.target.value }))} />
            </label>
            <label className="field">
              <span>语音名称</span>
              <input value={draftProfile.voice_name} onChange={(event) => setDraftProfile((current) => ({ ...current, voice_name: event.target.value }))} />
            </label>
            <label className="field full-span">
              <span>欢迎语</span>
              <input value={draftProfile.greeting} onChange={(event) => setDraftProfile((current) => ({ ...current, greeting: event.target.value }))} />
            </label>
            <label className="field full-span">
              <span>人物设定</span>
              <textarea rows={3} value={draftProfile.persona} onChange={(event) => setDraftProfile((current) => ({ ...current, persona: event.target.value }))} />
            </label>
            <label className="field">
              <span>默认语言</span>
              <input value={draftProfile.default_language} onChange={(event) => setDraftProfile((current) => ({ ...current, default_language: event.target.value }))} />
            </label>
            <label className="field">
              <span>头像图片</span>
              <input type="file" accept="image/*" onChange={(event) => void handleImageFile(event.target.files?.[0] || null)} />
            </label>
          </div>
          <div className="toolbar-row">
            <button className="button primary" type="button" onClick={handleSave} disabled={isSaving}>
              {isSaving ? "保存中..." : "保存本地头像"}
            </button>
            <button className="button ghost" type="button" onClick={() => setDraftProfile(props.profile || DEFAULT_PROFILE)}>
              恢复已保存配置
            </button>
          </div>
        </article>

        <article className="subpanel">
          <div className="subpanel-head">
            <div>
              <p className="section-kicker">Runtime</p>
              <h3>本地驱动策略</h3>
            </div>
            <span className="status-pill status-good">4060 8G 友好</span>
          </div>
          <div className="form-grid two-col">
            <label className="field">
              <span>动作模式</span>
              <select value={draftProfile.motion_mode} onChange={(event) => setDraftProfile((current) => ({ ...current, motion_mode: event.target.value as LocalAvatarProfile["motion_mode"] }))}>
                <option value="portrait_motion">肖像动态</option>
                <option value="studio_card">工作室卡片</option>
              </select>
            </label>
            <label className="field">
              <span>TTS 后端</span>
              <select value={draftProfile.tts_backend} onChange={(event) => setDraftProfile((current) => ({ ...current, tts_backend: event.target.value as LocalAvatarProfile["tts_backend"] }))}>
                <option value="browser">浏览器本地</option>
                <option value="local_server">预留本地服务</option>
              </select>
            </label>
            <label className="field">
              <span>ASR 后端</span>
              <select value={draftProfile.asr_backend} onChange={(event) => setDraftProfile((current) => ({ ...current, asr_backend: event.target.value as LocalAvatarProfile["asr_backend"] }))}>
                <option value="browser">浏览器识别</option>
                <option value="manual">手动输入</option>
              </select>
            </label>
          </div>
          <div className="task-card">
            <strong>后续可接本地模型</strong>
            <p>头像口型与表情：LivePortrait / MuseTalk</p>
            <p>语音识别：Faster-Whisper / FunASR</p>
            <p>本地播报：GPT-SoVITS / CosyVoice / Edge-TTS 替代方案</p>
          </div>
        </article>
      </div>
    </section>
  );
}