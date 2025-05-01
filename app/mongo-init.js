/**
 * TAKİP SİSTEMİ - MongoDB Kurulum Scripti v3.0
 * -------------------------------------------
 * Bu script, Takip Sistemi için MongoDB veritabanı yapılandırmasını otomatik olarak gerçekleştirir.
 * 
 * Özellikler:
 * - Ortam değişkenlerinden yapılandırma okuma
 * - Admin ve uygulama kullanıcılarını oluşturma
 * - Şema doğrulama (JSON Schema Validation) ile veri bütünlüğü sağlama
 * - Koleksiyon oluşturma ve indeksleme
 * - Başlangıç verilerini (seed data) yükleme
 * - Çoklu kiracı (multi-tenant) desteği
 * - İşlem durumlarını loglama
 * - Kurulum sağlık kontrolü
 */

// Yapılandırma ayarları - Ortam değişkenlerinden alınır
const config = {
  db: {
    main: process.env.MONGO_DB_NAME || "takip_db",
    user: process.env.MONGO_USER || "takip_user",
    pass: process.env.MONGO_PASSWORD || "StrongPass123!",
    adminUser: process.env.MONGO_INITDB_ROOT_USERNAME || "admin",
    adminPass: process.env.MONGO_INITDB_ROOT_PASSWORD || "admin123",
    transactionTimeoutMS: parseInt(process.env.MONGO_INITDB_TRANSACTION_TIMEOUT) || 30000,
    maxRetries: parseInt(process.env.MONGO_INITDB_MAX_RETRIES) || 5
  },
  tenants: {
    prefix: process.env.DEFAULT_TENANT_DB_PREFIX || "tenant_",
    initial: ["demo"], // Başlangıçta oluşturulacak örnek tenant veritabanları
  },
  options: {
    enableSSL: process.env.MONGO_SSL === "true", 
    replicaSet: process.env.MONGO_REPLICA_SET || null,
    sharding: process.env.MONGO_SHARDING === "true",
    wiredTigerCompression: process.env.MONGO_COMPRESSION || "zstd" // zstd, snappy, none
  },
  app: {
    version: "3.0.0",
    environment: process.env.APP_ENV || "development"
  }
};

/**
 * Veritabanı kullanıcılarını oluşturur
 */
function initializeDatabaseUsers() {
  const adminDb = db.getSiblingDB('admin');
  let adminCreated = false;

  // Admin kullanıcısını oluştur
  const existingAdminUser = adminDb.getUser(config.db.adminUser);
  if (!existingAdminUser) {
    try {
      adminDb.createUser({
        user: config.db.adminUser,
        pwd: config.db.adminPass,
        roles: [
          { role: "root", db: "admin" },
          { role: "userAdminAnyDatabase", db: "admin" },
          { role: "dbAdminAnyDatabase", db: "admin" },
          { role: "readWriteAnyDatabase", db: "admin" }
        ]
      });
      adminCreated = true;
      print(`✅ Admin kullanıcısı '${config.db.adminUser}' oluşturuldu`);
    } catch (error) {
      print(`❌ Admin kullanıcı oluşturma hatası: ${error.message}`);
      throw error;
    }
  } else {
    print(`ℹ️ Admin kullanıcı '${config.db.adminUser}' zaten mevcut`);
  }

  // Ana veritabanını ve uygulama kullanıcısını oluştur
  const mainDb = db.getSiblingDB(config.db.main);
  const existingAppUser = mainDb.getUser(config.db.user);
  
  if (!existingAppUser) {
    try {
      mainDb.createUser({
        user: config.db.user,
        pwd: config.db.pass,
        roles: [
          { role: "readWrite", db: config.db.main },
          { role: "dbAdmin", db: config.db.main }
        ]
      });
      print(`✅ Uygulama kullanıcısı '${config.db.user}' oluşturuldu`);
    } catch (error) {
      print(`❌ Uygulama kullanıcısı oluşturma hatası: ${error.message}`);
      throw error;
    }
  } else {
    print(`ℹ️ Uygulama kullanıcısı '${config.db.user}' zaten mevcut`);
  }

  // Yeni admin kullanıcısı oluşturulduysa, oturum açarak devam et
  if (adminCreated) {
    adminDb.auth(config.db.adminUser, config.db.adminPass);
  }

  return { adminDb, mainDb };
}

