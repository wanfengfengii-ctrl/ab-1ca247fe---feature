# ---- 构建阶段 ----
FROM node:22-alpine AS build
WORKDIR /build
COPY package.json package-lock.json ./
RUN npm ci --no-audit --no-fund
COPY . .
RUN npm run build

# ---- 运行阶段 ----
FROM nginx:1.27-alpine
ENV LISTEN_PORT=80
ENV API_UPSTREAM=api:8000

# 官方 nginx 镜像会用 envsubst 渲染 /etc/nginx/templates/*.template。
COPY docker/nginx/default.conf.template /etc/nginx/templates/default.conf.template
COPY --from=build /build/dist /usr/share/nginx/html

EXPOSE 80

HEALTHCHECK --interval=10s --timeout=3s --start-period=5s --retries=5 \
  CMD wget -qO- http://127.0.0.1:${LISTEN_PORT}/ >/dev/null 2>&1 || exit 1

CMD ["nginx", "-g", "daemon off;"]
