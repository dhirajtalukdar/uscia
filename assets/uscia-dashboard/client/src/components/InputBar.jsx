import React, { useRef, useEffect } from 'react';
import { Button, TextArea, MessageStrip } from '@ui5/webcomponents-react';
import './InputBar.css';

export default function InputBar({ input, setInput, loading, onSend }) {
  const textareaRef = useRef(null);

  // Focus on mount
  useEffect(() => {
    textareaRef.current?.getDomRef?.()?.focus?.();
  }, []);

  const handleKeyDown = (e) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
      onSend();
    }
  };

  return (
    <div className="input-bar">
      <div className="input-bar-inner">
        <div className="input-bar-field">
          <TextArea
            ref={textareaRef}
            className="fiori-textarea"
            placeholder="Describe your supply chain incident (e.g. 'Why is planned order for material M-1234 plant 1000 missing in MD04?')"
            value={input}
            onInput={e => setInput(e.target.value)}
            onKeyDown={handleKeyDown}
            rows={3}
            disabled={loading}
            style={{ width: '100%', resize: 'none' }}
          />
        </div>

        <div className="input-bar-actions">
          <Button
            design="Emphasized"
            icon="paper-plane"
            disabled={loading || !input.trim()}
            onClick={() => onSend()}
            tooltip="Send (Enter)"
          >
            {loading ? 'Investigating…' : 'Send'}
          </Button>
        </div>
      </div>

      <p className="input-bar-hint">
        Press <kbd>Enter</kbd> to send · <kbd>Shift+Enter</kbd> for new line · Investigations take up to 5 minutes
      </p>
    </div>
  );
}
