# Production image for the API. Applies pending migrations on start, and
# seeds the demo catalog + demo accounts when SEED_DEMO=true.
FROM node:22-alpine AS build
WORKDIR /app
COPY package.json package-lock.json ./
RUN npm ci
COPY tsconfig.json ./
COPY src ./src
RUN npm run build

FROM node:22-alpine
WORKDIR /app
ENV NODE_ENV=production
COPY package.json package-lock.json ./
RUN npm ci --omit=dev && npm cache clean --force
COPY --from=build /app/dist ./dist
USER node
EXPOSE 4000
CMD ["sh", "-c", "node dist/db/migrate.js && if [ \"$SEED_DEMO\" = \"true\" ]; then node dist/db/seed.js; fi && node dist/index.js"]
