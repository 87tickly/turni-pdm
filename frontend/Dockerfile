# =====================================================================
# Frontend Dockerfile — colazione React/Vite
# Dev (con HMR) e build produzione separate
# =====================================================================

FROM node:20-alpine AS base

RUN corepack enable && corepack prepare pnpm@10.33.2 --activate

WORKDIR /app

# Cache dependencies layer
COPY package.json pnpm-lock.yaml* ./
RUN pnpm install --frozen-lockfile

# Copy source
COPY . .

EXPOSE 5173

# Dev mode (override CMD per build produzione)
CMD ["pnpm", "dev", "--host", "0.0.0.0"]
