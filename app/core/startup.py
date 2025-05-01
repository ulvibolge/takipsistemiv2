"""
Startup Module - Uygulama Başlangıç ve Kapanış İşlemleri
--------------------------------------------------------
Bu modül, FastAPI uygulamasının başlangıç (startup) ve kapanış (shutdown) 
olaylarını yönetir.

✅ Veritabanı bağlantılarının kurulması ve kapatılması
✅ MongoDB koleksiyonları için indekslerin oluşturulması
✅ Süresi dolmuş token'ların temizlenmesi için zamanlanmış görevler
✅ Sistem durumu kontrolü ve performans metriklerinin başlatılması
✅ Uygulamaya özel middleware'lerin eklenmesi

Geliştirici Notu:
Bu modül, uygulama başlatıldığında ve kapatıldığında çalışacak olan
fonksiyonları içerir. Uygulama başlangıcında gerekli tüm kaynaklar
ve bağlantılar oluşturulur, kapanışta ise kaynaklar temizlenir.
"""

import asyncio
import logging
from datetime import datetime, timedelta, timezone
from fastapi import FastAPI, Request, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.gzip import GZipMiddleware
from fastapi.responses import JSONResponse
from typing import List, Dict, Any, Callable

from app.utils.database import db_manager, COLLECTIONS
from app.core.config import settings
from app.utils.logger import logger

# Zamanlanmış görevler için global değişken
background_tasks = set()
 
app = FastAPI(
    title=settings.APP_NAME,
    description="Proje ve iş takip sistemi API'si",
    version="1.0.0",
    docs_url=settings.DOCS_URL,
    redoc_url=settings.REDOC_URL,
    openapi_url="/openapi.json" if settings.DEBUG else None
)

# CORS middleware ekleme
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Sıkıştırma middleware'i (büyük yanıtlar için)
app.add_middleware(GZipMiddleware, minimum_size=1000)

# Global hata yakalama middleware'i
@app.middleware("http")
async def catch_exceptions_middleware(request: Request, call_next: Callable):
    try:
        return await call_next(request)
    except Exception as e:
        logger.exception(f"Beklenmeyen hata: {str(e)}")
        # Hata yanıtı döndür ama hata detaylarını gizle
        return JSONResponse(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            content={"detail": "Sunucu hatası. Lütfen daha sonra tekrar deneyin."}
        )

# Performans ölçüm middleware'i
@app.middleware("http")
async def add_process_time_header(request: Request, call_next: Callable):
    start_time = datetime.now()
    response = await call_next(request)
    process_time = (datetime.now() - start_time).total_seconds()
    response.headers["X-Process-Time"] = str(process_time)
    return response

# Süresi dolmuş token'ları temizleme görevi
async def cleanup_expired_tokens():
    while True:
        try:
            logger.info("Süresi dolmuş token'lar temizleniyor...")
            current_time = datetime.now(timezone.utc)
            
            # Süresi dolmuş tokenları bul ve sil
            result = await db_manager.main_db[COLLECTIONS.TOKEN_BLACKLIST].delete_many(
                {"expires_at": {"$lt": current_time}}
            )
            
            logger.info(f"{result.deleted_count} adet süresi dolmuş token temizlendi")
            
            # 24 saat bekle
            await asyncio.sleep(86400)  # 24 saat = 86400 saniye
        except Exception as e:
            logger.exception(f"Token temizleme görevi hatası: {str(e)}")
            await asyncio.sleep(3600)  # Hata durumunda 1 saat bekle ve tekrar dene

