"""
Bu dosya, Takip Sistemi API'sinin ana giriş noktasıdır. 
FastAPI framework'ü kullanılarak geliştirilmiştir ve aşağıdaki özellikleri içerir:

1. **Uygulama Fabrikası**:
   - `create_application` fonksiyonu, uygulamanın tüm yapılandırmalarını yapar ve bir FastAPI örneği döner.

2. **Middleware'ler**:
   - CORS (Cross-Origin Resource Sharing) desteği.
   - GZip sıkıştırma desteği.
   - HTTP isteklerini loglama.

3. **Özel Exception Handler'lar**:
   - HTTP hataları için özel handler.
   - Veri doğrulama hataları için özel handler.
   - Genel hatalar için özel handler.

4. **Router'lar**:
   - Modüler bir yapı ile farklı işlevler için router'lar eklenmiştir.
   - Örnek: `auth_router`, `tenant_router`, `project_router`.

5. **Statik Dosyalar**:
   - Statik dosyalar için bir dizin yapılandırması yapılmıştır.

6. **Yaşam Döngüsü Olayları**:
   - Uygulama başlatıldığında ve kapatıldığında yapılacak işlemler tanımlanmıştır.
   - Örnek: Veritabanı bağlantısı kurma ve kapatma.

7. **Sağlık Kontrolü**:
   - `/health` endpoint'i, uygulamanın çalışır durumda olup olmadığını kontrol etmek için kullanılır.

8. **Uvicorn Sunucusu**:
   - Uygulama, Uvicorn ile çalıştırılır ve yapılandırmalar `settings` modülünden alınır.

Bu dosya, uygulamanın temel yapı taşlarını içerir ve geliştiricilerin kolayca genişletip özelleştirebileceği bir yapı sunar.
"""

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.gzip import GZipMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException
from app.utils.database import db_manager
from app.core.config import settings
from app.routers import (
    tenant_router,
    auth_router,
    project_router,
    # expense_router,
    # material_router,
    # personnel_router,
)
from app.utils.logger import logger
from datetime import datetime, timezone 
from pathlib import Path
import uvicorn
datetime.now(timezone.utc)  # UTC zaman dilimini kullanmak için
app = FastAPI()

def create_application() -> FastAPI:
    """FastAPI uygulama fabrikası"""
    app = FastAPI(
        title=getattr(settings, "APP_TITLE", "Takip Sistemi API"),
        description=getattr(settings, "APP_DESCRIPTION", "Modüler Takip Sistemi"),
        version=getattr(settings, "APP_VERSION", "1.0.0"),
        docs_url=getattr(settings, "DOCS_URL", "/docs"),  # Varsayılan değer eklendi
        redoc_url=getattr(settings, "REDOC_URL", "/redoc"),  # Varsayılan değer eklendi
        openapi_url=f"{settings.API_PREFIX}/openapi.json",
        servers=[{"url": settings.API_PREFIX}] if settings.API_PREFIX else None
    )

    configure_middlewares(app)
    configure_exception_handlers(app)
    configure_routers(app)
    configure_static_files(app)
    configure_lifespan_events(app)

    return app


def configure_middlewares(app: FastAPI) -> None:
    """Middleware konfigürasyonu"""
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.CORS_ORIGINS,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    if getattr(settings, "USE_GZIP", False):
        app.add_middleware(GZipMiddleware, minimum_size=1000)

    @app.middleware("http")
    async def log_requests(request, call_next):
        """HTTP isteklerini loglama"""
        start_time = datetime.now()
        response = await call_next(request)
        duration = (datetime.now() - start_time).total_seconds() * 1000
        logger.info(
            f"{request.method} {request.url.path} - {response.status_code} - {duration:.2f}ms"
        )
        # İsteğin body ve header'larını loglamak için (isteğe bağlı)
        # body = await request.body()
        # logger.debug(f"Request Body: {body}")
        return response


