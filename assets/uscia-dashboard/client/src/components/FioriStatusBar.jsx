import React from 'react';
import { MessageStrip } from '@ui5/webcomponents-react';
import './FioriStatusBar.css';

export default function FioriStatusBar({ agentOnline, loading, messagesCount }) {
  if (loading) {
    return (
      <div className="fiori-status-bar">
        <MessageStrip
          design="Information"
          hideCloseButton
          style={{ width: '100%' }}
        >
          ⚙️ Investigation in progress — querying 15 systems in parallel (IBP · RTI/CPI · bgRFC · S/4HANA MRP · PP/DS · aATP · BDC · IBP Jobs)…
        </MessageStrip>
      </div>
    );
  }

  if (agentOnline === false) {
    return (
      <div className="fiori-status-bar">
        <MessageStrip
          design="Negative"
          hideCloseButton
          style={{ width: '100%' }}
        >
          USCIA Agent is unreachable. Check the agent service status and retry.
        </MessageStrip>
      </div>
    );
  }

  if (agentOnline === null) {
    return (
      <div className="fiori-status-bar">
        <MessageStrip
          design="Warning"
          hideCloseButton
          style={{ width: '100%' }}
        >
          Connecting to USCIA Agent…
        </MessageStrip>
      </div>
    );
  }

  return null; // Online + idle = no strip shown
}
