# Runtime image of the frontend. It contains no build step on purpose: the pages are
# prerendered from the API, which only exists on the compose network, and `docker build`
# cannot join that network. infra/build-web.sh runs `next build` there and then builds
# this image from its output (.next/standalone, .next/static, public).
FROM node:22-alpine

ENV NODE_ENV=production \
    NEXT_TELEMETRY_DISABLED=1 \
    PORT=3000 \
    HOSTNAME=0.0.0.0

WORKDIR /app
# Owned by `node`: Next writes its ISR cache under .next/cache at run time.
COPY --chown=node:node .next/standalone ./
COPY --chown=node:node .next/static ./.next/static
COPY --chown=node:node public ./public

USER node
EXPOSE 3000
CMD ["node", "server.js"]
