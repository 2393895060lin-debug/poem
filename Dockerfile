FROM python:3.12-slim

WORKDIR /app

COPY requirements.txt .
RUN apt-get update \
    && apt-get install -y --no-install-recommends fonts-noto-cjk \
    && rm -rf /var/lib/apt/lists/* \
    && useradd --create-home --uid 10001 appuser
RUN pip install --no-cache-dir -r requirements.txt

COPY --chown=appuser:appuser . .
RUN mkdir -p /app/.data && chown -R appuser:appuser /app/.data

ENV POEM_UI_HOST=0.0.0.0
ENV PORT=8080

EXPOSE 8080

USER appuser

CMD ["python", "server.py"]
