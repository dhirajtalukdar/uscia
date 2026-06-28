/**
 * USCIA Dashboard — Express server
 * Serves the React build and proxies A2A calls to the USCIA agent.
 *
 * A2A protocol (google/a2a):
 *   POST /  (JSON-RPC 2.0 envelope)
 *   GET  /.well-known/agent.json
 *
 * The server:
 *   1. Forwards POST / to the USCIA agent at USCIA_AGENT_URL
 *   2. Serves static React build from client/dist
 *   3. Exposes GET /health for CF liveness probe
 */

import express from 'express';
import compression from 'compression';
import cors from 'cors';
import { createRequire } from 'module';
import path from 'path';
import { fileURLToPath } from 'url';
import { v4 as uuidv4 } from 'uuid';

const __filename = fileURLToPath(import.meta.url);
const __dirname = path.dirname(__filename);

const app = express();
const PORT = parseInt(process.env.PORT || '3000', 10);

// USCIA agent A2A endpoint — override via env for local dev
const USCIA_AGENT_URL = process.env.USCIA_AGENT_URL ||
  '[REDACTED]';

app.use(compression());
app.use(cors());
app.use(express.json({ limit: '2mb' }));

// ── Health probe ────────────────────────────────────────────────────────────
app.get('/health', (_req, res) => {
  res.json({ status: 'ok', agent: USCIA_AGENT_URL });
});

// ── A2A proxy — POST /api/a2a ───────────────────────────────────────────────
// The React client calls /api/a2a (same-origin, no CORS issues).
// We forward to the USCIA agent using the A2A JSON-RPC 2.0 envelope.
app.post('/api/a2a', async (req, res) => {
  try {
    const { default: fetch } = await import('node-fetch');

    // Build A2A tasks/send JSON-RPC request
    const taskId = uuidv4();
    const contextId = req.body.contextId || uuidv4();
    const userMessage = req.body.message || '';

    const rpcPayload = {
      jsonrpc: '2.0',
      id: uuidv4(),
      method: 'message/send',
      params: {
        message: {
          messageId: uuidv4(),
          role: 'user',
          parts: [{ kind: 'text', text: userMessage }]
        }
      }
    };

    const agentRes = await fetch(`${USCIA_AGENT_URL}/`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(rpcPayload),
      timeout: 360000 // 6 min — investigations take up to 5 min
    });

    if (!agentRes.ok) {
      const errText = await agentRes.text();
      return res.status(502).json({
        error: `Agent returned ${agentRes.status}`,
        detail: errText.slice(0, 500)
      });
    }

    const data = await agentRes.json();
    res.json({ contextId, taskId, result: data });
  } catch (err) {
    console.error('A2A proxy error:', err);
    res.status(500).json({ error: err.message });
  }
});

// ── A2A proxy — GET /api/agent-card ────────────────────────────────────────
app.get('/api/agent-card', async (_req, res) => {
  try {
    const { default: fetch } = await import('node-fetch');
    const r = await fetch(`${USCIA_AGENT_URL}/.well-known/agent.json`);
    const data = await r.json();
    res.json(data);
  } catch (err) {
    res.status(502).json({ error: err.message });
  }
});

// ── Serve React build ───────────────────────────────────────────────────────
const clientDist = path.join(__dirname, 'client', 'dist');
app.use(express.static(clientDist));
app.get('*', (_req, res) => {
  res.sendFile(path.join(clientDist, 'index.html'));
});

app.listen(PORT, () => {
  console.log(`USCIA Dashboard running on port ${PORT}`);
  console.log(`Proxying A2A calls to: ${USCIA_AGENT_URL}`);
});
