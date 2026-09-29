FROM lexmachine-budget:20260929-migration-optimisee-v2
COPY budget_service/api.py /app/budget_service/api.py
COPY budget_service/historical_discrepancies.py /app/budget_service/historical_discrepancies.py
COPY budget_service/data/historical_discrepancy_notices_2017_2022.json /app/budget_service/data/historical_discrepancy_notices_2017_2022.json
COPY public/assets/explorer.js /app/public/assets/explorer.js
COPY public/assets/explorer.css /app/public/assets/explorer.css
COPY public/explorer.html /app/public/explorer.html
COPY tests/test_historical_discrepancies.py /app/tests/test_historical_discrepancies.py
