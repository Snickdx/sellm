/**
 * MediaRecorder + speech recognition for exit interviews (port of VoiceRoomPanel).
 * Includes mic-level meter and camera/mic device switchers for troubleshooting.
 */
(function (global) {
  const LS_MIC = "sellm.exit.micId";
  const LS_CAM = "sellm.exit.camId";

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
    let switching = false;
    let cancelled = false;
    let activeSessionId = sessionId;
    let audioCtx = null;
    let analyser = null;
    let meterRaf = 0;
    let meterData = null;
    let meterTracks = [];
    let speechWanted = Boolean(onTranscript);

    root.innerHTML = `
      <div class="video-room compact" aria-label="Video recording">
        <div class="video-preview-wrap">
          <video class="video-preview" playsinline muted autoplay></video>
          <div class="video-preview-empty">Camera</div>
          <span class="video-rec-badge" hidden>REC</span>
        </div>
        <div class="voice-meter" aria-live="polite">
          <span class="voice-meter-label">Mic level</span>
          <div class="voice-meter-track" role="meter" aria-valuemin="0" aria-valuemax="100" aria-valuenow="0" aria-label="Microphone input level">
            <div class="voice-meter-fill" data-meter-fill></div>
          </div>
          <span class="voice-meter-state" data-meter-state>Waiting…</span>
        </div>
        <div class="voice-devices">
          <label class="voice-device-field">
            <span>Camera</span>
            <select data-video-device aria-label="Camera source"></select>
          </label>
          <label class="voice-device-field">
            <span>Microphone</span>
            <select data-audio-device aria-label="Microphone source"></select>
          </label>
        </div>
        <div class="voice-tools">
          <button type="button" class="ghost voice-tool-btn" data-refresh-devices>Refresh devices</button>
          <button type="button" class="ghost voice-tool-btn" data-toggle-trouble aria-expanded="false">Troubleshoot</button>
        </div>
        <div class="voice-trouble" data-trouble hidden>
          <p class="hint">If the meter stays flat while you speak, check browser/OS mic permission, close other apps using the mic, pick another device, or re-request access.</p>
          <button type="button" class="ghost voice-tool-btn" data-reacquire>Re-request camera &amp; mic</button>
        </div>
        <p class="hint video-room-meta">Starting…</p>
        <p class="error video-room-error" hidden></p>
      </div>`;

    const video = root.querySelector(".video-preview");
    const empty = root.querySelector(".video-preview-empty");
    const badge = root.querySelector(".video-rec-badge");
    const meta = root.querySelector(".video-room-meta");
    const errEl = root.querySelector(".video-room-error");
    const meterFill = root.querySelector("[data-meter-fill]");
    const meterState = root.querySelector("[data-meter-state]");
    const meterTrack = root.querySelector(".voice-meter-track");
    const videoSelect = root.querySelector("[data-video-device]");
    const audioSelect = root.querySelector("[data-audio-device]");
    const troublePanel = root.querySelector("[data-trouble]");

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

    function preferredIds() {
      return {
        audioId: (localStorage.getItem(LS_MIC) || "").trim(),
        videoId: (localStorage.getItem(LS_CAM) || "").trim(),
      };
    }

    function mediaConstraints(override = {}) {
      const prefs = preferredIds();
      const audioId = override.audioId !== undefined ? override.audioId : prefs.audioId;
      const videoId = override.videoId !== undefined ? override.videoId : prefs.videoId;
      const audio = audioId ? { deviceId: { ideal: audioId } } : true;
      const video = videoId
        ? { deviceId: { ideal: videoId }, facingMode: "user" }
        : { facingMode: "user" };
      return { audio, video };
    }

    function stopMeter() {
      if (meterRaf) {
        cancelAnimationFrame(meterRaf);
        meterRaf = 0;
      }
      if (audioCtx) {
        try {
          audioCtx.close();
        } catch (_) {
          /* ignore */
        }
        audioCtx = null;
      }
      analyser = null;
      meterData = null;
      meterTracks.forEach((t) => {
        try {
          t.stop();
        } catch (_) {
          /* ignore */
        }
      });
      meterTracks = [];
      if (meterFill) meterFill.style.width = "0%";
      if (meterTrack) meterTrack.setAttribute("aria-valuenow", "0");
      if (meterState) meterState.textContent = "Off";
    }

    function tickMeter() {
      if (cancelled || !analyser || !meterData) return;
      analyser.getByteTimeDomainData(meterData);
      let sum = 0;
      for (let i = 0; i < meterData.length; i++) {
        const v = (meterData[i] - 128) / 128;
        sum += v * v;
      }
      const rms = Math.sqrt(sum / meterData.length);
      const level = Math.min(100, Math.round(rms * 340));
      if (meterFill) {
        meterFill.style.width = `${level}%`;
        meterFill.dataset.level =
          level < 4 ? "silent" : level < 18 ? "quiet" : level < 72 ? "good" : "hot";
      }
      if (meterTrack) meterTrack.setAttribute("aria-valuenow", String(level));
      if (meterState) {
        meterState.textContent =
          level < 4 ? "Silent — speak to test" : level < 18 ? "Quiet" : level < 72 ? "Good" : "Hot";
        meterState.dataset.level = meterFill?.dataset.level || "silent";
      }
      meterRaf = requestAnimationFrame(tickMeter);
    }

    async function startMeter(mediaStream) {
      stopMeter();
      const audioTracks = mediaStream?.getAudioTracks?.() || [];
      if (
        !audioTracks.length ||
        (typeof AudioContext === "undefined" && typeof webkitAudioContext === "undefined")
      ) {
        if (meterState) meterState.textContent = "Meter unavailable";
        return;
      }
      try {
        // Clone tracks so Web Audio metering does not contend with
        // SpeechRecognition / MediaRecorder on the live interview stream.
        meterTracks = audioTracks.map((t) => t.clone());
        const meterStream = new MediaStream(meterTracks);
        const Ctx = window.AudioContext || window.webkitAudioContext;
        audioCtx = new Ctx();
        if (audioCtx.state === "suspended") await audioCtx.resume().catch(() => undefined);
        const source = audioCtx.createMediaStreamSource(meterStream);
        analyser = audioCtx.createAnalyser();
        analyser.fftSize = 1024;
        analyser.smoothingTimeConstant = 0.8;
        source.connect(analyser);
        meterData = new Uint8Array(analyser.fftSize);
        tickMeter();
      } catch (_) {
        meterTracks.forEach((t) => {
          try {
            t.stop();
          } catch (__) {
            /* ignore */
          }
        });
        meterTracks = [];
        if (meterState) meterState.textContent = "Meter unavailable";
      }
    }

    async function listDevices() {
      if (!navigator.mediaDevices?.enumerateDevices) return { audio: [], video: [] };
      const devices = await navigator.mediaDevices.enumerateDevices();
      return {
        audio: devices.filter((d) => d.kind === "audioinput"),
        video: devices.filter((d) => d.kind === "videoinput"),
      };
    }

    function fillSelect(select, devices, selectedId, kindLabel) {
      if (!select) return;
      const prev = select.value;
      select.innerHTML = "";
      if (!devices.length) {
        const opt = document.createElement("option");
        opt.value = "";
        opt.textContent = `No ${kindLabel} found`;
        select.appendChild(opt);
        select.disabled = true;
        return;
      }
      select.disabled = false;
      devices.forEach((d, i) => {
        const opt = document.createElement("option");
        opt.value = d.deviceId;
        opt.textContent = d.label || `${kindLabel} ${i + 1}`;
        select.appendChild(opt);
      });
      const want = selectedId || prev;
      if (want && [...select.options].some((o) => o.value === want)) select.value = want;
      else if (devices[0]) select.value = devices[0].deviceId;
    }

    async function refreshDeviceLists() {
      const lists = await listDevices();
      const activeAudio = stream?.getAudioTracks?.()[0]?.getSettings?.().deviceId || preferredIds().audioId;
      const activeVideo = stream?.getVideoTracks?.()[0]?.getSettings?.().deviceId || preferredIds().videoId;
      fillSelect(audioSelect, lists.audio, activeAudio, "Microphone");
      fillSelect(videoSelect, lists.video, activeVideo, "Camera");
    }

    async function replaceTrack(kind, deviceId) {
      if (!stream || !deviceId || switching || cancelled) return;
      switching = true;
      setError(null);
      try {
        const constraints =
          kind === "audio"
            ? { audio: { deviceId: { exact: deviceId } }, video: false }
            : { audio: false, video: { deviceId: { exact: deviceId } } };
        const fresh = await navigator.mediaDevices.getUserMedia(constraints);
        if (cancelled) {
          fresh.getTracks().forEach((t) => t.stop());
          return;
        }
        const newTrack = kind === "audio" ? fresh.getAudioTracks()[0] : fresh.getVideoTracks()[0];
        const oldTrack = kind === "audio" ? stream.getAudioTracks()[0] : stream.getVideoTracks()[0];
        if (!newTrack) throw new Error(`Could not open selected ${kind === "audio" ? "microphone" : "camera"}`);
        if (oldTrack) {
          stream.removeTrack(oldTrack);
          oldTrack.stop();
        }
        stream.addTrack(newTrack);
        fresh.getTracks().forEach((t) => {
          if (t !== newTrack) t.stop();
        });
        if (kind === "audio") {
          localStorage.setItem(LS_MIC, deviceId);
          await startMeter(stream);
          restartSpeech();
        } else {
          localStorage.setItem(LS_CAM, deviceId);
          if (video) {
            video.srcObject = stream;
            await video.play().catch(() => undefined);
          }
        }
        setMeta(kind === "audio" ? "Microphone switched" : "Camera switched");
        await refreshDeviceLists();
      } catch (err) {
        setError(err instanceof Error ? err.message : "Could not switch device");
      } finally {
        switching = false;
      }
    }

    async function stopTracks() {
      stopSpeech();
      stopMeter();
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

    function stopSpeech() {
      if (!recognition) return;
      const rec = recognition;
      recognition = null;
      try {
        rec.onresult = null;
        rec.onerror = null;
        rec.onend = null;
        rec.abort();
      } catch (_) {
        /* ignore */
      }
    }

    function restartSpeech() {
      stopSpeech();
      if (!cancelled && speechWanted) startSpeech();
    }

    function startSpeech() {
      const Ctor = getSpeechRecognitionCtor();
      if (!Ctor || cancelled || !speechWanted) {
        setMeta(
          !Ctor
            ? "Mic ready · speech API unavailable"
            : "Mic ready — watch the level meter",
        );
        return;
      }
      stopSpeech();
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
      recognition.onerror = (event) => {
        const code = String(event?.error || "");
        if (code === "not-allowed" || code === "service-not-allowed") {
          setMeta("Speech blocked — allow mic in the browser");
          stopSpeech();
          return;
        }
        if (code === "audio-capture") {
          setMeta("Speech lost mic — try Refresh devices");
          return;
        }
        // no-speech / aborted / network: onend will restart
        setMeta(code === "network" ? "Speech reconnecting…" : "Listening…");
      };
      recognition.onend = () => {
        if (cancelled || !speechWanted || !recognition) return;
        window.setTimeout(() => {
          if (cancelled || !speechWanted || !recognition) return;
          try {
            recognition.start();
            setMeta("Listening…");
          } catch (_) {
            setMeta("Mic ready — tap Troubleshoot if speech stays quiet");
          }
        }, 120);
      };
      try {
        recognition.start();
        setMeta("Listening…");
      } catch (err) {
        setError(err instanceof Error ? err.message : "Speech recognition unavailable");
        setMeta("Mic ready — watch the level meter");
      }
    }

    async function acquireAndRecord({ force = false } = {}) {
      if (!autoStart || starting || cancelled) return;
      if (recorder && !force) return;
      starting = true;
      setError(null);
      setMeta("Requesting camera & microphone…");
      try {
        if (force) {
          if (recorder && recorder.state !== "inactive") {
            try {
              recorder.stop();
            } catch (_) {
              /* ignore */
            }
          }
          recorder = null;
          await stopTracks();
        }

        stream = await navigator.mediaDevices.getUserMedia(mediaConstraints());
        if (cancelled) {
          stream.getTracks().forEach((t) => t.stop());
          stream = null;
          return;
        }

        const audioSettings = stream.getAudioTracks()[0]?.getSettings?.() || {};
        const videoSettings = stream.getVideoTracks()[0]?.getSettings?.() || {};
        if (audioSettings.deviceId) localStorage.setItem(LS_MIC, audioSettings.deviceId);
        if (videoSettings.deviceId) localStorage.setItem(LS_CAM, videoSettings.deviceId);

        if (video) {
          video.srcObject = stream;
          await video.play().catch(() => undefined);
        }
        if (empty) empty.hidden = true;

        await refreshDeviceLists();

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

        // Start speech before metering so STT claims the mic first.
        startSpeech();
        await startMeter(stream);
      } catch (err) {
        setError(
          err instanceof Error
            ? err.message
            : "Camera/microphone permission is required to record the interview",
        );
        if (meterState) meterState.textContent = "No access";
      } finally {
        starting = false;
      }
    }

    audioSelect?.addEventListener("change", () => {
      const id = audioSelect.value;
      if (id) void replaceTrack("audio", id);
    });
    videoSelect?.addEventListener("change", () => {
      const id = videoSelect.value;
      if (id) void replaceTrack("video", id);
    });
    root.querySelector("[data-refresh-devices]")?.addEventListener("click", () => {
      void refreshDeviceLists().then(() => setMeta("Device list refreshed"));
    });
    root.querySelector("[data-toggle-trouble]")?.addEventListener("click", (e) => {
      const btn = e.currentTarget;
      const open = troublePanel?.hidden;
      if (troublePanel) troublePanel.hidden = !open;
      btn.setAttribute("aria-expanded", open ? "true" : "false");
      btn.textContent = open ? "Hide troubleshoot" : "Troubleshoot";
    });
    root.querySelector("[data-reacquire]")?.addEventListener("click", () => {
      void acquireAndRecord({ force: true });
    });

    const onDeviceChange = () => {
      void refreshDeviceLists();
    };
    if (navigator.mediaDevices?.addEventListener) {
      navigator.mediaDevices.addEventListener("devicechange", onDeviceChange);
    }

    function teardownMedia({ upload = true } = {}) {
      cancelled = true;
      speechWanted = false;
      if (navigator.mediaDevices?.removeEventListener) {
        navigator.mediaDevices.removeEventListener("devicechange", onDeviceChange);
      }
      stopSpeech();
      stopMeter();
      const sid = activeSessionId;
      const rec = recorder;
      const st = stream;
      const m = mime;
      const ch = chunks.slice();
      recorder = null;
      stream = null;
      chunks = [];
      const uploadChunks = () => {
        if (!upload || !ch.length) return;
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
      if (video) video.srcObject = null;
      root.innerHTML = "";
    }

    function destroy() {
      teardownMedia({ upload: true });
    }

    function discard() {
      teardownMedia({ upload: false });
    }

    void global.SellmApi.fetchVoiceStatus(activeSessionId).catch(() => undefined);
    void acquireAndRecord();

    return { stopAndUpload, destroy, discard };
  }

  global.SellmExitVoice = { createVoiceRoom };
})(window);
