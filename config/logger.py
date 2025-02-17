import logging
from logging.handlers import RotatingFileHandler
import os
import sys

def setup_logger(name: str = 'bot_logger') -> logging.Logger:
    """Настраивает и возвращает логгер с обработчиками для файла и консоли"""
    
    # Создаем директорию для логов, если её нет
    if not os.path.exists('logs'):
        os.makedirs('logs')
    
    logger = logging.getLogger(name)
    logger.setLevel(logging.INFO)
    
    # Форматтер для логов
    formatter = logging.Formatter(
        '%(asctime)s - %(name)s - %(levelname)s - %(message)s',
        '%Y-%m-%d %H:%M:%S'
    )
    
    # Обработчик для записи в файл с ротацией (максимум 5 файлов по 5 МБ)
    file_handler = RotatingFileHandler(
        'logs/bot.log',
        maxBytes=5_000_000,
        backupCount=5,
        encoding='utf-8'
    )
    file_handler.setLevel(logging.INFO)
    file_handler.setFormatter(formatter)
    
    # Обработчик для вывода в консоль
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setLevel(logging.INFO)
    console_handler.setFormatter(formatter)
    
    # Добавляем обработчики к логгеру
    logger.addHandler(file_handler)
    logger.addHandler(console_handler)
    
    return logger 