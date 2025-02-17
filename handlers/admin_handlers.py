from aiogram import Router, F, types
from aiogram.filters import Command, BaseFilter
from aiogram.types import Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.exceptions import TelegramBadRequest
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from database.database import Database, DatabaseError
from utils.message_utils import safe_send_message, safe_edit_message
from .states import AdminStates  # Убираем PaymentStates, так как он нам не нужен здесь
import logging
import re
import aiosqlite
from datetime import datetime

logger = logging.getLogger('bot_logger')

router = Router()
router.database = None  # Будет установлено в main.py
ADMIN_IDS = []  # Будет установлено при инициализации

APPS_PER_PAGE = 1  # Количество заявок на странице

class ApprovalStates(StatesGroup):
    waiting_for_username = State()
    waiting_for_promo = State()
    waiting_for_confirmation = State()
    waiting_for_comment = State()

class PaymentStates(StatesGroup):
    waiting_for_views = State()
    waiting_for_amount = State()
    waiting_for_confirmation = State()

# Добавляем новый набор состояний для создания связи
class ConnectionStates(StatesGroup):
    waiting_for_channel_link = State()  # Ожидаем ввода ссылки от пользователя
    # Здесь можно добавить дополнительные состояния, если потребуется

# Создаем фильтр для проверки состояния
class NoActiveState(BaseFilter):
    async def __call__(self, message: Message, state: FSMContext) -> bool:
        current_state = await state.get_state()
        if current_state is not None:
            await message.answer(
                "❌ Команды недоступны во время заполнения формы.\n"
                "Сначала завершите текущее действие или отмените его командой /cancel",
                disable_web_page_preview=True
            )
            return False
        return True

# Создаем фильтр для проверки админа
class IsAdmin(BaseFilter):
    async def __call__(self, message: Message) -> bool:
        return message.from_user.id in ADMIN_IDS

def register_admin_handlers(dp, db: Database, admin_ids: list[int]):
    """Регистрирует обработчики админ-команд"""
    global ADMIN_IDS
    ADMIN_IDS = admin_ids
    router.database = db
    dp.include_router(router)

async def safe_send_message(bot, user_id: int, text: str, **kwargs):
    """Безопасно отправляет сообщение пользователю, игнорируя ошибки блокировки"""
    try:
        await bot.send_message(user_id, text, **kwargs)
    except Exception as e:
        logging.error(f"Error sending message to user {user_id}: {e}")

async def format_application_text(app: dict) -> str:
    """Форматирует текст заявки для отображения"""
    # Безопасное получение значений с дефолтными значениями
    content_type = app.get('content_type', 'unknown')
    status = app.get('status', 'unknown')
    username = app.get('username', 'Нет username')
    link = app.get('link', 'Ссылка отсутствует')
    views_count = app.get('views_count', 0)
    publish_date = app.get('publish_date', 'Дата не указана')
    
    # Определяем тип контента для отображения
    content_type_display = {
        'video': '🎥 Видео',
        'shorts': '📱 Shorts/TikTok',
        'stream': '🎮 Стрим',
        'unknown': '❓ Тип не указан'
    }
    
    # Базовый текст для всех типов заявок
    text = (
        f"📊 Тип контента: {content_type_display.get(content_type, '❓ Неизвестный тип')}\n"
        f"🔗 Ссылка: {link}\n"
        f"👁 Просмотры: {views_count:,}\n"
        f"📅 Дата публикации: {publish_date}\n"
    )
    
    # Добавляем специфичные поля для стримов
    if content_type == 'stream' and 'screenshot' in app:
        text += f"📸 Скриншот статистики: {app['screenshot']}\n"
    
    # Добавляем дополнительные поля, если они есть
    if 'current_views' in app and app['current_views'] is not None:
        text += f"📊 Текущие просмотры: {app['current_views']:,}\n"
        
    if 'payment_amount' in app and app['payment_amount'] is not None:
        text += f"💰 Сумма выплаты: {app['payment_amount']} руб.\n"
        
    # Добавляем примечания
    if 'notes' in app and app['notes']:
        text += f"\n📝 Примечания: {app['notes']}\n"
    elif 'note' in app and app['note']:  # Поддержка обоих вариантов поля
        text += f"\n📝 Примечания: {app['note']}\n"
    
    return text

