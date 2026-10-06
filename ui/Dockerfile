# nb_graph UI: React + Vite build served by nginx (also reverse-proxies /api to graph-api).
FROM docker.io/node:22-alpine AS build
WORKDIR /ui
COPY ui/package.json ui/package-lock.json ./
RUN npm ci --no-audit --no-fund
COPY ui/ ./
RUN npm run build

FROM docker.io/nginx:1.29-alpine
COPY ui/nginx.conf /etc/nginx/conf.d/default.conf
COPY --from=build /ui/dist /usr/share/nginx/html
EXPOSE 80
HEALTHCHECK --interval=15s --timeout=3s CMD wget -qO- http://127.0.0.1/ >/dev/null || exit 1