/**
 * Ana koleksiyon şemalarını tanımlar
 */
const mainCollectionSchemas = {
  // Firmalar (Tenants) koleksiyonu
  tenants: {
    validator: {
      $jsonSchema: {
        bsonType: "object",
        required: ["company_name", "database_name", "is_active"],
        properties: {
          company_name: {
            bsonType: "string",
            description: "Firma adı"
          },
          database_name: {
            bsonType: "string",
            description: "Firma veritabanı adı"
          },
          license_type: {
            enum: ["basic", "professional", "enterprise"],
            description: "Lisans tipi"
          },
          max_users: {
            bsonType: "int",
            minimum: 1,
            description: "Maksimum kullanıcı sayısı"
          },
          is_active: {
            bsonType: "bool",
            description: "Firma hesabı aktif mi?"
          },
          contact_email: {
            bsonType: "string",
            pattern: "^\\S+@\\S+\\.\\S+$",
            description: "İletişim e-postası"
          },
          created_at: {
            bsonType: "date",
            description: "Oluşturulma tarihi"
          },
          expire_date: {
            bsonType: "date",
            description: "Lisans bitiş tarihi"
          }
        }
      }
    },
    indexes: [
      { key: { company_name: 1 }, options: { unique: true, name: "company_name_unique_idx" } },
      { key: { database_name: 1 }, options: { unique: true, name: "database_name_unique_idx" } },
      { key: { is_active: 1 }, options: { name: "is_active_idx" } },
      { key: { license_type: 1 }, options: { name: "license_type_idx" } },
      { key: { expire_date: 1 }, options: { name: "expire_date_idx" } }
    ],
    initialData: [
      {
        company_name: "Demo Firma",
        database_name: "tenant_demo",
        license_type: "professional",
        max_users: 10,
        is_active: true,
        contact_email: "demo@example.com",
        created_at: new Date(),
        expire_date: new Date(new Date().setFullYear(new Date().getFullYear() + 1)) // 1 yıl geçerli
      }
    ]
  },
  
  // Token Blacklist koleksiyonu
  token_blacklist: {
    validator: {
      $jsonSchema: {
        bsonType: "object",
        required: ["token", "blacklisted_at", "expires_at"],
        properties: {
          token: {
            bsonType: "string",
            description: "JWT token"
          },
          user_id: {
            bsonType: "string",
            description: "Kullanıcı ID"
          },
          blacklisted_at: {
            bsonType: "date",
            description: "Token'ın blacklist'e eklendiği tarih"
          },
          expires_at: {
            bsonType: "date",
            description: "Token'ın sona erme tarihi"
          },
          reason: {
            enum: ["logout", "password_change", "security_breach", "user_disabled"],
            description: "Blacklist nedeni"
          }
        }
      }
    },
    indexes: [
      { key: { token: 1 }, options: { unique: true, name: "token_unique_idx" } },
      { key: { expires_at: 1 }, options: { expireAfterSeconds: 0, name: "token_ttl_idx" } },
      { key: { user_id: 1 }, options: { name: "user_id_idx" } }
    ]
  },
  
  // Sistem ayarları koleksiyonu
  system_settings: {
    validator: {
      $jsonSchema: {
        bsonType: "object",
        required: ["key", "value"],
        properties: {
          key: {
            bsonType: "string",
            description: "Ayar anahtarı"
          },
          value: {
            description: "Ayar değeri"
          },
          description: {
            bsonType: "string",
            description: "Ayarın açıklaması"
          },
          updated_at: {
            bsonType: "date",
            description: "Son güncelleme tarihi"
          }
        }
      }
    },
    indexes: [
      { key: { key: 1 }, options: { unique: true, name: "key_unique_idx" } }
    ],
    initialData: [
      {
        key: "system_version",
        value: config.app.version,
        description: "Sistem sürümü",
        updated_at: new Date()
      },
      {
        key: "maintenance_mode",
        value: false,
        description: "Bakım modu",
        updated_at: new Date()
      }
    ]
  },
  
  // Sistem logları koleksiyonu
  system_logs: {
    validator: {
      $jsonSchema: {
        bsonType: "object",
        required: ["level", "message", "timestamp"],
        properties: {
          level: {
            enum: ["INFO", "WARNING", "ERROR", "CRITICAL"],
            description: "Log seviyesi"
          },
          message: {
            bsonType: "string",
            description: "Log mesajı"
          },
          timestamp: {
            bsonType: "date",
            description: "Log zamanı"
          },
          source: {
            bsonType: "string",
            description: "Log kaynağı"
          },
          details: {
            bsonType: "object",
            description: "Ek detaylar"
          }
        }
      }
    },
    options: {
      capped: true,
      size: 5242880, // 5MB
      max: 10000
    },
    indexes: [
      { key: { timestamp: -1 }, options: { name: "timestamp_idx" } },
      { key: { level: 1 }, options: { name: "level_idx" } }
    ]
  }
};

