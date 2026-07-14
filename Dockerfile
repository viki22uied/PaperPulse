FROM python:3.11-slim

WORKDIR /app

# Install dependencies first for better layer caching.
COPY pyproject.toml requirements.txt README.md ./
COPY paperpulse ./paperpulse
RUN pip install --no-cache-dir .

# Runtime state lives here; mount a volume to persist the learned profile.
VOLUME ["/data"]
ENV PAPERPULSE_STATE=/data/.paperpulse_state.json

EXPOSE 8000

# Default to the web dashboard + REST API. Override with `run`, `feedback`, etc.
ENTRYPOINT ["paperpulse"]
CMD ["serve", "--host", "0.0.0.0", "--port", "8000"]
