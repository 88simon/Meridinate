# Multi-stage Dockerfile for Gun Del Sol Web (Next.js 15)
# Based on official Next.js Docker example with optimizations

# Stage 1: Dependencies
FROM node:22-alpine AS deps
RUN apk add --no-cache libc6-compat

WORKDIR /app

# Install pnpm
RUN corepack enable && corepack prepare pnpm@10 --activate

# Copy package files
COPY package.json pnpm-lock.yaml ./

# Install dependencies (use --no-frozen-lockfile for Docker builds to handle version mismatches)
RUN pnpm install --no-frozen-lockfile


# Stage 2: Builder
FROM node:22-alpine AS builder

WORKDIR /app

# Install pnpm
RUN corepack enable && corepack prepare pnpm@10 --activate

# Copy dependencies from deps stage
COPY --from=deps /app/node_modules ./node_modules

# Copy application code
COPY . .

# Disable telemetry during build
ENV NEXT_TELEMETRY_DISABLED=1 \
    NEXT_PUBLIC_SENTRY_DISABLED=true

# Build Next.js application
RUN pnpm build


# Stage 3: Runner (Production)
FROM node:22-alpine AS runner

WORKDIR /app

# Set environment to production
ENV NODE_ENV=production \
    NEXT_TELEMETRY_DISABLED=1 \
    PORT=3000

# Create non-root user for security
RUN addgroup --system --gid 1001 nodejs && \
    adduser --system --uid 1001 nextjs

# Copy necessary files from builder
COPY --from=builder /app/public ./public
COPY --from=builder /app/.next/standalone ./
COPY --from=builder /app/.next/static ./.next/static

# Set proper permissions
RUN chown -R nextjs:nodejs /app

# Switch to non-root user
USER nextjs

# Expose port
EXPOSE 3000

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=40s --retries=3 \
    CMD node -e "require('http').get('http://localhost:3000/api/health', (res) => { process.exit(res.statusCode === 200 ? 0 : 1) })" || exit 1

# Start Next.js
CMD ["node", "server.js"]
