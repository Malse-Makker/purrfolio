FROM python:3.15-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY build.py .
COPY static ./static
COPY brand ./brand

ENV PHOTOS_DIR=/photos
ENV OUTPUT_DIR=/output
ENV CONTEXT_DIR=/app/context
ENV SITE_TITLE="My Portfolio"
ENV SITE_AUTHOR="Photographer"
ENV INSTAGRAM_URL=""

CMD ["python3", "build.py"]
