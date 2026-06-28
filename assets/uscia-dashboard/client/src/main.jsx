// ── UI5 Web Components — bare component registrations ──────────────────────
import '@ui5/webcomponents/dist/Button.js';
import '@ui5/webcomponents/dist/Input.js';
import '@ui5/webcomponents/dist/TextArea.js';
import '@ui5/webcomponents/dist/MessageStrip.js';
import '@ui5/webcomponents/dist/Panel.js';
import '@ui5/webcomponents/dist/Card.js';
import '@ui5/webcomponents/dist/CardHeader.js';
import '@ui5/webcomponents/dist/List.js';
import '@ui5/webcomponents/dist/ListItemStandard.js';
import '@ui5/webcomponents/dist/BusyIndicator.js';
import '@ui5/webcomponents/dist/Tag.js';
import '@ui5/webcomponents/dist/Label.js';
import '@ui5/webcomponents/dist/Text.js';
import '@ui5/webcomponents/dist/Avatar.js';
import '@ui5/webcomponents/dist/SegmentedButton.js';
import '@ui5/webcomponents/dist/SegmentedButtonItem.js';
import '@ui5/webcomponents/dist/Select.js';
import '@ui5/webcomponents/dist/Option.js';
import '@ui5/webcomponents/dist/Dialog.js';

// ── UI5 Fiori components ────────────────────────────────────────────────────
import '@ui5/webcomponents-fiori/dist/ShellBar.js';
import '@ui5/webcomponents-fiori/dist/ShellBarItem.js';
import '@ui5/webcomponents-fiori/dist/SideNavigation.js';
import '@ui5/webcomponents-fiori/dist/SideNavigationItem.js';
import '@ui5/webcomponents-fiori/dist/SideNavigationSubItem.js';
import '@ui5/webcomponents-fiori/dist/IllustratedMessage.js';

// ── Icons ───────────────────────────────────────────────────────────────────
import '@ui5/webcomponents-icons/dist/home.js';
import '@ui5/webcomponents-icons/dist/search.js';
import '@ui5/webcomponents-icons/dist/settings.js';
import '@ui5/webcomponents-icons/dist/bell.js';
import '@ui5/webcomponents-icons/dist/grid.js';
import '@ui5/webcomponents-icons/dist/menu2.js';
import '@ui5/webcomponents-icons/dist/delete.js';
import '@ui5/webcomponents-icons/dist/paper-plane.js';
import '@ui5/webcomponents-icons/dist/chain-link.js';
import '@ui5/webcomponents-icons/dist/alert.js';
import '@ui5/webcomponents-icons/dist/warning.js';
import '@ui5/webcomponents-icons/dist/information.js';
import '@ui5/webcomponents-icons/dist/accept.js';
import '@ui5/webcomponents-icons/dist/error.js';
import '@ui5/webcomponents-icons/dist/pending.js';
import '@ui5/webcomponents-icons/dist/process.js';
import '@ui5/webcomponents-icons/dist/product.js';
import '@ui5/webcomponents-icons/dist/shipping-status.js';
import '@ui5/webcomponents-icons/dist/calendar.js';
import '@ui5/webcomponents-icons/dist/refresh.js';
import '@ui5/webcomponents-icons/dist/log.js';
import '@ui5/webcomponents-icons/dist/message-error.js';
import '@ui5/webcomponents-icons/dist/message-warning.js';
import '@ui5/webcomponents-icons/dist/message-success.js';
import '@ui5/webcomponents-icons/dist/message-information.js';
import '@ui5/webcomponents-icons/dist/task.js';
import '@ui5/webcomponents-icons/dist/hint.js';
import '@ui5/webcomponents-icons/dist/upload.js';
import '@ui5/webcomponents-icons/dist/download.js';
import '@ui5/webcomponents-icons/dist/copy.js';
import '@ui5/webcomponents-icons/dist/factory.js';
import '@ui5/webcomponents-icons/dist/navigation-up-arrow.js';
import '@ui5/webcomponents-icons/dist/navigation-down-arrow.js';
import '@ui5/webcomponents-icons/dist/customer.js';

// ── App bootstrap ───────────────────────────────────────────────────────────
import { setTheme } from '@ui5/webcomponents-base/dist/config/Theme.js';
import React from 'react';
import ReactDOM from 'react-dom/client';
import { ThemeProvider } from '@ui5/webcomponents-react';
import App from './App.jsx';
import './index.css';

setTheme('sap_horizon');

ReactDOM.createRoot(document.getElementById('root')).render(
  <ThemeProvider>
    <App />
  </ThemeProvider>
);
