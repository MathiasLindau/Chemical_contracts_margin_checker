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
    sentence-transformers

EXPOSE 8501

CMD ["streamlit", "run", "app.py", "--server.address=0.0.0.0"]