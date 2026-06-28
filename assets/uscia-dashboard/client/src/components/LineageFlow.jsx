import React from 'react';
import { MessageStrip, Tag } from '@ui5/webcomponents-react';
import './LineageFlow.css';

/**
 * IBP -> RTI -> bgRFC -> S4HANA MRP -> CIF -> PP/DS -> aATP lineage flow.
 * Each hop gets a status based on which systems returned AVAILABLE vs MISSING_DATA.
 */

const HOPS = [
  { id: 'ibp',      label: 'IBP',            sub: 'Supply Planning',    system: 'IBP_SUPPLY',               requiresIBP: false, alwaysNA: false },
  { id: 'rti',      label: 'RTI/CPI',        sub: 'Message Routing',    system: 'SAP_CPI',                  requiresIBP: true,  alwaysNA: false },
  { id: 'bgrfc',    label: 'bgRFC',          sub: 'Queue Processing',   system: 'S4HANA_BGRFC_QUEUE',       requiresIBP: true,  alwaysNA: false },
  { id: 'mrp',      label: 'S/4HANA MRP',    sub: 'Planned Orders',     system: 'S4HANA_PLANNED_ORDER',     requiresIBP: false, alwaysNA: false },
  { id: 'matmaster',label: 'Material Master', sub: 'MRP Issues & Config',system: 'S4HANA_PPDS_CONFIG',      requiresIBP: false, alwaysNA: false },
  { id: 'cif',      label: 'CIF / SLG1',     sub: 'Transfer Logs',      system: 'S4HANA_APPLICATION_LOGS',  requiresIBP: false, alwaysNA: false },
  { id: 'ppds',     label: 'ePP/DS',         sub: 'Scheduling',         system: 'S4HANA_PPDS_STOCK',        requiresIBP: false, alwaysNA: false },
  { id: 'atp',      label: 'aATP',           sub: 'Phase 2',            system: 'S4HANA_ATP',               requiresIBP: false, alwaysNA: true  },
];

// Stubs are always grey — not a real gap
const STUB_SYSTEMS = new Set(['SAP_CPI', 'SAP_PIPO', 'CLOUD_ALM']);

function parseSystemStatuses(reportText) {
  if (!reportText) return {};
  const statuses = {};

  // Primary: three-state machine-readable HTML comments from report generator
  const hasDataComment  = reportText.match(/<!--\s*USCIA_SYSTEMS_HAS_DATA:\s*([^-\n]*?)\s*-->/);
  const noDataComment   = reportText.match(/<!--\s*USCIA_SYSTEMS_NO_DATA:\s*([^-\n]*?)\s*-->/);
  const missingComment  = reportText.match(/<!--\s*USCIA_SYSTEMS_MISSING:\s*([^-\n]*?)\s*-->/);

  if (hasDataComment) {
    hasDataComment[1].split(',').forEach(s => {
      const sys = s.trim(); if (sys) statuses[sys] = 'ok';
    });
  }
  if (noDataComment) {
    noDataComment[1].split(',').forEach(s => {
      const sys = s.trim(); if (sys) statuses[sys] = 'nodata';
    });
  }
  if (missingComment) {
    missingComment[1].split(',').forEach(s => {
      const sys = s.trim();
      if (sys) statuses[sys] = STUB_SYSTEMS.has(sys) ? 'stub' : 'missing';
    });
  }

  if (Object.keys(statuses).length > 0) return statuses;

  // Legacy fallback: old AVAILABLE comment
  const availComment = reportText.match(/<!--\s*USCIA_SYSTEMS_AVAILABLE:\s*([^-\n]*?)\s*-->/);
  if (availComment) {
    availComment[1].split(',').forEach(s => {
      const sys = s.trim(); if (sys) statuses[sys] = 'ok';
    });
  }
  if (missingComment) {
    missingComment[1].split(',').forEach(s => {
      const sys = s.trim();
      if (sys) statuses[sys] = STUB_SYSTEMS.has(sys) ? 'stub' : 'missing';
    });
  }

  return statuses;
}

