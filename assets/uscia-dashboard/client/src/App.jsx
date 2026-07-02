import React, { useState, useRef, useCallback, useEffect } from 'react';
import { v4 as uuidv4 } from 'uuid';
import SideNav from './components/SideNav.jsx';
import ReportView from './components/ReportView.jsx';
import './App.css';

const SESSION_ID = uuidv4();

/* ── Joule Diamond Icon (exact SAP Joule proportions) ───────────────────────── */
const JouleDiamond = ({ size = 34 }) => (
  <svg width={size} height={size} viewBox="0 0 40 40" fill="none">
    <circle cx="20" cy="20" r="20" fill="rgba(255,255,255,0.15)" />
    <polygon points="20,6 32,16 20,34 8,16" fill="rgba(255,255,255,0.2)" />
    <polygon points="20,6 32,16 20,22 8,16" fill="rgba(255,255,255,0.85)" />
    <polygon points="20,22 32,16 20,34" fill="rgba(255,255,255,0.45)" />
    <polygon points="20,22 8,16 20,34" fill="rgba(255,255,255,0.3)" />
    <polygon points="20,6 32,16 20,22 8,16" fill="white" />
  </svg>
);

/* ── Helpers ──────────────────────────────────────────────────────────────── */
function extractReport(rpcResult) {
  if (!rpcResult) return null;
  const result = rpcResult.result || rpcResult;
  if (result?.artifacts?.length) {
    const t = result.artifacts[0]?.parts?.map(p => p.text || p.data || '').join('\n');
    if (t) return t;
  }
  if (result?.status?.message?.parts?.length)
    return result.status.message.parts.map(p => p.text || '').join('\n');
  if (typeof result === 'string') return result;
  return null;
}

