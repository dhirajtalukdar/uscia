import React, { useEffect, useRef } from 'react';
import ReactMarkdown from 'react-markdown';
import remarkGfm from 'remark-gfm';
import {
  Card, CardHeader,
  BusyIndicator,
  MessageStrip,
  Avatar,
} from '@ui5/webcomponents-react';
import ReportView from './ReportView.jsx';
import './ChatArea.css';

export default function ChatArea({ messages, view, loading }) {
  const bottomRef = useRef(null);

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [messages, loading]);

  return (
    <div className="chat-area">
      <div className="chat-messages">
        {messages.map((msg, idx) => {
          const prevUser = idx > 0
            ? [...messages].slice(0, idx).reverse().find(m => m.role === 'user')
            : null;
          return (
            <MessageCard
              key={msg.id}
              msg={msg}
              view={view}
              userQuery={prevUser?.content || ''}
            />
          );
        })}

        {loading && (
          <div className="chat-row chat-row--agent">
            <Avatar icon="process" colorScheme="Accent9" size="S" className="chat-avatar" />
            <Card className="chat-card chat-card--agent">
              <div className="chat-card-thinking">
                <BusyIndicator active size="S" />
                <span className="thinking-label">Investigating — querying 15 systems in parallel…</span>
              </div>
            </Card>
          </div>
        )}

        <div ref={bottomRef} />
      </div>
    </div>
  );
}

function MessageCard({ msg, view, userQuery }) {
  const isUser   = msg.role === 'user';
  const isSystem = msg.role === 'system';
  const isAgent  = msg.role === 'agent';

  if (isUser) {
    return (
      <div className="chat-row chat-row--user">
        <div className="user-bubble">
          <p className="user-bubble-text">{msg.content}</p>
          <span className="user-bubble-time">{formatTime(msg.timestamp)}</span>
        </div>
        <Avatar icon="customer" colorScheme="Accent1" size="S" className="chat-avatar" />
      </div>
    );
  }

  if (isSystem) {
    return (
      <div className="chat-row chat-row--system">
        <Avatar icon="chain-link" colorScheme="Accent6" size="S" className="chat-avatar" />
        <Card className="chat-card chat-card--system">
          <CardHeader
            titleText="USCIA — Unified Supply Chain Intelligence Agent"
            subtitleText="A2A Protocol · JSON-RPC 2.0 · 12-System Coverage"
            avatar={<ui5-icon name="chain-link" />}
          />
          <div className="chat-card-content">
            <div className="report-markdown">
              <ReactMarkdown remarkPlugins={[remarkGfm]}>{msg.content}</ReactMarkdown>
            </div>
          </div>
        </Card>
      </div>
    );
  }

  if (isAgent && msg.content === null) return null;

  if (msg.status === 'error') {
    return (
      <div className="chat-row chat-row--agent">
        <Avatar icon="process" colorScheme="Accent9" size="S" className="chat-avatar" />
        <div className="chat-error-strip">
          <MessageStrip design="Negative" hideCloseButton>{msg.content}</MessageStrip>
        </div>
      </div>
    );
  }

  return (
    <div className="chat-row chat-row--agent chat-row--report">
      <ReportView
        query={userQuery}
        content={msg.content}
        timestamp={msg.timestamp}
        view={view}
      />
    </div>
  );
}

function formatTime(date) {
  if (!date) return '';
  const d = date instanceof Date ? date : new Date(date);
  return d.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });
}
