from datetime import datetime, timezone
from bson import ObjectId
import re
from fastapi import HTTPException, status
from pymongo.errors import DuplicateKeyError
from app.schemas.tenant_schema import TenantCreate, TenantOut, TenantList, TenantUpdate
from app.utils.database import db_manager, COLLECTIONS
from app.utils.logger import logger
from typing import List, Optional, Dict, Any


class TenantService:
    """Tenant (Firma) yönetimi için servis sınıfı"""
    
    MAX_DB_NAME_LENGTH = 64

    @staticmethod
    def _sanitize_database_name(company_name: str) -> str:
        """Şirket adından veritabanı ismi oluşturur"""
        normalized = re.sub(r"[^\w]+", "_", company_name.lower())
        return normalized.strip("_")[:TenantService.MAX_DB_NAME_LENGTH]

    @classmethod
    async def create_tenant(cls, data: TenantCreate) -> TenantOut:
        """Yeni bir tenant (firma) oluşturur
        
        Args:
            data: Tenant oluşturma verileri
            
        Returns:
            Oluşturulan tenant bilgisi
            
        Raises:
            HTTPException: Tenant oluşturulurken hata oluşursa
        """
        try:
            # Veritabanı adı oluştur
            db_name = cls._sanitize_database_name(data.company_name)
            
            tenant_data = {
                **data.dict(),
                "database_name": db_name,
                "created_at": datetime.now(timezone.utc),
                "is_active": True
            }
            
            async with await db_manager.client.start_session() as session:
                async with session.start_transaction():
                    result = await db_manager.main_db[COLLECTIONS.TENANTS].insert_one(
                        tenant_data,
                        session=session
                    )
                    
                    await cls._initialize_tenant_infrastructure(db_name, session)
                    
                    return TenantOut(
                        **tenant_data,
                        id=str(result.inserted_id)
                    )
                    
        except DuplicateKeyError:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Firma bilgileri zaten kayıtlı"
            )
        except Exception as e:
            logger.error("Tenant oluşturma hatası: %s", str(e))
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Firma oluşturulamadı"
            )

    @classmethod
    async def _initialize_tenant_infrastructure(cls, db_name: str, session=None) -> None:
        """Tenant için gerekli veritabanı altyapısını oluşturur
        
        Args:
            db_name: Tenant veritabanı adı
            session: MongoDB session objesi
        """
        tenant_db = db_manager.client[db_name]
        
        # Koleksiyonlar ve indexler oluşturuluyor
        collections_config = {
            COLLECTIONS.USERS: [
                [("email", 1), {"unique": True}]
            ],
            COLLECTIONS.PROJECTS: [
                [("tenant_id", 1)]
            ]
        }
        
        for collection_name, indexes in collections_config.items():
            await tenant_db[collection_name].create_indexes(indexes, session=session)

    @classmethod
    async def list_tenants(cls, page: int = 1, size: int = 10, query: Optional[dict] = None) -> List[Dict[str, Any]]:
        """Tenant listesini sayfalandırılmış olarak getirir
        
        Args:
            page: Sayfa numarası
            size: Sayfa başına kayıt sayısı
            query: Filtre sorgusu
            
        Returns:
            Tenant listesi
        """
        query = query or {}
        skip = (page - 1) * size

        cursor = db_manager.main_db[COLLECTIONS.TENANTS].find(query).skip(skip).limit(size)
        return [doc async for doc in cursor]

    @classmethod
    async def count_tenants(cls, query: Optional[dict] = None) -> int:
        """Tenant sayısını getirir
        
        Args:
            query: Filtre sorgusu
            
        Returns:
            Tenant sayısı
        """
        query = query or {}
        return await db_manager.main_db[COLLECTIONS.TENANTS].count_documents(query)
    
    @classmethod
    async def get_tenant_by_id(cls, tenant_id: str) -> Dict[str, Any]:
        """ID'ye göre tenant bilgisi getirir
        
        Args:
            tenant_id: Tenant ID (ObjectId string)
            
        Returns:
            Tenant bilgisi sözlüğü
        """
        return await db_manager.main_db[COLLECTIONS.TENANTS].find_one({"_id": ObjectId(tenant_id)})

    @classmethod
    async def update_tenant_status(cls, tenant_id: str, is_active: bool) -> Dict[str, Any]:
        """Tenant aktif/pasif durumunu günceller
        
        Args:
            tenant_id: Tenant ID (ObjectId string)
            is_active: Yeni durum (True/False)
            
        Returns:
            Güncellenmiş tenant bilgisi
        """
        result = await db_manager.main_db[COLLECTIONS.TENANTS].find_one_and_update(
            {"_id": ObjectId(tenant_id)},
            {"$set": {"is_active": is_active}},
            return_document=True
        )
        return result

    @classmethod
    async def update_tenant(cls, tenant_id: str, update_data: dict) -> Dict[str, Any]:
        """Tenant bilgilerini günceller
        
        Args:
            tenant_id: Tenant ID (ObjectId string)
            update_data: Güncellenecek veriler
            
        Returns:
            Güncellenmiş tenant bilgisi
            
        Raises:
            HTTPException: Tenant bulunamazsa
        """
        result = await db_manager.main_db[COLLECTIONS.TENANTS].find_one_and_update(
            {"_id": ObjectId(tenant_id)},
            {"$set": update_data},
            return_document=True
        )
        if not result:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Firma bulunamadı"
            )
        return result