/**
 * MediaRecorder + speech recognition for exit interviews (port of VoiceRoomPanel).
 */
(function (global) {
  function getSpeechRecognitionCtor() {
    return window.SpeechRecognition || window.webkitSpeechRecognition || null;
  }

  function pickMimeType() {
    const candidates = [
      "video/webm;codecs=vp9,opus",
      "video/webm;codecs=vp8,opus",
      "video/webm",
    ];
    for (const type of candidates) {
      if (typeof MediaRecorder !== "undefined" && MediaRecorder.isTypeSupported(type)) {
        return type;
      }
    }
    return "video/webm";
  }

  function createVoiceRoom(opts) {
    const root = opts.root;
    const sessionId = opts.sessionId;
    const onTranscript = opts.onTranscript || null;
    const autoStart = opts.autoStart !== false;

    let stream = null;
    let recorder = null;
    let chunks = [];
    let mime = "video/webm";
    let recognition = null;
    let uploading = false;
    let starting = false;
    let cancelled = false;
    let activeSessionId = sessionId;

    root.innerHTML = `
      <div class="video-room compact" aria-label="Video recording">
        <div class="video-preview-wrap">
          <video class="video-preview" playsinline muted autoplay></video>
          <div class="video-preview-empty">Camera</div>
          <span class="video-rec-badge" hidden>REC</span>
        </div>
        <p class="hint video-room-meta">Starting…</p>
        <p class="error video-room-error" hidden></p>
      </div>`;

    const video = root.querySelector(".video-preview");
    const empty = root.querySelector(".video-preview-empty");
    const badge = root.querySelector(".video-rec-badge");
    const meta = root.querySelector(".video-room-meta");
    const errEl = root.querySelector(".video-room-error");

    function setError(msg) {
      if (!errEl) return;
      if (!msg) {
        errEl.hidden = true;
        errEl.textContent = "";
        return;
      }
      errEl.hidden = false;
      errEl.textContent = msg;
    }

    function setMeta(text) {
      if (meta) meta.textContent = text;
    }

    async function stopTracks() {
      if (recognition) {
        try {
          recognition.abort();
        } catch (_) {
          /* ignore */
        }
        recognition = null;
      }
      if (stream) {
        stream.getTracks().forEach((t) => t.stop());
        stream = null;
      }
      if (video) video.srcObject = null;
      if (empty) empty.hidden = false;
      if (badge) badge.hidden = true;
    }

    async function flushUpload(sid) {
      if (uploading) return false;
      uploading = true;
      try {
        if (recorder && recorder.state !== "inactive") {
          const blob = await new Promise((resolve) => {
            recorder.onstop = () => resolve(new Blob(chunks, { type: mime }));
            try {
              recorder.stop();
            } catch (_) {
              resolve(new Blob(chunks, { type: mime }));
            }
          });
          recorder = null;
          if (badge) badge.hidden = true;
          if (blob.size > 0) {
            await global.SellmApi.uploadVoiceRecording(sid, blob);
            chunks = [];
            return true;
          }
        } else if (chunks.length) {
          const blob = new Blob(chunks, { type: mime });
          if (blob.size > 0) {
            await global.SellmApi.uploadVoiceRecording(sid, blob);
            chunks = [];
            return true;
          }
        }
        return false;
      } finally {
        uploading = false;
      }
    }

    async function stopAndUpload() {
      const sid = activeSessionId;
      try {
        await flushUpload(sid);
      } catch (err) {
        setError(err instanceof Error ? err.message : "Recording upload failed");
        throw err;
      } finally {
        await stopTracks();
        try {
          await global.SellmApi.stopVoiceRecording(sid);
        } catch (_) {
          /* browser upload is source of truth */
        }
      }
    }

    async function start() {
      if (!autoStart || starting || recorder) return;
      starting = true;
      setError(null);
      try {
        stream = await navigator.mediaDevices.getUserMedia({
          video: { facingMode: "user" },
          audio: true,
        });
        if (cancelled) {
          stream.getTracks().forEach((t) => t.stop());
          stream = null;
          return;
        }
        if (video) {
          video.srcObject = stream;
          await video.play().catch(() => undefined);
        }
        if (empty) empty.hidden = true;

        mime = pickMimeType();
        chunks = [];
        recorder = new MediaRecorder(stream, { mimeType: mime });
        recorder.ondataavailable = (event) => {
          if (event.data && event.data.size > 0) chunks.push(event.data);
        };
        recorder.start(1000);
        if (badge) badge.hidden = false;

        try {
          await global.SellmApi.startVoiceRecording(activeSessionId);
        } catch (err) {
          setError(err instanceof Error ? err.message : "Could not mark recording started");
        }

        const Ctor = getSpeechRecognitionCtor();
        if (Ctor && !cancelled) {
          recognition = new Ctor();
          recognition.continuous = true;
          recognition.interimResults = true;
          recognition.lang = "en-US";
          recognition.onresult = (event) => {
            let interim = "";
            for (let i = event.resultIndex; i < event.results.length; i++) {
              const result = event.results[i];
              const text = (result[0]?.transcript || "").trim();
              if (!text) continue;
              if (result.isFinal) onTranscript?.(text, true);
              else interim += (interim ? " " : "") + text;
            }
            if (interim) onTranscript?.(interim, false);
          };
          recognition.onerror = () => setMeta("Mic ready");
          recognition.onend = () => {
            if (!cancelled && recognition) {
              try {
                recognition.start();
                setMeta("Listening…");
              } catch (_) {
                setMeta("Mic ready");
              }
            }
          };
          try {
            recognition.start();
            setMeta("Listening…");
          } catch (err) {
            setError(err instanceof Error ? err.message : "Speech recognition unavailable");
            setMeta("Mic ready");
          }
        } else {
          setMeta(
            getSpeechRecognitionCtor()
              ? "Mic ready"
              : "Mic ready · speech API unavailable",
          );
        }
      } catch (err) {
        setError(
          err instanceof Error
            ? err.message
            : "Camera/microphone permission is required to record the interview",
        );
      } finally {
        starting = false;
      }
    }

    function destroy() {
      cancelled = true;
      const sid = activeSessionId;
      const rec = recorder;
      const st = stream;
      const m = mime;
      const ch = chunks.slice();
      recorder = null;
      stream = null;
      chunks = [];
      if (recognition) {
        try {
          recognition.abort();
        } catch (_) {
          /* ignore */
        }
        recognition = null;
      }
      const uploadChunks = () => {
        if (!ch.length) return;
        const blob = new Blob(ch, { type: m });
        if (blob.size > 0) {
          void global.SellmApi.uploadVoiceRecording(sid, blob).catch(() => undefined);
        }
      };
      if (rec && rec.state !== "inactive") {
        rec.onstop = () => {
          uploadChunks();
          st?.getTracks().forEach((t) => t.stop());
        };
        try {
          rec.stop();
        } catch (_) {
          uploadChunks();
          st?.getTracks().forEach((t) => t.stop());
        }
      } else {
        uploadChunks();
        st?.getTracks().forEach((t) => t.stop());
      }
      root.innerHTML = "";
    }

    void global.SellmApi.fetchVoiceStatus(activeSessionId).catch(() => undefined);
    void start();

    return { stopAndUpload, destroy };
  }

  global.SellmExitVoice = { createVoiceRoom };
})(window);
