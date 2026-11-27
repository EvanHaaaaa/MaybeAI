/**
 * MaybeAI AudioWorkletProcessor (MaybeAIPCMProcessor)
 * Downsamples browser AudioContext sampleRate to 16 kHz mono Int16 PCM frames
 * and posts transferable ArrayBuffer chunks to the main thread.
 */
class MaybeAIPCMProcessor extends AudioWorkletProcessor {
  constructor(options) {
    super();
    const opts = (options && options.processorOptions) || {};
    this.targetSampleRate = Number(opts.targetSampleRate) || 16000;
    this.frameSize = Number(opts.frameSize) || 512; // 32ms @ 16kHz
    this._buffer = new Int16Array(this.frameSize);
    this._offset = 0;
    this._phase = 0;
    this._lastSample = 0;
    this._hasLastSample = false;
    this._stopped = false;

    this.port.onmessage = (event) => {
      const data = event && event.data;
      if (!data) return;
      if (data.type === "stop") {
        this._flush(true);
        this._stopped = true;
      } else if (data.type === "flush") {
        this._flush(Boolean(data.final));
      }
    };
  }

  _flush(isFinal = false) {
    if (this._offset > 0) {
      const partial = this._buffer.slice(0, this._offset);
      this.port.postMessage(
        { type: "pcm16", buffer: partial.buffer, final: Boolean(isFinal) },
        [partial.buffer]
      );
      this._offset = 0;
    }
  }

  _pushInt16(sampleFloat) {
    const clamped = Math.max(-1, Math.min(1, sampleFloat));
    const int16 = clamped < 0 ? Math.round(clamped * 32768) : Math.round(clamped * 32767);
    this._buffer[this._offset++] = int16;
    if (this._offset >= this.frameSize) {
      const out = this._buffer;
      this._buffer = new Int16Array(this.frameSize);
      this._offset = 0;
      this.port.postMessage({ type: "pcm16", buffer: out.buffer }, [out.buffer]);
    }
  }

  process(inputs) {
    if (this._stopped) return false;
    const input = inputs && inputs[0];
    if (!input || input.length === 0) return true;

    const channelCount = input.length;
    const ch0 = input[0];
    if (!ch0 || ch0.length === 0) return true;

    const srcRate = typeof sampleRate === "number" && sampleRate > 0 ? sampleRate : 48000;
    const dstRate = this.targetSampleRate;
    const frameLen = ch0.length;

    // Mix down to mono if multiple channels exist
    let mono = ch0;
    if (channelCount > 1) {
      mono = new Float32Array(frameLen);
      for (let i = 0; i < frameLen; i++) {
        let sum = 0;
        for (let c = 0; c < channelCount; c++) {
          sum += input[c][i] || 0;
        }
        mono[i] = sum / channelCount;
      }
    }

    if (srcRate === dstRate) {
      for (let i = 0; i < frameLen; i++) {
        this._pushInt16(mono[i]);
      }
      this._lastSample = mono[frameLen - 1];
      this._hasLastSample = true;
      return true;
    }

    if (!this._hasLastSample) {
      this._lastSample = mono[0];
      this._hasLastSample = true;
    }

    const ratio = srcRate / dstRate;
    let pos = this._phase;
    // Interpolate across [frameLen - 1] so pos in [-1, 0) bridges _lastSample -> mono[0]
    // and pos in [0, frameLen - 1) bridges mono[idx] -> mono[idx + 1] without skipping mono[0].
    while (pos < frameLen - 1) {
      let interp;
      if (pos < 0) {
        const frac = pos + 1;
        interp = this._lastSample + (mono[0] - this._lastSample) * frac;
      } else {
        const idx = Math.floor(pos);
        const frac = pos - idx;
        const s0 = mono[idx];
        const s1 = mono[idx + 1];
        interp = s0 + (s1 - s0) * frac;
      }
      this._pushInt16(interp);
      pos += ratio;
    }
    this._phase = pos - frameLen;
    this._lastSample = mono[frameLen - 1];
    this._hasLastSample = true;
    return true;
  }
}

if (typeof registerProcessor === "function") {
  registerProcessor("maybeai-pcm-processor", MaybeAIPCMProcessor);
}
