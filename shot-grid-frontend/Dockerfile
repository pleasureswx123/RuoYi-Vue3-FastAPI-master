ARG NODE_BASE=node:22-alpine@sha256:c610fcdfb1d5b4740dd70c284ed3cb16bb857e0f7166196e36a5501df7a3aa32
ARG NGINX_BASE=nginx:1.30.6-alpine@sha256:901e593c95dc85f5a729f5765516321366ef4ac401821431d408897e95287d0a
FROM ${NODE_BASE} AS builder

WORKDIR /app

ARG NPM_REGISTRY=https://registry.npmmirror.com

COPY package.json package-lock.json ./
RUN --mount=type=cache,id=ruoyi-npm-build-cache,target=/root/.npm,sharing=locked \
    npm ci --registry="${NPM_REGISTRY}" --no-audit --no-fund

COPY . .
RUN npm run build:prod

FROM ${NGINX_BASE}

ENV BACKEND_UPSTREAM=http://ruoyi-backend-pg:9099

COPY nginx/default.conf.template /etc/nginx/templates/default.conf.template
COPY --from=builder /app/dist /usr/share/nginx/html/shot-grid-app

EXPOSE 80