/**
 * Tenant veritabanı koleksiyon şemalarını tanımlar
 */
const tenantCollectionSchemas = {
  // Kullanıcılar koleksiyonu
  users: {
    validator: {
      $jsonSchema: {
        bsonType: "object",
        required: ["email", "password_hash", "tenant_id", "role", "is_active"],
        properties: {
          email: {
            bsonType: "string",
            pattern: "^\\S+@\\S+\\.\\S+$",
            description: "Kullanıcı e-posta adresi"
          },
          password_hash: {
            bsonType: "string",
            minLength: 60,
            description: "Bcrypt ile hashlenmiş şifre"
          },
          tenant_id: {
            bsonType: "string",
            description: "Bağlı olduğu firma ID"
          },
          role: {
            enum: ["admin", "manager", "user", "client", "viewer"],
            description: "Kullanıcı rolü"
          },
          permissions: {
            bsonType: "array",
            items: {
              bsonType: "string"
            },
            description: "Kullanıcı izinleri"
          },
          full_name: {
            bsonType: "string",
            description: "Kullanıcının tam adı"
          },
          is_active: {
            bsonType: "bool",
            description: "Kullanıcı aktif mi?"
          },
          last_login: {
            bsonType: "date",
            description: "Son giriş tarihi"
          },
          created_at: {
            bsonType: "date",
            description: "Oluşturulma tarihi"
          }
        }
      }
    },
    indexes: [
      { key: { email: 1, tenant_id: 1 }, options: { unique: true, name: "email_tenant_unique_idx" } },
      { key: { role: 1 }, options: { name: "role_idx" } },
      { key: { is_active: 1 }, options: { name: "is_active_idx" } }
    ],
    initialData: [
      {
        email: "admin@demo.com",
        password_hash: "$2b$12$uZWT7ayXjUbBNmb82dt6/ub3XDyUBH40bJdCKKU7J6HqSyT1oC3we", // "admin123" bcrypt hash
        tenant_id: "tenant_demo",
        role: "admin",
        permissions: ["admin"],
        full_name: "Demo Admin",
        is_active: true,
        created_at: new Date(),
        last_login: null
      },
      {
        email: "user@demo.com",
        password_hash: "$2b$12$uZWT7ayXjUbBNmb82dt6/ub3XDyUBH40bJdCKKU7J6HqSyT1oC3we", // "admin123" bcrypt hash
        tenant_id: "tenant_demo",
        role: "user",
        permissions: ["project_read", "project_create"],
        full_name: "Demo Kullanıcı",
        is_active: true,
        created_at: new Date(),
        last_login: null
      }
    ]
  },
  
  // Projeler koleksiyonu
  projects: {
    validator: {
      $jsonSchema: {
        bsonType: "object",
        required: ["name", "status", "tenant_id"],
        properties: {
          name: { 
            bsonType: "string",
            description: "Proje adı"
          },
          status: { 
            enum: ["active", "pending", "completed", "cancelled", "archived"],
            description: "Proje durumu"
          },
          tenant_id: {
            bsonType: "string",
            description: "Bağlı olduğu firma ID"
          },
          firma_id: {
            bsonType: "string",
            description: "Müşteri firma ID"
          },
          description: {
            bsonType: "string",
            description: "Proje açıklaması"
          },
          start_date: {
            bsonType: "date",
            description: "Başlangıç tarihi"
          },
          end_date: {
            bsonType: "date",
            description: "Bitiş tarihi"
          },
          budget: {
            bsonType: "double",
            description: "Proje bütçesi"
          },
          assigned_personnel: {
            bsonType: "array",
            items: {
              bsonType: "string"
            },
            description: "Atanmış personel ID'leri"
          },
          manager_id: {
            bsonType: "string",
            description: "Proje yöneticisi ID"
          }
        }
      }
    },
    indexes: [
      { key: { name: 1, tenant_id: 1 }, options: { unique: true, name: "name_tenant_unique_idx" } },
      { key: { status: 1 }, options: { name: "status_idx" } },
      { key: { firma_id: 1, status: 1 }, options: { name: "firma_status_idx" } },
      { key: { manager_id: 1 }, options: { name: "manager_idx" } }
    ]
  },
  
  // Masraflar koleksiyonu
  expenses: {
    validator: {
      $jsonSchema: {
        bsonType: "object",
        required: ["proje_id", "amount", "date", "tenant_id"],
        properties: {
          proje_id: {
            bsonType: "string",
            description: "Bağlı olduğu proje ID"
          },
          tenant_id: {
            bsonType: "string",
            description: "Bağlı olduğu firma ID"
          },
          amount: {
            bsonType: "double",
            minimum: 0,
            description: "Masraf tutarı"
          },
          date: {
            bsonType: "date",
            description: "Masraf tarihi"
          },
          description: {
            bsonType: "string",
            description: "Masraf açıklaması"
          },
          category: {
            bsonType: "string",
            description: "Masraf kategorisi"
          },
          approved: {
            bsonType: "bool",
            description: "Onay durumu"
          },
          approved_by: {
            bsonType: "string",
            description: "Onaylayan kullanıcı ID"
          },
          document_ids: {
            bsonType: "array",
            items: {
              bsonType: "string"
            },
            description: "İlgili belge ID'leri"
          }
        }
      }
    },
    indexes: [
      { key: { proje_id: 1, date: -1 }, options: { name: "project_date_idx" } },
      { key: { approved: 1 }, options: { name: "approved_idx" } },
      { key: { category: 1 }, options: { name: "category_idx" } }
    ]
  },
  
  // Belgeler koleksiyonu
  documents: {
    validator: {
      $jsonSchema: {
        bsonType: "object",
        required: ["filename", "proje_id", "tur", "tenant_id"],
        properties: {
          filename: {
            bsonType: "string",
            description: "Dosya adı"
          },
          proje_id: {
            bsonType: "string",
            description: "Bağlı olduğu proje ID"
          },
          tenant_id: {
            bsonType: "string",
            description: "Bağlı olduğu firma ID"
          },
          tur: {
            enum: ["sozlesme", "rapor", "fatura", "resim", "diger"],
            description: "Belge türü"
          },
          upload_date: {
            bsonType: "date",
            description: "Yükleme tarihi"
          },
          uploaded_by: {
            bsonType: "string",
            description: "Yükleyen kullanıcı ID"
          },
          file_size: {
            bsonType: "int",
            description: "Dosya boyutu (byte)"
          },
          mime_type: {
            bsonType: "string",
            description: "Dosya MIME tipi"
          },
          storage_path: {
            bsonType: "string",
            description: "Depolama yolu"
          }
        }
      }
    },
    indexes: [
      { key: { proje_id: 1, tur: 1 }, options: { name: "project_type_idx" } },
      { key: { upload_date: -1 }, options: { name: "upload_date_idx" } }
    ]
  },
  
  // Tenant-spesifik ayarlar koleksiyonu
  settings: {
    validator: {
      $jsonSchema: {
        bsonType: "object",
        required: ["tenant_id"],
        properties: {
          tenant_id: {
            bsonType: "string",
            description: "Bağlı olduğu firma ID"
          },
          require_customer_approval: {
            bsonType: "bool",
            description: "Müşteri onayı gerekli mi?"
          },
          document_upload_required: {
            bsonType: "bool",
            description: "Belge yükleme zorunlu mu?"
          },
          document_types_required: {
            bsonType: "array",
            items: {
              bsonType: "string"
            },
            description: "Zorunlu belge türleri"
          },
          nfc_tracking_enabled: {
            bsonType: "bool",
            description: "NFC takibi etkin mi?"
          },
          require_material_before_start: {
            bsonType: "bool",
            description: "İş başlatmadan önce malzeme gerekli mi?"
          },
          allowed_roles_for_project_create: {
            bsonType: "array",
            items: {
              bsonType: "string"
            },
            description: "Proje oluşturma izinli roller"
          },
          allowed_roles_for_expense_create: {
            bsonType: "array",
            items: {
              bsonType: "string"
            },
            description: "Masraf oluşturma izinli roller"
          }
        }
      }
    },
    indexes: [
      { key: { tenant_id: 1 }, options: { unique: true, name: "tenant_id_unique_idx" } }
    ],
    initialData: [
      {
        tenant_id: "tenant_demo",
        require_customer_approval: false,
        document_upload_required: false,
        document_types_required: ["sozlesme"],
        nfc_tracking_enabled: false,
        require_material_before_start: true,
        allowed_roles_for_project_create: ["admin", "manager"],
        allowed_roles_for_expense_create: ["admin", "manager", "user"]
      }
    ]
  }
};