function hopStatus(hop, statuses) {
  const { system } = hop;

  // aATP is always N/A — Phase 2 scope
  if (hop.alwaysNA) return 'na';

  if (STUB_SYSTEMS.has(system)) return 'stub';
  const s = statuses[system];

  // bgRFC and RTI/CPI are N/A when IBP is not connected (stub or missing)
  // PP/DS is independent of IBP — always show real status
  if (hop.requiresIBP) {
    const ibpStatus = statuses['IBP_SUPPLY'];
    if (!ibpStatus || ibpStatus === 'stub' || ibpStatus === 'missing') {
      return 'na';
    }
  }

  if (s === 'ok')       return 'ok';
  if (s === 'nodata')   return 'nodata';
  if (s === 'missing')  return 'error';
  if (s === 'available') return 'ok'; // legacy
  return 'unknown';
}

const STATUS_CONFIG = {
  ok:      { color: '#107e3e', bg: '#f1fdf6', border: '#107e3e', label: 'Data Retrieved' },
  nodata:  { color: '#bb0000', bg: '#fff0f0', border: '#bb0000', label: 'Reachable - No Records' },
  error:   { color: '#bb0000', bg: '#fff0f0', border: '#bb0000', label: 'No Data / Missing' },
  na:      { color: '#8c9baa', bg: '#f5f6f7', border: '#c0c5ca', label: 'N/A - Requires IBP' },
  stub:    { color: '#8c9baa', bg: '#f5f6f7', border: '#c0c5ca', label: 'Stub / Unconfigured' },
  unknown: { color: '#8c9baa', bg: '#f5f6f7', border: '#c0c5ca', label: 'Unknown' },
};

export default function LineageFlow({ reportText }) {
  if (!reportText) return null;
  const statuses = parseSystemStatuses(reportText);
  // Always show the lineage — grey hops for unknown systems

  return (
    <div className="lineage-flow-wrapper">
      <div className="lineage-flow-title">Integration Chain</div>
      <div className="lineage-flow">
        {HOPS.map((hop, i) => {
          const status = hopStatus(hop, statuses);
          const cfg = STATUS_CONFIG[status];
          return (
            <React.Fragment key={hop.id}>
              <div
                className={`lineage-hop lineage-hop--${status}`}
                style={{ borderColor: cfg.border, background: cfg.bg }}
                title={cfg.label}
              >
                <div className="hop-label" style={{ color: cfg.color }}>{hop.label}</div>
                <div className="hop-sub">{hop.sub}</div>
                <div className="hop-status-dot" style={{ background: cfg.color }} />
              </div>
              {i < HOPS.length - 1 && (
                <div className={`lineage-arrow lineage-arrow--${status}`}>
                  <svg width="28" height="16" viewBox="0 0 28 16">
                    <line x1="0" y1="8" x2="22" y2="8"
                      stroke={['error','nodata'].includes(status) ? '#bb0000' : status === 'ok' ? '#107e3e' : '#c0c5ca'}
                      strokeWidth="2" strokeDasharray={['stub','na','unknown'].includes(status) ? '4,3' : 'none'} />
                    <polygon points="22,4 28,8 22,12"
                      fill={['error','nodata'].includes(status) ? '#bb0000' : status === 'ok' ? '#107e3e' : '#c0c5ca'} />
                  </svg>
                </div>
              )}
            </React.Fragment>
          );
        })}
      </div>
      <div className="lineage-legend">
        <span className="legend-item"><span className="legend-dot" style={{background:'#107e3e'}} /> Data Retrieved</span>
        <span className="legend-item"><span className="legend-dot" style={{background:'#bb0000'}} /> No Records / Missing</span>
        <span className="legend-item"><span className="legend-dot" style={{background:'#c0c5ca'}} /> N/A or Stub</span>
      </div>
    </div>
  );
}
