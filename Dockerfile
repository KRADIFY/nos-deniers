FROM python@sha256:d50fb7611f86d04a3b0471b46d7557818d88983fc3136726336b2a4c657aa30b
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
WORKDIR /app
COPY requirements.txt /app/requirements.txt
RUN pip install --no-cache-dir -r /app/requirements.txt
COPY budget_service /app/budget_service
COPY public /app/public
COPY tools/export_document_search.py /app/tools/export_document_search.py
COPY tests /app/tests
RUN mkdir /state /data && chown 1000:1000 /state /data && chmod 755 /state /data
USER 10001:10001
EXPOSE 8080
CMD ["python", "-m", "budget_service.web"]