/**
 * Koleksiyonları oluşturur ve indekslerini ayarlar
 */
function createCollections(targetDb, collectionSchemas, dbName) {
  const session = targetDb.getMongo().startSession();
  session.startTransaction({
    readConcern: { level: "majority" },
    writeConcern: { w: "majority" },
    maxTransactionLockRequestTimeoutMillis: config.db.transactionTimeoutMS
  });

  try {
    print(`🔄 ${dbName} veritabanında koleksiyonlar oluşturuluyor...`);
    
    for (const [collName, schema] of Object.entries(collectionSchemas)) {
      // Koleksiyon varsa atla, yoksa oluştur
      if (targetDb.getCollectionNames().includes(collName)) {
        print(`  ℹ️ '${collName}' koleksiyonu zaten mevcut, atlanıyor`);
        continue;
      }
      
      // Koleksiyon oluşturma seçenekleri
      const options = {
        validator: schema.validator,
        validationLevel: "moderate", // strict, moderate veya off
        validationAction: "error"    // error veya warn
      };
      
      // Ek koleksiyon seçenekleri (capped, vb.)
      if (schema.options) {
        Object.assign(options, schema.options);
      }
      
      // WiredTiger için sıkıştırma seçenekleri
      if (config.options.wiredTigerCompression !== "none") {
        options.storageEngine = { 
          wiredTiger: { 
            configString: `block_compressor=${config.options.wiredTigerCompression}` 
          } 
        };
      }

      // Koleksiyonu oluştur
      targetDb.createCollection(collName, options);
      print(`  ✅ '${collName}' koleksiyonu oluşturuldu`);

      // İndeksleri ekle
      if (schema.indexes) {
        schema.indexes.forEach(idx => {
          try {
            targetDb[collName].createIndex(idx.key, idx.options);
          } catch (error) {
            print(`  ⚠️ '${collName}' koleksiyonunda indeks oluşturma hatası: ${error.message}`);
          }
        });
        print(`  ✅ '${collName}' için ${schema.indexes.length} indeks oluşturuldu`);
      }

      // Başlangıç verilerini ekle
      if (schema.initialData && schema.initialData.length > 0) {
        try {
          targetDb[collName].insertMany(schema.initialData);
          print(`  ✅ '${collName}' için ${schema.initialData.length} başlangıç verisi eklendi`);
        } catch (error) {
          print(`  ⚠️ '${collName}' başlangıç verisi ekleme hatası: ${error.message}`);
        }
      }
    }

    session.commitTransaction();
    print(`✅ ${dbName} veritabanında koleksiyon oluşturma işlemi tamamlandı`);
    return true;
  } catch (error) {
    session.abortTransaction();
    print(`❌ ${dbName} veritabanında koleksiyon oluşturma hatası: ${error.message}`);
    return false;
  } finally {
    session.endSession();
  }
}

