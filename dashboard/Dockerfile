# Dashboard Next.js en modo "standalone".
FROM node:22-alpine AS build
WORKDIR /app
COPY dashboard/package.json dashboard/package-lock.json ./
RUN npm ci
COPY dashboard/ .
# Los rewrites de /api/* se fijan al compilar: dirección interna de la API en la red de Docker.
ARG NEXUS_API_URL=http://api:8000
ENV NEXUS_API_URL=$NEXUS_API_URL NEXT_TELEMETRY_DISABLED=1
RUN npm run build

FROM node:22-alpine
WORKDIR /app
ENV NODE_ENV=production NEXT_TELEMETRY_DISABLED=1 PORT=3000 HOSTNAME=0.0.0.0
RUN addgroup -S nexus && adduser -S nexus -G nexus
COPY --from=build --chown=nexus:nexus /app/.next/standalone ./
COPY --from=build --chown=nexus:nexus /app/.next/static ./.next/static
COPY --from=build --chown=nexus:nexus /app/public ./public
USER nexus
EXPOSE 3000
CMD ["node", "server.js"]