# Фильтр для проверки админа
def is_admin(admin_ids: list[int]):
    async def check(message: Message):
        return message.from_user.id in admin_ids
    return check

# Команда для просмотра заявок на сотрудничество
@router.message(Command("apps"), IsAdmin(), NoActiveState())
async def show_applications_menu(message: Message):
    # Получаем статистику по заявкам на сотрудничество
    stats = await router.database.get_collaboration_stats()
    
    # Формируем текст статистики
    stats_text = (
        "📊 <b>Статистика по заявкам на сотрудничество</b>\n\n"
        f"• Всего заявок: {stats['total_applications']}\n"
        f"• Ожидают проверки: {stats['pending_applications']}\n"
        f"• Одобрено: {stats['approved_applications']}\n"
        f"• Отклонено: {stats['rejected_applications']}\n"
    )
    
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(
            text=f"⏳ Новые заявки ({stats['pending_applications']})", 
            callback_data="show_pending_apps"
        )],
        [InlineKeyboardButton(
            text=f"✅ Одобренные ({stats['approved_applications']})", 
            callback_data="show_approved_apps"
        )],
        [InlineKeyboardButton(
            text=f"❌ Отклоненные ({stats['rejected_applications']})", 
            callback_data="show_rejected_apps"
        )]
    ])
    
    await message.answer(stats_text, reply_markup=keyboard, parse_mode="HTML")

# Обработчик для просмотра заявок определенного статуса
@router.callback_query(F.data.startswith("show_"))
async def show_requests_by_status(callback: CallbackQuery):
    status = callback.data.split("_")[1]  # pending, approved, rejected
    
    # Получаем заявки с соответствующим статусом
    requests = await router.database.get_requests_by_status(status)
    
    if not requests:
        status_text = {
            "pending": "ожидающих проверки",
            "approved": "одобренных",
            "rejected": "отклоненных"
        }.get(status, "")
        
        await callback.message.edit_text(
            f"📝 Нет {status_text} заявок",
            reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text="◀️ Назад", callback_data="back_to_admin_menu")]
            ])
        )
        return
    
    # Показываем первую заявку
    await show_request(callback.message, requests[0], len(requests), 0, status)

async def show_request(message: Message, request: dict, total: int, current_index: int, status: str):
    """Показывает одну заявку с кнопками управления"""
    
    # Форматируем текст заявки
    text = (
        f"📝 <b>Заявка #{request['id']}</b>\n\n"
        f"👤 Пользователь: @{request['username']}\n"
        f"🎮 Платформа: {request['platform']}\n"
        f"🔗 Ссылка: {request['link']}\n"
        f"👁 Просмотры: {request['views_count']:,}\n"
        f"⭐️ Опыт: {request['experience']}\n"
        f"📅 Частота: {request['frequency']}\n"
        f"🎟 Промокод: {request['promo_code']}\n"
    )

    # Добавляем комментарий администратора, если он есть и статус не pending
    if status != 'pending' and request.get('admin_comment'):
        text += f"\n💬 Комментарий: {request['admin_comment']}\n"
    
    text += f"\nЗаявка {current_index + 1} из {total}"
    
    # Создаем кнопки навигации и управления
    keyboard = []
    
    # Кнопки навигации
    nav_buttons = []
    if current_index > 0:
        nav_buttons.append(InlineKeyboardButton(text="◀️", callback_data=f"nav_request_{status}_{current_index-1}"))
    if current_index < total - 1:
        nav_buttons.append(InlineKeyboardButton(text="▶️", callback_data=f"nav_request_{status}_{current_index+1}"))
    if nav_buttons:
        keyboard.append(nav_buttons)
    
    # Кнопки действий (только для новых заявок)
    if status == "pending":
        keyboard.extend([
            [
                InlineKeyboardButton(text="✅ Одобрить", callback_data=f"approve_request_{request['id']}"),
                InlineKeyboardButton(text="❌ Отклонить", callback_data=f"reject_request_{request['id']}")
            ]
        ])
    
    # Кнопка "Назад"
    keyboard.append([InlineKeyboardButton(text="◀️ К списку", callback_data="back_to_admin_menu")])
    
    await message.edit_text(
        text,
        reply_markup=InlineKeyboardMarkup(inline_keyboard=keyboard),
        parse_mode="HTML",
        disable_web_page_preview=True
    )