/**
 * Tenant veritabanlarını oluşturur
 */
function initializeTenantDatabases() {
  const allTenants = config.tenants.initial;
  const results = [];
  
  for (const tenant of allTenants) {
    const tenantDbName = `${config.tenants.prefix}${tenant}`;
    const tenantDb = db.getSiblingDB(tenantDbName);
    
    print(`\n🔄 '${tenantDbName}' tenant veritabanı hazırlanıyor...`);
    
    // Tenant veritabanı için kullanıcı oluştur
    try {
      const existingUser = tenantDb.getUser(config.db.user);
      if (!existingUser) {
        tenantDb.createUser({
          user: config.db.user,
          pwd: config.db.pass,
          roles: [
            { role: "readWrite", db: tenantDbName },
            { role: "dbAdmin", db: tenantDbName }
          ]
        });
        print(`✅ '${tenantDbName}' için uygulama kullanıcısı oluşturuldu`);
      } else {
        print(`ℹ️ '${tenantDbName}' için uygulama kullanıcısı zaten mevcut`);
      }
    } catch (error) {
      print(`❌ '${tenantDbName}' için kullanıcı oluşturma hatası: ${error.message}`);
      continue;
    }
    
    // Tenant koleksiyonlarını oluştur
    const success = createCollections(tenantDb, tenantCollectionSchemas, tenantDbName);
    results.push({ tenant: tenantDbName, success });
  }
  
  return results;
}

