FROM python:3.14-slim

WORKDIR /app

COPY requirements.txt .
RUN apt-get update \
    && apt-get install -y --no-install-recommends fonts-noto-cjk \
    && rm -rf /var/lib/apt/lists/*
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

ENV POEM_UI_HOST=0.0.0.0
ENV PORT=8080

EXPOSE 8080

CMD ["python", "server.py"]
