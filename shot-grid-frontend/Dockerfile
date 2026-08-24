FROM node:22-alpine AS builder

WORKDIR /app

ARG NPM_REGISTRY=https://registry.npmmirror.com

COPY package.json package-lock.json ./
RUN npm ci --registry="${NPM_REGISTRY}" --no-audit --no-fund

COPY . .
RUN npm run build:prod

FROM nginx:1.27-alpine

ENV BACKEND_UPSTREAM=http://ruoyi-backend-pg:9099

COPY nginx/default.conf.template /etc/nginx/templates/default.conf.template
COPY --from=builder /app/dist /usr/share/nginx/html/shot-grid-app

EXPOSE 80
