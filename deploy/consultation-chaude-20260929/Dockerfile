ARG BASE=lexmachine-budget:20260929-style-classique-sans-audit
FROM ${BASE}
COPY --chmod=644 explorer.js explorer.css /app/public/assets/
COPY --chmod=644 explorer.html /app/public/
COPY --chmod=644 api.py web.py consultation.py /app/budget_service/
COPY --chmod=644 test_consultation_cache.py test_consultation_http.py test_rap_movements.py test_other_budget_historical_movements.py test_rap_pagination_review.py /app/tests/
