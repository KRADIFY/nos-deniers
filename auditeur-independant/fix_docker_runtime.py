from pathlib import Path
p=Path('Dockerfile');s=p.read_text('utf-8')
start=s.index('RUN apt-get update');end=s.index('RUN pip install',start)
s=s[:start]+'''RUN apt-get update && apt-get install -y --no-install-recommends chromium ca-certificates tzdata \
    && rm -rf /var/lib/apt/lists/*
COPY --from=node-runtime /usr/local/bin/node /usr/local/bin/node
COPY --from=node-runtime /opt/audit-runtime/node_modules /opt/audit-runtime/node_modules
'''+s[end:]
s='''FROM node:22-bookworm-slim AS node-runtime
WORKDIR /opt/audit-runtime
RUN npm install --omit=dev --ignore-scripts --no-audit --no-fund playwright@1.62.1

'''+s.replace('AUDIT_NODE=/usr/bin/node','AUDIT_NODE=/usr/local/bin/node')
p.write_text(s,'utf-8')