# Veritabanı indekslerini oluşturma işlevi
async def create_database_indexes():
    """Tüm veritabanları için gerekli indeksleri oluşturur"""
    try:
        logger.info("Veritabanı indeksleri oluşturuluyor...")
        
        # Ana veritabanı indeksleri
        # Firma adına göre benzersiz indeks
        await db_manager.main_db[COLLECTIONS.TENANTS].create_index("company_name", unique=True)
        
        # Token blacklist indeksi (hızlı arama için)
        await db_manager.main_db[COLLECTIONS.TOKEN_BLACKLIST].create_index("token")
        
        # Süresi dolan blacklist tokenları için TTL indeksi
        await db_manager.main_db[COLLECTIONS.TOKEN_BLACKLIST].create_index(
            "expires_at", expireAfterSeconds=0
        )
        
        # Örnek bir tenant veritabanı (geliştirme/test için)
        demo_db = db_manager.client["tenant_demo"]

        # Index: Projelerde firma + durum filtreleme
        await demo_db[COLLECTIONS.PROJECTS].create_index(
            [("firma_id", 1), ("status", 1)]
        )

        # Index: Masraf tarih sıralı listeleme
        await demo_db[COLLECTIONS.EXPENSES].create_index(
            [("proje_id", 1), ("date", -1)]
        )
        
        # Kullanıcılar için e-posta ve tenant_id kompozit indeksi
        await demo_db[COLLECTIONS.USERS].create_index(
            [("email", 1), ("tenant_id", 1)],
            unique=True
        )
        
        # Belge arama için indeks
        await demo_db[COLLECTIONS.DOCUMENTS].create_index(
            [("proje_id", 1), ("tur", 1)]
        )
        
        logger.info("Tüm veritabanı indeksleri başarıyla oluşturuldu")
    except Exception as e:
        logger.exception(f"Veritabanı indeksleri oluşturulurken hata: {str(e)}")
        # Bu kritik bir hata olduğu için uygulamayı sonlandırma seçeneğini düşünebilirsiniz
        # Ancak bu örnekte sadece log'luyoruz

# Uygulama durumu kontrolü görevi
async def health_check():
    while True:
        try:
            # Veritabanı bağlantısını kontrol et
            await db_manager.validate_connection()
            logger.debug("Sağlık kontrolü: Sistem çalışıyor")
            
            # 5 dakika bekle
            await asyncio.sleep(300)
        except Exception as e:
            logger.error(f"Sağlık kontrolü hatası: {str(e)}")
            await asyncio.sleep(60)  # Hata durumunda 1 dakika bekle ve tekrar dene

# Zamanlanmış görevi başlat
async def start_background_task(coroutine):
    task = asyncio.create_task(coroutine())
    background_tasks.add(task)
    task.add_done_callback(background_tasks.discard)

@app.on_event("startup")
async def startup_event():
    """
    Uygulama başlatıldığında çalışan fonksiyon.
    Veritabanı bağlantılarını kurar ve gerekli başlangıç işlemlerini yapar.
    """
    logger.info(f"{settings.APP_NAME} başlatılıyor... Ortam: {settings.APP_ENV}")
    
    # Veritabanı bağlantısını kur
    await db_manager.connect()
    logger.info("Veritabanı bağlantısı kuruldu")
    
    # Veritabanı indekslerini oluştur
    await create_database_indexes()
    
    # Arka plan görevlerini başlat
    await start_background_task(cleanup_expired_tokens)
    await start_background_task(health_check)
    
    logger.info(f"{settings.APP_NAME} başarıyla başlatıldı! 🚀")
    if settings.DEBUG:
        logger.warning("DİKKAT: Uygulama DEBUG modunda çalışıyor. Üretim ortamında DEBUG=False yapın!")

@app.on_event("shutdown")
async def shutdown_event():
    """
    Uygulama kapatıldığında çalışan fonksiyon.
    Kaynakları temizler ve bağlantıları düzgün şekilde kapatır.
    """
    logger.info(f"{settings.APP_NAME} kapatılıyor...")
    
    # Tüm zamanlanmış görevleri iptal et
    for task in background_tasks:
        task.cancel()
    
    # Veritabanı bağlantısını kapat
    await db_manager.close()
    logger.info("Veritabanı bağlantısı kapatıldı")
    
    logger.info(f"{settings.APP_NAME} güvenli bir şekilde kapatıldı")