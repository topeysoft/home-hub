# The Matter bridge: the house as Apple Home, Google Home and Alexa see it. docs/matter.md.
#
# The first Node process this hub runs at runtime, and that is the price of the direction: Matter's
# DEVICE side has one mature implementation and it is matter.js. python-matter-server, already in the
# stack, is a controller -- the opposite end of the wire.
FROM node:22-alpine AS build
WORKDIR /src
COPY package.json package-lock.json tsconfig.json ./
RUN npm ci
COPY src ./src
RUN npm run build

FROM node:22-alpine
WORKDIR /app
ENV NODE_ENV=production
COPY package.json package-lock.json ./
RUN npm ci --omit=dev && npm cache clean --force
COPY --from=build /src/dist ./dist
# Fabric credentials and the endpoint numbers live here. Losing it means every ecosystem in the house
# re-commissions from nothing, so it is a volume and it rides the backup.
VOLUME /data
ENV HUB_MATTER_STORAGE=/data
CMD ["node", "dist/main.js"]
