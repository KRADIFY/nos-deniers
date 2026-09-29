FROM node:22-bookworm-slim AS node-runtime
WORKDIR /opt/audit-runtime
RUN npm install --omit=dev --ignore-scripts --no-audit --no-fund playwright@1.62.1

FROM python:3.12-slim-bookworm
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 \
    AUDIT_NODE=/usr/local/bin/node AUDIT_CHROME=/usr/bin/chromium \
    AUDIT_NODE_MODULES=/opt/audit-runtime/node_modules \
    AUDIT_STATE_DIR=/audit-data HOME=/tmp TZ=Europe/Paris
RUN apt-get update && apt-get install -y --no-install-recommends chromium ca-certificates tzdata poppler-utils     && rm -rf /var/lib/apt/lists/*
COPY --from=node-runtime /usr/local/bin/node /usr/local/bin/node
COPY --from=node-runtime /opt/audit-runtime/node_modules /opt/audit-runtime/node_modules
RUN pip install --no-cache-dir xlrd==2.0.2
WORKDIR /app
COPY coverage.py coverage_report.py document-coverage.json mutation_check.py reporting.py audit.py oracle.py management.py zeros.py zero_reconcile.py document_zeros.py document-zero-proofs.json prepare_reference.py service.py zero_api.py worker.py browser.cjs ./
COPY web ./web
USER 10001:10001
EXPOSE 8095
HEALTHCHECK --interval=30s --timeout=5s --start-period=20s CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8095/healthz',timeout=3)"
CMD ["python", "-u", "service.py"]