# Обработчик навигации по заявкам
@router.callback_query(F.data.startswith("nav_request_"))
async def navigate_requests(callback: CallbackQuery):
    # Формат callback_data: "nav_request_status_index"
    parts = callback.data.split("_")
    if len(parts) < 4:
        logger.error(f"Invalid callback data format: {callback.data}")
        return

    status = parts[2]
    index = int(parts[3])
    
    requests = await router.database.get_requests_by_status(status)
    if 0 <= index < len(requests):
        await show_request(callback.message, requests[index], len(requests), index, status)

# Обработчик одобрения заявки
@router.callback_query(F.data.startswith("approve_request_"))
async def approve_request(callback: CallbackQuery, state: FSMContext):
    request_id = int(callback.data.split("_")[2])
    await state.update_data(request_id=request_id, action_type='approve')
    await state.set_state(AdminStates.waiting_for_comment)
    
    await callback.message.edit_text(
        "✍️ Укажите комментарий к одобрению заявки:\n"
        "(например: условия сотрудничества, ставка и т.д.)",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="❌ Отменить", callback_data="cancel_admin_action")]
        ])
    )

# Обработчик комментария к одобрению/отклонению
@router.message(AdminStates.waiting_for_comment)
async def process_admin_comment(message: Message, state: FSMContext):
    data = await state.get_data()
    request_id = data.get('request_id')
    action_type = data.get('action_type')
    
    if not request_id:
        await message.answer("❌ Ошибка: заявка не найдена")
        await state.clear()
        return

    success = False

    if action_type == 'approve':
        success = await router.database.approve_request(request_id, message.text)
        success_message = "✅ Заявка одобрена"
    else:
        success = await router.database.reject_request(request_id, message.text)
        success_message = "❌ Заявка отклонена"

    if success:
        await message.answer(success_message)
    else:
        await message.answer("❌ Ошибка при обработке заявки")
    
    await state.clear()
    # Возвращаемся к списку заявок
    await show_applications_menu(message)

# Обработчик отклонения заявки
@router.callback_query(F.data.startswith("reject_request_"))
async def start_reject_request(callback: CallbackQuery, state: FSMContext):
    request_id = int(callback.data.split("_")[2])
    await state.update_data(request_id=request_id, action_type='reject')
    await state.set_state(AdminStates.waiting_for_comment)
    
    await callback.message.edit_text(
        "❌ Укажите причину отклонения заявки:",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="❌ Отменить", callback_data="cancel_admin_action")]
        ])
    )

# Обработчик отмены действия админа
@router.callback_query(F.data == "cancel_admin_action")
async def cancel_admin_action(callback: CallbackQuery, state: FSMContext):
    await state.clear()
    await show_applications_menu(callback.message)

# Обработчик возврата в админ-меню
@router.callback_query(F.data == "back_to_admin_menu")
async def back_to_admin_menu(callback: CallbackQuery):
    await show_applications_menu(callback.message)