/**
 * Veritabanı sağlık kontrolü
 */
function performHealthCheck(mainDb) {
  print("\n🔍 Veritabanı sağlık kontrolü yapılıyor...");
  
  try {
    // Ping testi
    const pingResult = mainDb.adminCommand({ ping: 1 });
    if (!pingResult.ok) {
      throw new Error("Ping başarısız");
    }
    print("✅ Ping testi başarılı");
    
    // Koleksiyon listeleme testi
    const collStats = mainDb.runCommand({ listCollections: 1 });
    if (!collStats.ok) {
      throw new Error("Koleksiyon listesi alınamadı");
    }
    print("✅ Koleksiyon listeleme testi başarılı");
    
    // Okuma yazma testi
    const testCollection = mainDb.getCollection("_setup_test");
    const testDoc = { test: true, timestamp: new Date() };
    testCollection.insertOne(testDoc);
    
    const readTest = testCollection.findOne({ test: true });
    if (!readTest) {
      throw new Error("Yazılan veri okunamadı");
    }
    
    // Test verilerini temizle
    testCollection.drop();
    print("✅ Okuma/yazma testi başarılı");
    
    return true;
  } catch (error) {
    print(`❌ Sağlık kontrolü başarısız: ${error.message}`);
    return false;
  }
}

/**
 * Kurulum işlemlerini loglar
 */
function logSetup(success, details) {
  const adminDb = db.getSiblingDB('admin');

  if (!adminDb.getCollectionNames().includes('setup_logs')) {
    adminDb.createCollection('setup_logs', { 
      capped: true, 
      size: 5242880,  // 5MB
      max: 1000
    });
  }

  const logEntry = {
    event: "DB_INITIALIZATION",
    status: success ? "SUCCESS" : "FAILED",
    timestamp: new Date(),
    details: details,
    environment: {
      version: config.app.version,
      dbName: config.db.main,
      user: config.db.user,
      nodeEnv: config.app.environment,
      hostname: new Date().getTime().toString()
    }
  };

  adminDb.setup_logs.insertOne(logEntry);
  print(`📝 Kurulum durumu loglandı: ${success ? "BAŞARILI" : "BAŞARISIZ"}`);
}

/**
 * Otomatik temizleme işlemi için TTL indeksi ekler
 */
