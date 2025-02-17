import logging
from aiogram import Bot
from aiogram.exceptions import TelegramAPIError, TelegramBadRequest

logger = logging.getLogger(__name__)

async def safe_send_message(bot: Bot, user_id: int, text: str, **kwargs) -> bool:
    """
    Безопасно отправляет сообщение пользователю с обработкой ошибок.
    
    Args:
        bot: Экземпляр бота
        user_id: ID пользователя
        text: Текст сообщения
        **kwargs: Дополнительные параметры для метода send_message
        
    Returns:
        bool: True если сообщение успешно отправлено, False в противном случае
    """
    try:
        await bot.send_message(user_id, text, **kwargs)
        return True
        
    except TelegramBadRequest as e:
        if "user not found" in str(e).lower():
            logger.warning(f"User {user_id} not found")
        elif "blocked" in str(e).lower():
            logger.warning(f"User {user_id} blocked the bot")
        else:
            logger.error(f"Failed to send message to user {user_id}: {e}")
        return False
        
    except TelegramAPIError as e:
        logger.error(f"Telegram API error while sending message to user {user_id}: {e}")
        return False
        
    except Exception as e:
        logger.error(f"Unexpected error while sending message to user {user_id}: {e}")
        return False

async def safe_edit_message(bot: Bot, chat_id: int, message_id: int, text: str, **kwargs) -> bool:
    """
    Безопасно редактирует сообщение с обработкой ошибок.
    
    Args:
        bot: Экземпляр бота
        chat_id: ID чата
        message_id: ID сообщения
        text: Новый текст сообщения
        **kwargs: Дополнительные параметры для метода edit_message_text
        
    Returns:
        bool: True если сообщение успешно отредактировано, False в противном случае
    """
    try:
        await bot.edit_message_text(text, chat_id=chat_id, message_id=message_id, **kwargs)
        return True
        
    except TelegramBadRequest as e:
        if "message is not modified" in str(e).lower():
            # Это не ошибка, просто текст не изменился
            return True
        logger.error(f"Failed to edit message {message_id} in chat {chat_id}: {e}")
        return False
        
    except TelegramAPIError as e:
        logger.error(f"Telegram API error while editing message {message_id} in chat {chat_id}: {e}")
        return False
        
    except Exception as e:
        logger.error(f"Unexpected error while editing message {message_id} in chat {chat_id}: {e}")
        return False 