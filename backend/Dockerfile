FROM python:3.12-slim

WORKDIR /app
COPY backend/requirements.txt /app/requirements.txt
RUN pip install --no-cache-dir -r /app/requirements.txt
COPY backend /app
COPY scripts/sql/datavines-mysql.sql /app/sql/datavines-mysql.sql
ENV PYTHONUNBUFFERED=1
ENV DATAVINES_SQL_PATH=/app/sql/datavines-mysql.sql
EXPOSE 5600
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "5600"]
