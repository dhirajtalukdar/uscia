import React, { useState } from 'react';
import {
  Card, CardHeader,
  Tag,
  MessageStrip,
  Text,
  Button,
} from '@ui5/webcomponents-react';
import ReactMarkdown from 'react-markdown';
import remarkGfm from 'remark-gfm';
import LineageFlow from './LineageFlow.jsx';
import './ReportView.css';

/* ─── Parse the raw markdown report into a structured object ─── */
function parseReport(markdown) {
  if (!markdown) return null;

  const lines = markdown.split('\n');
  const meta = {};
  const sections = {};
  let current = null;

  for (const line of lines) {
    // Top-level meta lines: "## Investigation: X / Plant Y" etc.
    const invMatch = line.match(/^##\s+Investigation:\s+(.+?)\s*\/\s*Plant\s+(.+)$/i);
    if (invMatch) { meta.material = invMatch[1].trim(); meta.plant = invMatch[2].trim(); continue; }

    const incMatch = line.match(/^##\s+Incident Type:\s+(.+)$/i);
    if (incMatch) { meta.incidentType = incMatch[1].trim(); continue; }

    const rcMatch = line.match(/^##\s+Root Cause:\s+(.+?)\s+\[(.+?)\s+confidence\]/i);
    if (rcMatch) { meta.rootCause = rcMatch[1].trim(); meta.confidence = rcMatch[2].trim(); continue; }

    const idMatch = line.match(/^##\s+Incident ID:\s+(.+)$/i);
    if (idMatch) { meta.incidentId = idMatch[1].trim(); continue; }

    // Numbered section headers: "## 1. Executive Summary"
    const secMatch = line.match(/^##\s+(\d+)\.\s+(.+)$/);
    if (secMatch) {
      current = `s${secMatch[1]}`;
      sections[current] = { num: parseInt(secMatch[1]), title: secMatch[2].trim(), body: '' };
      continue;
    }

    // Machine-readable actions block
    const actMatch = line.match(/^##\s+Recommended Actions \(Machine-Readable\)/i);
    if (actMatch) { current = 'actions'; sections['actions'] = { num: 99, title: 'Recommended Actions (Machine-Readable)', body: '' }; continue; }

    if (current) sections[current].body += line + '\n';
  }

  return { meta, sections };
}

/* ─── Evidence system rows from section 3 or 6 body ─── */
function parseEvidenceSystems(body) {
  if (!body) return [];
  const rows = [];
  const lines = body.split('\n');
  for (const line of lines) {
    const confirmedMatch = line.match(/\[CONFIRMED\]\s+([A-Z0-9_]+):\s+(.+)/);
    if (confirmedMatch) {
      rows.push({ system: confirmedMatch[1], status: 'AVAILABLE', detail: confirmedMatch[2].trim() });
      continue;
    }
    const missingMatch = line.match(/\[MISSING DATA\]\s+([A-Z0-9_]+):\s+(.+)/);
    if (missingMatch) {
      rows.push({ system: missingMatch[1], status: 'MISSING_DATA', detail: missingMatch[2].slice(0, 120).trim() });
    }
  }
  return rows;
}

/* ─── Parse machine-readable actions ─── */
function parseActions(body) {
  if (!body) return [];
  const actions = [];
  const blocks = body.split(/(?=- action_type:)/);
  for (const block of blocks) {
    if (!block.trim()) continue;
    const typeMatch = block.match(/action_type:\s*(\w+)/);
    const rankMatch = block.match(/rank:\s*(\d+)/);
    const approvalMatch = block.match(/requires_approval:\s*(True|False)/i);
    const paramsMatch = block.match(/action_params:\s*(\{.+?\})/s);
    if (typeMatch) {
      let params = {};
      if (paramsMatch) {
        try { params = JSON.parse(paramsMatch[1].replace(/'/g, '"')); } catch { params = {}; }
      }
      actions.push({
        rank: rankMatch ? parseInt(rankMatch[1]) : 1,
        actionType: typeMatch[1],
        requiresApproval: approvalMatch ? approvalMatch[1] === 'True' : true,
        description: params.description || '',
        material: params.material || '',
        plant: params.plant || '',
        rootCause: params.root_cause || ''
      });
    }
  }
  return actions;
}

/* ─── Confidence badge design ─── */
function confidenceDesign(confidence) {
  if (!confidence) return '8';
  const c = confidence.toUpperCase();
  if (c === 'HIGH') return '8';       // green
  if (c === 'MEDIUM') return '6';     // yellow
  if (c === 'LOW') return '2';        // orange
  return '1';
}

function rootCauseDesign(rootCause) {
  if (!rootCause) return 'Information';
  const rc = rootCause.toUpperCase();
  if (rc.includes('ERROR') || rc.includes('FAILURE') || rc.includes('BLOCKAGE')) return 'Negative';
  if (rc.includes('GAP') || rc.includes('MISMATCH')) return 'Critical';
  if (rc === 'OTHER' || rc === 'INDETERMINATE') return 'Warning';
  return 'Negative';
}

function systemStatusBadge(status) {
  return status === 'AVAILABLE'
    ? <Tag colorScheme="8">✓ Available</Tag>
    : <Tag colorScheme="2">⚠ Missing</Tag>;
}

/* ─── Enhance tags in markdown ─── */
function enhanceTags(text) {
  if (!text) return '';
  return text
    .replace(/\[CONFIRMED\]/g, '**✅ [CONFIRMED]**')
    .replace(/\[PROBABLE\]/g, '**🟡 [PROBABLE]**')
    .replace(/\[MISSING DATA\]/g, '**⚠️ [MISSING DATA]**');
}

/* ─── Main ReportView component ─── */
export default function ReportView({ query, content, timestamp, view }) {
  const [expandedSections, setExpandedSections] = useState(new Set([1, 2, 3, 6, 8, 9]));

  const parsed = parseReport(content);

  // Fallback: if parseReport fails or returns empty meta (e.g. clarification question),
  // render as plain markdown — never show an empty context card with dashes
  if (!parsed || !parsed.meta?.material) {
    if (!content) return null;
    return (
      <div className="report-view">
        <Card className="full-report-card">
          <CardHeader titleText="Agent Response" avatar={<ui5-icon name="detail-view" />} />
          <div className="report-sections" style={{padding: '1rem'}}>
            <div className="report-markdown">
              <ReactMarkdown remarkPlugins={[remarkGfm]}>{content}</ReactMarkdown>
            </div>
          </div>
        </Card>
      </div>
    );
  }

  const { meta, sections } = parsed;

  const evidenceSystems = parseEvidenceSystems(
    sections['s6']?.body || sections['s3']?.body || ''
  );
  const actions = parseActions(sections['actions']?.body || '');

  const toggleSection = (num) => {
    setExpandedSections(prev => {
      const next = new Set(prev);
      next.has(num) ? next.delete(num) : next.add(num);
      return next;
    });
  };

  const formatTime = (d) => d ? (d instanceof Date ? d : new Date(d)).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' }) : '';

  // Sections to show in Planner view
  const plannerSections = [1, 2, 7, 8, 9, 12, 13, 14];

  const sectionsToRender = view === 'planner'
    ? Object.values(sections).filter(s => plannerSections.includes(s.num) && s.body.trim() && s.num !== 99)
    : Object.values(sections).filter(s => s.num !== 99 && s.body.trim());

  // ── PLANNER VIEW — clean executive card, no tables, no tech ──────────────
  if (view === 'planner') {
    const execSummary = sections['s1']?.body?.trim() || '';
    const businessImpact = sections['s12']?.body?.trim() || '';
    const recommendedActions = sections['s9']?.body?.trim() || '';
    const escalation = sections['s13']?.body?.trim() || '';
    const preventive = sections['s14']?.body?.trim() || '';

    const confidenceColor = { HIGH: '#107e3e', MEDIUM: '#e9730c', LOW: '#bb0000', MEDIUM_CONFIDENCE: '#e9730c' };
    const confColor = confidenceColor[meta.confidence?.toUpperCase()] || '#6a6d73';

    return (
      <div className="report-view report-view--planner">
        {/* Query */}
        <div className="planner-query-bar">
          <ui5-icon name="sys-find" style={{fontSize:'1rem',color:'#0070f2'}} />
          <span className="planner-query-text">"{query}"</span>
          <span className="planner-query-time">{formatTime(timestamp)}</span>
        </div>

        {/* Big status card */}
        <div className="planner-status-card">
          <div className="planner-status-left">
            <div className="planner-material-badge">
              <span className="planner-material">{meta.material || '—'}</span>
              <span className="planner-plant-sep">/</span>
              <span className="planner-plant">Plant {meta.plant || '—'}</span>
            </div>
            <div className="planner-incident">{meta.incidentType || '—'}</div>
          </div>
          <div className="planner-status-right">
            <div className="planner-root-cause-badge" style={{borderColor: confColor, background: confColor + '15'}}>
              <span className="planner-rc-label" style={{color: confColor}}>{meta.rootCause?.replace(/_/g,' ') || '—'}</span>
            </div>
            <div className="planner-confidence" style={{color: confColor}}>
              {meta.confidence || ''} confidence
            </div>
          </div>
        </div>

        {/* Lineage */}
        <Card className="lineage-card">
          <CardHeader titleText="Where did it break?" avatar={<ui5-icon name="chain-link" />} />
          <LineageFlow reportText={content} />
        </Card>

        {/* Action card — most prominent */}
        {actions.length > 0 && (
          <div className="planner-action-card">
            <div className="planner-action-header">
              <ui5-icon name="task" style={{fontSize:'1.25rem',color:'#0070f2'}} />
              <span>What to do next</span>
            </div>
            {actions.map((a, i) => (
              <div key={i} className="planner-action-item">
                <span className="planner-action-num">{a.rank}</span>
                <span className="planner-action-desc">{a.description || a.actionType?.replace(/_/g,' ')}</span>
              </div>
            ))}
          </div>
        )}

        {/* Summary sections */}
        {[
          { title: 'What happened', body: execSummary, icon: 'information' },
          { title: 'Business impact', body: businessImpact, icon: 'warning' },
          { title: 'Escalation path', body: escalation, icon: 'alert' },
          { title: 'How to prevent recurrence', body: preventive, icon: 'accept' },
        ].filter(s => s.body).map((s, i) => (
          <div key={i} className="planner-section-card">
            <div className="planner-section-title">
              <ui5-icon name={s.icon} style={{fontSize:'1rem'}} />
              <span>{s.title}</span>
            </div>
            <p className="planner-section-body">{s.body}</p>
          </div>
        ))}

        <div className="report-footer">
          <div className="report-footer-left">
            Report · USCIA
            {meta.incidentId && <span style={{opacity:0.6}}> · {meta.incidentId.slice(0,8)}…</span>}
            {timestamp && <span> · {formatTime(timestamp)}</span>}
          </div>
          <div className="report-footer-actions">
            <Button design="Transparent" icon="print" onClick={() => window.print()}>Export PDF</Button>
          </div>
        </div>
        {meta.incidentId && <OutcomeFeedback incidentId={meta.incidentId} actions={actions} />}
      </div>
    );
  }

  // ── CONSULTANT VIEW — full technical detail ───────────────────────────────
  return (
    <div className="report-view report-view--consultant">

      {/* ── Query card ── */}
      <Card className="query-card">
        <div className="query-card-inner">
          <ui5-icon name="sys-find" class="query-icon" />
          <div className="query-text-block">
            <Text className="query-label">Investigation Query</Text>
            <Text className="query-text">"{query}"</Text>
          </div>
          <span className="query-time">{formatTime(timestamp)}</span>
        </div>
      </Card>

      {/* ── Investigation context table ── */}
      <Card className="context-card">
        <CardHeader
          titleText="Investigation Context"
          subtitleText={`Incident ID: ${meta.incidentId || '—'}`}
          avatar={<ui5-icon name="detail-view" />}
          action={
            <div className="context-header-tags">
              <Tag colorScheme="1">USCIA</Tag>
              {view === 'planner' && <Tag colorScheme="6">Planner View</Tag>}
              {view === 'consultant' && <Tag colorScheme="2">Consultant View</Tag>}
            </div>
          }
        />
        <div className="context-table-wrapper">
          <table className="fiori-context-table">
            <tbody>
              <tr>
                <th>Material</th>
                <td><strong>{meta.material || '—'}</strong></td>
                <th>Plant</th>
                <td><strong>{meta.plant || '—'}</strong></td>
              </tr>
              <tr>
                <th>Incident Type</th>
                <td colSpan={3}>{meta.incidentType || '—'}</td>
              </tr>
              <tr>
                <th>Root Cause</th>
                <td>
                  <MessageStrip
                    design={rootCauseDesign(meta.rootCause)}
                    hideCloseButton
                    className="root-cause-strip"
                  >
                    {meta.rootCause || '—'}
                  </MessageStrip>
                </td>
                <th>Confidence</th>
                <td>
                  <Tag colorScheme={confidenceDesign(meta.confidence)}>
                    {meta.confidence || '—'}
                  </Tag>
                </td>
              </tr>
            </tbody>
          </table>
        </div>
      </Card>

      {/* ── Integration chain lineage flow ── */}
      <Card className="lineage-card">
        <CardHeader
          titleText="Integration Chain Status"
          subtitleText="IBP → RTI/CPI → bgRFC → S/4HANA MRP → CIF → PP/DS → aATP"
          avatar={<ui5-icon name="chain-link" />}
        />
        <LineageFlow reportText={content} />
      </Card>

      {/* ── Evidence system coverage table ── */}
      {evidenceSystems.length > 0 && (
        <Card className="evidence-table-card">
          <CardHeader
            titleText="System Evidence Coverage"
            subtitleText={`${evidenceSystems.filter(r => r.status === 'AVAILABLE').length} of ${evidenceSystems.length} systems returned live data`}
            avatar={<ui5-icon name="database" />}
          />
          <div className="evidence-table-wrapper">
            <table className="fiori-evidence-table">
              <thead>
                <tr>
                  <th>System</th>
                  <th>Status</th>
                  <th>Detail</th>
                </tr>
              </thead>
              <tbody>
                {evidenceSystems.map((row, i) => (
                  <tr key={i} className={row.status === 'AVAILABLE' ? 'row-available' : 'row-missing'}>
                    <td><code>{row.system}</code></td>
                    <td>{systemStatusBadge(row.status)}</td>
                    <td className="evidence-detail">{row.detail}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </Card>
      )}

      {/* ── Recommended actions table ── */}
      {actions.length > 0 && (
        <Card className="actions-table-card">
          <CardHeader
            titleText="Recommended Actions"
            subtitleText="Machine-readable — Phase 4 execution ready"
            avatar={<ui5-icon name="action" />}
          />
          <div className="actions-table-wrapper">
            <table className="fiori-actions-table">
              <thead>
                <tr>
                  <th>Rank</th>
                  <th>Action Type</th>
                  <th>Material</th>
                  <th>Plant</th>
                  <th>Description</th>
                  <th>Approval</th>
                </tr>
              </thead>
              <tbody>
                {actions.map((a, i) => (
                  <tr key={i}>
                    <td className="action-rank">{a.rank}</td>
                    <td><Tag colorScheme="5">{a.actionType}</Tag></td>
                    <td><code>{a.material || meta.material || '—'}</code></td>
                    <td><code>{a.plant || meta.plant || '—'}</code></td>
                    <td className="action-desc">{a.description || a.rootCause}</td>
                    <td>
                      <Tag colorScheme={a.requiresApproval ? '2' : '8'}>
                        {a.requiresApproval ? 'Required' : 'Auto'}
                      </Tag>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </Card>
      )}

      {/* ── 5-section merged report ── */}
      <Card className="full-report-card">
        <CardHeader
          titleText={view === 'planner' ? 'Investigation Summary' : 'Forensic Report'}
          subtitleText="Click sections to expand"
          avatar={<ui5-icon name="detail-view" />}
        />
        <div className="report-sections">
          <MergedSection
            num={1}
            title="Executive Summary"
            icon="information"
            defaultOpen={true}
            body={sections['s1']?.body}
            sections={[]}
          />
          <MergedSection
            num={2}
            title="Key Findings"
            icon="sys-find"
            defaultOpen={true}
            body={null}
            sections={[
              { label: 'Confirmed Findings', body: sections['s6']?.body },
              { label: 'Probable Causes',    body: sections['s7']?.body },
              { label: 'Missing Data Gaps',  body: sections['s8']?.body },
            ]}
          />
          <MergedSection
            num={3}
            title="Root Cause & Diagnostic Evidence"
            icon="alert"
            defaultOpen={false}
            body={null}
            sections={[
              { label: 'Issue Classification',   body: sections['s2']?.body },
              { label: 'Affected System Boundary', body: sections['s3']?.body },
              { label: 'Evidence Timeline',      body: sections['s4']?.body },
              { label: 'Evidence Graph Summary', body: sections['s5']?.body },
            ]}
          />
          <MergedSection
            num={4}
            title="Recommended Actions & Business Impact"
            icon="task"
            defaultOpen={true}
            body={null}
            sections={[
              { label: 'Recommended Actions',       body: sections['s9']?.body },
              { label: 'Business Impact',            body: sections['s12']?.body },
              { label: 'Escalation Path',            body: sections['s13']?.body },
              { label: 'Preventive Recommendation', body: sections['s14']?.body },
            ]}
          />
          <MergedSection
            num={5}
            title="Technical Reference"
            icon="developer-settings"
            defaultOpen={false}
            body={null}
            sections={[
              { label: 'SAP Objects to Check',      body: sections['s10']?.body },
              { label: 'Logs & Transactions',        body: sections['s11']?.body },
            ]}
          />
        </div>
      </Card>

      {/* ── Footer: export + outcome feedback ── */}
      <div className="report-footer">
        <div className="report-footer-left">
          <span>Report generated by USCIA</span>
          {meta.incidentId && <span> · Incident ID: {meta.incidentId}</span>}
          {timestamp && <span> · {formatTime(timestamp)}</span>}
        </div>
        <div className="report-footer-actions">
          <Button
            design="Transparent"
            icon="print"
            onClick={() => window.print()}
            tooltip="Print / Save as PDF"
          >
            Export PDF
          </Button>
        </div>
      </div>

      {/* ── Outcome feedback ── */}
      {meta.incidentId && (
        <OutcomeFeedback incidentId={meta.incidentId} actions={actions} />
      )}
    </div>
  );
}

/* ─── Outcome feedback widget ─── */
function OutcomeFeedback({ incidentId, actions }) {
  const [submitted, setSubmitted] = useState(false);
  const [selected, setSelected] = useState('');

  const OUTCOMES = ['Resolved', 'Partially Resolved', 'Not Resolved', 'Made Worse'];
  const COLORS = { 'Resolved': '8', 'Partially Resolved': '6', 'Not Resolved': '2', 'Made Worse': '3' };

  const actionId = actions.length > 0 ? actions[0].rank : '';

  if (submitted) {
    return (
      <div className="outcome-feedback outcome-feedback--done">
        <ui5-icon name="accept" style={{color: '#107e3e', fontSize: '1rem'}} />
        <span>Outcome recorded. Thank you — this improves future recommendations.</span>
      </div>
    );
  }

  return (
    <div className="outcome-feedback">
      <span className="outcome-label">Did the recommended action resolve the issue?</span>
      <div className="outcome-buttons">
        {OUTCOMES.map(o => (
          <Tag
            key={o}
            colorScheme={COLORS[o]}
            className={`outcome-tag${selected === o ? ' outcome-tag--selected' : ''}`}
            onClick={() => setSelected(o)}
            style={{ cursor: 'pointer' }}
          >
            {o}
          </Tag>
        ))}
      </div>
      {selected && (
        <Button
          design="Emphasized"
          icon="paper-plane"
          onClick={() => {
            // Copy outcome recording command to clipboard for easy pasting
            const cmd = `outcome incident_id=${incidentId} action_id=${actionId} outcome=${selected}`;
            navigator.clipboard?.writeText(cmd).catch(() => {});
            setSubmitted(true);
          }}
        >
          Submit Feedback
        </Button>
      )}
    </div>
  );
}

/* ─── MergedSection: collapsible panel with optional sub-sections ─── */
function MergedSection({ num, title, icon, defaultOpen, body, sections }) {
  const [open, setOpen] = React.useState(defaultOpen);
  const hasContent = body?.trim() || sections.some(s => s.body?.trim());
  if (!hasContent) return null;

  return (
    <div className="report-section">
      <div className={`report-section-header${open ? ' open' : ''}`} onClick={() => setOpen(v => !v)}>
        <span className="section-num">{num}</span>
        <span className="section-title">{title}</span>
        <ui5-icon name={open ? 'navigation-up-arrow' : 'navigation-down-arrow'} class="section-chevron" />
      </div>
      {open && (
        <div className="report-section-body">
          {/* Single body */}
          {body?.trim() && (
            <div className="report-markdown">
              <ReactMarkdown remarkPlugins={[remarkGfm]}>{enhanceTags(body)}</ReactMarkdown>
            </div>
          )}
          {/* Sub-sections */}
          {sections.filter(s => s.body?.trim()).map((s, i) => (
            <div key={i} className="merged-subsection">
              <div className="merged-subsection-title">{s.label}</div>
              <div className="report-markdown">
                <ReactMarkdown remarkPlugins={[remarkGfm]}>{enhanceTags(s.body)}</ReactMarkdown>
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