function getCtx(msgs) {
  const ctx = { material: null, plant: null };
  for (const m of msgs) {
    if (m.role === 'agent' && m.content && m.content !== 'USCIA_WELCOME') {
      const inv = m.content.match(/##\s+Investigation:\s+([^\s/]+)\s*\/\s*Plant\s+([^\s\n]+)/i);
      if (inv) { ctx.material = inv[1].trim(); ctx.plant = inv[2].trim(); }
    }
    if (m.role === 'user' && m.content) {
      const SKIP = new Set(['MD04','MRP','IBP','SAP','PIR','RRP','CIF','ATP','PPDS','PP','DS','ERP']);
      const mm = m.content.match(/\b([A-Z][A-Z0-9_-]{2,17})\b/);
      const pm = m.content.match(/\b(?:plant|location)\s+([0-9]{2,4})\b/i);
      if (mm && !SKIP.has(mm[1])) ctx.material = mm[1];
      if (pm) ctx.plant = pm[1];
    }
  }
  return ctx;
}

function enrich(query, ctx) {
  const q = query.trim();
  if (!ctx.material && !ctx.plant) return q;
  const justPlant = /^(?:plant\s+)?([0-9]{2,4})$/.test(q);
  if (justPlant && ctx.material) return `Why is the planned order for material ${ctx.material} plant ${q.replace(/^plant\s+/i,'').trim()} missing in MD04?`;
  const hasM = /\b([A-Z][A-Z0-9_-]{3,})\b/.test(q);
  const hasP = /\b(?:plant|location)\s+[0-9]{2,4}\b/i.test(q);
  const follow = /^(are|is|can|do|did|what|why|how|when|which|show|check|explain|tell|any|does|they|it|this)/i.test(q)
    || /\b(rrp3|ppds|cif|md04|mrp|ibp|bgrfc|smq1|slg1|mm02|mm03|order|queue|transfer|schedule|plan|config|issue)\b/i.test(q);
  if (follow && !hasM && !hasP && ctx.material && ctx.plant) return `Regarding material ${ctx.material} plant ${ctx.plant}: ${q}`;
  if (ctx.material && hasP && !hasM) return `Material ${ctx.material} ${q}`;
  if (ctx.plant && hasM && !hasP) return `${q} plant ${ctx.plant}`;
  return q;
}

function latestReport(msgs) {
  for (let i = msgs.length - 1; i >= 0; i--) {
    const m = msgs[i];
    if (m.role === 'agent' && m.content?.includes('## Investigation:')) return m;
  }
  return null;
}

function precedingQuery(msgs, id) {
  // Find the canonical investigation query for the report identified by `id`.
  //
  // Strategy:
  // 1. Read the LLM-generated canonical query embedded in the report markdown
  //    as <!-- USCIA_CANONICAL_QUERY: ... -->. The agent backend produces this
  //    using GPT-4o over the full conversation — no client-side keyword matching.
  // 2. If absent (older reports), fall back to the first user message in the
  //    current chain (walk back until previous agent report or conversation start).
  const idx = msgs.findIndex(m => m.id === id);
  if (idx < 0) return '';

  // 1) LLM-generated canonical query embedded in the report
  const report = msgs[idx]?.content || '';
  const canonical = report.match(/<!--\s*USCIA_CANONICAL_QUERY:\s*([^>]*?)\s*-->/);
  if (canonical && canonical[1]?.trim()) return canonical[1].trim();

  // 2) Fallback: first user message in the chain leading to this report
  const chainUsers = [];
  for (let i = idx - 1; i >= 0; i--) {
    const m = msgs[i];
    if (m.role === 'agent' && m.content?.includes('## Investigation:')) break;
    if (m.content === 'USCIA_WELCOME') break;
    if (m.role === 'user' && m.content) chainUsers.unshift(m.content);
  }
  return chainUsers[0] || '';
}

const fmt = d => d ? (d instanceof Date ? d : new Date(d)).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' }) : '';
// Parse approval gate content into structured fields
function parseApprovalGate(content) {
  if (!content) return null;
  const mat   = content.match(/\*\*Material:\*\*\s*`([^`]+)`/)?.[1] || content.match(/Material[:\s]+`?([A-Z0-9_-]+)`?/)?.[1] || '';
  const plant = content.match(/\*\*Plant:\*\*\s*`([^`]+)`/)?.[1]   || content.match(/Plant[:\s]+`?([0-9]+)`?/)?.[1] || '';
  const rc    = content.match(/\*\*Root Cause:\*\*\s*`([^`]+)`/)?.[1] || '';
  const conf  = content.match(/\[([A-Z]+)\s+confidence\]/)?.[1] || '';
  const action= content.match(/`(RESTART_BGRFC|REPROCESS_CPI_MESSAGE|RERUN_PPDS_HEURISTIC|RERUN_MRP_SINGLE_ITEM|RERUN_IBP_JOB|MANUAL_ONLY)`/)?.[1] || '';
  const desc  = content.match(/description=([^,\n]+)/)?.[1]?.trim() || '';
  return { mat, plant, rc, conf, action, desc };
}

const parseRC = c => {
  if (!c?.includes('## Investigation:')) return null;
  return c?.match(/##\s+Root Cause:\s*([^\n\[]+)/)?.[1]?.trim() || null;
};
const parseMat = c => {
  if (!c?.includes('## Investigation:')) return null;
  return c?.match(/##\s+Investigation:\s*([^\s/]+)/)?.[1]?.trim() || null;
};
const parsePlant = c => {
  if (!c?.includes('## Investigation:')) return null;
  return c?.match(/##\s+Investigation:.*\/\s*Plant\s+([^\s\n]+)/)?.[1]?.trim() || null;
};
const rcClass = rc => {
  if (!rc) return 'info';
  if (rc === 'Unable to Determine' || rc.includes('INDETERMINATE')) return 'warning';
  if (rc.includes('NOT_FOUND') || rc.includes('FAILURE') || rc.includes('ERROR')) return 'error';
  if (rc.includes('GAP') || rc.includes('MISMATCH') || rc.includes('BLOCKAGE')) return 'warning';
  return 'info';
};

/* ── App ─────────────────────────────────────────────────────────────────── */

// Derive first name — priority order:
// 1. SAP Launchpad UserInfo service (when running inside Joule/Fiori)
// 2. ?user= or ?name= URL query param
// 3. localStorage (remembered from previous session)
// 4. 'Consultant' fallback
function getFirstName() {
  try {
    const u = window.sap?.ushell?.Container?.getService?.('UserInfo');
    if (u) {
      const fn = u.getFirstName?.() || u.getFullName?.()?.split(' ')[0];
      if (fn && fn.trim()) return fn.trim();
    }
  } catch (_) {}
  const p = new URLSearchParams(window.location.search);
  const qp = p.get('user') || p.get('name');
  if (qp && qp.trim()) {
    localStorage.setItem('uscia_user_name', qp.trim());
    return qp.trim();
  }
  const stored = localStorage.getItem('uscia_user_name');
  if (stored && stored.trim()) return stored.trim();
  return 'Consultant';
}

const FIRST_NAME = getFirstName();

export default function App() {
  const [messages, setMessages]     = useState([{ id:'w', role:'agent', status:'done', timestamp:new Date(), content:'USCIA_WELCOME' }]);
  const [input, setInput]           = useState('');
  const [loading, setLoading]       = useState(false);
  const [navOpen, setNavOpen]       = useState(true);
  const [view, setView]             = useState('consultant');
  const [online, setOnline]         = useState(null);
  const [activeId, setActiveId]     = useState(null);
  const [pendingApproval, setPending] = useState(false);
  const [approvalUsed, setApprovalUsed] = useState(false);
  const [userName, setUserName]     = useState(FIRST_NAME);

  const handleSetName = (name) => {
    localStorage.setItem('uscia_user_name', name);
    setUserName(name);
  };

  const ctxRef   = useRef(SESSION_ID);
  const msgsRef  = useRef(messages);
  const inputRef = useRef(null);
  const endRef   = useRef(null);

  useEffect(() => { msgsRef.current = messages; }, [messages]);
  useEffect(() => { endRef.current?.scrollIntoView({ behavior:'smooth' }); }, [messages, loading]);
  useEffect(() => {
    fetch('/api/agent-card').then(r => r.ok ? r.json() : Promise.reject())
      .then(() => setOnline(true)).catch(() => setOnline(false));
  }, []);

  const addMsg = useCallback(m => setMessages(p => [...p, { id:uuidv4(), timestamp:new Date(), ...m }]), []);

  const updateAgent = useCallback(patch => {
    setMessages(p => {
      const c = [...p];
      for (let i = c.length-1; i >= 0; i--) {
        if (c[i].role === 'agent' && c[i].status === 'thinking') {
          c[i] = { ...c[i], ...patch };
          if (patch.content?.includes('## Investigation:')) setActiveId(c[i].id);
          break;
        }
      }
      return c;
    });
  }, []);

  const send = useCallback(async (text) => {
    const q = (text || input).trim();
    if (!q || loading) return;
    setInput('');
    setLoading(true);
    addMsg({ role:'user', content:q });
    addMsg({ role:'agent', content:null, status:'thinking' });
    const enriched = enrich(q, getCtx(msgsRef.current));
    try {
      const res = await fetch('/api/a2a', {
        method:'POST', headers:{'Content-Type':'application/json'},
        body: JSON.stringify({ message:enriched, contextId:ctxRef.current }),
        signal: AbortSignal.timeout(360000),
      });
      if (!res.ok) {
        const e = await res.json().catch(() => ({ error:`HTTP ${res.status}` }));
        updateAgent({ content:`⚠️ ${e.error || 'Error'}`, status:'error' });
        return;
      }
      const data = await res.json();
      ctxRef.current = data.contextId || ctxRef.current;
      const report = extractReport(data.result);
      const isApproval = report?.includes('Action Approval Required') ||
                         report?.includes('PENDING_APPROVAL') ||
                         report?.includes('Do you want to proceed');
      if (isApproval) setPending(true);
      updateAgent({ content: report || '⚠️ Empty response', status:'done', requiresApproval:isApproval });
    } catch (e) {
      const msg = e.name === 'TimeoutError'
        ? '⏱️ Investigation timed out (> 6 min). The agent may still be running — please retry.'
        : e.message === 'Failed to fetch'
          ? '⚠️ Connection lost. The dashboard lost contact with the agent. Please retry your message.'
          : `⚠️ ${e.message}`;
      updateAgent({ content: msg, status:'error' });
    } finally {
      setLoading(false);
      setTimeout(() => inputRef.current?.focus(), 80);
    }
  }, [input, loading, addMsg, updateAgent]);

  const clear = useCallback(() => {
    ctxRef.current = uuidv4();
    setMessages([{ id:'w', role:'agent', status:'done', timestamp:new Date(), content:'USCIA_WELCOME' }]);
    setActiveId(null);
    setPending(false);
    setApprovalUsed(false);
  }, []);

  const approve = useCallback(async (yes) => {
    if (!pendingApproval || approvalUsed) return;
    setApprovalUsed(true);
    setPending(false);
    await send(yes ? 'Yes, proceed' : 'No, skip');
  }, [send, pendingApproval, approvalUsed]);

  const latest = latestReport(messages);
  const active = activeId ? messages.find(m => m.id === activeId) : latest;
  const activeQ = active ? precedingQuery(messages, active?.id) : '';

  const sessions = messages.filter(m => m.role==='agent' && m.content?.includes('## Investigation:'))
    .map(m => ({ id:m.id, mat:parseMat(m.content), plant:parsePlant(m.content), rc:parseRC(m.content), time:fmt(m.timestamp) }));

  return (
    <div className="app-shell">

      {/* ── SAP Fiori Shell Bar — white, clean ── */}
      <header className="shell-bar">
        <img src="/logo.svg" alt="SAP" className="shell-logo" />
        <div className="shell-divider" />
        <span className="shell-app-name">USCIA</span>
        <span className="shell-app-sub">Supply Chain Intelligence</span>
        <div className="shell-spacer" />

        {/* View toggle — prominent with icons, like original */}
        <div className="view-toggle">
          <button className={`view-btn${view==='consultant' ? ' active' : ''}`} onClick={() => setView('consultant')}>
            <span className="view-btn-icon">🔍</span> Consultant View
          </button>
          <button className={`view-btn planner${view==='planner' ? ' active' : ''}`} onClick={() => setView('planner')}>
            <span className="view-btn-icon">👤</span> Planner View
          </button>
        </div>

        <button className="shell-icon-btn" onClick={() => setNavOpen(v => !v)}>
          {navOpen ? '◀ Hide' : '▶ Panel'}
        </button>
        <button className="shell-icon-btn" onClick={clear}>+ New</button>

        <div className="shell-divider" />
        <div className="agent-status">
          <span className={`status-dot${online===true?' online':online===false?' offline':' pending'}`} />
          {online===null ? 'Connecting…' : online ? 'Agent Online' : 'Offline'}
        </div>
      </header>

      <div className="app-body">

        {/* ── Left: original SideNav with collapsible incident types ── */}
        <div className={`side-nav${navOpen ? '' : ' collapsed'}`}>
          <div className="side-nav-scroll">
            {/* Session history */}
            {sessions.length > 0 && (
              <div className="session-section">
                <div className="session-header">
                  This Session
                  <span className="session-count">{sessions.length}</span>
                </div>
                {sessions.map(s => (
                  <div key={s.id} className={`session-item${activeId===s.id?' active':''}`} onClick={() => setActiveId(s.id)}>
                    <div className="session-mat">
                      {s.mat} / {s.plant}
                      <span className="session-mat-time">{s.time}</span>
                    </div>
                    <div className={`session-rc ${rcClass(s.rc)}`}>{s.rc?.replace(/_/g,' ')}</div>
                    {activeId===s.id && <div className="session-viewing">▸ Viewing</div>}
                  </div>
                ))}
              </div>
            )}

            {/* Incident types — use the original SideNav component */}
            <SideNav collapsed={false} onExampleClick={t => { setInput(t); setTimeout(() => inputRef.current?.focus(), 50); }} />
          </div>
        </div>

        {/* ── Center: forensic report ── */}
        <main className="main-content">
          <div className="main-scroll">
            {active && active.content && active.content !== 'USCIA_WELCOME'
              ? active.status === 'error'
                ? <div style={{padding:'2rem',color:'#BB0000'}}>{active.content}</div>
                : !active.content.includes('## Investigation:')
                  ? <WelcomeScreen userName={userName} onSetName={handleSetName} onPick={t => { setInput(t); setTimeout(() => inputRef.current?.focus(), 50); }} />
                  : <ReportView query={activeQ} content={active.content} timestamp={active.timestamp} view={view} />
              : <WelcomeScreen userName={userName} onSetName={handleSetName} onPick={t => { setInput(t); setTimeout(() => inputRef.current?.focus(), 50); }} />
            }
          </div>
          <div className="ai-footer">
            <span className="ai-spark">✦</span>
            Created with AI · USCIA Forensic Agent · Verify results before use.
          </div>
        </main>

        {/* ── Right: Joule panel ── */}
        <div className="joule-panel">

          {/* Purple gradient header */}
          <div className="joule-hdr">
            <JouleDiamond size={34} />
            <div className="joule-hdr-text">
              <div className="joule-hdr-name">USCIA</div>
              <div className="joule-hdr-sub">Supply Chain Forensic Intelligence</div>
            </div>
            <div className="joule-hdr-status">
              <span className="joule-hdr-dot" />
              {online ? 'Online' : online===null ? '…' : 'Offline'}
            </div>
          </div>

          {/* History */}
          <div className="joule-history">
            {messages.map(msg => {
              if (msg.content === 'USCIA_WELCOME') return (
                <div key={msg.id} className="msg-system">
                  Start an investigation using the input below
                </div>
              );

              if (msg.role === 'user') return (
                <div key={msg.id} className="msg-user">
                  <div className="msg-user-bubble">{msg.content}</div>
                  <div className="msg-time">{fmt(msg.timestamp)}</div>
                </div>
              );

              if (msg.role === 'agent') {
                if (msg.status === 'thinking') return (
                  <div key={msg.id} className="msg-thinking">
                    <div className="thinking-bubble">
                      <div className="thinking-dots"><span/><span/><span/></div>
                      <span className="thinking-label">Investigating…</span>
                    </div>
                  </div>
                );
                if (msg.status === 'error') return (
                  <div key={msg.id} className="msg-agent">
                    <div className="msg-agent-bubble" style={{color:'#BB0000'}}>{msg.content}</div>
                  </div>
                );
                const isRep = msg.content?.includes('## Investigation:');
                const isApprovalMsg = msg.content?.includes('Action Approval Required') ||
                                      msg.content?.includes('Do you want to proceed');

                // Approval gate message — render as clean action card in chat
                if (isApprovalMsg && !isRep) {
                  const ag = parseApprovalGate(msg.content);
                  return (
                    <div key={msg.id} className="msg-agent">
                      <div className="msg-approval-card">
                        <div className="approval-card-hdr">
                          <span className="uscia-badge">✦ USCIA</span>
                          <span className="approval-card-label">Action Approval Required</span>
                          <span className="msg-time" style={{marginLeft:'auto'}}>{fmt(msg.timestamp)}</span>
                        </div>
                        {ag?.mat && (
                          <div className="approval-card-meta">
                            <span><b>Material:</b> {ag.mat}</span>
                            <span><b>Plant:</b> {ag.plant}</span>
                            {ag.rc && <span><b>Root Cause:</b> <span className="rc-tag-inline">{ag.rc.replace(/_/g,' ')}</span></span>}
                            {ag.conf && <span className="conf-tag">{ag.conf}</span>}
                          </div>
                        )}
                        {ag?.action && ag.action !== 'MANUAL_ONLY' && (
                          <div className="approval-card-action">
                            <span className="action-type-tag">{ag.action}</span>
                            {ag.desc && <span className="action-desc">{ag.desc}</span>}
                          </div>
                        )}
                        <div className="approval-card-note">
                          IBP credentials are not yet configured — this action cannot be auto-dispatched until IBP is connected.
                          Approve to queue for manual execution, or reject to receive the report only.
                        </div>
                        <div className="approval-card-btns">
                          <button className="btn-approve" disabled={approvalUsed} onClick={() => approve(true)}>
                            {approvalUsed ? '✓ Submitted' : '✓ Approve & Proceed'}
                          </button>
                          <button className="btn-reject" disabled={approvalUsed} onClick={() => approve(false)}>
                            {approvalUsed ? '✗ Submitted' : '✗ Skip — Show Report Only'}
                          </button>
                        </div>
                      </div>
                    </div>
                  );
                }

                // Conversational / ASK message — show full text, no truncation
                if (!isRep) return (
                  <div key={msg.id} className="msg-agent">
                    <div className="msg-agent-bubble">{msg.content}</div>
                    <div className="msg-time">{fmt(msg.timestamp)}</div>
                  </div>
                );
                const rc = parseRC(msg.content);
                const mat = parseMat(msg.content);
                const plant = parsePlant(msg.content);
                return (
                  <div key={msg.id} className="msg-agent">
                    <div className={`msg-agent-bubble clickable${activeId===msg.id?' selected':''}`} onClick={() => setActiveId(msg.id)}>
                      <div className="report-card-hdr">
                        <span className="uscia-badge">✦ USCIA</span>
                        <span style={{fontSize:'0.62rem',color:'#9CA3AF'}}>{fmt(msg.timestamp)}</span>
                      </div>
                      <div className="report-card-mat">{mat} / {plant}</div>
                      {rc && <div className={`report-card-rc ${rcClass(rc)}`}>{rc.replace(/_/g,' ')}</div>}
                      <div className="report-card-cta">View full report →</div>
                    </div>
                  </div>
                );
              }
              return null;
            })}
            {loading && (
              <div className="msg-thinking">
                <div className="thinking-bubble">
                  <div className="thinking-dots"><span/><span/><span/></div>
                  <span className="thinking-label">Collecting evidence…</span>
                </div>
              </div>
            )}
            <div ref={endRef} />
          </div>

          {/* Input — exact Joule: rounded border, mic icon, send button */}
          <div className="joule-input-area">
            <div className="joule-input-wrap">
              <textarea
                ref={inputRef}
                className="joule-textarea"
                placeholder="Type or speak something…"
                value={input}
                onChange={e => setInput(e.target.value)}
                onKeyDown={e => { if (e.key==='Enter' && !e.shiftKey) { e.preventDefault(); send(); } }}
                rows={2}
                disabled={loading}
              />
              {/* Mic icon — shown when no input, matches Joule */}
              {!input.trim() && (
                <button className="joule-mic" title="Voice input (coming soon)" disabled>
                  <svg width="18" height="18" viewBox="0 0 24 24" fill="none">
                    <rect x="9" y="2" width="6" height="12" rx="3" fill="#6236FF"/>
                    <path d="M5 11a7 7 0 0 0 14 0" stroke="#6236FF" strokeWidth="2" strokeLinecap="round"/>
                    <line x1="12" y1="18" x2="12" y2="22" stroke="#6236FF" strokeWidth="2" strokeLinecap="round"/>
                    <line x1="8" y1="22" x2="16" y2="22" stroke="#6236FF" strokeWidth="2" strokeLinecap="round"/>
                  </svg>
                </button>
              )}
              {/* Send button — shown only when typing */}
              {input.trim() && (
                <button className="joule-send" onClick={() => send()} disabled={loading} title="Send">
                  <svg width="15" height="15" viewBox="0 0 15 15" fill="none">
                    <path d="M13 7.5L1.5 2L4 7.5L1.5 13L13 7.5Z" fill="white" strokeLinejoin="round"/>
                  </svg>
                </button>
              )}
            </div>
            <div className="joule-hint">Press Enter to send · Shift+Enter for new line</div>
          </div>
        </div>

      </div>
    </div>
  );
}

function WelcomeScreen({ onPick, userName, onSetName }) {
  const [editing, setEditing] = React.useState(false);
  const [nameInput, setNameInput] = React.useState('');
  const isDefault = !userName || userName === 'Consultant';
  const examples = [
    'Why is planned order for AUGUST21_S1 plant 0001 missing in MD04?',
    'Planned order not reaching PP/DS RRP3 for material X-5678 plant 2000',
    'PIR exists for M-9012 plant 1000 but no planned order created',
    'bgRFC queue blockage suspected — plant 0001 IBP orders not arriving',
  ];
  return (
    <div className="welcome">
      <div className="welcome-icon">
        <svg width="56" height="56" viewBox="0 0 56 56" fill="none">
          <defs>
            <linearGradient id="wg" x1="0" y1="0" x2="1" y2="1">
              <stop offset="0%" stopColor="#6236FF"/>
              <stop offset="100%" stopColor="#8B5CF6"/>
            </linearGradient>
          </defs>
          <circle cx="28" cy="28" r="28" fill="url(#wg)" opacity="0.12"/>
          <polygon points="28,10 40,22 28,46 16,22" fill="#E0D7FF"/>
          <polygon points="28,10 40,22 28,30 16,22" fill="#6236FF"/>
          <polygon points="28,30 40,22 28,46" fill="#8B5CF6" opacity="0.7"/>
          <polygon points="28,30 16,22 28,46" fill="#7C3AED" opacity="0.5"/>
        </svg>
      </div>

      {editing ? (
        <div className="welcome-name-edit">
          <input
            className="welcome-name-input"
            autoFocus
            placeholder="Enter your first name"
            value={nameInput}
            onChange={e => setNameInput(e.target.value)}
            onKeyDown={e => {
              if (e.key === 'Enter' && nameInput.trim()) {
                onSetName(nameInput.trim());
                setEditing(false);
              }
              if (e.key === 'Escape') setEditing(false);
            }}
          />
          <button className="welcome-name-btn" onClick={() => {
            if (nameInput.trim()) { onSetName(nameInput.trim()); setEditing(false); }
          }}>Set name</button>
        </div>
      ) : (
        <div className="welcome-title" title="Click to set your name" onClick={() => { if(isDefault){ setEditing(true); setNameInput(''); } }}>
          Good {getGreeting()}{isDefault
            ? <span className="welcome-name-prompt"> — <span style={{textDecoration:'underline',cursor:'pointer',fontSize:'0.9em',opacity:0.7}}>click to set your name</span></span>
            : `, ${userName}.`
          }
        </div>
      )}

      <div className="welcome-desc">
        I'm USCIA — your supply chain forensic agent. I investigate planning failures
        across SAP IBP → RTI/CIF → S/4HANA MRP → PP/DS → aATP in under 5 minutes.
        Describe the issue below or pick an example.
      </div>
      <div className="welcome-grid">
        {examples.map((ex, i) => (
          <div key={i} className="welcome-card" onClick={() => onPick(ex)}>
            <div className="welcome-card-tag">✦ Example {i+1}</div>
            <div className="welcome-card-text">{ex}</div>
          </div>
        ))}
      </div>
    </div>
  );
}

function getGreeting() {
  const h = new Date().getHours();
  if (h < 12) return 'morning';
  if (h < 17) return 'afternoon';
  return 'evening';
}
