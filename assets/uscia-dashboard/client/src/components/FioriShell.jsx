import React from 'react';
import { ShellBar, ShellBarItem, Button, Tag } from '@ui5/webcomponents-react';
import './FioriShell.css';

// SAP official logo SVG (simplified version of the SAP brand mark)
const SAPLogo = () => (
  <svg width="42" height="21" viewBox="0 0 42 21" fill="none" xmlns="http://www.w3.org/2000/svg">
    <rect width="42" height="21" rx="3" fill="#0070F2"/>
    <text x="21" y="15" textAnchor="middle" fill="white" fontSize="12" fontWeight="bold" fontFamily="Arial, sans-serif">SAP</text>
  </svg>
);

export default function FioriShell({ agentOnline, view, onViewChange, onClear, sidebarCollapsed, onToggleSidebar }) {
  const isOnline = agentOnline === true;
  const isConnecting = agentOnline === null;

  return (
    <div className="fiori-shell-wrapper">
      <ShellBar
        primaryTitle="USCIA"
        secondaryTitle="Supply Chain Diagnostics · 14 Systems · A2A"
        logo={<SAPLogo />}
        showNotifications={false}
        showProductSwitch={false}
        onMenuButtonClick={onToggleSidebar}
      >
        <ShellBarItem
          icon="delete"
          text="New Investigation"
          title="Clear and start new investigation"
          onClick={onClear}
          slot="endContent"
        />
      </ShellBar>

      <div className="fiori-sub-header">
        <div className="fiori-sub-header-left">
          <button
            className="sidebar-toggle-btn"
            onClick={onToggleSidebar}
            title={sidebarCollapsed ? 'Show incident types' : 'Hide panel'}
          >
            <ui5-icon name={sidebarCollapsed ? 'show-edit' : 'hide'} style={{fontSize:'1rem'}} />
            <span>{sidebarCollapsed ? 'Show Panel' : 'Hide Panel'}</span>
          </button>

          <div className="view-selector">
            <button
              className={`view-btn${view === 'consultant' ? ' active' : ''}`}
              onClick={() => onViewChange('consultant')}
            >
              <ui5-icon name="sys-find" />
              <span>Consultant View</span>
            </button>
            <button
              className={`view-btn${view === 'planner' ? ' active' : ''}`}
              onClick={() => onViewChange('planner')}
            >
              <ui5-icon name="employee" />
              <span>Planner View</span>
            </button>
          </div>
        </div>

        <div className="fiori-sub-header-right">
          <div className={`agent-pill${isOnline ? ' online' : isConnecting ? ' connecting' : ' offline'}`}>
            <span className="agent-pill-dot" />
            <span className="agent-pill-text">
              {isOnline ? 'USCIA Online' : isConnecting ? 'Connecting…' : 'Agent Offline'}
            </span>
          </div>
        </div>
      </div>
    </div>
  );
}
