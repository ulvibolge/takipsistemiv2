#...
#...
# app/utils/logger.py


import logging
import sys
from logging.handlers import RotatingFileHandler
from pathlib import Path
from app.core.config import settings

def setup_logger():
    """Logging konfigürasyonunu başlatır"""
    log_dir = Path("logs")
    log_dir.mkdir(exist_ok=True)
    
    logger = logging.getLogger("takip_sistemi")
    logger.setLevel(logging.DEBUG if settings.DEBUG else logging.INFO)

    # Log formatı
    formatter = logging.Formatter(
        "%(asctime)s - %(name)s - %(levelname)s - %(module)s:%(lineno)d - %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S"
    )

    # Console handler
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setFormatter(formatter)
    console_handler.setLevel(logging.DEBUG if settings.DEBUG else logging.INFO)

    # File handler (rotating)
    file_handler = RotatingFileHandler(
        filename=log_dir / "takip_sistemi.log",
        maxBytes=10 * 1024 * 1024,  # 10 MB
        backupCount=5,
        encoding="utf-8"
    )
    file_handler.setFormatter(formatter)
    file_handler.setLevel(logging.INFO)

    # Error handler (sadece hatalar)
    error_handler = RotatingFileHandler(
        filename=log_dir / "errors.log",
        maxBytes=5 * 1024 * 1024,  # 5 MB
        backupCount=3,
        encoding="utf-8"
    )
    error_handler.setFormatter(formatter)
    error_handler.setLevel(logging.WARNING)

    # Handlers'ları ekleme
    logger.addHandler(console_handler)
    logger.addHandler(file_handler)
    logger.addHandler(error_handler)

    # Uvicorn loglarını filtrele
    logging.getLogger("uvicorn").handlers = []
    logging.getLogger("uvicorn.access").handlers = []

    return logger

logger = setup_logger()

# Özel log fonksiyonları
def log_database_operation(operation: str, collection: str, details: dict):
    """Veritabanı işlemleri için özel log"""
    logger.info(
        "DB Operation - %s | Collection: %s | Details: %s",
        operation.upper(),
        collection,
        details,
        extra={"type": "database"}
    )

def log_security_event(event_type: str, user: str, ip: str, details: str = None):
    """Güvenlik olayları için özel log"""
    logger.warning(
        "Security Event - %s | User: %s | IP: %s | Details: %s",
        event_type,
        user,
        ip,
        details or "N/A",
        extra={"type": "security"}
    )

def log_tenant_activity(tenant_id: str, action: str, user: str, details: dict):
    """Tenant aktiviteleri için özel log"""
    logger.info(
        "Tenant Activity - %s | Tenant: %s | User: %s | Details: %s",
        action,
        tenant_id,
        user,
        details,
        extra={"type": "tenant_activity"}
    )