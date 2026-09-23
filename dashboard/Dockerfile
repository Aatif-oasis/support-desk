# Two stages so the shipped image carries the built app and its runtime
# dependencies, not the toolchain that produced them.
FROM node:20-alpine AS builder

WORKDIR /app

# Dependencies are installed from the lockfile first, in their own layer,
# so a source-only change doesn't reinstall everything.
COPY package.json package-lock.json ./
RUN npm ci

COPY . .

# The API base is read by the browser, so it is baked in at build time
# rather than read from the container's environment at runtime.
ARG NEXT_PUBLIC_API_BASE=http://localhost:8000
ENV NEXT_PUBLIC_API_BASE=$NEXT_PUBLIC_API_BASE

RUN npm run build

FROM node:20-alpine AS runner

WORKDIR /app
ENV NODE_ENV=production

# Runtime deps only — no TypeScript, no build tooling.
COPY package.json package-lock.json ./
RUN npm ci --omit=dev

COPY --from=builder /app/.next ./.next
COPY --from=builder /app/public ./public
COPY --from=builder /app/next.config.ts ./

EXPOSE 3000

CMD ["npm", "run", "start"]
