import React, { useEffect, useRef, useState } from 'react';
import {
  Plus, Send, Trash2, Loader2, ImagePlus, X,
  MessageSquare, Search, ClipboardList, Camera, Stethoscope,
  Lightbulb, TrendingUp, Users, PanelLeftClose, PanelLeft, CalendarDays,
} from 'lucide-react';
import { Link } from 'react-router-dom';
import LogCalendar from '../components/LogCalendar';
import CallMeButton from '../components/CallMeButton';
import {
  chatAgents, listSessions, createSession, getSession, deleteSession,
  sendMessage, analyzeMealPhoto, logCalendarDay,
} from '../services/api';

const ICONS = {
  general: MessageSquare,
  nutrition_lookup: Search,
  diet_planner: ClipboardList,
  food_vision: Camera,
  profile_health: Stethoscope,
  recommendation: Lightbulb,
  progress_feedback: TrendingUp,
};

const TOOLS = [
  { to: '/plan', label: 'Meal Plan', Icon: ClipboardList },
  { to: '/recommendations', label: 'Insights', Icon: Lightbulb },
  { to: '/household', label: 'Household', Icon: Users },
  { to: '/', label: 'Profile', Icon: Stethoscope },
];

export default function Chat() {
  const [agents, setAgents] = useState([]);
  const [sources, setSources] = useState(null);
  const [sessions, setSessions] = useState([]);
  const [active, setActive] = useState(null);
  const [messages, setMessages] = useState([]);
  const [agent, setAgent] = useState('general');
  const [draft, setDraft] = useState('');
  const [image, setImage] = useState(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState(null);
  const [sidebar, setSidebar] = useState(true);
  const [dayView, setDayView] = useState(null);   // ISO date, or null for chat

  const bottomRef = useRef(null);
  const fileRef = useRef(null);

  useEffect(() => {
    chatAgents()
      .then((d) => { setAgents(d.agents || []); setSources(d.sources); })
      .catch(() => setError('Could not load agents.'));
    refreshSessions();
  }, []);

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [messages, busy]);

  const refreshSessions = () =>
    listSessions().then((d) => setSessions(d.sessions || [])).catch(() => {});

  const openSession = async (id) => {
    setError(null);
    const s = await getSession(id);
    setActive(id);
    setMessages(s.messages || []);
    setAgent(s.agent || 'general');
  };

  const newChat = async (agentKey = agent) => {
    setError(null);
    setDayView(null);
    setMessages([]);
    setAgent(agentKey);
    const s = await createSession({ agent: agentKey });
    setActive(s.session_id);
    refreshSessions();
  };

  const removeSession = async (id, e) => {
    e.stopPropagation();
    await deleteSession(id);
    if (id === active) { setActive(null); setMessages([]); }
    refreshSessions();
  };

  const pickImage = (e) => {
    const file = e.target.files?.[0];
    if (file) setImage(file);
    e.target.value = '';
  };

  /** Photo path: analyse first, then show the measured result as a message. */
  const submitImage = async () => {
    setBusy(true);
    setError(null);
    const file = image;
    setImage(null);
    setMessages((m) => [...m, {
      role: 'user',
      content: `Analyse this meal photo (${file.name})`,
    }]);

    try {
      const data = await analyzeMealPhoto(file, {
        cooking_method: 'home', oil_level: 'normal',
      });
      const lines = (data.items || []).map(
        (i) => `${i.name} — ${Math.round(i.portion_g)} g · ${i.calories} kcal · ${i.protein_g} g protein`
      );
      const t = data.totals || {};
      setMessages((m) => [...m, {
        role: 'assistant',
        content: [
          data.dish_name,
          '',
          ...lines,
          '',
          `Total: ${Math.round(t.calories || 0)} kcal · ${Math.round(t.protein_g || 0)} g protein · ${Math.round(t.carbs_g || 0)} g carbs · ${Math.round(t.fat_g || 0)} g fat`,
          data.unresolved?.length ? `\nNot found: ${data.unresolved.map((u) => u.name).join(', ')}` : '',
          `\n${data.disclaimer || ''}`,
        ].filter(Boolean).join('\n'),
        facts: (data.items || []).map((i) => ({
          name: i.name, source: i.source, estimated: i.source?.includes('estimate'),
        })),
      }]);
      window.dispatchEvent(new Event('nutriai:log-changed'));
    } catch (err) {
      setError(err.response?.data?.detail || 'Could not analyse that image.');
      setMessages((m) => m.slice(0, -1));
    } finally {
      setBusy(false);
    }
  };

  const submit = async (e) => {
    e?.preventDefault();
    if (busy) return;
    if (image) return submitImage();

    const text = draft.trim();
    if (!text) return;

    setError(null);
    setDraft('');
    setBusy(true);
    setMessages((m) => [...m, { role: 'user', content: text }]);

    try {
      let id = active;
      if (!id) {
        const s = await createSession({ agent });
        id = s.session_id;
        setActive(id);
      }
      const res = await sendMessage(id, { content: text, agent });
      setMessages(res.messages || []);
      refreshSessions();
      window.dispatchEvent(new Event('nutriai:log-changed'));
    } catch (err) {
      setError(err.response?.data?.detail || 'Message failed.');
      setMessages((m) => m.slice(0, -1));
      setDraft(text);
    } finally {
      setBusy(false);
    }
  };

  const current = agents.find((a) => a.key === agent);
  const CurrentIcon = ICONS[agent] || MessageSquare;

  return (
    <div className="flex h-[calc(100vh-4.75rem)] gap-px bg-white/[0.06] rounded-lg overflow-hidden border border-white/[0.06]">
      {/* ── Sidebar ─────────────────────────────────────────── */}
      {sidebar && (
        <aside className="w-[248px] flex-shrink-0 flex flex-col bg-[#0d0d0f]">
          <div className="p-3">
            <button
              onClick={() => newChat()}
              className="w-full flex items-center gap-2.5 px-3 py-2.5 rounded-lg border border-white/10 text-[13px] text-gray-300 hover:bg-white/[0.04] hover:border-white/20 transition-colors"
            >
              <Plus className="w-4 h-4" strokeWidth={1.75} /> New chat
            </button>
          </div>

          {/* One scroll region for all navigation; the calendar is pinned below. */}
          <div className="flex-1 overflow-y-auto min-h-0">
            <Section label="Assistants" />
            <nav className="px-2 space-y-0.5">
            {agents.map((a) => {
              const Icon = ICONS[a.key] || MessageSquare;
              const on = agent === a.key;
              return (
                <button
                  key={a.key}
                  onClick={() => newChat(a.key)}
                  title={a.description}
                  className={`w-full text-left px-3 py-2 rounded-lg text-[13px] flex items-center gap-2.5 transition-colors ${
                    on ? 'bg-white/[0.07] text-white' : 'text-gray-500 hover:text-gray-300 hover:bg-white/[0.03]'
                  }`}
                >
                    <Icon className="w-4 h-4 flex-shrink-0" strokeWidth={1.75} />
                    <span className="truncate">{a.name}</span>
                  </button>
                );
              })}
            </nav>

            <Section label="Tools" />
            <nav className="px-2 space-y-0.5">
              {TOOLS.map(({ to, label, Icon }) => (
              <Link
                key={to}
                to={to}
                className="w-full text-left px-3 py-2 rounded-lg text-[13px] flex items-center gap-2.5 text-gray-500 hover:text-gray-300 hover:bg-white/[0.03] transition-colors"
              >
                  <Icon className="w-4 h-4 flex-shrink-0" strokeWidth={1.75} />
                  <span className="truncate">{label}</span>
                </Link>
              ))}
            </nav>

            <Section label="Recent" />
            <div className="px-2 pb-2 space-y-0.5">
              {sessions.length === 0 && (
                <p className="px-3 text-[12px] text-gray-700">No conversations yet</p>
              )}
              {sessions.map((s) => (
                <div
                  key={s.session_id}
                  onClick={() => { setDayView(null); openSession(s.session_id); }}
                  className={`group px-3 py-2 rounded-lg text-[13px] cursor-pointer flex items-center gap-2 transition-colors ${
                    active === s.session_id && !dayView
                      ? 'bg-white/[0.07] text-white'
                      : 'text-gray-500 hover:text-gray-300 hover:bg-white/[0.03]'
                  }`}
                >
                  <span className="flex-1 truncate">{s.title}</span>
                  <button
                    onClick={(e) => removeSession(s.session_id, e)}
                    className="opacity-0 group-hover:opacity-100 text-gray-600 hover:text-gray-300 transition-opacity"
                    aria-label="Delete conversation"
                  >
                    <Trash2 className="w-3.5 h-3.5" strokeWidth={1.75} />
                  </button>
                </div>
              ))}
            </div>
          </div>

          {/* Pinned footer: the calendar must not compete with the scroll
              region above it, or the sidebar sections collapse into each other. */}
          <div className="flex-shrink-0 border-t border-white/[0.06]">
            <CallMeButton />
            <LogCalendar selected={dayView} onSelectDay={setDayView} />
            {sources && (
              <div className="px-4 py-3 border-t border-white/[0.06] text-[11px] text-gray-700 leading-[1.6]">
                <div className="text-gray-600 mb-1">Data sources</div>
                IFCT 2017 · ICMR<br />
                USDA FoodData Central<br />
                <span className="text-amber-600/70">OpenAI estimate (flagged)</span>
              </div>
            )}
          </div>
        </aside>
      )}

      {/* ── Main pane: day view, or the conversation ────────── */}
      {dayView ? (
        <DayView date={dayView} onClose={() => setDayView(null)}
                 onToggleSidebar={() => setSidebar((v) => !v)} sidebar={sidebar} />
      ) : (
      <section className="flex-1 flex flex-col bg-[#0a0a0b] min-w-0">
        <header className="flex items-center gap-3 px-6 h-14 border-b border-white/[0.06] flex-shrink-0">
          <button
            onClick={() => setSidebar((v) => !v)}
            className="text-gray-600 hover:text-gray-300 transition-colors"
            aria-label="Toggle sidebar"
          >
            {sidebar ? <PanelLeftClose className="w-4 h-4" strokeWidth={1.75} />
                     : <PanelLeft className="w-4 h-4" strokeWidth={1.75} />}
          </button>
          <CurrentIcon className="w-4 h-4 text-gray-500" strokeWidth={1.75} />
          <div className="min-w-0">
            <div className="text-[13px] font-medium text-gray-200 leading-tight">
              {current?.name || 'Assistant'}
            </div>
            <div className="text-[11px] text-gray-600 truncate">
              {current?.description}
            </div>
          </div>
        </header>

        <div className="flex-1 overflow-y-auto">
          <div className="max-w-3xl mx-auto px-6 py-8 space-y-6">
            {messages.length === 0 && !busy && (
              <Empty agent={current} Icon={CurrentIcon} onPick={setDraft} />
            )}
            {messages.map((m, i) => <Bubble key={i} message={m} />)}
            {busy && (
              <div className="flex items-center gap-2.5 text-[13px] text-gray-600">
                <Loader2 className="w-3.5 h-3.5 animate-spin" strokeWidth={1.75} />
                Thinking
              </div>
            )}
            <div ref={bottomRef} />
          </div>
        </div>

        <div className="flex-shrink-0 px-6 pb-5">
          <div className="max-w-3xl mx-auto">
            {error && (
              <div className="mb-2 text-[12px] text-red-400/90 bg-red-500/[0.07] border border-red-500/20 rounded-lg px-3 py-2">
                {error}
              </div>
            )}

            {image && (
              <div className="mb-2 flex items-center gap-2.5 text-[12px] text-gray-400 bg-white/[0.04] border border-white/[0.08] rounded-lg px-3 py-2">
                <ImagePlus className="w-3.5 h-3.5" strokeWidth={1.75} />
                <span className="flex-1 truncate">{image.name}</span>
                <button onClick={() => setImage(null)} className="text-gray-600 hover:text-gray-300">
                  <X className="w-3.5 h-3.5" strokeWidth={1.75} />
                </button>
              </div>
            )}

            <form
              onSubmit={submit}
              className="flex items-end gap-2 bg-white/[0.04] border border-white/[0.09] rounded-xl px-3 py-2.5 focus-within:border-white/20 transition-colors"
            >
              <button
                type="button"
                onClick={() => fileRef.current?.click()}
                className="text-gray-600 hover:text-gray-300 transition-colors p-1"
                title="Attach a meal photo"
              >
                <ImagePlus className="w-4.5 h-4.5" strokeWidth={1.75} />
              </button>
              <input ref={fileRef} type="file" accept="image/*" className="hidden" onChange={pickImage} />

              <textarea
                rows={1}
                value={draft}
                onChange={(e) => setDraft(e.target.value)}
                onKeyDown={(e) => { if (e.key === 'Enter' && !e.shiftKey) submit(e); }}
                placeholder={image ? 'Press send to analyse the photo' : 'Message NutriAI'}
                disabled={!!image}
                className="flex-1 resize-none bg-transparent text-[14px] text-gray-200 placeholder:text-gray-600 focus:outline-none max-h-40 py-1 disabled:opacity-50"
              />

              <button
                type="submit"
                disabled={busy || (!draft.trim() && !image)}
                className="text-gray-500 hover:text-white disabled:opacity-25 disabled:cursor-not-allowed transition-colors p-1"
                aria-label="Send"
              >
                <Send className="w-4 h-4" strokeWidth={1.75} />
              </button>
            </form>

            <p className="mt-2 text-center text-[11px] text-gray-700">
              Nutrient values come from IFCT 2017 and USDA. Estimates are marked.
            </p>
          </div>
        </div>
      </section>
      )}
    </div>
  );
}

