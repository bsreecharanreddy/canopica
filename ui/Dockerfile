FROM node:22-alpine AS build
WORKDIR /app
COPY package.json package-lock.json ./
RUN npm ci
COPY . .
RUN npm run build

FROM nginx:alpine
COPY --from=build /app/dist /usr/share/nginx/html
COPY nginx.conf.template /etc/nginx/templates/default.conf.template
# Overridable per deployment target (see nginx.conf.template's own
# comment) -- Docker Compose's service DNS name, unchanged from before.
ENV API_UPSTREAM=api:8080
EXPOSE 80
# 127.0.0.1, not localhost: BusyBox wget in this Alpine image resolves
# "localhost" to ::1 first, and nginx below only listens on 0.0.0.0:80 (no
# IPv6), so a "localhost" URL fails with connection refused even though
# the server itself is fine -- confirmed by testing 127.0.0.1 directly.
HEALTHCHECK --interval=10s --timeout=5s --retries=12 --start-period=15s \
    CMD wget -qO- http://127.0.0.1/ || exit 1
