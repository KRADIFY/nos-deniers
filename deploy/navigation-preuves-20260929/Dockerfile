ARG BASE=lexmachine-budget:20260929-style-classique-sans-audit
FROM ${BASE}
COPY --chmod=644 explorer.js explorer.css /app/public/assets/
COPY --chmod=644 explorer.html /app/public/explorer.html
COPY --chmod=644 api.py /app/budget_service/api.py