function Section({ label }) {
  return (
    <div className="px-5 pt-5 pb-2 text-[10px] uppercase tracking-[0.12em] text-gray-700">
      {label}
    </div>
  );
}

function Empty({ agent, Icon, onPick }) {
  const prompts = [
    'How much protein is in 150 g paneer?',
    'Compare toor dal and moong dal',
    'What should I eat for dinner tonight?',
  ];
  return (
    <div className="pt-20 flex flex-col items-center text-center">
      <div className="w-11 h-11 rounded-xl border border-white/10 flex items-center justify-center mb-4">
        <Icon className="w-5 h-5 text-gray-500" strokeWidth={1.5} />
      </div>
      <h2 className="text-[15px] font-medium text-gray-200 mb-1">
        {agent?.name || 'Assistant'}
      </h2>
      <p className="text-[13px] text-gray-600 mb-8 max-w-sm leading-relaxed">
        {agent?.description}
      </p>
      <div className="w-full max-w-md space-y-1.5">
        {prompts.map((p) => (
          <button
            key={p}
            onClick={() => onPick(p)}
            className="w-full text-left text-[13px] text-gray-500 hover:text-gray-300 border border-white/[0.07] hover:border-white/15 rounded-lg px-4 py-2.5 transition-colors"
          >
            {p}
          </button>
        ))}
      </div>
    </div>
  );
}

