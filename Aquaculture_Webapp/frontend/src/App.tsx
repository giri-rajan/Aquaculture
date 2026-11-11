import { FileText, Fish, Languages, MessagesSquare, Moon, Radar, Sun, TrendingUp, Waves } from 'lucide-react'
import { useEffect, useState } from 'react'
import { ErrorNote, Skeleton } from './components/ui'
import { I18nProvider, LANGS, useI18n, type Lang } from './i18n'
import { Ask } from './pages/Ask'
import { Farmer } from './pages/Farmer'
import { Impact } from './pages/Impact'
import { Live } from './pages/Live'
import { Reports } from './pages/Reports'
import { Zones } from './pages/Zones'
import { LiveProvider, useLive } from './store'

const TABS = [
  { id: 'live', label: 'nav.live', short: 'nav.live.s', Icon: Radar },
  { id: 'zones', label: 'nav.zones', short: 'nav.zones.s', Icon: Fish },
  { id: 'ask', label: 'nav.ask', short: 'nav.ask.s', Icon: MessagesSquare },
  { id: 'reports', label: 'nav.reports', short: 'nav.reports.s', Icon: FileText },
  { id: 'impact', label: 'nav.impact', short: 'nav.impact.s', Icon: TrendingUp },
] as const
type TabId = (typeof TABS)[number]['id']
/** The officer's dashboard is the five tabs; `farmer` is the separate one-page view for a fish farmer. */
type Route = TabId | 'farmer'

function readRoute(): Route {
  const h = location.hash.slice(1)
  if (h === 'farmer') return 'farmer'
  if (h === 'benchmarks') return 'impact'                              // the benchmarks now sit at the foot of the Impact page
  if (!h && new URLSearchParams(location.search).get('view') === 'farmer') return 'farmer'      // ?view=farmer for the phone demo
  return TABS.find((x) => x.id === h)?.id ?? 'live'
}
const osDark = () => matchMedia('(prefers-color-scheme: dark)').matches

