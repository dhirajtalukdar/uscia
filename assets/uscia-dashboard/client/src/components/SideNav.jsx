import React, { useState } from 'react';
import {
  Panel,
  Text,
  Button,
  Tag
} from '@ui5/webcomponents-react';
import './SideNav.css';

const INCIDENT_TYPES = [
  {
    id: 1,
    icon: 'product',
    label: 'Planned order missing in MD04',
    description: 'IBP planning ran but order not visible in S/4HANA MD04',
    example: 'Why is the planned order for material M-1234 plant 1000 missing in MD04 after the IBP planning run on 2024-06-01?'
  },
  {
    id: 2,
    icon: 'process',
    label: 'Not reaching PP/DS RRP3',
    description: 'Order exists in MD04 but not transferred to PP/DS scheduling',
    example: 'Planned order for material P-5678 plant 2000 is in MD04 but not appearing in PP/DS RRP3. Please investigate the CIF transfer.'
  },
  {
    id: 3,
    icon: 'warning',
    label: 'Quantity / date inconsistency',
    description: 'IBP and S/4HANA show different order quantities or dates',
    example: 'The planned order quantity for material M-9012 plant 3000 in IBP is 500 EA but S/4HANA MD04 shows only 200 EA. Investigate the discrepancy.'
  },
  {
    id: 4,
    icon: 'task',
    label: 'PIR exists but no planned order',
    description: 'Planned Independent Requirement created but MRP produced no planned order',
    example: 'A PIR was created for material M-3456 plant 1000 for Q1 2024 but MRP did not generate any planned orders. Please diagnose.'
  },
  {
    id: 5,
    icon: 'factory',
    label: 'PP/DS scheduling failure',
    description: 'Order received by PP/DS but not scheduled due to capacity or master data',
    example: 'PP/DS received the planned order for material P-7890 plant 2000 but it is unscheduled. Investigate capacity constraints and master data.'
  },
  {
    id: 6,
    icon: 'accept',
    label: 'aATP confirmation missing',
    description: 'Advanced ATP check returned no confirmation or incorrect result',
    example: 'The aATP check for material M-1111 plant 1000 is returning no confirmation despite available stock. Please investigate the ATP scope.'
  },
  {
    id: 7,
    icon: 'chain-link',
    label: 'CIF transfer failure',
    description: 'Planned order exists in MD04 but not transferred to PP/DS via CIF',
    example: 'Planned order 1000045678 for material M-2222 plant 3000 is confirmed in MD04 but missing in PP/DS after CIF transfer. Diagnose the CIF issue.'
  },
  {
    id: 8,
    icon: 'calendar',
    label: 'IBP planning job failure',
    description: 'IBP planning job ran but produced no supply output for material-location',
    example: 'The IBP planning job for material M-3333 location 1000 on 2024-06-01 ran without errors but generated no planned orders. Investigate the IBP planning gap.'
  },
  {
    id: 9,
    icon: 'alert',
    label: 'RTI/CPI message failure',
    description: 'IBP output not transferred to S/4HANA via integration middleware',
    example: 'IBP generated planned orders for material M-4444 plant 2000 but they have not appeared in S/4HANA. Suspect RTI/CPI message routing failure.'
  },
  {
    id: 10,
    icon: 'pending',
    label: 'bgRFC queue blockage',
    description: 'Message received by S/4HANA but stuck in bgRFC queue, not processed',
    example: 'S/4HANA received the IBP transfer message for material M-5555 plant 3000 but the planned order was not created. Suspect bgRFC queue blockage — please investigate.'
  }
];

const QUICK_TIPS = [
  'Include material number + plant for best results',
  'Add a date range to narrow the investigation',
  'Provide a planned order number if you have one',
  'Use JSON input for precise context'
];

export default function SideNav({ collapsed, onExampleClick }) {
  const [selectedIncident, setSelectedIncident] = useState(null);
  const [tipsOpen, setTipsOpen] = useState(false);

  if (collapsed) {
    return (
      <div className="side-nav-collapsed">
        {INCIDENT_TYPES.map(item => (
          <div
            key={item.id}
            className="collapsed-item"
            title={`#${item.id} ${item.label}`}
            onClick={() => onExampleClick(item.example)}
          >
            <span className="collapsed-num">{item.id}</span>
          </div>
        ))}
      </div>
    );
  }

  return (
    <div className="side-nav-full">
      {/* Incident list header */}
      <div className="side-nav-header">
        <ui5-icon name="search" class="side-nav-header-icon" />
        <span className="side-nav-header-label">10 Incident Types</span>
        <Tag colorScheme="8" style={{ marginLeft: 'auto' }}>A2A</Tag>
      </div>

      {/* Incident items */}
      <div className="incident-list-scroll">
        {INCIDENT_TYPES.map(item => (
          <div
            key={item.id}
            className={`incident-nav-item${selectedIncident === item.id ? ' selected' : ''}`}
          >
            <div
              className="incident-nav-item-header"
              onClick={() => setSelectedIncident(selectedIncident === item.id ? null : item.id)}
            >
              <span className="incident-nav-num">{item.id}</span>
              <ui5-icon name={item.icon} class="incident-nav-icon" />
              <span className="incident-nav-label">{item.label}</span>
              <ui5-icon
                name={selectedIncident === item.id ? 'navigation-up-arrow' : 'navigation-down-arrow'}
                class="incident-nav-chevron"
              />
            </div>

            {selectedIncident === item.id && (
              <div className="incident-nav-detail">
                <p className="incident-nav-desc">{item.description}</p>
                <div className="incident-example-box">
                  <span className="incident-example-label">Example query</span>
                  <p className="incident-example-text">"{item.example}"</p>
                  <Button
                    design="Emphasized"
                    icon="upload"
                    style={{ width: '100%', marginTop: '0.5rem' }}
                    onClick={() => onExampleClick(item.example)}
                  >
                    Use this query
                  </Button>
                </div>
              </div>
            )}
          </div>
        ))}
      </div>

      {/* Tips panel */}
      <div className="side-nav-tips">
        <div
          className="tips-header"
          onClick={() => setTipsOpen(v => !v)}
        >
          <ui5-icon name="hint" class="side-nav-header-icon" />
          <span className="side-nav-header-label">Investigation Tips</span>
          <ui5-icon
            name={tipsOpen ? 'navigation-up-arrow' : 'navigation-down-arrow'}
            class="incident-nav-chevron"
            style={{ marginLeft: 'auto' }}
          />
        </div>
        {tipsOpen && (
          <ul className="tips-list">
            {QUICK_TIPS.map((tip, i) => (
              <li key={i} className="tips-item">{tip}</li>
            ))}
          </ul>
        )}
      </div>

      {/* Footer badges */}
      <div className="side-nav-footer">
        <Tag colorScheme="1">A2A Protocol</Tag>
        <Tag colorScheme="2">12 Systems</Tag>
        <Tag colorScheme="6">14-Section Report</Tag>
      </div>
    </div>
  );
}