function Bubble({ message }) {
  const isUser = message.role === 'user';
  const facts = (message.facts || []).filter((f) => f.found !== false);
  const estimated = facts.some((f) => f.estimated);

  if (isUser) {
    return (
      <div className="flex justify-end">
        <div className="max-w-[85%] bg-white/[0.07] border border-white/[0.08] rounded-2xl rounded-br-md px-4 py-2.5">
          <p className="text-[14px] text-gray-200 whitespace-pre-wrap leading-relaxed">
            {message.content}
          </p>
        </div>
      </div>
    );
  }

  return (
    <div className="max-w-[92%]">
      <p className="text-[14px] text-gray-300 whitespace-pre-wrap leading-[1.75]">
        {message.content}
      </p>

      {facts.length > 0 && (
        <div className="mt-4 pt-3 border-t border-white/[0.06] space-y-1.5">
          <div className="text-[10px] uppercase tracking-[0.12em] text-gray-700">Sources</div>
          {facts.map((f, i) => (
            <div key={i} className="text-[12px] text-gray-600 flex items-center gap-2">
              <span className={`w-1 h-1 rounded-full ${f.estimated ? 'bg-amber-500' : 'bg-emerald-600'}`} />
              <span>{f.name || f.food}</span>
              <span className="text-gray-700">·</span>
              <span className="text-gray-700">{f.source}</span>
            </div>
          ))}
          {estimated && (
            <p className="text-[11px] text-amber-600/80 pt-1">
              Amber entries are model estimates, not measured composition data.
            </p>
          )}
        </div>
      )}
    </div>
  );
}


