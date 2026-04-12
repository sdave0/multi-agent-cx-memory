FROM python:3.11-slim
WORKDIR /app
# Copy requirements first to leverage caching, but using full path to ensure absolute clarity
COPY ./requirements.txt /app/requirements.txt
RUN pip install --upgrade pip && \
    pip install --no-cache-dir -r /app/requirements.txt
# Copy the entire workspace
COPY . /app/
ENV PYTHONPATH=/app
CMD ["uvicorn", "backend.main:app", "--host", "0.0.0.0", "--port", "8000"]
