import { AudioLines, Loader2, Square } from 'lucide-react'
import { useCallback, useEffect, useRef, useState } from 'react'
import { BACKEND } from '../api'
import { useI18n } from '../i18n'

/** One piece of a spoken exchange. Transcripts arrive in fragments; `appendVoice` joins them into turns. */
export interface VoiceTurn { role: 'user' | 'assistant'; text: string; voice: true }
export function appendVoice<X extends { role: string; text: string; voice?: boolean }>(turns: X[], role: 'user' | 'assistant', fragment: string): X[] {
  const last = turns[turns.length - 1]
  if (last && last.voice && last.role === role) return [...turns.slice(0, -1), { ...last, text: last.text + fragment }]
  return [...turns, { role, text: fragment, voice: true } as unknown as X]
}

// Runs on the audio thread: hands each block of microphone samples to the page
const WORKLET = `class PcmCapture extends AudioWorkletProcessor {
  process(inputs) { const c = inputs[0][0]; if (c) this.port.postMessage(c.slice(0)); return true }
}
registerProcessor('pcm-capture', PcmCapture)`
const IN_RATE = 16000, OUT_RATE = 24000, CHUNK = 1600       // 100 ms of microphone audio per message

const canTalk = typeof window !== 'undefined' && !!navigator.mediaDevices?.getUserMedia && typeof AudioWorkletNode !== 'undefined'

interface Props {
  /** A fragment of what was heard (user) or said (assistant). */
  onDelta: (role: 'user' | 'assistant', fragment: string) => void
  onError: (message: string | null) => void
  large?: boolean
}

/**
 * Talk button: a spoken conversation with the lake's data over the Gemini Live API.
 * The microphone is streamed to the backend (/ws/voice) as 16 kHz PCM; the reply is played as it
 * arrives, and speaking over it interrupts it. Shown only when the backend has a Live model set.
 */
export function LiveVoice({ onDelta, onError, large }: Props) {
  const { t, lang } = useI18n()
  const [state, setState] = useState<'idle' | 'connecting' | 'live'>('idle')
  const [speaking, setSpeaking] = useState(false)
  const stopRef = useRef<(() => void) | null>(null)
  const cb = useRef({ onDelta, onError })
  useEffect(() => { cb.current = { onDelta, onError } })
  useEffect(() => () => stopRef.current?.(), [])

  const start = useCallback(async () => {
    cb.current.onError(null)
    if (!window.isSecureContext) return cb.current.onError(t('voice.insecure'))
    setState('connecting')
    let stream: MediaStream
    try {
      stream = await navigator.mediaDevices.getUserMedia({ audio: { echoCancellation: true, noiseSuppression: true, channelCount: 1 } })
    } catch {
      setState('idle')
      return cb.current.onError(t('voice.denied'))
    }
    const mic = new AudioContext({ sampleRate: IN_RATE })
    const out = new AudioContext({ sampleRate: OUT_RATE })
    const base = BACKEND || location.origin
    const ws = new WebSocket(`${base.replace(/^http/, 'ws')}/ws/voice?lang=${lang}`)
    ws.binaryType = 'arraybuffer'
    let playAt = 0
    let playing: AudioBufferSourceNode[] = []
    let closed = false

    const stop = () => {
      if (closed) return
      closed = true
      stopRef.current = null
      stream.getTracks().forEach((tr) => tr.stop())
      playing.forEach((s) => { try { s.stop() } catch { /* already ended */ } })
      void mic.close(); void out.close()
      if (ws.readyState <= WebSocket.OPEN) { try { ws.send(JSON.stringify({ type: 'stop' })) } catch { /* closing */ } ws.close() }
      setState('idle'); setSpeaking(false)
    }
    stopRef.current = stop

    const flush = () => {                       // the person spoke over the reply: drop what is queued
      playing.forEach((s) => { try { s.stop() } catch { /* already ended */ } })
      playing = []; playAt = 0; setSpeaking(false)
    }
    const play = (pcm: ArrayBuffer) => {
      const i16 = new Int16Array(pcm)
      if (!i16.length) return
      const buf = out.createBuffer(1, i16.length, OUT_RATE)
      const ch = buf.getChannelData(0)
      for (let i = 0; i < i16.length; i++) ch[i] = i16[i] / 32768
      const src = out.createBufferSource()
      src.buffer = buf
      src.connect(out.destination)
      playAt = Math.max(out.currentTime + 0.02, playAt)
      src.start(playAt)
      playAt += buf.duration
      playing.push(src)
      setSpeaking(true)
      src.onended = () => { playing = playing.filter((s) => s !== src); if (!playing.length) setSpeaking(false) }
    }

    const capture = async () => {
      const url = URL.createObjectURL(new Blob([WORKLET], { type: 'application/javascript' }))
      try { await mic.audioWorklet.addModule(url) } finally { URL.revokeObjectURL(url) }
      const node = new AudioWorkletNode(mic, 'pcm-capture')
      let pending = new Int16Array(CHUNK), n = 0
      node.port.onmessage = (ev: MessageEvent<Float32Array>) => {
        const f = ev.data
        for (let i = 0; i < f.length; i++) {
          const v = Math.max(-1, Math.min(1, f[i]))
          pending[n++] = v < 0 ? v * 32768 : v * 32767
          if (n === CHUNK) {
            if (ws.readyState === WebSocket.OPEN) ws.send(pending.buffer)
            pending = new Int16Array(CHUNK); n = 0
          }
        }
      }
      mic.createMediaStreamSource(stream).connect(node)
    }

    ws.onmessage = (ev) => {
      if (typeof ev.data !== 'string') return play(ev.data as ArrayBuffer)
      const m = JSON.parse(ev.data) as { type: string; text?: string; message?: string }
      if (m.type === 'ready') { setState('live'); void capture().catch((e: Error) => { cb.current.onError(`${t('voice.unsupported')} (${e.message})`); stop() }) }
      else if (m.type === 'user' || m.type === 'assistant') cb.current.onDelta(m.type, m.text ?? '')
      else if (m.type === 'interrupted') flush()
      else if (m.type === 'error') { cb.current.onError(m.message ?? t('lv.error')); stop() }
    }
    ws.onerror = () => { if (!closed) cb.current.onError(t('lv.error')) }
    ws.onclose = () => stop()
  }, [lang, t])

  if (!canTalk) return null
  const on = state !== 'idle'
  const label = state === 'connecting' ? t('lv.connecting') : state === 'live' ? (speaking ? t('lv.speaking') : t('lv.listening')) : t('lv.talk')
  return (
    <button type="button" onClick={() => (on ? stopRef.current?.() : void start())} aria-pressed={on} title={on ? t('lv.stop') : t('lv.talkTitle')}
      className={`btn ${large ? 'btn-lg' : ''} ${state === 'live' ? 'mic-live' : ''}`}
      style={state === 'live' ? { background: 'var(--critical)', color: '#fff', borderColor: 'transparent' } : undefined}>
      {state === 'connecting' ? <Loader2 size={large ? 18 : 15} className="animate-spin" /> : state === 'live' ? <Square size={large ? 15 : 12} fill="currentColor" /> : <AudioLines size={large ? 18 : 15} />}
      {label}
    </button>
  )
}
