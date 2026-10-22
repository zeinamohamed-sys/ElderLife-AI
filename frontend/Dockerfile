FROM node:20-alpine AS build
WORKDIR /app
COPY package.json ./
RUN npm install
COPY . .
ARG VITE_API=http://localhost:8000
ENV VITE_API=$VITE_API
RUN npm run build
FROM nginx:alpine
COPY --from=build /app/dist /usr/share/nginx/html
