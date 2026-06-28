import React, { useState, useRef, useCallback, useEffect } from 'react';
import { v4 as uuidv4 } from 'uuid';
import FioriShell from './components/FioriShell.jsx';
import SideNav from './components/SideNav.jsx';
import ReportView from './components/ReportView.jsx';
import SessionHistory from './components/SessionHistory.jsx';
import './App.css';

const SESSION_ID = uuidv4();

const WELCOME = {
  id: 'welcome',
  role: 'agent',
  status: 'done',
  timestamp: new Date(),
  content: 'USCIA_WELCOME',
};

function extractReport(rpcResult) {
  if (!rpcResult) return null;
  const result = rpcResult.result || rpcResult;
  if (result?.artifacts?.length) {
    const t = result.artifacts[0]?.parts?.map(p => p.text || p.data || '').join('\n');
    if (t) return t;
  }
  if (result?.status?.message?.parts?.length) {
    return result.status.message.parts.map(p => p.text || '').join('\n');
  }
  if (typeof result === 'string') return result;
  return null;
}

// Extract current investigation context from message history
function getInvestigationContext(msgs) {
  const ctx = { material: null, plant: null };
  for (const msg of msgs) {
    if (msg.role === 'agent' && msg.content && msg.content !== 'USCIA_WELCOME') {
      const inv = msg.content.match(/##\s+Investigation:\s+([^\s/]+)\s*\/\s*Plant\s+([^\s\n]+)/i);
      if (inv) { ctx.material = inv[1].trim(); ctx.plant = inv[2].trim(); }
    }
    if (msg.role === 'user' && msg.content) {
      const SKIP = new Set(['MD04','MRP','IBP','SAP','PIR','RRP','CIF','ATP','PPDS','PP','DS','ERP']);
      const matM = msg.content.match(/\b([A-Z][A-Z0-9_-]{2,17})\b/);
      const pltM = msg.content.match(/\b(?:plant|location)\s+([0-9]{2,4})\b/i);
      if (matM && !SKIP.has(matM[1])) ctx.material = matM[1];
      if (pltM) ctx.plant = pltM[1];
    }
  }
  return ctx;
}

function buildEnrichedQuery(query, prevCtx) {
  const q = query.trim();
  if (!prevCtx.material && !prevCtx.plant) return q;
  const justPlant = /^(?:plant\s+)?([0-9]{2,4})$/.test(q.trim());
  if (justPlant && prevCtx.material) {
    const plant = q.replace(/^plant\s+/i, '').trim();
    return `Why is the planned order for material ${prevCtx.material} plant ${plant} missing in MD04?`;
  }
  const hasExplicitMat = /\b([A-Z][A-Z0-9_-]{3,})\b/.test(q);
  const hasExplicitPlant = /\b(?:plant|location)\s+[0-9]{2,4}\b/i.test(q);
  const followUp = /^(are|is|can|do|did|what|why|how|when|which|show|check|explain|tell|any|does|they|it|this)/i.test(q)
    || /\b(rrp3|ppds|cif|md04|mrp|ibp|bgrfc|smq1|slg1|mm02|mm03|order|queue|transfer|schedule|plan|config|issue)\b/i.test(q);
  if (followUp && !hasExplicitMat && !hasExplicitPlant && prevCtx.material && prevCtx.plant) {
    return `Regarding material ${prevCtx.material} plant ${prevCtx.plant}: ${q}`;
  }
  if (prevCtx.material && hasExplicitPlant && !hasExplicitMat) return `Material ${prevCtx.material} ${q}`;
  if (prevCtx.plant && hasExplicitMat && !hasExplicitPlant) return `${q} plant ${prevCtx.plant}`;
  return q;
}

// Find the most recent complete investigation report
function getLatestReport(msgs) {
  for (let i = msgs.length - 1; i >= 0; i--) {
    const m = msgs[i];
    if (m.role === 'agent' && m.content && m.content !== 'USCIA_WELCOME'
        && m.content.includes('## Investigation:')) {
      return m;
    }
  }
  return null;
}

// Find user message that preceded an agent message
function getPrecedingUserQuery(msgs, agentMsgId) {
  const idx = msgs.findIndex(m => m.id === agentMsgId);
  if (idx < 0) return '';
  for (let i = idx - 1; i >= 0; i--) {
    if (msgs[i].role === 'user') return msgs[i].content || '';
  }
  return '';
}

export default function App() {
  const [messages, setMessages]       = useState([WELCOME]);
  const [input, setInput]             = useState('');
  const [loading, setLoading]         = useState(false);
  const [sidebarCollapsed, setSidebarCollapsed] = useState(false);
  const [view, setView]               = useState('consultant');
  const [agentOnline, setAgentOnline] = useState(null);
  const [activeReportId, setActiveReportId] = useState(null);
  const [pendingApproval, setPendingApproval] = useState(false);

  const contextIdRef = useRef(SESSION_ID);
  const messagesRef  = useRef(messages);
  const inputRef     = useRef(null);
  const historyEndRef = useRef(null);

  useEffect(() => { messagesRef.current = messages; }, [messages]);
  useEffect(() => {
    historyEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [messages, loading]);

  useEffect(() => {
    fetch('/api/agent-card')
      .then(r => r.ok ? r.json() : Promise.reject())
      .then(() => setAgentOnline(true))
      .catch(() => setAgentOnline(false));
  }, []);

  const addMessage = useCallback((msg) => {
    setMessages(prev => [...prev, { id: uuidv4(), timestamp: new Date(), ...msg }]);
  }, []);

  const updateLastAgent = useCallback((patch) => {
    setMessages(prev => {
      const copy = [...prev];
      for (let i = copy.length - 1; i >= 0; i--) {
        if (copy[i].role === 'agent' && copy[i].status === 'thinking') {
          copy[i] = { ...copy[i], ...patch };
          if (patch.content && patch.content.includes('## Investigation:')) {
            setActiveReportId(copy[i].id);
          }
          break;
        }
      }
      return copy;
    });
  }, []);

  const sendMessage = useCallback(async (text) => {
    const query = (text || input).trim();
    if (!query || loading) return;
    setInput('');
    setLoading(true);

    addMessage({ role: 'user', content: query });
    addMessage({ role: 'agent', content: null, status: 'thinking' });

    const prevCtx = getInvestigationContext(messagesRef.current);
    const enrichedQuery = buildEnrichedQuery(query, prevCtx);

    try {
      const res = await fetch('/api/a2a', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ message: enrichedQuery, contextId: contextIdRef.current }),
        signal: AbortSignal.timeout(360000),
      });
      if (!res.ok) {
        const err = await res.json().catch(() => ({ error: `HTTP ${res.status}` }));
        updateLastAgent({ content: `⚠️ ${err.error || 'Agent error'}`, status: 'error' });
        return;
      }
      const data = await res.json();
      contextIdRef.current = data.contextId || contextIdRef.current;
      const report = extractReport(data.result);
      const isApproval = report && report.includes('PENDING_APPROVAL');
      if (isApproval) setPendingApproval(true);
      updateLastAgent({ content: report || '⚠️ Empty response', status: 'done', incidentId: data.taskId, requiresApproval: isApproval });
    } catch (err) {
      updateLastAgent({
        content: err.name === 'TimeoutError' ? '⏱️ Investigation timed out.' : `⚠️ ${err.message}`,
        status: 'error',
      });
    } finally {
      setLoading(false);
      setTimeout(() => inputRef.current?.focus(), 100);
    }
  }, [input, loading, addMessage, updateLastAgent]);

  const handleKeyDown = (e) => {
    if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); sendMessage(); }
  };

  const handleClear = useCallback(() => {
    contextIdRef.current = uuidv4();
    setMessages([WELCOME]);
    setActiveReportId(null);
    setPendingApproval(false);
  }, []);

  // Send approval/rejection follow-up
  const handleApproval = useCallback(async (approve) => {
    setPendingApproval(false);
    const word = approve ? 'approve' : 'reject';
    await sendMessage(word);
  }, [sendMessage]);

  // Determine what to show in main content area
  const latestReport = getLatestReport(messages);
  const activeReport = activeReportId
    ? messages.find(m => m.id === activeReportId)
    : latestReport;
  const activeQuery = activeReport ? getPrecedingUserQuery(messages, activeReport?.id) : '';

  // Format timestamp
  const fmt = (d) => d ? (d instanceof Date ? d : new Date(d)).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' }) : '';

  return (
    <div className="fiori-app-shell">
      <FioriShell
        agentOnline={agentOnline}
        view={view}
        onViewChange={setView}
        onClear={handleClear}
        sidebarCollapsed={sidebarCollapsed}
        onToggleSidebar={() => setSidebarCollapsed(v => !v)}
      />

      <div className="fiori-app-body">
        {/* Left: Session History + Incident Navigator */}
        <div className={`fiori-side-nav-wrapper${sidebarCollapsed ? ' collapsed' : ''}`}>
          {!sidebarCollapsed && (
            <SessionHistory
              messages={messages}
              activeReportId={activeReportId}
              onSelect={(id) => setActiveReportId(id)}
            />
          )}
          <SideNav collapsed={sidebarCollapsed} onExampleClick={(t) => setInput(t)} />
        </div>

        {/* Center: Forensic Report Content */}
        <main className="fiori-main-content">
          <div className="main-scroll-area">
            {activeReport && activeReport.content && activeReport.content !== 'USCIA_WELCOME' ? (
              activeReport.status === 'error' ? (
                <div style={{padding:'2rem',color:'#bb0000'}}>{activeReport.content}</div>
              ) : (
                <ReportView
                  query={activeQuery}
                  content={activeReport.content}
                  timestamp={activeReport.timestamp}
                  view={view}
                />
              )
            ) : (
              <WelcomeScreen onExample={(t) => { setInput(t); setTimeout(() => inputRef.current?.focus(), 100); }} />
            )}
          </div>
          <div className="ai-verify-banner">
            <ui5-icon name="ai" style={{fontSize:'0.8rem',color:'#0070f2'}} />
            Created with AI. Verify results before use.
          </div>
        </main>

        {/* Right: Joule-style chat panel */}
        <div className="joule-panel">
          <div className="joule-panel-header">
            <div className="joule-icon" style={{
              background: 'linear-gradient(135deg, #0070f2 0%, #00b0f0 60%, #6644cc 100%)',
              borderRadius: 8, width: 26, height: 26, display: 'flex', alignItems: 'center',
              justifyContent: 'center', fontWeight: 800, fontSize: '0.78rem', letterSpacing: '-0.5px',
              boxShadow: '0 0 10px rgba(0,112,242,0.5)'
            }}>✦</div>
            <span style={{fontWeight: 600, letterSpacing: '0.02em'}}>USCIA</span>
            <span style={{marginLeft: 4, fontSize: '0.68rem', opacity: 0.55, fontWeight: 400}}>Supply Chain AI</span>
            <span style={{marginLeft:'auto', fontSize:'0.68rem', display:'flex', alignItems:'center', gap:'0.3rem'}}>
              {agentOnline === true && <>
                <span style={{width:6,height:6,borderRadius:'50%',background:'#2ecc71',boxShadow:'0 0 5px #2ecc71',display:'inline-block'}} />
                <span style={{opacity:0.8}}>Online</span>
              </>}
              {agentOnline === false && <>
                <span style={{width:6,height:6,borderRadius:'50%',background:'#e74c3c',display:'inline-block'}} />
                <span style={{opacity:0.8}}>Offline</span>
              </>}
              {agentOnline === null && <span style={{opacity:0.5}}>Connecting…</span>}
            </span>
          </div>

          <div className="joule-panel-history">
            {messages.map((msg) => {
              if (msg.content === 'USCIA_WELCOME') {
                return (
                  <div key={msg.id} className="joule-bubble-system">
                    USCIA ready. Describe a supply chain incident or pick one from the left panel.
                  </div>
                );
              }
              if (msg.role === 'user') {
                return (
                  <div key={msg.id}>
                    <div className="joule-bubble-user">{msg.content}</div>
                    <div className="joule-bubble-time" style={{color:'rgba(255,255,255,0.5)',textAlign:'right'}}>{fmt(msg.timestamp)}</div>
                  </div>
                );
              }
              if (msg.role === 'agent') {
                if (msg.status === 'thinking') {
                  return (
                    <div key={msg.id} className="joule-bubble-agent joule-thinking">
                      <span>Investigating</span>
                      <span className="joule-thinking-dots">
                        <span/><span/><span/>
                      </span>
                    </div>
                  );
                }
                if (msg.status === 'error') {
                  return <div key={msg.id} className="joule-bubble-agent" style={{color:'#bb0000'}}>{msg.content}</div>;
                }
                // For completed reports — show summary bubble, clickable to view in main
                const isReport = msg.content?.includes('## Investigation:');
                const rootCause = msg.content?.match(/Root Cause:\s*([^\n\[]+)/i)?.[1]?.trim();
                const material = msg.content?.match(/Investigation:\s*([^\s/]+)/i)?.[1]?.trim();
                return (
                  <div key={msg.id}
                    className="joule-bubble-agent"
                    style={{cursor: isReport ? 'pointer' : 'default',
                            border: activeReportId === msg.id ? '2px solid #0070f2' : '2px solid transparent',
                            borderRadius: '4px 12px 12px 12px'}}
                    onClick={() => isReport && setActiveReportId(msg.id)}
                  >
                    {isReport ? (
                      <div>
                        <div style={{display:'flex',alignItems:'center',gap:'0.4rem',marginBottom:'0.3rem'}}>
                          <span className="ai-badge">✦ USCIA</span>
                          <span style={{fontSize:'0.72rem',color:'#6a6d73'}}>{fmt(msg.timestamp)}</span>
                        </div>
                        <div style={{fontWeight:600,fontSize:'0.82rem',marginBottom:'0.2rem'}}>
                          Forensic Report: {material}
                        </div>
                        {rootCause && (
                          <div style={{fontSize:'0.75rem',color:'#bb0000',fontWeight:500}}>
                            Root Cause: {rootCause}
                          </div>
                        )}
                        <div style={{fontSize:'0.7rem',color:'#0070f2',marginTop:'0.3rem'}}>
                          Click to view full report →
                        </div>
                      </div>
                    ) : (
                      <div>
                        <div style={{marginBottom:'0.2rem'}}>{msg.content?.slice(0, 200)}{msg.content?.length > 200 ? '…' : ''}</div>
                        <div style={{fontSize:'0.65rem',color:'#9ea3a8'}}>{fmt(msg.timestamp)}</div>
                      </div>
                    )}
                  </div>
                );
              }
              return null;
            })}
            {loading && (
              <div className="joule-bubble-agent joule-thinking">
                <span>Collecting evidence</span>
                <span className="joule-thinking-dots"><span/><span/><span/></span>
              </div>
            )}
            <div ref={historyEndRef} />
          </div>

          {/* ── Approval gate card ── */}
          {pendingApproval && (
            <div style={{
              margin: '0 0.75rem 0.5rem',
              background: 'linear-gradient(135deg, #fff8e1, #fffde7)',
              border: '1.5px solid #f59e0b',
              borderRadius: 10,
              padding: '0.85rem 1rem',
              flexShrink: 0,
            }}>
              <div style={{display:'flex',alignItems:'center',gap:'0.4rem',marginBottom:'0.5rem'}}>
                <span style={{fontSize:'1.1rem'}}>⚠️</span>
                <span style={{fontWeight:700,fontSize:'0.82rem',color:'#92400e'}}>Action Requires Approval</span>
              </div>
              <p style={{fontSize:'0.75rem',color:'#78350f',margin:'0 0 0.75rem',lineHeight:1.5}}>
                USCIA has identified an executable action. Review the recommended actions in the report, then approve or reject execution.
              </p>
              <div style={{display:'flex',gap:'0.5rem'}}>
                <button
                  onClick={() => handleApproval(true)}
                  style={{
                    flex:1, padding:'0.5rem', borderRadius:6,
                    background:'#107e3e', color:'#fff', border:'none',
                    fontWeight:600, fontSize:'0.78rem', cursor:'pointer',
                    display:'flex',alignItems:'center',justifyContent:'center',gap:'0.3rem',
                  }}
                >
                  ✓ Approve
                </button>
                <button
                  onClick={() => handleApproval(false)}
                  style={{
                    flex:1, padding:'0.5rem', borderRadius:6,
                    background:'#bb0000', color:'#fff', border:'none',
                    fontWeight:600, fontSize:'0.78rem', cursor:'pointer',
                    display:'flex',alignItems:'center',justifyContent:'center',gap:'0.3rem',
                  }}
                >
                  ✕ Reject
                </button>
              </div>
            </div>
          )}

          <div className="joule-panel-input">
            <div className="joule-input-row">
              <textarea
                ref={inputRef}
                className="joule-textarea"
                placeholder="Describe your supply chain incident…"
                value={input}
                onChange={e => setInput(e.target.value)}
                onKeyDown={handleKeyDown}
                rows={2}
                disabled={loading}
              />
              <button
                className="joule-send-btn"
                onClick={() => sendMessage()}
                disabled={loading || !input.trim()}
                title="Send (Enter)"
              >
                <ui5-icon name="paper-plane" style={{fontSize:'0.9rem'}} />
              </button>
            </div>
            <div className="joule-disclaimer">
              Press Enter to send · Shift+Enter for new line
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}

// Welcome screen shown when no report is active
function WelcomeScreen({ onExample }) {
  const examples = [
    'Why is planned order for material AUGUST21_S1 plant 0001 missing in MD04?',
    'Planned order not reaching PP/DS RRP3 for material X-5678 plant 2000',
    'PIR exists in MD61 for material M-9012 plant 1000 but no planned order created',
    'bgRFC queue blockage suspected for plant 0001 — IBP orders not arriving',
  ];
  return (
    <div style={{padding:'2rem',maxWidth:'700px',margin:'0 auto'}}>
      <div style={{textAlign:'center',marginBottom:'2rem'}}>
        <div style={{width:56,height:56,background:'linear-gradient(135deg,#0070f2,#00b0f0)',borderRadius:14,
          display:'flex',alignItems:'center',justifyContent:'center',
          fontSize:'1.5rem',color:'#fff',fontWeight:700,margin:'0 auto 1rem'}}>
          ✦
        </div>
        <h2 style={{color:'#1d2d3e',fontWeight:700,marginBottom:'0.5rem',fontSize:'1.3rem'}}>
          USCIA — Supply Chain Intelligence
        </h2>
        <p style={{color:'#6a6d73',fontSize:'0.88rem',maxWidth:'480px',margin:'0 auto'}}>
          Diagnoses cross-system SAP planning failures across IBP → S/4HANA MRP → PP/DS
          in under 5 minutes. Type your incident in the panel on the right or select an example below.
        </p>
      </div>
      <div style={{display:'grid',gridTemplateColumns:'1fr 1fr',gap:'0.75rem'}}>
        {examples.map((ex, i) => (
          <div key={i}
            onClick={() => onExample(ex)}
            style={{background:'#fff',border:'1px solid #d9dbdd',borderRadius:8,padding:'0.85rem 1rem',
              cursor:'pointer',fontSize:'0.8rem',color:'#1d2d3e',lineHeight:1.5,
              transition:'border-color 0.15s,box-shadow 0.15s'}}
            onMouseEnter={e => { e.currentTarget.style.borderColor='#0070f2'; e.currentTarget.style.boxShadow='0 2px 8px rgba(0,112,242,0.1)'; }}
            onMouseLeave={e => { e.currentTarget.style.borderColor='#d9dbdd'; e.currentTarget.style.boxShadow='none'; }}
          >
            <span className="ai-badge" style={{marginBottom:'0.4rem',display:'inline-flex'}}>Example</span>
            <div style={{marginTop:'0.3rem'}}>{ex}</div>
          </div>
        ))}
      </div>
    </div>
  );
}