/**
 * A full-width view of one logged day.
 *
 * This replaces the conversation pane rather than expanding inside the 248px
 * sidebar -- meals, macros and a micronutrient panel are simply not legible
 * in a column that narrow.
 */
function DayView({ date, onClose, onToggleSidebar, sidebar }) {
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    setLoading(true);
    logCalendarDay(date)
      .then(setData)
      .catch(() => setData(null))
      .finally(() => setLoading(false));
  }, [date]);

  const pretty = new Date(date).toLocaleDateString(undefined, {
    weekday: 'long', day: 'numeric', month: 'long', year: 'numeric',
  });

  const MICROS = [
    ['iron_mg', 'Iron', 'mg'], ['calcium_mg', 'Calcium', 'mg'],
    ['zinc_mg', 'Zinc', 'mg'], ['vitamin_c_mg', 'Vitamin C', 'mg'],
    ['folate_ug', 'Folate', 'µg'], ['vitamin_a_ug', 'Vitamin A', 'µg'],
    ['potassium_mg', 'Potassium', 'mg'], ['magnesium_mg', 'Magnesium', 'mg'],
  ];

  return (
    <section className="flex-1 flex flex-col bg-[#0a0a0b] min-w-0">
      <header className="flex items-center gap-3 px-6 h-14 border-b border-white/[0.06] flex-shrink-0">
        <button onClick={onToggleSidebar} className="text-gray-600 hover:text-gray-300 transition-colors">
          {sidebar ? <PanelLeftClose className="w-4 h-4" strokeWidth={1.75} />
                   : <PanelLeft className="w-4 h-4" strokeWidth={1.75} />}
        </button>
        <CalendarDays className="w-4 h-4 text-gray-500" strokeWidth={1.75} />
        <div className="flex-1 min-w-0">
          <div className="text-[13px] font-medium text-gray-200 leading-tight">{pretty}</div>
          <div className="text-[11px] text-gray-600">Logged intake for this day</div>
        </div>
        <button onClick={onClose} className="text-gray-600 hover:text-gray-300 transition-colors" aria-label="Close">
          <X className="w-4 h-4" strokeWidth={1.75} />
        </button>
      </header>

      <div className="flex-1 overflow-y-auto">
        <div className="max-w-4xl mx-auto px-6 py-8">
          {loading && (
            <div className="flex items-center gap-2.5 text-[13px] text-gray-600">
              <Loader2 className="w-3.5 h-3.5 animate-spin" strokeWidth={1.75} /> Loading
            </div>
          )}

          {!loading && !data?.logged && (
            <div className="pt-20 text-center">
              <CalendarDays className="w-8 h-8 text-gray-700 mx-auto mb-3" strokeWidth={1.25} />
              <p className="text-[14px] text-gray-400 mb-1">Nothing logged on this day</p>
              <p className="text-[13px] text-gray-600">
                Close this and tell the assistant what you ate.
              </p>
            </div>
          )}

          {!loading && data?.logged && (
            <>
              <div className="grid grid-cols-2 sm:grid-cols-5 gap-3 mb-8">
                {[['calories', 'kcal'], ['protein_g', 'protein g'],
                  ['carbs_g', 'carbs g'], ['fat_g', 'fat g'],
                  ['fiber_g', 'fibre g']].map(([k, label]) => (
                  <div key={k} className="border border-white/[0.07] rounded-lg px-4 py-3">
                    <div className="text-[19px] text-gray-200 leading-none mb-1.5">
                      {Math.round(data.totals[k] || 0)}
                    </div>
                    <div className="text-[10px] uppercase tracking-[0.1em] text-gray-600">{label}</div>
                  </div>
                ))}
              </div>

              {Object.entries(data.by_slot || {}).map(([slot, bucket]) => (
                <div key={slot} className="mb-6">
                  <div className="flex items-baseline justify-between mb-2 pb-2 border-b border-white/[0.06]">
                    <h3 className="text-[13px] font-medium text-gray-300 capitalize">{slot}</h3>
                    <span className="text-[12px] text-gray-600">
                      {bucket.calories} kcal · {bucket.protein_g} g protein
                    </span>
                  </div>
                  <div className="space-y-1.5">
                    {(data.items || []).filter((i) => (i.slot || 'other') === slot).map((item, i) => (
                      <div key={i} className="flex items-baseline gap-3 text-[13px]">
                        <span className="text-gray-300 flex-1">{item.name}</span>
                        <span className="text-gray-600 tabular-nums">{Math.round(item.portion_g)} g</span>
                        <span className="text-gray-600 tabular-nums w-20 text-right">{item.calories} kcal</span>
                        <span className="text-gray-600 tabular-nums w-20 text-right">{item.protein_g} g P</span>
                        <span className={`text-[11px] w-32 truncate ${
                          item.source?.includes('estimate') ? 'text-amber-600/80' : 'text-gray-700'
                        }`}>{item.source}</span>
                      </div>
                    ))}
                  </div>
                </div>
              ))}

              {data.micronutrients && Object.keys(data.micronutrients).length > 0 && (
                <div className="mt-8 pt-6 border-t border-white/[0.06]">
                  <h3 className="text-[10px] uppercase tracking-[0.12em] text-gray-600 mb-3">
                    Micronutrients
                  </h3>
                  <div className="grid grid-cols-2 sm:grid-cols-4 gap-x-6 gap-y-2">
                    {MICROS.filter(([k]) => data.micronutrients[k] != null).map(([k, label, unit]) => (
                      <div key={k} className="flex items-baseline justify-between text-[13px] border-b border-white/[0.04] py-1">
                        <span className="text-gray-500">{label}</span>
                        <span className="text-gray-300 tabular-nums">
                          {Math.round(data.micronutrients[k] * 10) / 10} {unit}
                        </span>
                      </div>
                    ))}
                  </div>
                  <p className="mt-3 text-[11px] text-gray-700">
                    From IFCT 2017 (NIN, ICMR). Judge against ICMR-NIN RDA 2020 in Insights.
                  </p>
                </div>
              )}
            </>
          )}
        </div>
      </div>
    </section>
  );
}
