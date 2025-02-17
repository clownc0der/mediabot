import aiosqlite
import logging
import asyncio
from typing import Optional, Tuple, List, Dict, Any
from datetime import datetime

logger = logging.getLogger('bot_logger')

class DatabaseError(Exception):
    """Базовый класс для ошибок базы данных"""
    pass

class ConnectionError(DatabaseError):
    """Ошибка подключения к базе данных"""
    pass

class Database:
    def __init__(self, db_path: str = "rust_media.db"):
        self.db_path = db_path
        self._connection_retries = 3
        self._retry_delay = 1  # секунда
        self.logger = logging.getLogger(__name__)
        self._connection = None
        self._lock = asyncio.Lock()

    async def _create_connection(self) -> aiosqlite.Connection:
        """Создает новое соединение с базой данных"""
        try:
            connection = await aiosqlite.connect(self.db_path)
            connection.row_factory = aiosqlite.Row
            return connection
        except Exception as e:
            self.logger.error(f"Failed to create database connection: {e}")
            raise ConnectionError(f"Failed to connect to database: {e}")

    async def _get_connection(self) -> aiosqlite.Connection:
        """Получает соединение с базой данных"""
        try:
            if self._connection is None or self._connection.closed:
                self._connection = await self._create_connection()
            return self._connection
        except Exception as e:
            self.logger.error(f"Error getting database connection: {e}")
            raise ConnectionError(f"Failed to get database connection: {e}")

    async def close(self):
        """Закрывает соединение с базой данных"""
        async with self._lock:
            if self._connection is not None:
                await self._connection.close()
                self._connection = None

    async def execute_query(self, query: str, params: tuple = None) -> Any:
        """Выполняет SQL-запрос с обработкой ошибок"""
        try:
            async with await self._get_connection() as db:
                cursor = await db.execute(query, params or ())
                await db.commit()
                return cursor
        except Exception as e:
            logger.error(f"Database query failed: {str(e)}\nQuery: {query}\nParams: {params}")
            raise DatabaseError(f"Database query failed: {str(e)}") from e

    async def fetch_one(self, query: str, params: tuple = None) -> Optional[Dict]:
        """Получает одну запись из базы данных"""
        try:
            async with await self._get_connection() as db:
                cursor = await db.execute(query, params or ())
                return await cursor.fetchone()
        except Exception as e:
            logger.error(f"Database fetch_one failed: {str(e)}\nQuery: {query}\nParams: {params}")
            raise DatabaseError(f"Database fetch_one failed: {str(e)}") from e

    async def fetch_all(self, query: str, params: tuple = None) -> List[Dict]:
        """Получает все записи из базы данных"""
        try:
            async with await self._get_connection() as db:
                cursor = await db.execute(query, params or ())
                return await cursor.fetchall()
        except Exception as e:
            logger.error(f"Database fetch_all failed: {str(e)}\nQuery: {query}\nParams: {params}")
            raise DatabaseError(f"Database fetch_all failed: {str(e)}") from e

    async def create_tables(self):
        """Создает необходимые таблицы в базе данных"""
        try:
            async with aiosqlite.connect(self.db_path) as db:
                # Основная таблица пользователей Telegram
                await db.execute('''
                    CREATE TABLE IF NOT EXISTS telegram_users (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        telegram_id INTEGER UNIQUE,
                        username TEXT,
                        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                    )
                ''')

                # Таблица каналов пользователей
                await db.execute('''
                    CREATE TABLE IF NOT EXISTS user_channels (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        telegram_user_id INTEGER,
                        platform TEXT CHECK(platform IN ('youtube', 'tiktok', 'shorts', 'twitch', 'other')),
                        channel_link TEXT,
                        channel_name TEXT,
                        
                        -- Данные для партнерской программы
                        promo_code TEXT,                    -- Промокод блогера
                        blogger_nickname TEXT,              -- Никнейм на платформе
                        
                        -- Статистика канала
                        views_count INTEGER DEFAULT 0,      -- Количество просмотров
                        twitch_viewers INTEGER DEFAULT 0,   -- Среднее количество зрителей (для Twitch)
                        experience TEXT,                    -- Опыт работы
                        frequency TEXT,                     -- Частота выпуска контента
                        
                        -- Общая статистика
                        total_requests INTEGER DEFAULT 0,      -- Всего заявок
                        approved_requests INTEGER DEFAULT 0,   -- Одобренных заявок
                        pending_requests INTEGER DEFAULT 0,    -- Заявок в ожидании
                        rejected_requests INTEGER DEFAULT 0,   -- Отклоненных заявок
                        
                        -- Финансовая статистика
                        pending_amount DECIMAL(10,2) DEFAULT 0.00,    -- Сумма в ожидании
                        total_earned DECIMAL(10,2) DEFAULT 0.00,      -- Всего заработано
                        
                        -- Служебные поля
                        status TEXT DEFAULT 'pending',
                        admin_comment TEXT,
                        is_active BOOLEAN DEFAULT TRUE,
                        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                        updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                        
                        FOREIGN KEY (telegram_user_id) REFERENCES telegram_users(id),
                        UNIQUE(telegram_user_id, channel_link, platform)
                    )
                ''')

                # Добавляем новые колонки, если их нет
                try:
                    await db.execute('ALTER TABLE user_channels ADD COLUMN views_count INTEGER DEFAULT 0')
                    await db.execute('ALTER TABLE user_channels ADD COLUMN experience TEXT')
                    await db.execute('ALTER TABLE user_channels ADD COLUMN frequency TEXT')
                    await db.execute('ALTER TABLE user_channels ADD COLUMN twitch_viewers INTEGER DEFAULT 0')
                except aiosqlite.OperationalError:
                    # Колонки уже существуют
                    pass

                # Таблица заявок на выплаты
                await db.execute('''
                    CREATE TABLE IF NOT EXISTS payment_requests (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        channel_id INTEGER,
                        content_link TEXT NOT NULL,           -- Ссылка на контент
                        content_type TEXT NOT NULL,           -- Тип контента (видео/стрим/etc)
                        views_count INTEGER,                  -- Количество просмотров
                        requested_amount DECIMAL(10,2),       -- Запрошенная сумма
                        approved_amount DECIMAL(10,2),        -- Одобренная сумма
                        status TEXT DEFAULT 'pending' CHECK(
                            status IN ('pending', 'approved', 'rejected', 'paid')
                        ),
                        admin_comment TEXT,                   -- Комментарий администратора
                        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                        updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                        
                        FOREIGN KEY (channel_id) REFERENCES user_channels(id)
                    )
                ''')

                # Удаляем создание таблицы blogger_connections
                await db.execute('DROP TABLE IF EXISTS blogger_connections')
                await db.commit()

                # Таблица для заявок с множественными площадками
                await db.execute('''
                    CREATE TABLE IF NOT EXISTS collaboration_applications (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        telegram_user_id INTEGER,
                        status TEXT DEFAULT 'pending',
                        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                        FOREIGN KEY (telegram_user_id) REFERENCES telegram_users(id)
                    )
                ''')

                # Таблица для площадок в рамках одной заявки
                await db.execute('''
                    CREATE TABLE IF NOT EXISTS application_platforms (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        application_id INTEGER,
                        platform TEXT CHECK(platform IN ('youtube', 'tiktok', 'shorts', 'twitch', 'other')),
                        channel_link TEXT,
                        views_count INTEGER,
                        experience TEXT,
                        frequency TEXT,
                        promo_code TEXT,
                        platform_order INTEGER,  -- порядковый номер площадки в заявке
                        FOREIGN KEY (application_id) REFERENCES collaboration_applications(id)
                    )
                ''')

                # Таблица для заявок на оплату контента
                await db.execute('''
                    CREATE TABLE IF NOT EXISTS paid_content_applications (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        user_id INTEGER NOT NULL,
                        username TEXT,
                        user_mention TEXT,
                        content_type TEXT NOT NULL,
                        link TEXT NOT NULL,
                        publish_date TEXT,
                        views_count INTEGER,
                        current_views INTEGER,
                        payment_amount REAL,
                        note TEXT,
                        status TEXT DEFAULT 'pending' CHECK(
                            status IN ('pending', 'approved', 'rejected', 'paid')
                        ),
                        admin_comment TEXT,
                        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                        updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                        FOREIGN KEY (user_id) REFERENCES telegram_users(id)
                    )
                ''')

                # Добавляем колонку channel_id, если её нет
                try:
                    await db.execute('ALTER TABLE paid_content_applications ADD COLUMN channel_id INTEGER REFERENCES user_channels(id)')
                except aiosqlite.OperationalError:
                    # Колонка уже существует
                    pass

                # Добавляем индексы для оптимизации запросов
                await db.execute('''
                    CREATE INDEX IF NOT EXISTS idx_paid_content_user_id 
                    ON paid_content_applications(user_id)
                ''')
                await db.execute('''
                    CREATE INDEX IF NOT EXISTS idx_paid_content_status 
                    ON paid_content_applications(status)
                ''')

                await db.commit()
                
                # Проверяем существование необходимых столбцов
                cursor = await db.execute("PRAGMA table_info(paid_content_applications)")
                columns = {column[1] for column in await cursor.fetchall()}
                
                required_columns = {
                    'user_id', 'username', 'user_mention', 'content_type', 'link',
                    'publish_date', 'views_count', 'current_views', 'payment_amount',
                    'note', 'status', 'admin_comment', 'created_at', 'updated_at'
                }
                
                missing_columns = required_columns - columns
                if missing_columns:
                    self.logger.warning(f"Missing columns in paid_content_applications: {missing_columns}")
                    for column in missing_columns:
                        try:
                            if column in {'current_views', 'payment_amount'}:
                                await db.execute(f'ALTER TABLE paid_content_applications ADD COLUMN {column} REAL')
                            else:
                                await db.execute(f'ALTER TABLE paid_content_applications ADD COLUMN {column} TEXT')
                        except Exception as e:
                            self.logger.error(f"Error adding column {column}: {e}")
                
                await db.commit()
                
        except Exception as e:
            self.logger.error(f"Error creating tables: {e}")
            raise DatabaseError(f"Failed to create tables: {e}")

    async def add_media(self, user_id: int, media_type: str, file_id: str, caption: str = None):
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute(
                'INSERT INTO media_content (user_id, media_type, file_id, caption) VALUES (?, ?, ?, ?)',
                (user_id, media_type, file_id, caption)
            )
            await db.commit()

    async def get_applications_stats(self):
        """Получает статистику по всем каналам и заявкам"""
        try:
            async with aiosqlite.connect(self.db_path) as db:
                cursor = await db.execute('''
                    SELECT 
                        COUNT(DISTINCT uc.id) as total_channels,
                        SUM(uc.total_requests) as total_requests,
                        SUM(uc.approved_requests) as approved_requests,
                        SUM(uc.pending_requests) as pending_requests,
                        SUM(uc.rejected_requests) as rejected_requests,
                        SUM(uc.pending_amount) as total_pending,
                        SUM(uc.total_earned) as total_earned
                    FROM user_channels uc
                    WHERE uc.is_active = TRUE
                ''')
                row = await cursor.fetchone()
                return {
                    'total_channels': row[0] or 0,
                    'total_requests': row[1] or 0,
                    'approved_requests': row[2] or 0,
                    'pending_requests': row[3] or 0,
                    'rejected_requests': row[4] or 0,
                    'total_pending': float(row[5] or 0),
                    'total_earned': float(row[6] or 0)
                }
        except Exception as e:
            self.logger.error(f"Error getting applications stats: {e}")
            return {
                'total_channels': 0,
                'total_requests': 0,
                'approved_requests': 0,
                'pending_requests': 0,
                'rejected_requests': 0,
                'total_pending': 0.0,
                'total_earned': 0.0
            }

    async def is_approved_blogger(self, username: str) -> bool:
        """Проверяет, является ли пользователь одобренным блогером."""
        try:
            async with aiosqlite.connect(self.db_path) as db:
                db.row_factory = aiosqlite.Row
                cursor = await db.execute('''
                    SELECT 1 FROM user_channels uc
                    JOIN telegram_users tu ON uc.telegram_user_id = tu.id
                    WHERE (tu.username = ? OR tu.username = ? OR tu.username = ?)
                    AND uc.is_active = TRUE
                    AND uc.status = 'approved'
                    LIMIT 1
                ''', (
                    username,  # Проверяем как есть
                    f"@{username}",  # Проверяем с @
                    username.lstrip('@')  # Проверяем без @
                ))
                result = await cursor.fetchone()
                return bool(result)
        except Exception as e:
            logger.error(f"Error checking approved blogger status: {e}")
            return False

    async def save_paid_content_application(self, user_id: int, username: str | None, 
                                          content_type: str, link: str, publish_date: str, 
                                          note: str, views_count: int) -> int:
        # Создаем user_mention: если есть username, используем его, иначе используем ID
        user_mention = f"@{username}" if username else f"id{user_id}"
        
        async with aiosqlite.connect(self.db_path) as db:
            cursor = await db.execute('''
                INSERT INTO paid_content_applications 
                (user_id, username, user_mention, content_type, link, publish_date, note, views_count, status)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, 'pending')
            ''', (user_id, username, user_mention, content_type, link, publish_date, note, views_count))
            await db.commit()
            return cursor.lastrowid

    async def get_user_applications_stats(self, user_id: int):
        """Получает статистику заявок пользователя"""
        async with aiosqlite.connect(self.db_path) as db:
            cursor = await db.execute('''
                SELECT 
                    COUNT(CASE WHEN status = 'paid' THEN 1 END) as paid_count,
                    COUNT(CASE WHEN status != 'paid' THEN 1 END) as unpaid_count
                FROM paid_content_applications 
                WHERE user_id = ?
            ''', (user_id,))
            row = await cursor.fetchone()
            return {'paid': row[0], 'unpaid': row[1]}

    async def get_user_applications(self, user_id: int, offset: int = 0, limit: int = 10):
        """Получает список заявок пользователя с пагинацией"""
        async with aiosqlite.connect(self.db_path) as db:
            db.row_factory = aiosqlite.Row
            
            # Получаем общее количество заявок пользователя
            cursor = await db.execute(
                'SELECT COUNT(*) as total FROM paid_content_applications WHERE user_id = ?',
                (user_id,)
            )
            total = (await cursor.fetchone())['total']
            
            # Получаем заявки с пагинацией
            cursor = await db.execute('''
                SELECT * FROM paid_content_applications 
                WHERE user_id = ? 
                ORDER BY created_at DESC
                LIMIT ? OFFSET ?
            ''', (user_id, limit, offset))
            
            applications = await cursor.fetchall()
            return applications, total

    async def add_username_column(self):
        """Добавляет столбец username в таблицу paid_content_applications если его нет"""
        async with aiosqlite.connect(self.db_path) as db:
            # Проверяем существование столбца username
            cursor = await db.execute("PRAGMA table_info(paid_content_applications)")
            columns = await cursor.fetchall()
            has_username = any(column[1] == 'username' for column in columns)
            
            if not has_username:
                try:
                    await db.execute('ALTER TABLE paid_content_applications ADD COLUMN username TEXT')
                    await db.commit()
                except:
                    pass  # Если столбец уже существует, пропускаем 

    async def add_user_mention_column(self):
        """Добавляет столбец user_mention в таблицу paid_content_applications если его нет"""
        async with aiosqlite.connect(self.db_path) as db:
            cursor = await db.execute("PRAGMA table_info(paid_content_applications)")
            columns = await cursor.fetchall()
            has_user_mention = any(column[1] == 'user_mention' for column in columns)
            
            if not has_user_mention:
                try:
                    await db.execute('ALTER TABLE paid_content_applications ADD COLUMN user_mention TEXT')
                    # Обновляем существующие записи
                    await db.execute('''
                        UPDATE paid_content_applications 
                        SET user_mention = COALESCE('@' || username, 'id' || user_id)
                        WHERE user_mention IS NULL
                    ''')
                    await db.commit()
                except:
                    pass 

    async def get_user_applications_by_status(self, user_id: int, status: str, offset: int = 0, limit: int = 10):
        """Получает список заявок пользователя с фильтром по статусу"""
        async with aiosqlite.connect(self.db_path) as db:
            db.row_factory = aiosqlite.Row
            
            # Получаем общее количество заявок пользователя с данным статусом
            cursor = await db.execute(
                'SELECT COUNT(*) as total FROM paid_content_applications WHERE user_id = ? AND status = ?',
                (user_id, status)
            )
            total = (await cursor.fetchone())['total']
            
            # Получаем заявки с пагинацией
            cursor = await db.execute('''
                SELECT * FROM paid_content_applications 
                WHERE user_id = ? AND status = ?
                ORDER BY created_at DESC
                LIMIT ? OFFSET ?
            ''', (user_id, status, limit, offset))
            
            applications = await cursor.fetchall()
            return applications, total 

    async def get_paid_content_applications(self, offset: int = 0, limit: int = 1):
        """Получает список заявок на оплату контента с пагинацией"""
        try:
            async with await self._get_connection() as db:
                cursor = await db.execute('''
                    SELECT * FROM paid_content_applications 
                    WHERE status = 'pending'
                    ORDER BY created_at ASC
                    LIMIT ? OFFSET ?
                ''', (limit, offset))
                return await cursor.fetchall()
        except Exception as e:
            logger.error(f"Error getting paid content applications: {e}")
            raise DatabaseError(f"Failed to get paid content applications: {e}")

    async def get_paid_content_applications_count(self) -> int:
        """Получает общее количество заявок на оплату контента"""
        try:
            async with await self._get_connection() as db:
                cursor = await db.execute('''
                    SELECT COUNT(*) as count 
                    FROM paid_content_applications 
                    WHERE status = 'pending'
                ''')
                result = await cursor.fetchone()
                return result['count']
        except Exception as e:
            logger.error(f"Error getting paid content applications count: {e}")
            raise DatabaseError(f"Failed to get paid content applications count: {e}")

    async def get_paid_content_application(self, app_id: int):
        """Получает информацию о конкретной заявке на оплату контента"""
        try:
            async with aiosqlite.connect(self.db_path) as db:
                db.row_factory = aiosqlite.Row
                cursor = await db.execute('''
                    SELECT * FROM paid_content_applications 
                    WHERE id = ?
                ''', (app_id,))
                return await cursor.fetchone()
        except Exception as e:
            logger.error(f"Error getting paid content application {app_id}: {e}")
            raise DatabaseError(f"Failed to get paid content application: {e}")

    async def update_paid_content_status(self, app_id: int, status: str, current_views: int = None, payment_amount: float = None):
        """Обновляет статус заявки на оплату контента"""
        try:
            async with aiosqlite.connect(self.db_path) as db:
                db.row_factory = aiosqlite.Row
                
                # Формируем SQL запрос в зависимости от наличия дополнительных данных
                if current_views is not None and payment_amount is not None:
                    await db.execute('''
                        UPDATE paid_content_applications 
                        SET status = ?,
                            current_views = ?,
                            payment_amount = ?,
                            status_changed_at = CURRENT_TIMESTAMP
                        WHERE id = ?
                    ''', (status, current_views, payment_amount, app_id))
                else:
                    await db.execute('''
                        UPDATE paid_content_applications 
                        SET status = ?,
                            status_changed_at = CURRENT_TIMESTAMP
                        WHERE id = ?
                    ''', (status, app_id))
                
                await db.commit()
                
                cursor = await db.execute('''
                    SELECT * FROM paid_content_applications 
                    WHERE id = ?
                ''', (app_id,))
                return await cursor.fetchone()
        except Exception as e:
            logger.error(f"Error updating paid content application {app_id} status: {e}")
            raise DatabaseError(f"Failed to update paid content application status: {e}")

    async def get_existing_connections(self, telegram_username: str, platform: str) -> List[Dict]:
        """Получает все существующие связи пользователя для указанной платформы"""
        try:
            async with aiosqlite.connect(self.db_path) as db:
                db.row_factory = aiosqlite.Row
                # Очищаем username от @ если он есть
                clean_username = telegram_username.lstrip('@')
                
                cursor = await db.execute('''
                    SELECT id, telegram_username, blogger_nickname, platform, promo_code, channel_link, is_active,
                           datetime(created_at, 'localtime') as created_at
                    FROM blogger_connections 
                    WHERE telegram_username = ? AND platform = ?
                    ORDER BY created_at DESC
                ''', (clean_username, platform))
                
                return await cursor.fetchall()
        except Exception as e:
            logger.error(f"Error getting existing connections: {e}")
            raise DatabaseError(f"Failed to get existing connections: {e}")

    async def create_blogger_connection(self, telegram_username: str, blogger_nickname: str, platform: str, promo: str, channel_link: str):
        """Создает связь между Telegram пользователем и никнеймом блогера для конкретной платформы"""
        try:
            async with aiosqlite.connect(self.db_path) as db:
                db.row_factory = aiosqlite.Row
                # Очищаем username от @ если он есть
                clean_username = telegram_username.lstrip('@')
                
                # Создаем новую связь (все связи остаются активными)
                await db.execute('''
                    INSERT INTO blogger_connections 
                    (telegram_username, blogger_nickname, platform, promo_code, channel_link, is_active)
                    VALUES (?, ?, ?, ?, ?, TRUE)
                ''', (clean_username, blogger_nickname, platform, promo, channel_link))
                
                await db.commit()
        except Exception as e:
            logger.error(f"Error creating blogger connection: {e}")
            raise DatabaseError(f"Failed to create blogger connection: {e}")

    async def get_blogger_by_telegram(self, telegram_username: str) -> List[Dict]:
        """Получает все активные связи блогера по Telegram username"""
        try:
            async with aiosqlite.connect(self.db_path) as db:
                db.row_factory = aiosqlite.Row
                cursor = await db.execute('''
                    SELECT blogger_nickname, platform, promo_code 
                    FROM blogger_connections 
                    WHERE telegram_username = ? AND is_active = TRUE
                    ORDER BY platform ASC
                ''', (telegram_username,))
                return await cursor.fetchall()
        except Exception as e:
            logger.error(f"Error getting blogger by telegram: {e}")
            raise DatabaseError(f"Failed to get blogger by telegram: {e}")

    async def get_telegram_by_blogger(self, blogger_nickname: str) -> Optional[str]:
        """Получает Telegram username по никнейму блогера"""
        try:
            async with aiosqlite.connect(self.db_path) as db:
                db.row_factory = aiosqlite.Row
                cursor = await db.execute('''
                    SELECT telegram_username 
                    FROM blogger_connections 
                    WHERE blogger_nickname = ?
                ''', (blogger_nickname,))
                result = await cursor.fetchone()
                return result['telegram_username'] if result else None
        except Exception as e:
            logger.error(f"Error getting telegram by blogger: {e}")
            raise DatabaseError(f"Failed to get telegram by blogger: {e}")

    async def get_all_active_bloggers(self) -> List[Dict]:
        """Получает список всех активных блогеров с количеством ожидающих заявок"""
        try:
            async with aiosqlite.connect(self.db_path) as db:
                db.row_factory = aiosqlite.Row
                cursor = await db.execute('''
                    SELECT 
                        bc.blogger_nickname,
                        bc.telegram_username,
                        COUNT(pca.id) as pending_applications
                    FROM blogger_connections bc
                    LEFT JOIN paid_content_applications pca 
                        ON pca.user_mention = '@' || bc.telegram_username 
                        AND pca.status = 'pending'
                    GROUP BY bc.blogger_nickname, bc.telegram_username
                    ORDER BY bc.blogger_nickname ASC
                ''')
                return await cursor.fetchall()
        except Exception as e:
            logger.error(f"Error getting active bloggers: {e}")
            raise DatabaseError(f"Failed to get active bloggers: {e}")

    async def get_blogger_applications(self, blogger_nickname: str, status: Optional[str] = None, page: int = 0, limit: int = 5) -> List[Dict]:
        """Получает заявки блогера с фильтром по статусу и пагинацией"""
        try:
            async with aiosqlite.connect(self.db_path) as db:
                db.row_factory = aiosqlite.Row
                query = '''
                    SELECT pca.* 
                    FROM paid_content_applications pca
                    JOIN blogger_connections bc ON pca.user_mention = '@' || bc.telegram_username
                    WHERE bc.blogger_nickname = ?
                '''
                params = [blogger_nickname]
                
                if status:
                    query += ' AND pca.status = ?'
                    params.append(status)
                    
                query += ' ORDER BY pca.created_at DESC LIMIT ? OFFSET ?'
                params.extend([limit, page * limit])
                
                cursor = await db.execute(query, params)
                return await cursor.fetchall()
        except Exception as e:
            logger.error(f"Error getting blogger applications: {e}")
            raise DatabaseError(f"Failed to get blogger applications: {e}")

    async def get_application(self, app_id: int):
        """Получает информацию о конкретной заявке на сотрудничество"""
        try:
            async with aiosqlite.connect(self.db_path) as db:
                db.row_factory = aiosqlite.Row
                cursor = await db.execute('''
                    SELECT * FROM collaboration 
                    WHERE id = ?
                ''', (app_id,))
                return await cursor.fetchone()
        except Exception as e:
            logger.error(f"Error getting application {app_id}: {e}")
            raise DatabaseError(f"Failed to get application: {e}")

    async def add_payment_columns(self):
        """Добавляет столбцы для хранения информации об оплате"""
        async with aiosqlite.connect(self.db_path) as db:
            # Проверяем существование столбцов
            cursor = await db.execute("PRAGMA table_info(paid_content_applications)")
            columns = await cursor.fetchall()
            column_names = [column[1] for column in columns]
            
            try:
                if 'current_views' not in column_names:
                    await db.execute('ALTER TABLE paid_content_applications ADD COLUMN current_views INTEGER')
                
                if 'payment_amount' not in column_names:
                    await db.execute('ALTER TABLE paid_content_applications ADD COLUMN payment_amount REAL')
                
                await db.commit()
            except Exception as e:
                logger.error(f"Error adding payment columns: {e}")
                raise DatabaseError(f"Failed to add payment columns: {e}") 

    async def count_blogger_applications(self, blogger_nickname: str, status: Optional[str] = None) -> int:
        """Получает количество заявок блогера с фильтром по статусу"""
        try:
            async with aiosqlite.connect(self.db_path) as db:
                query = '''
                    SELECT COUNT(*) as count
                    FROM paid_content_applications pca
                    JOIN blogger_connections bc ON pca.user_mention = '@' || bc.telegram_username
                    WHERE bc.blogger_nickname = ?
                '''
                params = [blogger_nickname]
                
                if status:
                    query += ' AND pca.status = ?'
                    params.append(status)
                
                cursor = await db.execute(query, params)
                result = await cursor.fetchone()
                return result[0]
        except Exception as e:
            logger.error(f"Error counting blogger applications: {e}")
            raise DatabaseError(f"Failed to count blogger applications: {e}") 

    async def init_db(self):
        """Инициализирует базу данных"""
        try:
            async with aiosqlite.connect(self.db_path) as db:
                # Создаем таблицы
                await db.execute('''
                    CREATE TABLE IF NOT EXISTS users (
                        id INTEGER PRIMARY KEY,
                        username TEXT,
                        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                    )
                ''')

                await db.execute('''
                    CREATE TABLE IF NOT EXISTS blogger_connections (
                        telegram_username TEXT PRIMARY KEY,
                        blogger_nickname TEXT UNIQUE,
                        promo_code TEXT,
                        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                    )
                ''')

                # Добавляем колонку promo_code, если её нет
                try:
                    await db.execute('ALTER TABLE blogger_connections ADD COLUMN promo_code TEXT')
                    await db.commit()
                except aiosqlite.OperationalError:
                    # Колонка уже существует
                    pass

                await db.execute('''
                    CREATE TABLE IF NOT EXISTS applications (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        user_id INTEGER,
                        username TEXT,
                        status TEXT DEFAULT 'new',
                        details TEXT,
                        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                        FOREIGN KEY (user_id) REFERENCES users(id)
                    )
                ''')

                await db.commit()
        except Exception as e:
            raise DatabaseError(f"Failed to initialize database: {e}") 

    async def check_channel_exists(self, channel_link: str, platform: str, telegram_id: int = None) -> Dict:
        """
        Проверяет существование канала в базе
        
        Returns:
            Dict с информацией о существующем канале или None
        """
        try:
            async with aiosqlite.connect(self.db_path) as db:
                db.row_factory = aiosqlite.Row
                
                # Базовый запрос для проверки существования канала
                query = """
                    SELECT uc.*, tu.telegram_id, tu.username
                    FROM user_channels uc
                    JOIN telegram_users tu ON uc.telegram_user_id = tu.id
                    WHERE uc.channel_link = ? 
                    AND uc.platform = ?
                    AND uc.is_active = TRUE
                    AND uc.status != 'rejected'
                """
                params = [channel_link, platform]
                
                cursor = await db.execute(query, params)
                channel = await cursor.fetchone()
                
                if not channel:
                    # Канал не найден - можно регистрировать
                    return None
                
                # Если канал существует, проверяем владельца
                if channel['telegram_id'] == telegram_id:
                    return {
                        'exists': True,
                        'own_channel': True,
                        'platform': channel['platform']
                    }
                
                return {
                    'exists': True,
                    'own_channel': False,
                    'platform': channel['platform']
                }
                
        except Exception as e:
            self.logger.error(f"Error checking channel existence: {e}")
            raise DatabaseError(f"Failed to check channel: {e}")

    async def add_channel(
        self, 
        telegram_id: int, 
        platform: str, 
        channel_link: str, 
        channel_name: str,
        views_count: int = 0,
        experience: str = None,
        frequency: str = None,
        promo_code: str = None
    ) -> int:
        """Добавляет новый канал пользователю или обновляет отклоненную заявку"""
        try:
            async with aiosqlite.connect(self.db_path) as db:
                # Получаем telegram_user_id
                cursor = await db.execute(
                    "SELECT id FROM telegram_users WHERE telegram_id = ?",
                    (telegram_id,)
                )
                user = await cursor.fetchone()
                if not user:
                    self.logger.error(f"User not found: {telegram_id}")
                    return False

                # Проверяем существование канала
                cursor = await db.execute("""
                    SELECT id, status 
                    FROM user_channels 
                    WHERE telegram_user_id = ? AND channel_link = ? AND platform = ?
                """, (user[0], channel_link, platform))
                existing_channel = await cursor.fetchone()

                if existing_channel:
                    if existing_channel[1] != 'rejected':
                        self.logger.warning(f"Channel already exists and not rejected: {channel_link}")
                        return False
                    
                    # Обновляем существующую отклоненную заявку
                    self.logger.info(f"Updating rejected channel application: {channel_link}")
                    await db.execute("""
                        UPDATE user_channels 
                        SET status = 'pending',
                            channel_name = ?,
                            views_count = ?,
                            experience = ?,
                            frequency = ?,
                            promo_code = ?,
                            admin_comment = NULL,
                            updated_at = CURRENT_TIMESTAMP
                        WHERE id = ?
                    """, (channel_name, views_count, experience, frequency, promo_code, existing_channel[0]))
                    await db.commit()
                    return existing_channel[0]
                
                # Добавляем новый канал
                self.logger.info(f"Adding new channel for user {telegram_id}: {platform} - {channel_link}")
                cursor = await db.execute("""
                    INSERT INTO user_channels 
                    (telegram_user_id, platform, channel_link, channel_name, 
                     views_count, experience, frequency, promo_code, status)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, 'pending')
                """, (
                    user[0], platform, channel_link, channel_name,
                    views_count, experience, frequency, promo_code
                ))
                await db.commit()
                
                channel_id = cursor.lastrowid
                self.logger.info(f"Channel added successfully with ID: {channel_id}")
                return channel_id

        except Exception as e:
            self.logger.error(f"Error adding channel: {e}")
            return False

    async def get_user_channels(self, telegram_id: int) -> List[Dict]:
        """Получает все каналы пользователя со статистикой"""
        try:
            async with aiosqlite.connect(self.db_path) as db:
                db.row_factory = aiosqlite.Row
                cursor = await db.execute("""
                    SELECT uc.* 
                    FROM user_channels uc
                    JOIN telegram_users tu ON uc.telegram_user_id = tu.id
                    WHERE tu.telegram_id = ? AND uc.is_active = TRUE
                    ORDER BY uc.platform, uc.created_at
                """, (telegram_id,))
                return [dict(row) for row in await cursor.fetchall()]
        except Exception as e:
            self.logger.error(f"Error getting user channels: {e}")
            return []

    async def create_collaboration_request(
        self,
        channel_id: int,
        views_count: int,
        additional_info: str
    ) -> int:
        """Создает новую заявку на сотрудничество"""
        try:
            async with aiosqlite.connect(self.db_path) as db:
                cursor = await db.execute(
                    """
                    INSERT INTO collaboration_requests 
                    (channel_id, views_count, additional_info) 
                    VALUES (?, ?, ?)
                    """,
                    (channel_id, views_count, additional_info)
                )
                await db.commit()
                return cursor.lastrowid
        except Exception as e:
            self.logger.error(f"Error creating collaboration request: {e}")
            raise DatabaseError(f"Failed to create collaboration request: {e}")

    async def get_or_create_user(self, telegram_id: int, username: str) -> int:
        """Получает или создает пользователя Telegram"""
        try:
            async with aiosqlite.connect(self.db_path) as db:
                # Проверяем существование пользователя
                cursor = await db.execute(
                    "SELECT id FROM telegram_users WHERE telegram_id = ?",
                    (telegram_id,)
                )
                user = await cursor.fetchone()
                
                if user:
                    # Обновляем username если он изменился
                    await db.execute(
                        "UPDATE telegram_users SET username = ? WHERE telegram_id = ?",
                        (username, telegram_id)
                    )
                    await db.commit()
                    return user[0]
                
                # Создаем нового пользователя
                cursor = await db.execute(
                    "INSERT INTO telegram_users (telegram_id, username) VALUES (?, ?)",
                    (telegram_id, username)
                )
                await db.commit()
                return cursor.lastrowid
        except Exception as e:
            self.logger.error(f"Error in get_or_create_user: {e}")
            raise DatabaseError(f"Failed to get or create user: {e}")

    async def create_payment_request(
        self, 
        channel_id: int, 
        content_link: str,
        content_type: str,
        views_count: int,
        requested_amount: float
    ) -> int:
        """Создает новую заявку на выплату"""
        try:
            async with aiosqlite.connect(self.db_path) as db:
                # Добавляем заявку
                cursor = await db.execute("""
                    INSERT INTO payment_requests 
                    (channel_id, content_link, content_type, views_count, requested_amount)
                    VALUES (?, ?, ?, ?, ?)
                """, (channel_id, content_link, content_type, views_count, requested_amount))
                
                # Обновляем статистику канала
                await db.execute("""
                    UPDATE user_channels 
                    SET total_requests = total_requests + 1,
                        pending_requests = pending_requests + 1,
                        pending_amount = pending_amount + ?
                    WHERE id = ?
                """, (requested_amount, channel_id))
                
                await db.commit()
                return cursor.lastrowid
        except Exception as e:
            self.logger.error(f"Error creating payment request: {e}")
            raise DatabaseError(f"Failed to create payment request: {e}")

    async def update_payment_request_status(
        self, 
        request_id: int, 
        new_status: str,
        approved_amount: float = None,
        admin_comment: str = None
    ) -> bool:
        """Обновляет статус заявки на выплату"""
        try:
            async with aiosqlite.connect(self.db_path) as db:
                # Получаем текущую заявку
                cursor = await db.execute(
                    "SELECT channel_id, requested_amount, status FROM payment_requests WHERE id = ?",
                    (request_id,)
                )
                request = await cursor.fetchone()
                if not request:
                    return False
                    
                channel_id, old_amount, old_status = request
                
                # Обновляем заявку
                await db.execute("""
                    UPDATE payment_requests 
                    SET status = ?,
                        approved_amount = ?,
                        admin_comment = ?,
                        updated_at = CURRENT_TIMESTAMP
                    WHERE id = ?
                """, (new_status, approved_amount, admin_comment, request_id))
                
                # Обновляем статистику канала
                if new_status == 'approved':
                    await db.execute("""
                        UPDATE user_channels 
                        SET pending_requests = pending_requests - 1,
                            approved_requests = approved_requests + 1,
                            pending_amount = pending_amount - ?,
                            total_earned = total_earned + ?
                        WHERE id = ?
                    """, (old_amount, approved_amount, channel_id))
                elif new_status == 'rejected':
                    await db.execute("""
                        UPDATE user_channels 
                        SET pending_requests = pending_requests - 1,
                            rejected_requests = rejected_requests + 1,
                            pending_amount = pending_amount - ?
                        WHERE id = ?
                    """, (old_amount, channel_id))
                
                await db.commit()
                return True
        except Exception as e:
            self.logger.error(f"Error updating payment request: {e}")
            return False 

    async def get_channel_stats(self, channel_id: int) -> Dict:
        """Получает статистику по конкретному каналу"""
        try:
            async with aiosqlite.connect(self.db_path) as db:
                cursor = await db.execute("""
                    SELECT 
                        COUNT(*) as total_requests,
                        SUM(CASE WHEN status = 'approved' THEN 1 ELSE 0 END) as approved_requests,
                        SUM(CASE WHEN status = 'pending' THEN 1 ELSE 0 END) as pending_requests,
                        SUM(CASE WHEN status = 'rejected' THEN 1 ELSE 0 END) as rejected_requests,
                        SUM(CASE WHEN status = 'pending' THEN requested_amount ELSE 0 END) as pending_amount,
                        SUM(CASE WHEN status = 'approved' THEN approved_amount ELSE 0 END) as total_earned,
                        views_count
                    FROM payment_requests
                    WHERE channel_id = ?
                """, (channel_id,))
                row = await cursor.fetchone()
                
                return {
                    'total_requests': row[0] or 0,
                    'approved_requests': row[1] or 0,
                    'pending_requests': row[2] or 0,
                    'rejected_requests': row[3] or 0,
                    'pending_amount': float(row[4] or 0),
                    'total_earned': float(row[5] or 0),
                    'views_count': row[6] or 0
                }
        except Exception as e:
            self.logger.error(f"Error getting channel stats: {e}")
            return {
                'total_requests': 0,
                'approved_requests': 0,
                'pending_requests': 0,
                'rejected_requests': 0,
                'pending_amount': 0.0,
                'total_earned': 0.0,
                'views_count': 0
            }

    async def update_channel_status(self, channel_id: int, status: str, admin_comment: str = None) -> bool:
        """Обновляет статус канала и добавляет комментарий администратора"""
        try:
            async with aiosqlite.connect(self.db_path) as db:
                if admin_comment:
                    await db.execute("""
                        UPDATE user_channels 
                        SET status = ?, admin_comment = ?, updated_at = CURRENT_TIMESTAMP
                        WHERE id = ?
                    """, (status, admin_comment, channel_id))
                else:
                    await db.execute("""
                        UPDATE user_channels 
                        SET status = ?, updated_at = CURRENT_TIMESTAMP
                        WHERE id = ?
                    """, (status, channel_id))
                
                await db.commit()
                return True
        except Exception as e:
            self.logger.error(f"Error updating channel status: {e}")
            return False

    async def get_channels_by_status(self, status: str, limit: int = 10, offset: int = 0) -> List[Dict]:
        """Получает список каналов с определенным статусом"""
        try:
            async with aiosqlite.connect(self.db_path) as db:
                db.row_factory = aiosqlite.Row
                cursor = await db.execute("""
                    SELECT 
                        uc.*,
                        tu.username as owner_username,
                        datetime(uc.created_at, 'localtime') as created_at,
                        datetime(uc.updated_at, 'localtime') as updated_at
                    FROM user_channels uc
                    JOIN telegram_users tu ON uc.telegram_user_id = tu.id
                    WHERE uc.status = ?
                    ORDER BY uc.created_at DESC
                    LIMIT ? OFFSET ?
                """, (status, limit, offset))
                return [dict(row) for row in await cursor.fetchall()]
        except Exception as e:
            self.logger.error(f"Error getting channels by status: {e}")
            return []

    async def add_admin_comment(self, channel_id: int, comment: str) -> bool:
        """Добавляет комментарий администратора к каналу"""
        try:
            async with aiosqlite.connect(self.db_path) as db:
                await db.execute("""
                    UPDATE user_channels 
                    SET admin_comment = ?, updated_at = CURRENT_TIMESTAMP
                    WHERE id = ?
                """, (comment, channel_id))
                await db.commit()
                return True
        except Exception as e:
            self.logger.error(f"Error adding admin comment: {e}")
            return False

    async def get_statistics(self) -> Dict:
        """Получает общую статистику для админ-панели"""
        try:
            async with aiosqlite.connect(self.db_path) as db:
                cursor = await db.execute("""
                    SELECT 
                        COUNT(DISTINCT telegram_user_id) as total_users,
                        COUNT(*) as total_applications,
                        SUM(CASE WHEN status = 'approved' THEN 1 ELSE 0 END) as approved_applications,
                        SUM(CASE WHEN status = 'rejected' THEN 1 ELSE 0 END) as rejected_applications,
                        SUM(CASE WHEN status = 'pending' THEN 1 ELSE 0 END) as pending_applications
                    FROM user_channels
                """)
                row = await cursor.fetchone()
                
                return {
                    'total_users': row[0] or 0,
                    'total_applications': row[1] or 0,
                    'approved_applications': row[2] or 0,
                    'rejected_applications': row[3] or 0,
                    'pending_applications': row[4] or 0
                }
        except Exception as e:
            self.logger.error(f"Error getting statistics: {e}")
            return {
                'total_users': 0,
                'total_applications': 0,
                'approved_applications': 0,
                'rejected_applications': 0,
                'pending_applications': 0
            } 

    async def get_payment_stats(self, channel_id: int) -> Dict:
        """Получает статистику выплат по каналу"""
        try:
            async with aiosqlite.connect(self.db_path) as db:
                cursor = await db.execute("""
                    SELECT 
                        COUNT(*) as total_payments,
                        SUM(CASE WHEN status = 'paid' THEN approved_amount ELSE 0 END) as total_paid,
                        SUM(CASE WHEN status = 'pending' THEN requested_amount ELSE 0 END) as pending_amount,
                        MAX(approved_amount) as max_payment,
                        AVG(approved_amount) as avg_payment
                    FROM payment_requests
                    WHERE channel_id = ? AND status IN ('paid', 'pending')
                """, (channel_id,))
                row = await cursor.fetchone()
                
                return {
                    'total_payments': row[0] or 0,
                    'total_paid': float(row[1] or 0),
                    'pending_amount': float(row[2] or 0),
                    'max_payment': float(row[3] or 0),
                    'avg_payment': float(row[4] or 0)
                }
        except Exception as e:
            self.logger.error(f"Error getting payment stats: {e}")
            return {
                'total_payments': 0,
                'total_paid': 0.0,
                'pending_amount': 0.0,
                'max_payment': 0.0,
                'avg_payment': 0.0
            }

    async def process_payment(self, request_id: int, payment_amount: float) -> bool:
        """Обрабатывает выплату"""
        try:
            async with aiosqlite.connect(self.db_path) as db:
                await db.execute("""
                    UPDATE payment_requests 
                    SET status = 'paid',
                        paid_amount = ?,
                        paid_at = CURRENT_TIMESTAMP
                    WHERE id = ?
                """, (payment_amount, request_id))
                await db.commit()
                return True
        except Exception as e:
            self.logger.error(f"Error processing payment: {e}")
            return False 

    async def get_promo_stats(self, promo_code: str) -> Dict:
        """Получает статистику использования промокода"""
        try:
            async with aiosqlite.connect(self.db_path) as db:
                cursor = await db.execute("""
                    SELECT 
                        COUNT(*) as total_uses,
                        SUM(CASE WHEN status = 'approved' THEN 1 ELSE 0 END) as successful_uses,
                        SUM(CASE WHEN status = 'approved' THEN amount ELSE 0 END) as total_amount
                    FROM promo_uses
                    WHERE promo_code = ?
                """, (promo_code,))
                row = await cursor.fetchone()
                
                return {
                    'total_uses': row[0] or 0,
                    'successful_uses': row[1] or 0,
                    'total_amount': float(row[2] or 0)
                }
        except Exception as e:
            self.logger.error(f"Error getting promo stats: {e}")
            return {
                'total_uses': 0,
                'successful_uses': 0,
                'total_amount': 0.0
            }

    async def log_promo_use(self, promo_code: str, user_id: int, amount: float) -> bool:
        """Логирует использование промокода"""
        try:
            async with aiosqlite.connect(self.db_path) as db:
                await db.execute("""
                    INSERT INTO promo_uses (promo_code, user_id, amount)
                    VALUES (?, ?, ?)
                """, (promo_code, user_id, amount))
                await db.commit()
                return True
        except Exception as e:
            self.logger.error(f"Error logging promo use: {e}")
            return False 

    async def check_promo_exists(self, promo_code: str, telegram_id: int) -> bool:
        """
        Проверяет, существует ли промокод в базе данных
        
        Args:
            promo_code: Промокод для проверки
            telegram_id: ID пользователя в Telegram
            
        Returns:
            True если промокод уже используется другим пользователем
            False если промокод свободен или принадлежит этому пользователю
        """
        try:
            async with aiosqlite.connect(self.db_path) as db:
                cursor = await db.execute("""
                    SELECT tu.telegram_id 
                    FROM user_channels uc
                    JOIN telegram_users tu ON uc.telegram_user_id = tu.id
                    WHERE uc.promo_code = ? 
                    AND uc.is_active = TRUE
                    LIMIT 1
                """, (promo_code,))
                
                result = await cursor.fetchone()
                
                if not result:
                    # Промокод не существует
                    return False
                    
                existing_user_id = result[0]
                # Возвращаем True только если промокод принадлежит другому пользователю
                return existing_user_id != telegram_id
            
        except Exception as e:
            self.logger.error(f"Error checking promo code: {e}")
            # В случае ошибки возвращаем True, чтобы предотвратить создание дубликата
            return True 

    async def get_payment_requests(self, status: str = None, limit: int = 10, offset: int = 0) -> List[Dict]:
        """Получает список заявок на выплату с фильтрацией"""
        try:
            async with aiosqlite.connect(self.db_path) as db:
                db.row_factory = aiosqlite.Row
                
                query = """
                    SELECT 
                        pr.*,
                        datetime(pr.created_at, 'localtime') as created_at,
                        datetime(pr.updated_at, 'localtime') as updated_at
                    FROM payment_requests pr
                    WHERE 1=1
                """
                params = []
                
                if status:
                    query += " AND pr.status = ?"
                    params.append(status)
                
                query += " ORDER BY pr.created_at DESC LIMIT ? OFFSET ?"
                params.extend([limit, offset])
                
                cursor = await db.execute(query, params)
                return [dict(row) for row in await cursor.fetchall()]
        except Exception as e:
            self.logger.error(f"Error getting payment requests: {e}")
            return [] 

    async def update_channel_viewers(self, channel_id: int, viewers_count: int) -> bool:
        """Обновляет количество зрителей для Twitch канала"""
        try:
            async with aiosqlite.connect(self.db_path) as db:
                # Добавляем колонку twitch_viewers, если её нет
                try:
                    await db.execute('ALTER TABLE user_channels ADD COLUMN twitch_viewers INTEGER DEFAULT 0')
                except aiosqlite.OperationalError:
                    # Колонка уже существует
                    pass
                
                await db.execute("""
                    UPDATE user_channels 
                    SET twitch_viewers = ?
                    WHERE id = ? AND platform = 'twitch'
                """, (viewers_count, channel_id))
                await db.commit()
                return True
        except Exception as e:
            self.logger.error(f"Error updating Twitch viewers: {e}")
            return False 

    async def get_promo_effectiveness(self, promo_code: str) -> Dict:
        """Анализирует эффективность промокода"""
        try:
            async with aiosqlite.connect(self.db_path) as db:
                cursor = await db.execute("""
                    SELECT 
                        COUNT(*) as total_uses,
                        COUNT(DISTINCT user_id) as unique_users,
                        AVG(amount) as avg_amount,
                        SUM(amount) as total_amount,
                        MAX(amount) as max_amount,
                        MIN(created_at) as first_use,
                        MAX(created_at) as last_use
                    FROM promo_uses
                    WHERE promo_code = ?
                """, (promo_code,))
                row = await cursor.fetchone()
                
                return {
                    'total_uses': row[0] or 0,
                    'unique_users': row[1] or 0,
                    'avg_amount': float(row[2] or 0),
                    'total_amount': float(row[3] or 0),
                    'max_amount': float(row[4] or 0),
                    'first_use': row[5],
                    'last_use': row[6]
                }
        except Exception as e:
            self.logger.error(f"Error analyzing promo effectiveness: {e}")
            return None 

    async def save_stream_stats(self, channel_id: int, stream_data: Dict) -> bool:
        """Сохраняет статистику стрима"""
        try:
            async with aiosqlite.connect(self.db_path) as db:
                await db.execute("""
                    INSERT INTO stream_stats (
                        channel_id, 
                        stream_date,
                        duration_minutes,
                        avg_viewers,
                        max_viewers,
                        chat_messages,
                        followers_gained
                    ) VALUES (?, ?, ?, ?, ?, ?, ?)
                """, (
                    channel_id,
                    stream_data['date'],
                    stream_data['duration'],
                    stream_data['avg_viewers'],
                    stream_data['max_viewers'],
                    stream_data['chat_messages'],
                    stream_data['followers_gained']
                ))
                await db.commit()
                return True
        except Exception as e:
            self.logger.error(f"Error saving stream stats: {e}")
            return False

    async def save_vod_stats(self, channel_id: int, vod_data: Dict) -> bool:
        """Сохраняет статистику VOD"""
        try:
            async with aiosqlite.connect(self.db_path) as db:
                await db.execute("""
                    INSERT INTO vod_stats (
                        channel_id,
                        vod_link,
                        publish_date,
                        views_count,
                        avg_view_duration,
                        likes_count,
                        comments_count
                    ) VALUES (?, ?, ?, ?, ?, ?, ?)
                """, (
                    channel_id,
                    vod_data['link'],
                    vod_data['date'],
                    vod_data['views'],
                    vod_data['avg_duration'],
                    vod_data['likes'],
                    vod_data['comments']
                ))
                await db.commit()
                return True
        except Exception as e:
            self.logger.error(f"Error saving VOD stats: {e}")
            return False 

    async def check_twitch_requirements(self, channel_id: int) -> Dict:
        """Проверяет соответствие требованиям для Twitch"""
        try:
            async with aiosqlite.connect(self.db_path) as db:
                # Получаем среднюю статистику за последний месяц
                cursor = await db.execute("""
                    SELECT 
                        AVG(avg_viewers) as monthly_avg_viewers,
                        MAX(max_viewers) as monthly_max_viewers,
                        COUNT(*) as streams_count,
                        AVG(duration_minutes) as avg_duration
                    FROM stream_stats
                    WHERE channel_id = ?
                    AND stream_date >= datetime('now', '-30 days')
                """, (channel_id,))
                stats = await cursor.fetchone()
                
                # Проверяем требования
                meets_requirements = {
                    'avg_viewers': (stats[0] or 0) >= 20,  # Минимум 20 зрителей в среднем
                    'streams_count': (stats[2] or 0) >= 8,  # Минимум 8 стримов в месяц
                    'avg_duration': (stats[3] or 0) >= 120  # Минимум 2 часа в среднем
                }
                
                return {
                    'stats': {
                        'monthly_avg_viewers': float(stats[0] or 0),
                        'monthly_max_viewers': float(stats[1] or 0),
                        'streams_count': int(stats[2] or 0),
                        'avg_duration': float(stats[3] or 0)
                    },
                    'meets_requirements': meets_requirements,
                    'overall_eligible': all(meets_requirements.values())
                }
        except Exception as e:
            self.logger.error(f"Error checking Twitch requirements: {e}")
            return None 

    async def get_requests_by_status(self, status: str) -> List[Dict]:
        """Получает список заявок с определенным статусом"""
        try:
            async with aiosqlite.connect(self.db_path) as db:
                db.row_factory = aiosqlite.Row
                cursor = await db.execute("""
                    SELECT 
                        uc.id,
                        tu.username,
                        uc.platform,
                        uc.channel_link as link,
                        uc.views_count,
                        uc.experience,
                        uc.frequency,
                        uc.promo_code,
                        uc.status,
                        datetime(uc.created_at, 'localtime') as created_at
                    FROM user_channels uc
                    JOIN telegram_users tu ON uc.telegram_user_id = tu.id
                    WHERE uc.status = ? AND uc.is_active = TRUE
                    ORDER BY uc.created_at DESC
                """, (status,))
                return [dict(row) for row in await cursor.fetchall()]
        except Exception as e:
            self.logger.error(f"Error getting requests by status: {e}")
            return []

    async def approve_request(self, request_id: int, comment: str) -> bool:
        """Одобряет заявку на сотрудничество с комментарием"""
        try:
            async with aiosqlite.connect(self.db_path) as db:
                await db.execute("""
                    UPDATE user_channels 
                    SET status = 'approved',
                        admin_comment = ?,
                        updated_at = CURRENT_TIMESTAMP
                    WHERE id = ?
                """, (comment, request_id))
                await db.commit()
                return True
        except Exception as e:
            self.logger.error(f"Error approving request: {e}")
            return False

    async def reject_request(self, request_id: int, comment: str) -> bool:
        """Отклоняет заявку на сотрудничество с комментарием"""
        try:
            async with aiosqlite.connect(self.db_path) as db:
                await db.execute("""
                    UPDATE user_channels 
                    SET status = 'rejected', 
                        admin_comment = ?,
                        updated_at = CURRENT_TIMESTAMP
                    WHERE id = ?
                """, (comment, request_id))
                await db.commit()
                return True
        except Exception as e:
            self.logger.error(f"Error rejecting request: {e}")
            return False 

    async def get_collaboration_stats(self) -> Dict:
        """Получает статистику по заявкам на сотрудничество"""
        try:
            async with aiosqlite.connect(self.db_path) as db:
                cursor = await db.execute("""
                    SELECT 
                        COUNT(*) as total_applications,
                        COUNT(CASE WHEN status = 'pending' THEN 1 END) as pending_applications,
                        COUNT(CASE WHEN status = 'approved' THEN 1 END) as approved_applications,
                        COUNT(CASE WHEN status = 'rejected' THEN 1 END) as rejected_applications
                    FROM user_channels
                    WHERE is_active = TRUE
                """)
                row = await cursor.fetchone()
                return {
                    'total_applications': row[0] or 0,
                    'pending_applications': row[1] or 0,
                    'approved_applications': row[2] or 0,
                    'rejected_applications': row[3] or 0
                }
        except Exception as e:
            self.logger.error(f"Error getting collaboration stats: {e}")
            return {
                'total_applications': 0,
                'pending_applications': 0,
                'approved_applications': 0,
                'rejected_applications': 0
            } 

    async def get_users_with_pending_applications(self) -> List[Dict]:
        """Получает список пользователей с заявками в ожидании оплаты"""
        try:
            self.logger.info("Starting get_users_with_pending_applications")
            connection = await self._create_connection()  # Создаем новое соединение
            try:
                # Проверяем существование таблиц и их структуру
                self.logger.info("Checking tables structure")
                tables_cursor = await connection.execute("SELECT name FROM sqlite_master WHERE type='table'")
                tables = [table[0] for table in await tables_cursor.fetchall()]
                self.logger.info(f"Found tables: {tables}")
                
                if 'paid_content_applications' not in tables or 'telegram_users' not in tables:
                    self.logger.error("Required tables are missing!")
                    return []
                
                # Сначала получаем пользователей с ожидающими заявками
                self.logger.info("Executing main query for pending applications")
                query = """
                    SELECT 
                        tu.telegram_id,
                        tu.username,
                        COUNT(pca.id) as pending_count
                    FROM telegram_users tu
                    INNER JOIN paid_content_applications pca ON tu.id = pca.user_id
                    WHERE pca.status = 'pending'
                    GROUP BY tu.telegram_id, tu.username
                    HAVING pending_count > 0
                    ORDER BY pending_count DESC
                """
                self.logger.info(f"Query: {query}")
                
                cursor = await connection.execute(query)
                rows = await cursor.fetchall()
                self.logger.info(f"Found {len(rows)} users with pending applications")
                
                results = []
                for row in rows:
                    self.logger.info(f"Processing user: {row['username']} (ID: {row['telegram_id']})")
                    # Получаем платформы для каждого пользователя
                    platforms_query = """
                        SELECT DISTINCT uc.platform
                        FROM user_channels uc
                        JOIN telegram_users tu ON uc.telegram_user_id = tu.id
                        WHERE tu.telegram_id = ?
                        AND uc.status = 'approved'
                    """
                    platforms_cursor = await connection.execute(platforms_query, (row['telegram_id'],))
                    platforms = [platform[0] for platform in await platforms_cursor.fetchall()]
                    self.logger.info(f"Found platforms for user {row['username']}: {platforms}")
                    
                    results.append({
                        'telegram_id': row['telegram_id'],
                        'username': row['username'],
                        'pending_count': row['pending_count'],
                        'platforms': platforms
                    })
                
                self.logger.info(f"Returning {len(results)} results")
                return results
            finally:
                await connection.close()  # Всегда закрываем соединение
                
        except Exception as e:
            self.logger.error(f"Error in get_users_with_pending_applications: {str(e)}")
            self.logger.exception(e)  # Это выведет полный стек ошибки
            return [] 