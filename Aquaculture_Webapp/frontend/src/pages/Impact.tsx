import { Clock, IndianRupee, Radar, TrendingUp } from 'lucide-react'
import { useCallback, useEffect, useState } from 'react'
import { api } from '../api'
import { Card, EmptyState, ErrorNote, Skeleton, Stat } from '../components/ui'
import { useI18n } from '../i18n'
import { useLive } from '../store'
import { zoneName } from '../text'
import { Benchmarks } from './Benchmarks'

interface Event { anomaly_id: number; zone: string; started: number; first_alert_s: number | null; first_alert_by: string | null; source_s: number | null; diagnosis_s: number | null }
interface ImpactData {
  simulated: boolean; since: number; readings: number; readings_per_hour: number; speed_scale: number; events: Event[]
  median: { first_alert_s: number | null; source_s: number | null; diagnosis_s: number | null }
}

const MANUAL_PER_DAY = 20        // assumption shown to the reader: a field team's grab samples per day
const LOSS_RATE = 14.95          // % of production value lost to disease in Indian aquaculture (Frontiers in Sustainable Food Systems, 2025)
const inr = (v: number) => `₹${Math.round(v).toLocaleString('en-IN')}`

export function Impact() {
  const { live } = useLive()
  const { t, tm } = useI18n()
  const [d, setD] = useState<ImpactData | null>(null)
  const [err, setErr] = useState<string | null>(null)
  const [labHours, setLabHours] = useState(48)
  const [sales, setSales] = useState(1_000_000)
  const [loss, setLoss] = useState(LOSS_RATE)
  const [prevented, setPrevented] = useState(20)
  const load = useCallback(() => { api<ImpactData>('/impact').then((x) => { setD(x); setErr(null) }).catch((e: Error) => setErr(e.message)) }, [])
  useEffect(() => { load(); const id = setInterval(load, 5000); return () => clearInterval(id) }, [load])
  if (!live) return null

  const dur = (s: number | null | undefined) => s == null ? '–' : s < 90 ? t('imp.sec', { n: Math.round(s) }) : t('imp.min', { n: (s / 60).toFixed(1) })
  const diag = d?.median.diagnosis_s ?? null
  const scale = d?.speed_scale ?? 1
  // Conservative: the demo boat moves `scale` times faster than the real hull, so the whole response is stretched by it
  const speedup = diag ? Math.round((labHours * 3600) / (diag * scale)) : null
  const lost = (sales * loss) / 100
  const saved = (lost * prevented) / 100
  const manualDays = d ? d.readings_per_hour / MANUAL_PER_DAY : 0

  return (
    <div className="space-y-3 sm:space-y-4">
      <section className="band rounded-2xl p-5 sm:p-7">
        <div className="eyebrow">{t('imp.eyebrow')}</div>
        <h1 className="display m-0 mt-1.5 text-2xl sm:text-4xl">{t('imp.title')}</h1>
        <p className="m-0 mt-2 text-sm sm:text-base text-ink-2 max-w-3xl leading-relaxed">{t('imp.lead')}</p>
      </section>
      <ErrorNote>{err}</ErrorNote>

      <div className="grid gap-3 sm:gap-4 grid-cols-1 lg:grid-cols-3 items-start">
        {/* Time */}
        <Card title={<><Clock size={15} className="shrink-0" /> {t('imp.timeTitle')}</>} right={<span className="chip chip-soft">{t('imp.measured')}</span>}>
          {!d ? <Skeleton className="h-24 w-full" /> : diag == null ? (
            <EmptyState icon={<Radar size={18} />} title={t('imp.noEvents')} hint={live.config.simulated ? t('imp.noEventsHint') : undefined} />
          ) : (
            <>
              <Stat label={t('imp.toDiagnosis')} value={dur(diag)} caption={speedup != null && speedup > 1 ? <b className="text-ink">{t('imp.faster', { n: speedup.toLocaleString() })}</b> : undefined} />
              <dl className="m-0 mt-3 grid grid-cols-[1fr_auto] gap-x-3 gap-y-1.5 text-xs">
                <dt className="text-ink-2">{t('imp.toAlert')}</dt><dd className="m-0 tnum font-semibold">{dur(d.median.first_alert_s)}</dd>
                <dt className="text-ink-2">{t('imp.toSource')}</dt><dd className="m-0 tnum font-semibold">{dur(d.median.source_s)}</dd>
                <dt className="text-ink-2">{t('imp.toDiagnosis')}</dt><dd className="m-0 tnum font-semibold">{dur(diag)}</dd>
              </dl>
            </>
          )}
          <label className="mt-3 pt-3 border-t border-line flex items-center justify-between gap-2 text-xs text-ink-2">
            <span>{t('imp.lab')} <span className="chip">{t('imp.assumed')}</span></span>
            <span className="inline-flex items-center gap-1.5"><input type="number" min={1} max={720} value={labHours} onChange={(e) => setLabHours(Math.max(1, Number(e.target.value) || 1))} className="field !w-20 !py-1 tnum text-right" /> h</span>
          </label>
          {d && scale > 1 && <p className="m-0 mt-2 text-[0.7rem] text-muted leading-relaxed">{t('imp.scaleNote', { n: scale })}</p>}
        </Card>

        {/* Coverage */}
        <Card title={<><TrendingUp size={15} className="shrink-0" /> {t('imp.covTitle')}</>} right={<span className="chip chip-soft">{t('imp.measured')}</span>}>
          {!d ? <Skeleton className="h-24 w-full" /> : (
            <>
              <Stat label={t('imp.perHour')} value={d.readings_per_hour.toLocaleString()} caption={manualDays >= 1 ? <b className="text-ink">{t('imp.manualDays', { n: Math.round(manualDays).toLocaleString() })}</b> : undefined} />
              <div className="mt-4 space-y-2" role="img" aria-label={t('imp.covAlt', { a: d.readings_per_hour, b: MANUAL_PER_DAY })}>
                <Bar label={t('imp.boatHour')} value={d.readings_per_hour} max={Math.max(d.readings_per_hour, MANUAL_PER_DAY)} strong />
                <Bar label={t('imp.manualDay')} value={MANUAL_PER_DAY} max={Math.max(d.readings_per_hour, MANUAL_PER_DAY)} />
              </div>
              <p className="m-0 mt-3 text-[0.7rem] text-muted leading-relaxed">{t('imp.covNote', { n: d.readings.toLocaleString(), m: MANUAL_PER_DAY })}</p>
            </>
          )}
        </Card>

        {/* Money */}
        <Card title={<><IndianRupee size={15} className="shrink-0" /> {t('imp.moneyTitle')}</>} right={<span className="chip">{t('imp.scenario')}</span>}>
          <Stat label={t('imp.saved')} value={inr(saved)} caption={t('imp.ofLoss', { loss: inr(lost) })} />
          <div className="mt-3 space-y-2.5 text-xs text-ink-2">
            <label className="flex items-center justify-between gap-2">{t('imp.sales')}
              <input type="number" min={0} step={50000} value={sales} onChange={(e) => setSales(Math.max(0, Number(e.target.value) || 0))} className="field !w-32 !py-1 tnum text-right" />
            </label>
            <label className="flex items-center justify-between gap-2">{t('imp.lossRate')}
              <span className="inline-flex items-center gap-1.5"><input type="number" min={0} max={100} step={0.05} value={loss} onChange={(e) => setLoss(Math.min(100, Math.max(0, Number(e.target.value) || 0)))} className="field !w-20 !py-1 tnum text-right" /> %</span>
            </label>
            <label className="block">
              <span className="flex items-center justify-between gap-2">{t('imp.prevented')}<b className="text-ink tnum">{prevented}%</b></span>
              <input type="range" min={0} max={100} step={5} value={prevented} onChange={(e) => setPrevented(Number(e.target.value))} className="w-full mt-1" style={{ accentColor: 'var(--accent)' }} />
            </label>
          </div>
          <p className="m-0 mt-2 text-[0.7rem] text-muted leading-relaxed">{t('imp.moneyNote', { r: LOSS_RATE })}</p>
        </Card>
      </div>

      {d && d.events.length > 0 && (
        <Card title={t('imp.eventsTitle')}>
          <div className="overflow-x-auto">
            <table className="w-full text-xs border-collapse min-w-[30rem]">
              <thead><tr className="text-left eyebrow">{[t('imp.event'), t('imp.toAlert'), t('imp.toSource'), t('imp.toDiagnosis')].map((h) => <th key={h} className="py-2 pr-4 font-semibold border-b border-line">{h}</th>)}</tr></thead>
              <tbody>
                {d.events.map((e) => (
                  <tr key={e.anomaly_id}>
                    <td className="py-2 pr-4 border-b border-line font-semibold">#{e.anomaly_id} · {zoneName(tm, e.zone)}</td>
                    <td className="py-2 pr-4 border-b border-line tnum">{dur(e.first_alert_s)}{e.first_alert_by && <span className="text-muted"> · {t(e.first_alert_by === 'gemma' ? 'imp.byGemma' : 'imp.byRule')}</span>}</td>
                    <td className="py-2 pr-4 border-b border-line tnum">{dur(e.source_s)}</td>
                    <td className="py-2 pr-4 border-b border-line tnum">{dur(e.diagnosis_s)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          <p className="m-0 mt-2 text-[0.7rem] text-muted">{t('imp.eventsNote')}</p>
        </Card>
      )}

      <div id="benchmarks"><Benchmarks /></div>
    </div>
  )
}

function Bar({ label, value, max, strong }: { label: string; value: number; max: number; strong?: boolean }) {
  return (
    <div>
      <div className="flex items-baseline justify-between gap-2 text-xs"><span className="text-ink-2">{label}</span><b className="tnum">{value.toLocaleString()}</b></div>
      <div className="mt-1 h-2 rounded-full bg-surface-2 overflow-hidden">
        <div className="h-full rounded-full" style={{ width: `${Math.max(1.5, (100 * value) / Math.max(1, max))}%`, background: strong ? 'var(--accent)' : 'var(--axis)' }} />
      </div>
    </div>
  )
}
