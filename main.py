import asyncio
import logging
import os
from dotenv import load_dotenv
from aiogram import Bot, Dispatcher
from aiogram.client.session.aiohttp import AiohttpSession
from aiogram.exceptions import TelegramAPIError, TelegramNetworkError
from config.config import load_config
from config.logger import setup_logger
from database.database import Database, DatabaseError
from handlers.media_handlers import register_media_handlers
from handlers.admin_handlers import register_admin_handlers
from handlers.paid_content_handlers import router as paid_content_router

# Создаем базу данных глобально
db = Database()

async def main():
    try:
        # Загружаем переменные окружения
        load_dotenv()
        
        # Настраиваем логгер
        logger = setup_logger()
        logger.info("Starting bot...")
        
        # Загружаем конфигурацию
        try:
            config = load_config()
        except Exception as e:
            logger.error(f"Failed to load configuration: {e}")
            return
        
        # Инициализируем бота и диспетчер
        try:
            bot = Bot(token=config.bot.token)
            dp = Dispatcher()
            
            # Добавляем базу данных в storage диспетчера
            dp.storage.database = db
            
            # Инициализируем базу данных
            try:
                await db.create_tables()
                await db.add_username_column()
                await db.add_user_mention_column()
                logger.info("Database initialized successfully")
            except DatabaseError as e:
                logger.error(f"Database initialization failed: {e}")
                return
            
            # Регистрируем хендлеры
            paid_content_router.database = db
            dp.include_router(paid_content_router)
            
            register_media_handlers(dp, db)
            
            # Регистрируем админ-хендлеры с передачей списка админов
            register_admin_handlers(dp, db, config.bot.admin_ids)
            
            logger.info("Starting polling...")
            
            # Запускаем поллинг с обработкой ошибок
            while True:
                try:
                    await dp.start_polling(bot)
                except TelegramNetworkError as e:
                    logger.error(f"Network error occurred: {e}. Retrying in 5 seconds...")
                    await asyncio.sleep(5)
                except TelegramAPIError as e:
                    logger.error(f"Telegram API error: {e}. Retrying in 5 seconds...")
                    await asyncio.sleep(5)
                except Exception as e:
                    logger.error(f"Unexpected error: {e}. Retrying in 5 seconds...")
                    await asyncio.sleep(5)
            
        except TelegramAPIError as e:
            logger.error(f"Telegram API error: {e}")
        except Exception as e:
            logger.error(f"Unexpected error: {e}")
        finally:
            if 'bot' in locals():
                await bot.session.close()
                logger.info("Bot session closed")
            await db.close()
            logger.info("Database connection closed")
    
    except Exception as e:
        logging.error(f"Critical error: {e}")
        raise

if __name__ == '__main__':
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logging.info("Bot stopped by user")
    except Exception as e:
        logging.critical(f"Bot crashed: {e}")
        raise 