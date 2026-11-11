import { AlertTriangle, Check, CircleCheck, Fish, OctagonAlert, Square, Volume2 } from 'lucide-react'
import { useEffect, useMemo, useState } from 'react'
import { api } from '../api'
import { appendVoice, LiveVoice, type VoiceTurn } from '../components/LiveVoice'
import { ErrorNote, healthColor, Skeleton } from '../components/ui'
import { useI18n } from '../i18n'
import { useLive } from '../store'
import { edgeText, zoneName } from '../text'

interface Brief { status_line: string; what_happened: string; do_now: string[]; model: string; language: string }
const ORDER = ['Healthy', 'Stressed', 'Critical']
const ICON = { Healthy: Check, Stressed: AlertTriangle, Critical: OctagonAlert } as const
const RECENT_S = 6 * 3600

/** True when the browser can read text aloud in this language. */
function useCanSpeak(locale: string) {
  const [ok, setOk] = useState(false)
  useEffect(() => {
    if (!('speechSynthesis' in window)) return
    const check = () => setOk(speechSynthesis.getVoices().some((v) => v.lang.toLowerCase().startsWith(locale.slice(0, 2))))
    check()
    speechSynthesis.addEventListener('voiceschanged', check)
    return () => speechSynthesis.removeEventListener('voiceschanged', check)
  }, [locale])
  return ok
}

/**
 * The fish farmer's page: one zone, one status, what happened and what to do now, in large type
 * for a phone. The status comes from the fish-health model; Gemini only puts it into plain words.
 */
