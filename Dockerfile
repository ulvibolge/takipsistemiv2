# ----- BUILD AŞAMASI -----
    FROM python:3.10-slim AS builder

    # APP_ENV argümanını tanımla
    ARG APP_ENV=development
    ENV APP_ENV=${APP_ENV}

    WORKDIR /app
    
    # Gerekli sistem paketleri (örneğin bcrypt, email-validator gibi native bağımlılıklar için)
    RUN apt-get update && apt-get install -y --no-install-recommends \
        build-essential gcc curl && \
        rm -rf /var/lib/apt/lists/*
    
    # Python bağımlılıklarını kur
    COPY requirements.txt .
    RUN python -m venv /opt/venv && \
        /opt/venv/bin/pip install --upgrade pip && \
        /opt/venv/bin/pip install --no-cache-dir -r requirements.txt
    
    # ----- RUNTIME AŞAMASI -----
    FROM python:3.10-slim
    
    # Güvenlik için non-root kullanıcı
    RUN groupadd -r appuser && \
        useradd -r -g appuser appuser && \
        mkdir /app && \
        chown appuser:appuser /app
    
    # Sadece runtime için gerekli olanları yükle
    RUN apt-get update && \
        apt-get install -y --no-install-recommends \
        curl && \
        rm -rf /var/lib/apt/lists/*
    
    # Sanal ortamı kopyala
    COPY --from=builder /opt/venv /opt/venv
    
    # Uygulama dosyalarını kopyala
    COPY --chown=appuser:appuser . /app
    WORKDIR /app
    
    # Ortam değişkenleri
    ENV PATH="/opt/venv/bin:$PATH" \
        PYTHONDONTWRITEBYTECODE=1 \
        PYTHONUNBUFFERED=1 \
        PYTHONPATH=/app \
        PIP_NO_CACHE_DIR=1
    
    # Uygulama portu
    EXPOSE 8000
    
    # Kullanıcıyı değiştir
    USER appuser
    
    # Sağlık kontrolü
    HEALTHCHECK --interval=30s --timeout=5s --start-period=5s --retries=3 \
      CMD curl -f http://localhost:8000/health || exit 1
    
    # Uygulama komutu
    CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
    