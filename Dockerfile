FROM python:3.12-slim

WORKDIR /app

RUN pip install --no-cache-dir Pillow

COPY build.py .

ENV PHOTOS_DIR=/photos
ENV OUTPUT_DIR=/output
ENV CONTEXT_DIR=/app/context
ENV SITE_TITLE="My Portfolio"
ENV SITE_AUTHOR="Photographer"
ENV INSTAGRAM_URL=""

CMD ["python3", "build.py"]