# Команда для просмотра пользователей с ожидающими заявками
@router.message(Command("pay"), IsAdmin())
async def show_users_with_pending_apps(message: Message):
    """Показывает список пользователей с заявками в ожидании оплаты"""
    logger.info("Processing /pay command")
    
    users = await router.database.get_users_with_pending_applications()
    logger.info(f"Found {len(users)} users with pending applications")
    
    if not users:
        logger.warning("No users with pending applications found")
        await message.answer("📝 Нет заявок, ожидающих оплаты")
        return
    
    # Формируем общую статистику
    total_pending = sum(user['pending_count'] for user in users)
    logger.info(f"Total pending applications: {total_pending}")
    
    text = [
        "📊 <b>Статистика заявок на оплату</b>",
        f"• Всего заявок в ожидании: {total_pending}",
        f"• Количество пользователей: {len(users)}",
        "\n👥 <b>Список пользователей с заявками:</b>"
    ]
    
    keyboard = []
    for user in users:
        username = user['username'] or f"id{user['telegram_id']}"
        platforms_str = " ".join([
            {
                'youtube': '📺',
                'tiktok': '📱',
                'shorts': '📱',
                'twitch': '🎮',
                'other': '🎯'
            }.get(platform, '🔗') for platform in user['platforms']
        ])
        
        logger.info(f"Processing user @{username} with {user['pending_count']} pending applications")
        
        # Добавляем информацию о пользователе в текст
        text.append(
            f"\n@{username}"
            f"\n└ Заявок: 🕒 {user['pending_count']}"
            f"\n└ Платформы: {platforms_str}"
        )
        
        # Добавляем кнопку для пользователя
        keyboard.append([
            InlineKeyboardButton(
                text=f"@{username} ({platforms_str} | 🕒 {user['pending_count']})",
                callback_data=f"show_user_{user['telegram_id']}"
            )
        ])
    
    # Добавляем кнопку обновления списка
    keyboard.append([
        InlineKeyboardButton(text="🔄 Обновить список", callback_data="refresh_pay_list")
    ])
    
    logger.info("Sending response message")
    await message.answer(
        "\n".join(text),
        reply_markup=InlineKeyboardMarkup(inline_keyboard=keyboard),
        parse_mode="HTML"
    )

# Добавляем обработчик для кнопки обновления
@router.callback_query(F.data == "refresh_pay_list")
async def refresh_pay_list(callback: CallbackQuery):
    """Обновляет список пользователей с заявками"""
    await show_users_with_pending_apps(callback.message)
    await callback.answer("Список обновлен")

@router.callback_query(F.data.startswith("show_user_"))
async def show_user_menu(callback: CallbackQuery):
    """Показывает меню действий для конкретного пользователя"""
    user_id = int(callback.data.split("_")[2])
    
    # Получаем информацию о платформах пользователя
    platforms = await router.database.get_user_platforms(user_id)
    
    keyboard = [
        [InlineKeyboardButton(text="📊 Платформы", callback_data=f"user_platforms_{user_id}")],
        [InlineKeyboardButton(text="📈 Статистика", callback_data=f"user_stats_{user_id}")],
        [InlineKeyboardButton(text="💬 Связаться", callback_data=f"contact_user_{user_id}")],
        [InlineKeyboardButton(text="◀️ Назад", callback_data="back_to_pay_menu")]
    ]
    
    platforms_text = "\n".join([
        f"• {p['platform']}: всего {p['total_content']}, оплачено {p['paid_content']}"
        for p in platforms
    ]) if platforms else "Нет активных платформ"
    
    await callback.message.edit_text(
        f"👤 Информация о пользователе:\n\n"
        f"🎮 Платформы:\n{platforms_text}\n\n"
        f"Выберите действие:",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=keyboard)
    )

@router.callback_query(F.data == "back_to_pay_menu")
async def back_to_pay_menu(callback: CallbackQuery):
    """Возвращает к списку пользователей с ожидающими заявками"""
    await show_users_with_pending_apps(callback.message)

# ... остальные обработчики для админки 