export function Farmer() {
  const { live } = useLive()
  const { t, tm, ago, lang, speech } = useI18n()
  const [sel, setSel] = useState<string | null>(null)
  const [brief, setBrief] = useState<Brief | null>(null)
  const [loading, setLoading] = useState(false)
  const [speakingAloud, setSpeakingAloud] = useState(false)
  const [voiceErr, setVoiceErr] = useState<string | null>(null)
  const [talk, setTalk] = useState<VoiceTurn[]>([])
  const canSpeak = useCanSpeak(speech)

  const zones = live?.zones.zones
  const worst = useMemo(() => zones && Object.values(zones).filter((z) => z.available)
    .sort((a, b) => ORDER.indexOf(b.health_status) - ORDER.indexOf(a.health_status))[0]?.zone, [zones])
  const zone = sel ?? worst ?? live?.lake.zones[0]?.id ?? null
  const p = zone && zones ? zones[zone] : undefined
  const anomaly = live?.anomalies.find((a) => a.zone === zone && a.status !== 'linked' && Date.now() / 1000 - a.started < RECENT_S)
  const diag = anomaly && live?.diagnoses.find((d) => d.anomaly_id === anomaly.id)
  const ready = !!live?.config.gemini_ready
  const key = `${zone}|${p?.available ? p.health_status : ''}|${anomaly?.id ?? ''}|${diag?.id ?? ''}|${lang}`

  useEffect(() => {
    setBrief(null)
    if (!zone || !ready || !p?.available) return
    let stale = false
    setLoading(true)
    api<{ brief: Brief | null }>(`/farmer?zone=${zone}&lang=${lang}`)
      .then((r) => { if (!stale) setBrief(r.brief) })
      .catch(() => { /* the page falls back to the model's own advice */ })
      .finally(() => { if (!stale) setLoading(false) })
    return () => { stale = true }
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [key, ready])
  useEffect(() => () => { if ('speechSynthesis' in window) speechSynthesis.cancel() }, [])

  if (!live || !zone) return null
  const status = p?.available ? p.health_status : null
  const Icon = status ? ICON[status] : Fish
  const color = status ? healthColor(status) : 'var(--muted)'
  const edge = anomaly?.edge_alert ? edgeText(t, tm, anomaly.edge_alert) : null
  const statusLine = brief?.status_line ?? (status ? t(`far.line.${status}`) : (p?.reason ?? t('far.waiting')))
  const happened = brief?.what_happened ?? edge?.body ?? (status ? t(anomaly ? 'far.found' : 'far.nothing') : '')
  const steps = brief?.do_now ?? (p?.available ? p.advice.slice(0, 3) : [])
  const stepsEnglish = !brief && steps.length > 0 && lang !== 'en'

  const listen = () => {
    if (speakingAloud) { speechSynthesis.cancel(); return setSpeakingAloud(false) }
    const u = new SpeechSynthesisUtterance([status ? tm(`health.${status}`, status) : '', statusLine, happened, steps.length ? t('far.doNow') : '', ...steps].filter(Boolean).join('. '))
    u.lang = speech
    u.rate = 0.95
    u.onend = u.onerror = () => setSpeakingAloud(false)
    speechSynthesis.cancel()
    speechSynthesis.speak(u)
    setSpeakingAloud(true)
  }

  return (
    <div className="max-w-xl mx-auto space-y-3 sm:space-y-4">
      {/* Status */}
      <section className="band rounded-2xl p-5 sm:p-7" aria-live="polite">
        <div className="flex items-center justify-between gap-3 flex-wrap">
          <label className="eyebrow inline-flex items-center gap-2">{t('far.myZone')}
            <select className="btn btn-sm normal-case tracking-normal" value={zone} onChange={(e) => { setSel(e.target.value); setTalk([]) }}>
              {live.lake.zones.map((z) => <option key={z.id} value={z.id}>{zoneName(tm, z.id)}</option>)}
            </select>
          </label>
          {live.config.simulated && <span className="chip">{t('hdr.sim')}</span>}
        </div>
        <div className="mt-5 flex items-center gap-4">
          <span className={`inline-flex items-center justify-center rounded-full shrink-0 w-16 h-16 sm:w-20 sm:h-20 ${status === 'Critical' ? 'flash' : ''}`} style={{ background: color }}>
            <Icon size={36} color="#fff" strokeWidth={2.6} />
          </span>
          <div className="min-w-0">
            <div className="eyebrow">{t('far.fishHealth')}</div>
            <div className="display text-4xl sm:text-5xl">{status ? tm(`health.${status}`, status) : '–'}</div>
          </div>
        </div>
        {loading && !brief ? <div className="mt-4 space-y-2"><Skeleton className="h-5 w-11/12" /><Skeleton className="h-5 w-2/3" /></div>
          : <p className="mt-4 mb-0 text-lg sm:text-xl leading-snug">{statusLine}</p>}
        <p className="mt-3 mb-0 text-xs text-muted">
          {status && p ? t('far.sure', { n: Math.round(p.confidence * 100) }) : ''}{status ? ' · ' : ''}{t('far.updated', { ago: ago(live.zones.updated) })}
        </p>
      </section>

      {/* What happened */}
      {happened && (
        <section className="card p-5">
          <div className="eyebrow mb-1.5">{t('far.what')}</div>
          {loading && !brief ? <Skeleton className="h-5 w-full" /> : <p className="m-0 text-base sm:text-lg leading-relaxed">{happened}</p>}
          {diag && <p className="mt-2 mb-0 text-sm text-ink-2">{t('far.cause', { cause: tm(`cause.${diag.body.probable_cause}`, diag.body.probable_cause), c: tm(`conf.${diag.body.confidence}`, diag.body.confidence) })}</p>}
          {!brief && edge && anomaly?.edge_alert && (
            <p className="mt-2 mb-0 text-xs text-muted">{t(anomaly.edge_alert.by === 'gemma' ? 'edge.byGemma' : 'edge.byRule', { model: anomaly.edge_alert.model ?? '' })}</p>
          )}
        </section>
      )}

      {/* What to do */}
      <section className="card p-5">
        <div className="eyebrow mb-2.5">{t('far.doNow')}</div>
        {loading && !brief ? <div className="space-y-2.5"><Skeleton className="h-6 w-full" /><Skeleton className="h-6 w-5/6" /></div>
          : steps.length === 0 ? <p className="m-0 text-base text-ink-2 flex items-center gap-2"><CircleCheck size={20} style={{ color: 'var(--good)' }} /> {t('far.noSteps')}</p> : (
            <ol className="m-0 p-0 list-none space-y-3">
              {steps.map((s, i) => (
                <li key={i} className="flex gap-3 items-start">
                  <span className="inline-flex items-center justify-center w-8 h-8 rounded-full shrink-0 font-semibold tnum bg-accent-soft text-accent">{i + 1}</span>
                  <span className="text-base sm:text-lg leading-snug pt-0.5">{s}</span>
                </li>
              ))}
            </ol>
          )}
        {stepsEnglish && <p className="mt-3 mb-0 text-xs text-muted">{t('far.english')}</p>}
        {brief && <p className="mt-3 mb-0 text-xs text-muted">{t('far.wordedBy', { model: brief.model })}</p>}
      </section>

      {/* Listen and talk */}
      <div className="flex gap-2.5 flex-wrap">
        {canSpeak && (
          <button className="btn btn-primary btn-lg flex-1" onClick={listen} disabled={!status}>
            {speakingAloud ? <Square size={15} fill="currentColor" /> : <Volume2 size={18} />} {speakingAloud ? t('far.stop') : t('far.listen')}
          </button>
        )}
        {live.config.live_model && <LiveVoice large onError={setVoiceErr} onDelta={(role, frag) => setTalk((prev) => appendVoice(prev, role, frag).slice(-4))} />}
      </div>
      <ErrorNote>{voiceErr}</ErrorNote>
      {talk.length > 0 && (
        <section className="card p-4 space-y-2.5" aria-live="polite">
          {talk.map((x, i) => x.role === 'user'
            ? <div key={i} className="flex justify-end"><div className="max-w-[85%] rounded-2xl rounded-br-md px-3.5 py-2 text-sm" style={{ background: 'var(--accent)', color: 'var(--accent-ink)' }}>{x.text}</div></div>
            : <div key={i} className="max-w-[92%] rounded-2xl rounded-bl-md bg-surface-2 px-3.5 py-2.5 text-base leading-relaxed">{x.text}</div>)}
        </section>
      )}

      <p className="m-0 px-1 text-xs text-muted leading-relaxed">{t('far.note')}{live.config.simulated ? ` ${t('hdr.simTitle')}.` : ''}</p>
    </div>
  )
}
