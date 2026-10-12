FROM python:3.12-slim

WORKDIR /app
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY roadworks ./roadworks
COPY api ./api
COPY scripts ./scripts
COPY data ./data

# Build the dataset at image build time so the API works even without a database
RUN python -m roadworks.pipeline

EXPOSE 8000
CMD ["uvicorn", "api.main:app", "--host", "0.0.0.0", "--port", "8000"]
