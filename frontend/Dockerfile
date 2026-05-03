# =====================================================================
# Frontend Dockerfile — colazione React/Vite (multi-stage produzione)
# Sprint 7.9 entry 117: deploy Railway. Stage 1 build con pnpm,
# stage 2 nginx serve dist + fallback SPA per react-router.
# =====================================================================

# ---- Stage 1: build ---------------------------------------------------
FROM node:20-alpine AS build

RUN corepack enable && corepack prepare pnpm@10.33.2 --activate

WORKDIR /app

# Cache dependencies layer
COPY package.json pnpm-lock.yaml* ./
RUN pnpm install --frozen-lockfile

# Vite legge VITE_* a build-time. Railway può iniettarli via env.
ARG VITE_API_BASE_URL=""
ENV VITE_API_BASE_URL=${VITE_API_BASE_URL}

COPY . .
RUN pnpm build

# ---- Stage 2: nginx serve --------------------------------------------
FROM nginx:1.27-alpine AS runtime

# Config nginx per SPA fallback + bind dinamico a $PORT (Railway).
RUN rm /etc/nginx/conf.d/default.conf
COPY <<'EOF' /etc/nginx/templates/default.conf.template
server {
    listen ${PORT};
    listen [::]:${PORT};
    server_name _;
    root /usr/share/nginx/html;
    index index.html;

    # SPA fallback: ogni route → index.html (react-router lato client).
    location / {
        try_files $uri $uri/ /index.html;
    }

    # Asset hash-based: cache lunga.
    location /assets/ {
        expires 1y;
        add_header Cache-Control "public, immutable";
    }
}
EOF

COPY --from=build /app/dist /usr/share/nginx/html

ENV PORT=8080
EXPOSE 8080

# nginx entrypoint applica il template con envsubst.
CMD ["nginx", "-g", "daemon off;"]