def configure_exception_handlers(app: FastAPI) -> None:
    """Özel exception handler'lar"""

    @app.exception_handler(StarletteHTTPException)
    async def http_exception_handler(request, exc):
        logger.warning(f"HTTP Exception: {exc.detail}")
        return JSONResponse(
            status_code=exc.status_code,
            content={"message": exc.detail},
        )

    @app.exception_handler(RequestValidationError)
    async def validation_exception_handler(request, exc):
        logger.warning(f"Validation error: {exc.errors()}")
        return JSONResponse(
            status_code=422,
            content={"message": "Geçersiz veri", "errors": exc.errors()},
        )

    @app.exception_handler(Exception)
    async def general_exception_handler(request, exc):
        logger.error(f"Beklenmeyen hata: {str(exc)}", exc_info=True)
        return JSONResponse(
            status_code=500,
            content={"message": "Sunucu hatası oluştu"},
        )


def configure_routers(app: FastAPI) -> None:
    """Router konfigürasyonu"""
    app.include_router(auth_router.router, prefix=settings.API_PREFIX)
    app.include_router(tenant_router.router, prefix=settings.API_PREFIX)
    app.include_router(project_router.router, prefix=settings.API_PREFIX)
    #app.include_router(expense_router.router, prefix=settings.API_PREFIX)
    #app.include_router(material_router.router, prefix=settings.API_PREFIX)
    #app.include_router(personnel_router.router, prefix=settings.API_PREFIX)


def configure_static_files(app: FastAPI) -> None:
    """Statik dosya konfigürasyonu"""
    static_dir = Path(settings.STATIC_FILES_DIR)
    if static_dir.exists():
        app.mount("/static", StaticFiles(directory=static_dir), name="static")
    else:
        logger.warning(f"⚠️ Statik dosya dizini bulunamadı: {static_dir}")


def configure_lifespan_events(app: FastAPI) -> None:
    """Uygulama yaşam döngüsü event'leri"""

    @app.on_event("startup")
    async def startup():
        logger.info("🔧 Uygulama başlatılıyor...")
        await db_manager.connect()
        logger.info("✅ Veritabanı bağlantısı kuruldu")
        await perform_startup_checks()

    @app.on_event("shutdown")
    async def shutdown():
        logger.info("🛑 Uygulama kapatılıyor...")
        await db_manager.close()
        logger.info("💤 Veritabanı bağlantısı kapatıldı")


async def perform_startup_checks():
    """Başlangıç kontrolleri"""
    try:
        await db_manager.main_db.command("ping")
        required = ["tenants", "users"]
        existing = await db_manager.main_db.list_collection_names()
        for col in required:
            if col not in existing:
                logger.error(f"Gerekli koleksiyon eksik: {col}")
                raise RuntimeError(f"Gerekli koleksiyon bulunamadı: {col}")
    except Exception as e:
        logger.critical(f"🚨 Başlangıç kontrol hatası: {str(e)}")
        raise


app = create_application()

@app.get("/health")
async def health_check():
    """Sağlık kontrolü endpoint'i"""
    try:
        # MongoDB bağlantısını kontrol et
        await db_manager.main_db.command("ping")
        # Redis bağlantısını kontrol et (örnek)
        # await redis_client.ping()
        return {"status": "ok", "services": {"mongodb": "ok", "redis": "ok"}}
    except Exception as e:
        logger.error(f"Sağlık kontrolü başarısız: {str(e)}", exc_info=True)
        return {"status": "error", "details": str(e)}

if __name__ == "__main__":
    uvicorn.run(
        "app.main:app",
        host=getattr(settings, "UVICORN_HOST", "127.0.0.1"),
        port=getattr(settings, "UVICORN_PORT", 8000),
        reload=getattr(settings, "UVICORN_RELOAD", False),
        workers=getattr(settings, "UVICORN_WORKERS", 1),
        log_level=getattr(settings, "LOG_LEVEL", "info").lower(),
        proxy_headers=getattr(settings, "UVICORN_PROXY_HEADERS", True),
        timeout_keep_alive=getattr(settings, "UVICORN_KEEP_ALIVE", 60)
    )
