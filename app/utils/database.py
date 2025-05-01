from motor.motor_asyncio import AsyncIOMotorClient, AsyncIOMotorDatabase
from app.core.config import settings
from contextlib import asynccontextmanager
from typing import AsyncGenerator, Optional, Dict, Any
import logging
from enum import Enum

logger = logging.getLogger(__name__)

# Koleksiyon sabitleri - tüm sistem genelinde kullanılır
class COLLECTIONS(str, Enum):
    TENANTS = "tenants"
    USERS = "users"
    PROJECTS = "projects"
    EXPENSES = "expenses"
    MATERIALS = "materials"
    ISSUES = "issues"
    DEPENDENCIES = "dependencies"
    SUBCONTRACTORS = "subcontractors"
    CLIENTS = "clients"
    DOCUMENTS = "documents"
    RATE_LIMITS = "rate_limits"
    TOKEN_BLACKLIST = "token_blacklist"
    SETTINGS = "settings"  # Her tenant'ın kendi ayarları için


class DatabaseManager:
    def __init__(self):
        self.client = None
        self.main_db = None
        self._db_cache: Dict[str, AsyncIOMotorDatabase] = {}
        self._connected = False

    async def connect(self):
        """MongoDB'ye asenkron bağlantı kurar"""
        if self._connected:
            return
            
        try:
            self.client = AsyncIOMotorClient(
                settings.MONGO_URI,
                maxPoolSize=settings.MONGO_MAX_POOL_SIZE,
                minPoolSize=5,
                serverSelectionTimeoutMS=5000,
                tlsInsecure=True if getattr(settings, "MONGO_TLS", False) else False
            )
            await self.client.server_info()  # Bağlantıyı test et
            self.main_db = self.client[settings.MONGO_DB_NAME]
            self._connected = True
            logger.info("MongoDB bağlantısı başarılı")
        except Exception as e:
            logger.error(f"MongoDB bağlantı hatası: {e}")
            raise

    async def close(self):
        """Bağlantıyı kapat"""
        if self.client:
            self.client.close()
            self._connected = False
            self._db_cache.clear()
            logger.info("MongoDB bağlantısı kapatıldı")

    def get_db(self, db_name: str) -> AsyncIOMotorDatabase:
        """
        İsimle veritabanına erişim sağlar.
        
        Args:
            db_name: Veritabanı adı
            
        Returns:
            AsyncIOMotorDatabase: Veritabanı nesnesi
        """
        if not self._connected:
            raise RuntimeError("DatabaseManager bağlantısı kurulmadan önce veritabanı erişimi denemesi")
            
        if db_name not in self._db_cache:
            self._db_cache[db_name] = self.client[db_name]
            
        return self._db_cache[db_name]

    @asynccontextmanager
    async def tenant_db_context(self, tenant_db_name: str) -> AsyncGenerator[AsyncIOMotorDatabase, None]:
        """
        Tenant veritabanı için context manager.
        Otomatik kaynak yönetimi sağlar.
        
        Kullanım:
        async with db_manager.tenant_db_context("tenant_123") as db:
            await db[COLLECTIONS.USERS].find_one(...)
        """
        if not self._connected:
            await self.connect()
            
        try:
            db = self.get_db(tenant_db_name)
            yield db
        except Exception as e:
            logger.error(f"Tenant DB hatası: {tenant_db_name}: {e}")
            raise

    async def validate_connection(self) -> bool:
        """
        Veritabanı bağlantısının hala geçerli olduğunu kontrol eder.
        Geçersizse yeniden bağlanmayı dener.
        
        Returns:
            bool: Bağlantı durumu
        """
        try:
            if not self._connected:
                await self.connect()
                return True
                
            await self.client.server_info()
            return True
        except Exception as e:
            logger.warning(f"Veritabanı bağlantısı geçersiz, yeniden bağlanılıyor: {e}")
            self._connected = False
            await self.connect()
            return self._connected

# Singleton instance
db_manager = DatabaseManager()