FROM python:3.12-slim

WORKDIR /app

COPY pyproject.toml README.md ./
COPY corpusgate ./corpusgate

RUN pip install --no-cache-dir -e ".[serve]"

EXPOSE 8000

CMD ["uvicorn", "corpusgate.serve.app:app", "--host", "0.0.0.0", "--port", "8000"]
