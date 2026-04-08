FROM python:3.12-slim

WORKDIR /app

# Ensure HTTPS certificate chain validation works for outbound API calls (GitHub OAuth).
RUN apt-get update \
	&& apt-get install -y --no-install-recommends ca-certificates \
	&& update-ca-certificates \
	&& rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY app ./app

# Template and local metadata directory are mounted at runtime.
RUN mkdir -p /app/portfolio_template /app/data

ENV PORTFOLIO_TEMPLATE_DIR=/app/portfolio_template
ENV APP_BASE_URL=http://localhost:8000

EXPOSE 8000
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
