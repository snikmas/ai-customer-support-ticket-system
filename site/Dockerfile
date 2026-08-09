# Frontend image — MULTI-STAGE build.
#
# Stage 1 (build): full Node.js image, compiles TypeScript + bundles the app
# with Vite into static files (dist/).
# Stage 2 (serve): tiny nginx image that only serves those static files.
# The final image contains NO Node, NO npm, NO source — just HTML/JS/CSS.
# Result: ~25 MB instead of ~1 GB, and a much smaller attack surface.

# ---------- Stage 1: build ----------
FROM node:20-alpine AS build
WORKDIR /app

# Layer caching again: package files first, so `npm ci` only re-runs when
# dependencies change, not on every source edit.
COPY package.json package-lock.json ./
RUN npm ci

COPY . .

# Vite inlines env vars into the bundle AT BUILD TIME (they end up in the
# static JavaScript). The value comes from compose.yaml's build args.
ARG VITE_API_BASE_URL
ENV VITE_API_BASE_URL=$VITE_API_BASE_URL

RUN npm run build

# ---------- Stage 2: serve ----------
FROM nginx:alpine
# SPA routing: unknown paths must serve index.html (React Router owns them).
COPY nginx.conf /etc/nginx/conf.d/default.conf
COPY --from=build /app/dist /usr/share/nginx/html
EXPOSE 80
