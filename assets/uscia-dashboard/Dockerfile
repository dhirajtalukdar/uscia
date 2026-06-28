# ── Stage 1: build React client ──────────────────────────────────────────────
FROM node:20-alpine AS client-builder
WORKDIR /build/client
COPY client/package*.json ./
RUN npm ci
COPY client/ ./
RUN npm run build

# ── Stage 2: production server ────────────────────────────────────────────────
FROM node:20-alpine
WORKDIR /app

# Server dependencies
COPY package*.json ./
RUN npm ci --omit=dev

# Server source
COPY server.js ./

# React build output
COPY --from=client-builder /build/client/dist ./client/dist

ENV NODE_ENV=production
ENV PORT=3000

EXPOSE 3000
CMD ["node", "server.js"]
