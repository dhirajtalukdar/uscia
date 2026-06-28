import React from 'react';

/* Extract a short summary from a forensic report message */
function summariseReport(msg) {
  if (!msg.content || msg.content === 'USCIA_WELCOME') return null;

  const matMatch  = msg.content.match(/##\s+Investigation:\s+([^\s/]+)/i);
  const pltMatch  = msg.content.match(/##\s+Investigation:\s+[^\s/]+\s*\/\s*Plant\s+([^\s\n]+)/i);
  const rcMatch   = msg.content.match(/##\s+Root Cause:\s+([^\n\[]+)/i);
  const confMatch = msg.content.match(/##\s+Root Cause:.+\[([^\]]+)\s+confidence\]/i);
  const incMatch  = msg.content.match(/##\s+Incident Type:\s+([^\n]+)/i);

  if (!matMatch) return null;

  return {
    material:   matMatch[1].trim(),
    plant:      pltMatch ? pltMatch[1].trim() : '—',
    rootCause:  rcMatch  ? rcMatch[1].trim().replace(/_/g,' ') : 'Under investigation',
    confidence: confMatch ? confMatch[1].trim() : '',
    incident:   incMatch  ? incMatch[1].trim() : '',
  };
}

const CONF_COLOR = {
  HIGH:              '#107e3e',
  MEDIUM:            '#e9730c',
  MEDIUM_CONFIDENCE: '#e9730c',
  LOW:               '#bb0000',
};

export default function SessionHistory({ messages, activeReportId, onSelect }) {
  // Collect all completed agent reports in chronological order
  const reports = messages
    .filter(m => m.role === 'agent' && m.status === 'done' && m.content && m.content !== 'USCIA_WELCOME')
    .map(m => ({ id: m.id, timestamp: m.timestamp, summary: summariseReport(m) }))
    .filter(r => r.summary !== null)
    .reverse(); // most recent first

  if (reports.length === 0) return null;

  return (
    <div style={{
      borderBottom: '1px solid #d9dbdd',
      background: '#fafbfc',
      flexShrink: 0,
    }}>
      {/* Header */}
      <div style={{
        display: 'flex', alignItems: 'center', gap: '0.4rem',
        padding: '0.55rem 0.75rem',
        background: '#f0f4fa',
        borderBottom: '1px solid #e3e5e8',
        fontSize: '0.72rem', fontWeight: 700,
        color: '#6a6d70', textTransform: 'uppercase', letterSpacing: '0.05em',
      }}>
        <span style={{fontSize:'0.85rem'}}>🕐</span>
        <span>This Session ({reports.length})</span>
      </div>

      {/* Report cards — max 5 shown */}
      <div style={{ maxHeight: 220, overflowY: 'auto' }}>
        {reports.slice(0, 5).map(r => {
          const isActive = r.id === activeReportId;
          const confColor = CONF_COLOR[r.summary.confidence?.toUpperCase()] || '#6a6d73';
          const fmt = (d) => d ? (d instanceof Date ? d : new Date(d)).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' }) : '';

          return (
            <div
              key={r.id}
              onClick={() => onSelect(r.id)}
              style={{
                padding: '0.55rem 0.75rem',
                borderBottom: '1px solid #e3e5e8',
                cursor: 'pointer',
                background: isActive ? '#e8f2fd' : '#fafbfc',
                borderLeft: isActive ? '3px solid #0070f2' : '3px solid transparent',
                transition: 'background 0.12s',
              }}
              onMouseEnter={e => { if (!isActive) e.currentTarget.style.background = '#f0f4fa'; }}
              onMouseLeave={e => { if (!isActive) e.currentTarget.style.background = '#fafbfc'; }}
            >
              {/* Material / Plant + time */}
              <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '0.2rem' }}>
                <span style={{ fontWeight: 700, fontSize: '0.8rem', color: '#1d2d3e' }}>
                  {r.summary.material}
                  <span style={{ fontWeight: 400, color: '#6a6d73', marginLeft: '0.3rem', fontSize: '0.72rem' }}>
                    / {r.summary.plant}
                  </span>
                </span>
                <span style={{ fontSize: '0.65rem', color: '#9ea3a8' }}>{fmt(r.timestamp)}</span>
              </div>

              {/* Root cause */}
              <div style={{ fontSize: '0.73rem', color: confColor, fontWeight: 600, lineHeight: 1.3 }}>
                {r.summary.rootCause}
              </div>

              {/* Incident type — truncated */}
              {r.summary.incident && (
                <div style={{
                  fontSize: '0.68rem', color: '#9ea3a8', marginTop: '0.15rem',
                  overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap',
                }}>
                  {r.summary.incident}
                </div>
              )}

              {isActive && (
                <div style={{ fontSize: '0.65rem', color: '#0070f2', marginTop: '0.2rem', fontWeight: 600 }}>
                  ▸ Viewing
                </div>
              )}
            </div>
          );
        })}
      </div>
    </div>
  );
}
