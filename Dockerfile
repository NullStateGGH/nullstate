FROM python:3.13-slim AS builder
WORKDIR /app
COPY pyproject.toml ./
COPY src/ src/
RUN pip install --no-cache-dir .

FROM python:3.13-slim AS runtime
WORKDIR /app
ENV PYTHONPATH=/app/src
COPY --from=builder /usr/local/lib/python3.13/site-packages /usr/local/lib/python3.13/site-packages
COPY --from=builder /app/src src/
COPY --from=builder /app/pyproject.toml ./
EXPOSE 8080 8081
CMD ["python3", "-m", "network.gateway"]
