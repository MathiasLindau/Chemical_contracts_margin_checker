FROM python:3.11-slim

WORKDIR /app

COPY . .

# CPU-only PyTorch
RUN pip install --no-cache-dir \
    --index-url https://download.pytorch.org/whl/cpu \
    torch

# Application dependencies
RUN pip install --no-cache-dir \
    streamlit \
    openai \
    pandas \
    psycopg[binary] \
    python-dotenv \
    minsearch \
    sentence-transformers \
    tqdm

RUN chmod +x docker-entrypoint.sh

EXPOSE 8501

CMD ["./docker-entrypoint.sh"]
