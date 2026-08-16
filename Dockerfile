FROM python:3.11-slim

RUN useradd -m -u 1000 user
WORKDIR /home/user/app

COPY --chown=user pyproject.toml uv.lock ./
RUN pip install --no-cache-dir uv==0.11.21 && uv sync --frozen --no-dev

COPY --chown=user src/ ./src/
COPY --chown=user config/ ./config/
COPY --chown=user data/index/ ./data/index/
COPY --chown=user app.py start.sh ./
COPY --chown=user .streamlit/ ./.streamlit/

# Bake the embedding model in so the container never downloads at startup.
RUN uv run python -c "from sentence_transformers import SentenceTransformer; \
    SentenceTransformer('BAAI/bge-small-en-v1.5')"

USER user
ENV API_URL=http://localhost:8000 PYTHONPATH=/home/user/app/src
EXPOSE 7860
RUN chmod +x start.sh
CMD ["./start.sh"]
