FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app
RUN addgroup --system valuebridge && adduser --system --ingroup valuebridge valuebridge

COPY pyproject.toml README.md ./
COPY app ./app
COPY mockdesk ./mockdesk
COPY data ./data
RUN pip install --no-cache-dir . \
    && mkdir -p /app/runtime \
    && chown -R valuebridge:valuebridge /app

ARG BUILD_SHA=dev
ENV VALUEBRIDGE_BUILD_SHA=$BUILD_SHA

USER valuebridge
EXPOSE 8000 8001
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
