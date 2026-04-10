# Stage 1: Build frontend
FROM node:22-slim AS frontend
WORKDIR /app/frontend
ARG APP_VERSION=dev
RUN echo "${APP_VERSION}" > /app/VERSION
COPY frontend/package*.json ./
RUN npm ci
COPY frontend/ ./
ARG VITE_GOOGLE_CLIENT_ID
ENV VITE_GOOGLE_CLIENT_ID=$VITE_GOOGLE_CLIENT_ID
RUN npm run build

# Stage 2: Python app serving built frontend
FROM python:3.12-slim
WORKDIR /app
ARG APP_VERSION=dev
RUN echo "${APP_VERSION}" > VERSION
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY server/ server/
COPY --from=frontend /app/frontend/dist frontend/dist
EXPOSE 8080
CMD ["uvicorn", "server.main:app", "--host", "0.0.0.0", "--port", "8080"]