function Shell() {
  const { live, connected, error } = useLive()
  const { t, lang, setLang } = useI18n()
  const [route, setRoute] = useState<Route>(readRoute)
  const [lastTab, setLastTab] = useState<TabId>(() => { const r = readRoute(); return r === 'farmer' ? 'live' : r })
  const [dark, setDark] = useState<boolean>(() => {
    const q = new URLSearchParams(location.search).get('theme')          // ?theme=light|dark for screenshots and demos
    if (q === 'light' || q === 'dark') return q === 'dark'
    try { const s = localStorage.getItem('theme'); if (s) return s === 'dark' } catch { /* storage blocked */ }
    return osDark()
  })
  useEffect(() => { document.documentElement.dataset.theme = dark ? 'dark' : 'light' }, [dark])
  useEffect(() => {
    const f = () => {
      const r = readRoute()
      setRoute(r)
      if (r !== 'farmer') setLastTab(r)
      if (location.hash === '#benchmarks') requestAnimationFrame(() => document.getElementById('benchmarks')?.scrollIntoView())
      else scrollTo(0, 0)
    }
    addEventListener('hashchange', f)
    return () => removeEventListener('hashchange', f)
  }, [])
  const toggle = () => setDark((d) => { try { localStorage.setItem('theme', d ? 'light' : 'dark') } catch { /* storage blocked */ } return !d })
  const farmer = route === 'farmer'

  return (
    <div className="min-h-full flex flex-col">
      <header className="band sticky top-0 z-[1100] border-b border-line" style={{ paddingTop: 'env(safe-area-inset-top)' }}>
        <div className="max-w-[1500px] mx-auto px-3 sm:px-6 pt-2.5 flex items-center gap-x-5 gap-y-2 flex-wrap">
          <div className="flex items-center gap-2.5 min-w-0 pb-2.5">
            <span className="inline-flex items-center justify-center w-9 h-9 rounded-full shrink-0 bg-cta text-cta-ink"><Waves size={19} /></span>
            <div className="leading-tight min-w-0">
              <div className="font-semibold text-base tracking-tight">AquaSentinel</div>
              <div className="text-[0.7rem] text-muted truncate">{live ? live.lake.name : t('hdr.connecting')}</div>
            </div>
          </div>
          {/* Tablets and up: tabs in the header (own row until there is room beside the logo) */}
          {!farmer && (
            <nav className="hidden md:flex gap-1 overflow-x-auto order-3 w-full xl:order-none xl:w-auto self-end" aria-label={t('hdr.sections')}>
              {TABS.map(({ id, label, Icon }) => (
                <a key={id} href={`#${id}`} aria-current={route === id ? 'page' : undefined} className="navtab"><Icon size={15} />{t(label)}</a>
              ))}
            </nav>
          )}
          <div className="ml-auto flex items-center gap-1.5 justify-end flex-wrap pb-2.5">
            {live?.config.simulated && <span className="chip hidden sm:inline-flex" title={t('hdr.simTitle')}>{t('hdr.sim')}</span>}
            {live && <span className="chip hidden lg:inline-flex">
              <i className="inline-block w-1.5 h-1.5 rounded-full" style={{ background: live.config.gemini_ready ? 'var(--cta)' : 'var(--axis)' }} />
              {live.config.gemini_ready ? live.config.gemini_model : t('hdr.geminiOff')}
            </span>}
            <span className="chip" role="status">
              <i className="inline-block w-1.5 h-1.5 rounded-full" style={{ background: connected ? 'var(--cta)' : 'var(--critical)' }} />{connected ? t('hdr.live') : t('hdr.offline')}
            </span>
            <div className="seg" role="group" aria-label={t('hdr.view')}>
              <button aria-pressed={!farmer} onClick={() => { location.hash = lastTab }}>{t('view.officer')}</button>
              <button aria-pressed={farmer} onClick={() => { location.hash = 'farmer' }}>{t('view.farmer')}</button>
            </div>
            <label className="btn btn-sm !gap-1 !pr-1 cursor-pointer" title={t('hdr.language')}>
              <Languages size={14} aria-hidden />
              <select className="bg-transparent border-0 outline-none font-[inherit] text-[inherit] cursor-pointer max-w-24" style={{ fontSize: 'inherit' }}
                aria-label={t('hdr.language')} value={lang} onChange={(e) => setLang(e.target.value as Lang)}>
                {LANGS.map((l) => <option key={l.code} value={l.code}>{l.name}</option>)}
              </select>
            </label>
            <button className="icon-btn" onClick={toggle} aria-label={dark ? t('hdr.toLight') : t('hdr.toDark')}>{dark ? <Sun size={15} /> : <Moon size={15} />}</button>
          </div>
        </div>
      </header>

      <main className={`flex-1 max-w-[1500px] w-full mx-auto px-3 sm:px-6 py-4 sm:py-6 ${farmer ? 'pb-8' : 'pb-24 md:pb-8'}`}>
        {live?.config.simulated && !farmer && <div className="sm:hidden mb-3 flex gap-1.5 flex-wrap">
          <span className="chip">{t('hdr.sim')}</span>
          <span className="chip">{live.config.gemini_ready ? live.config.gemini_model : t('hdr.geminiOff')}</span>
        </div>}
        {error && !live && <ErrorNote>{t('app.noBackend', { error })}</ErrorNote>}
        {!error && !live && (
          <div className="space-y-4" role="status" aria-label={t('app.loading')}>
            <Skeleton className="h-24 w-full" />
            <div className="grid gap-4 lg:grid-cols-12"><Skeleton className="h-96 lg:col-span-8" /><Skeleton className="h-96 lg:col-span-4" /></div>
          </div>
        )}
        {live && (route === 'farmer' ? <Farmer /> : route === 'live' ? <Live dark={dark} /> : route === 'zones' ? <Zones /> : route === 'ask' ? <Ask /> : route === 'reports' ? <Reports /> : <Impact />)}
      </main>

      {/* Phones: tabs along the bottom edge, within thumb reach */}
      {!farmer && (
        <nav className="tabbar md:hidden" aria-label={t('hdr.sections')}>
          {TABS.map(({ id, short, Icon }) => (
            <a key={id} href={`#${id}`} aria-current={route === id ? 'page' : undefined}><Icon size={19} /><span>{t(short)}</span></a>
          ))}
        </nav>
      )}
    </div>
  )
}

export default function App() {
  return <I18nProvider><LiveProvider><Shell /></LiveProvider></I18nProvider>
}
