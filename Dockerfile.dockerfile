FROM python:3.11-slim

WORKDIR /app

#Install dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

#copy application
COPY app/ .

#Expose port
EXPOSE 5000

#Health check
HEALTHCHECK --interval=30s --timeout=3s --start-period=40s --retries=3\
    CMD python -c "import requests; requests.get('http//localhost:5000/health')"

#run with gunicorn
CMD ["gunicorn", "--bind", "0.0.0.0:5000", "--workers", "2", "--timeout", "120", "app:app"]