function setupAutoCleanup(mainDb) {
  print("\n🔧 Otomatik temizleme ayarları yapılandırılıyor...");
  
  try {
    // Token Blacklist koleksiyonu için TTL indeksi
    if (mainDb.getCollectionNames().includes('token_blacklist')) {
      mainDb.token_blacklist.createIndex(
        { "expires_at": 1 }, 
        { expireAfterSeconds: 0, name: "ttl_token_cleanup_idx" }
      );
      print("✅ Token blacklist temizleme indeksi oluşturuldu");
    }
    
    // Sistem logları için TTL indeksi (30 günden eski kayıtlar silinecek)
    if (mainDb.getCollectionNames().includes('system_logs')) {
      mainDb.system_logs.createIndex(
        { "timestamp": 1 }, 
        { expireAfterSeconds: 2592000, name: "ttl_logs_cleanup_idx" }
      );
      print("✅ Sistem logları temizleme indeksi oluşturuldu (30 gün)");
    }
    
    return true;
  } catch (error) {
    print(`❌ Otomatik temizleme ayarları yapılandırma hatası: ${error.message}`);
    return false;
  }
}

/**
 * Ana kurulum fonksiyonu
 */
function main() {
  print("\n=====================================================");
  print(`🚀 TAKİP SİSTEMİ - MONGODB KURULUMU v${config.app.version}`);
  print(`🌐 Ortam: ${config.app.environment.toUpperCase()}`);
  print("=====================================================\n");

  try {
    const adminDb = db.getSiblingDB('admin');
    
    // Kurulumun daha önce yapılıp yapılmadığını kontrol et
    const setupLog = adminDb.getCollection('setup_logs').findOne({ 
      event: "DB_INITIALIZATION", 
      status: "SUCCESS",
      "environment.version": config.app.version
    });
    
    if (setupLog && config.app.environment !== "development") {
      print("ℹ️ Bu sürüm için kurulum zaten tamamlanmış. Yeniden kurulum atlanıyor.");
      print(`ℹ️ Önceki kurulum tarihi: ${setupLog.timestamp}`);
      return;
    }
    
    // Veritabanı kullanıcılarını oluştur
    const { adminDb: _, mainDb } = initializeDatabaseUsers();
    print("✅ Veritabanı kullanıcıları oluşturuldu");
    
    // Ana koleksiyonları oluştur
    const mainCollectionsCreated = createCollections(mainDb, mainCollectionSchemas, config.db.main);
    if (!mainCollectionsCreated) {
      throw new Error("Ana koleksiyonları oluşturma işlemi başarısız oldu");
    }
    
    // Tenant veritabanlarını oluştur
    const tenantResults = initializeTenantDatabases();
    const allTenantsSuccess = tenantResults.every(r => r.success);
    
    if (!allTenantsSuccess) {
      print("⚠️ Bazı tenant veritabanları oluşturulamadı");
      tenantResults.forEach(r => {
        if (!r.success) {
          print(`  ❌ ${r.tenant} oluşturulamadı`);
        }
      });
    } else {
      print("✅ Tüm tenant veritabanları başarıyla oluşturuldu");
    }
    
    // Otomatik temizleme ayarlarını yap
    setupAutoCleanup(mainDb);
    
    // Veritabanı sağlık kontrolü
    const isHealthy = performHealthCheck(mainDb);
    if (!isHealthy) {
      throw new Error("Veritabanı sağlık kontrolü başarısız oldu");
    }
    
    // Başarılı kurulumu logla
    logSetup(true, {
      mainDatabase: config.db.main,
      tenants: tenantResults,
      healthCheck: isHealthy
    });
    
    print("\n✅✅✅ KURULUM BAŞARIYLA TAMAMLANDI ✅✅✅");
    print("=====================================================");
    
  } catch (error) {
    print(`\n❌❌❌ KRİTİK HATA: ${error.message}`);
    
    // Başarısız kurulumu logla
    logSetup(false, {
      error: error.message,
      stack: error.stack
    });
    
    print("Kurulum sırasında hata oluştu, lütfen logları kontrol edin.");
    print("=====================================================");
  }
}

// Kurulumu başlat
main();