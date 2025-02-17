from aiogram import Router, F, types
from aiogram.filters import Command
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton, ReplyKeyboardMarkup, KeyboardButton, ReplyKeyboardRemove
from aiogram.fsm.context import FSMContext
from database.database import Database
from keyboards.keyboards import get_main_keyboard
from config.messages import (
    START_MESSAGE,
    ABOUT_BOT_MESSAGE,
    COLLABORATION_MESSAGE,
    PAID_CONTENT_MESSAGE
)
from .states import ContentStates
from aiogram.fsm.state import State, StatesGroup
from .paid_content_handlers import show_paid_content_menu, back_to_start_callback
import re
from database.database import DatabaseError
import logging

logger = logging.getLogger(__name__)

# В начале файла добавим константы для сообщений об ошибках
LINK_ERROR_MESSAGES = {
    "youtube": (
        "❌ Неверный формат ссылки\n\n"
        "📌 Примеры правильных ссылок:\n"
        "• youtube.com/@ваш_канал\n"
        "• youtube.com/channel/ID\n\n"
        "Пожалуйста, отправьте корректную ссылку:"
    ),
    "shorts": (
        "❌ Неверный формат ссылки\n\n"
        "📌 Примеры правильных ссылок:\n"
        "• youtube.com/@ваш_канал\n"
        "• youtube.com/channel/ID\n\n"
        "Пожалуйста, отправьте корректную ссылку:"
    ),
    "tiktok": (
        "❌ Неверный формат ссылки\n\n"
        "📌 Пример правильной ссылки:\n"
        "• tiktok.com/@ваш_аккаунт\n\n"
        "Пожалуйста, отправьте корректную ссылку:"
    ),
    "twitch": (
        "❌ Неверный формат ссылки\n\n"
        "📌 Пример правильной ссылки:\n"
        "• twitch.tv/ваш_канал\n\n"
        "Пожалуйста, отправьте корректную ссылку:"
    ),
    "other": (
        "❌ Неверный формат ссылки\n\n"
        "📌 Пример формата:\n"
        "• https://ваш_сайт.com/ваш_канал\n\n"
        "Пожалуйста, отправьте корректную ссылку:"
    )
}

class CollaborationStates(StatesGroup):
    waiting_for_platform = State()
    waiting_for_link = State()
    waiting_for_views = State()
    waiting_for_experience = State()
    waiting_for_frequency = State()
    waiting_for_promo = State()
    waiting_for_more = State()
    waiting_for_viewers = State()

router = Router()
router.database = None  # Будет установлено в main.py

@router.message(Command("start"))
async def cmd_start(message: types.Message):
    # Проверяем, является ли пользователь одобренным блогером
    user_id = message.from_user.id
    username = message.from_user.username or str(user_id)
    is_approved = await router.database.is_approved_blogger(username)
    
    # Создаем обычную клавиатуру
    keyboard_buttons = [
        [KeyboardButton(text="Сотрудничество")],
        [KeyboardButton(text="О боте")]
    ]
    
    # Добавляем кнопку "Контент на оплату" только для одобренных блогеров
    if is_approved:
        keyboard_buttons.insert(1, [KeyboardButton(text="Контент на оплату")])
    
    keyboard_regular = ReplyKeyboardMarkup(
        keyboard=keyboard_buttons,
        resize_keyboard=True,
        persistent=True
    )
    
    # Создаем inline-клавиатуру с теми же опциями
    inline_buttons = [
        [InlineKeyboardButton(text="🤝 Сотрудничество", callback_data="collaboration")],
        [InlineKeyboardButton(text="ℹ️ О боте", callback_data="about")]
    ]
    
    # Добавляем inline-кнопку "Контент на оплату" только для одобренных блогеров
    if is_approved:
        inline_buttons.insert(1, [InlineKeyboardButton(text="💰 Контент на оплату", callback_data="paid_content")])
    
    keyboard_inline = InlineKeyboardMarkup(inline_keyboard=inline_buttons)
    
    # Отправляем сообщение с обеими клавиатурами
    await message.answer(
        START_MESSAGE,
        reply_markup=keyboard_regular,
        disable_web_page_preview=True
    )
    await message.answer(
        "Выберите действие:",
        reply_markup=keyboard_inline,
        parse_mode="HTML",
        disable_web_page_preview=True
    )

@router.message(F.text == "Сотрудничество")
async def collaboration(message: types.Message):
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="📝 Подать заявку", callback_data="apply_collab"),
            InlineKeyboardButton(text="📋 Требования", callback_data="collab_requirements")
        ],
        [
            InlineKeyboardButton(text="❓ FAQ", callback_data="collab_faq"),
            InlineKeyboardButton(text="◀️ Назад", callback_data="back_to_start")
        ]
    ])
    
    await message.answer(
        "💎 Информация о сотрудничестве:\n\n"
        "- Условия сотрудничества\n"
        "- Требования к контенту\n"
        "- Контактные данные\n\n"
        "Для получения дополнительной информации, пожалуйста,\n"
        "свяжитесь с администратором.",
        reply_markup=keyboard,
        parse_mode="HTML"
    )

@router.message(F.text == "О боте")
async def about_bot(message: types.Message):
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🤝 Сотрудничество", callback_data="collaboration")]
    ])
    
    await message.answer(
        ABOUT_BOT_MESSAGE,
        reply_markup=keyboard,
        parse_mode="HTML",
        disable_web_page_preview=True
    )

@router.message(Command("test_emoji"))
async def test_emoji(message: types.Message):
    await message.answer(
        text="<tg-emoji emoji-id='5201987788173500097'>⚔️</tg-emoji> Тест эмодзи из RaidTool пака",
        parse_mode="HTML",
        disable_web_page_preview=True
    )

@router.message(F.custom_emoji)
async def get_emoji_info(message: types.Message):
    if message.entities:
        for entity in message.entities:
            if hasattr(entity, 'custom_emoji_id'):
                await message.reply(
                    f"Emoji ID: {entity.custom_emoji_id}\n"
                    f"Tag format: <tg-emoji emoji-id='{entity.custom_emoji_id}'>⚔️</tg-emoji>",
                    disable_web_page_preview=True
                )

@router.message(Command("test_all_emoji"))
async def test_all_emoji(message: types.Message):
    await message.answer(
        text=(
            "Тест кастомного эмодзи:\n"
            "<tg-emoji emoji-id='5201987788173500097'>🌍</tg-emoji> - должен быть ваш кастомный эмодзи\n"
        ),
        parse_mode="HTML",
        disable_web_page_preview=True
    )

@router.message(F.text == "Контент на оплату")
async def paid_content_text(message: types.Message):
    # Получаем ID и username пользователя
    user_id = message.from_user.id
    username = message.from_user.username or str(user_id)
    
    # Проверяем, является ли пользователь одобренным блогером
    is_approved = await router.database.is_approved_blogger(username)
    
    if not is_approved:
        # Если пользователь не одобрен, показываем сообщение о необходимости подать заявку
        keyboard = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="📝 Подать заявку", callback_data="apply_collab")],
            [InlineKeyboardButton(text="❓ FAQ", callback_data="collab_faq")]
        ])
        
        await message.answer(
            "❗️ Для доступа к разделу 'Контент на оплату' необходимо:\n\n"
            "1️⃣ Подать заявку на сотрудничество\n"
            "2️⃣ Получить одобрение от администрации\n"
            "3️⃣ Выполнить минимальные требования\n\n"
            "Нажмите 'Подать заявку', чтобы начать сотрудничество!",
            reply_markup=keyboard,
            parse_mode="HTML"
        )
        return
    
    # Если пользователь авторизован, показываем меню контента на оплату
    stats = await router.database.get_user_applications_stats(user_id)
    
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="📤 Подать заявку", callback_data="submit_paid_content")],
        [InlineKeyboardButton(
            text=f"📋 Мои заявки (💰 {stats['paid']} | ⏳ {stats['unpaid']})", 
            callback_data="my_paid_content"
        )],
        [
            InlineKeyboardButton(text="ℹ️ Для нарезчиков", callback_data="info_for_cutters"),
            InlineKeyboardButton(text="📌 О функционале", callback_data="info_functionality")
        ],
        [
            InlineKeyboardButton(text="🔍 Проверить баннер", callback_data="check_banner"),
            InlineKeyboardButton(text="◀️ Назад", callback_data="back_to_start")
        ]
    ])
    
    text = (
        "💰 <b>Раздел контента на оплату</b>\n\n"
        "Здесь вы можете:\n"
        "• Подать заявку на оплату контента\n"
        "• Просмотреть статус ваших заявок\n"
        "• Проверить баннер на соответствие требованиям\n"
        "• Ознакомиться с правилами и условиями"
    )
    
    await message.answer(text, reply_markup=keyboard, parse_mode="HTML", disable_web_page_preview=True)

def is_valid_platform_link(platform: str, link: str) -> bool:
    """Проверяет валидность ссылки в зависимости от платформы."""
    patterns = {
        "youtube": (
            # Поддерживаем форматы:
            # https://youtube.com/@username
            # https://youtube.com/channel/ID
            # С www. или без, с http:// или https://
            r'https?://(?:www\.)?youtube\.com/'
            r'(?:'
            r'@[\w-]{3,}/?$|'  # username формат (минимум 3 символа)
            r'channel/[\w-]{24}/?$'  # channel ID формат (24 символа)
            r')'
        ),
        "shorts": (
            # Такой же паттерн как для YouTube
            r'https?://(?:www\.)?youtube\.com/'
            r'(?:'
            r'@[\w-]{3,}/?$|'
            r'channel/[\w-]{24}/?$'
            r')'
        ),
        "tiktok": (
            # Поддерживаем формат:
            # https://tiktok.com/@username
            # С www. или без, с http:// или https://
            r'https?://(?:www\.)?tiktok\.com/@[\w.]{2,}/?$'
        ),
        "twitch": (
            # Поддерживаем формат:
            # https://twitch.tv/username
            # С www. или без, с http:// или https://
            r'https?://(?:www\.)?twitch\.tv/[\w-]{4,}/?$'
        ),
        "other": (
            # Любой валидный URL
            r'https?://\S+'
        )
    }
    
    pattern = patterns.get(platform.lower(), patterns["other"])
    return bool(re.match(pattern, link))

# Обработчики для кнопок
@router.callback_query(F.data == "apply_collab")
async def start_collaboration(callback: types.CallbackQuery, state: FSMContext):
    # Используем edit_text для первого сообщения
    await state.set_state(CollaborationStates.waiting_for_platform)
    
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="YouTube", callback_data="platform_youtube")],
        [InlineKeyboardButton(text="Shorts", callback_data="platform_shorts")],
        [InlineKeyboardButton(text="TikTok", callback_data="platform_tiktok")],
        [InlineKeyboardButton(text="Twitch", callback_data="platform_twitch")],
        [InlineKeyboardButton(text="Другое", callback_data="platform_other")],
        [InlineKeyboardButton(text="❌ Отменить", callback_data="cancel_application")]
    ])
    
    await callback.message.edit_text(
        "🎮 Выберите платформу для сотрудничества:",
        reply_markup=keyboard
    )

@router.callback_query(F.data.startswith("platform_"))
async def process_platform(callback: types.CallbackQuery, state: FSMContext):
    # Удаляем предыдущее сообщение с выбором платформы
    await callback.message.delete()
    
    platform = callback.data.split("_")[1]
    await state.update_data(platform=platform)
    await state.set_state(CollaborationStates.waiting_for_link)
    
    # Отправляем новое сообщение
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="❌ Отменить", callback_data="cancel_application")]
    ])
    
    # Разные сообщения для разных платформ
    if platform == "youtube":
        message_text = (
            "🔗 Отправьте ссылку на ваш YouTube канал:\n\n"
            "📌 Примеры форматов:\n"
            "• youtube.com/@ваш_канал\n"
            "• youtube.com/channel/ID"
        )
    elif platform == "shorts":
        message_text = (
            "🔗 Отправьте ссылку на ваш YouTube канал:\n\n"
            "📌 Примеры форматов:\n"
            "• youtube.com/@ваш_канал\n"
            "• youtube.com/channel/ID"
        )
    elif platform == "tiktok":
        message_text = (
            "🔗 Отправьте ссылку на ваш TikTok:\n\n"
            "📌 Пример формата:\n"
            "• tiktok.com/@ваш_аккаунт"
        )
    elif platform == "twitch":
        message_text = (
            "🔗 Отправьте ссылку на ваш Twitch канал:\n\n"
            "📌 Пример формата:\n"
            "• twitch.tv/ваш_канал"
        )
    else:
        message_text = "🔗 Отправьте ссылку на ваш канал"
    
    await callback.message.answer(
        message_text,
        reply_markup=keyboard,
        disable_web_page_preview=True
    )

@router.message(CollaborationStates.waiting_for_link)
async def process_link(message: types.Message, state: FSMContext):
    # Удаляем сообщение пользователя
    await message.delete()
    
    data = await state.get_data()
    platform = data.get('platform')
    
    # Общая функция для отправки сообщения об ошибке
    async def send_error_message():
        error_message = LINK_ERROR_MESSAGES.get(platform, LINK_ERROR_MESSAGES["other"])
        keyboard = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="❌ Отменить", callback_data="cancel_application")]
        ])
        await message.answer(
            error_message,
            reply_markup=keyboard,
            disable_web_page_preview=True
        )
    
    # Проверяем, что сообщение является текстом
    if not message.text:
        await send_error_message()
        return

    # Проверяем формат ссылки
    if not is_valid_platform_link(platform, message.text):
        await send_error_message()
        return

    # Проверяем существование канала
    try:
        channel_info = await router.database.check_channel_exists(
            channel_link=message.text,
            platform=platform,
            telegram_id=message.from_user.id
        )
        
        if channel_info:
            if channel_info['own_channel']:
                await message.answer(
                    f"❌ Этот канал уже зарегистрирован у вас как {channel_info['platform']}!\n\n"
                    "Нельзя регистрировать один канал дважды на одной платформе.",
                    reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                        [InlineKeyboardButton(text="❌ Отменить", callback_data="cancel_application")]
                    ]),
                    disable_web_page_preview=True
                )
            else:
                await message.answer(
                    "❌ Этот канал уже зарегистрирован другим пользователем!\n\n"
                    "Если вы считаете, что произошла ошибка,\n"
                    "пожалуйста, обратитесь к администратору.",
                    reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                        [InlineKeyboardButton(text="❌ Отменить", callback_data="cancel_application")]
                    ]),
                    disable_web_page_preview=True
                )
            return
            
        # Если канал не существует, продолжаем процесс регистрации
        await state.update_data(current_link=message.text)
        await state.set_state(CollaborationStates.waiting_for_views)
        
        data = await state.get_data()
        platform = data.get("platform")
        
        if platform == "Twitch":
            await message.answer(
                "3️⃣ Укажите среднее количество зрителей на стриме:",
                disable_web_page_preview=True
            )
        else:
            await message.answer(
                "3️⃣ Укажите средние показатели просмотров:",
                disable_web_page_preview=True
            )

    except DatabaseError as e:
        logger.error(f"Error checking channel: {e}")
        await message.answer(
            "❌ Произошла ошибка при проверке канала.\n"
            "Пожалуйста, попробуйте позже или обратитесь в поддержку.",
            reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text="❌ Отменить", callback_data="cancel_application")]
            ])
        )

@router.message(CollaborationStates.waiting_for_views)
async def process_views(message: types.Message, state: FSMContext):
    # Проверяем, что сообщение является текстом
    if not message.text:
        data = await state.get_data()
        platform = data.get("platform")
        
        if platform == "Twitch":
            error_text = (
                "❌ Ошибка: Отправлено некорректное сообщение\n\n"
                "Пожалуйста, отправьте количество зрителей текстом, а не фото/видео/файлом\n\n"
                "✅ Примеры правильного формата:\n"
                "• 20\n"
                "• 50\n"
                "• 100"
            )
        else:
            error_text = (
                "❌ Ошибка: Отправлено некорректное сообщение\n\n"
                "Пожалуйста, отправьте количество просмотров текстом, а не фото/видео/файлом\n\n"
                "✅ Примеры правильного формата:\n"
                "• 1000\n"
                "• 5000\n"
                "• 10000"
            )
        
        await message.answer(
            error_text,
            reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text="❌ Отменить", callback_data="cancel_application")]
            ]),
            disable_web_page_preview=True
        )
        return

    # Проверяем, что введены только цифры
    views_text = message.text.strip()
    
    # Удаляем пробелы и запятые для проверки
    clean_views = views_text.replace(" ", "").replace(",", "")
    
    if not clean_views.isdigit():
        data = await state.get_data()
        platform = data.get("platform")
        
        if platform == "Twitch":
            error_text = (
                "❌ Ошибка: Неверный формат числа зрителей\n\n"
                "✅ Примеры правильного формата:\n"
                "• 20\n"
                "• 50\n"
                "• 100\n\n"
                "❌ Примеры неправильного формата:\n"
                "• 20к\n"
                "• много\n"
                "• ~20\n\n"
                "Пожалуйста, введите только число (цифры):"
            )
        else:
            error_text = (
                "❌ Ошибка: Неверный формат числа просмотров\n\n"
                "✅ Примеры правильного формата:\n"
                "• 1000\n"
                "• 5000\n"
                "• 10000\n\n"
                "❌ Примеры неправильного формата:\n"
                "• 1к\n"
                "• много\n"
                "• ~1000\n\n"
                "Пожалуйста, введите только число (цифры):"
            )
        
        await message.answer(
            error_text,
            disable_web_page_preview=True
        )
        return
    
    await state.update_data(current_views=clean_views)
    await state.set_state(CollaborationStates.waiting_for_experience)
    
    await message.answer(
        "4️⃣ Опишите ваш опыт работы с Rust:",
        disable_web_page_preview=True
    )

@router.message(CollaborationStates.waiting_for_experience)
async def process_experience(message: types.Message, state: FSMContext):
    if not message.text:
        await message.answer(
            "❌ Пожалуйста, отправьте текстовое описание вашего опыта",
            reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text="❌ Отменить", callback_data="cancel_application")]
            ])
        )
        return

    # Сохраняем опыт работы
    await state.update_data(current_experience=message.text)
    await state.set_state(CollaborationStates.waiting_for_frequency)
    
    await message.answer(
        "5️⃣ Как часто вы планируете выпускать контент?",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="❌ Отменить", callback_data="cancel_application")]
        ])
    )

@router.message(CollaborationStates.waiting_for_frequency)
async def process_frequency(message: types.Message, state: FSMContext):
    if not message.text:
        await message.answer(
            "❌ Пожалуйста, отправьте текстовое описание частоты выпуска контента",
            reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text="❌ Отменить", callback_data="cancel_application")]
            ])
        )
        return

    # Сохраняем частоту выпуска контента
    await state.update_data(current_frequency=message.text)
    await state.set_state(CollaborationStates.waiting_for_promo)
    
    await message.answer(
        "6️⃣ Укажите желаемый промокод для вашей аудитории:\n\n"
        "❗️ Требования к промокоду:\n"
        "• От 2 до 10 символов\n"
        "• Только английские буквы и цифры\n"
        "• Только ВЕРХНИЙ регистр",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="❌ Отменить", callback_data="cancel_application")]
        ])
    )

@router.message(CollaborationStates.waiting_for_promo)
async def process_promo(message: types.Message, state: FSMContext):
    if not message.text:
        await message.answer(
            "❌ Пожалуйста, отправьте промокод текстом",
            reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text="❌ Отменить", callback_data="cancel_application")]
            ])
        )
        return

    promo = message.text.strip().upper()
    
    # Проверяем формат промокода
    if not re.match(r'^[A-Z0-9]{2,10}$', promo):
        await message.answer(
            "❌ Неверный формат промокода\n\n"
            "Требования:\n"
            "• От 2 до 10 символов\n"
            "• Только английские буквы и цифры\n"
            "• Только ВЕРХНИЙ регистр\n\n"
            "Пожалуйста, отправьте корректный промокод:",
            reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text="❌ Отменить", callback_data="cancel_application")]
            ])
        )
        return

    try:
        # Проверяем уникальность промокода с учетом telegram_id
        if await router.database.check_promo_exists(promo, message.from_user.id):
            await message.answer(
                "❌ Этот промокод уже используется другим пользователем\n\n"
                "Пожалуйста, придумайте другой промокод:",
                reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                    [InlineKeyboardButton(text="❌ Отменить", callback_data="cancel_application")]
                ])
            )
            return

        # Сохраняем промокод
        await state.update_data(promo_code=promo)
        
        # Получаем все данные для предварительного просмотра
        data = await state.get_data()
        
        # Меняем текст и кнопки предпросмотра
        preview_text = (
            "📋 Проверьте данные заявки:\n\n"
            f"🎮 Платформа: {data['platform']}\n"
            f"🔗 Ссылка: {data['current_link']}\n"
            f"👁 Просмотры: {data['current_views']}\n"
            f"⭐️ Опыт: {data['current_experience']}\n"
            f"📅 Частота: {data['current_frequency']}\n"
            f"🎟 Промокод: {data['promo_code']}\n\n"
            "Все данные указаны верно?"
        )
        
        await state.set_state(CollaborationStates.waiting_for_more)
        await message.answer(
            preview_text,
            reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                [
                    InlineKeyboardButton(text="✅ Подтвердить", callback_data="finish_application"),
                    InlineKeyboardButton(text="❌ Отменить", callback_data="cancel_application")
                ]
            ])
        )

    except DatabaseError as e:
        logger.error(f"Error checking promo code: {e}")
        await message.answer(
            "❌ Произошла ошибка при проверке промокода.\n"
            "Пожалуйста, попробуйте позже или обратитесь в поддержку.",
            reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text="❌ Отменить", callback_data="cancel_application")]
            ])
        )

# Добавляем новые обработчики для инлайн-кнопок
@router.callback_query(lambda c: c.data == "about")
async def about_bot_callback(callback: types.CallbackQuery):
    # Проверяем, является ли пользователь одобренным блогером
    user_id = callback.from_user.id
    username = callback.from_user.username or str(user_id)
    is_approved = await router.database.is_approved_blogger(username)
    
    # Создаем кнопки в зависимости от статуса пользователя
    buttons = [[InlineKeyboardButton(text="🤝 Сотрудничество", callback_data="collaboration")]]
    
    # Добавляем кнопку "Назад"
    buttons.append([InlineKeyboardButton(text="◀️ Назад", callback_data="back_to_start")])
    
    keyboard = InlineKeyboardMarkup(inline_keyboard=buttons)
    
    await callback.message.edit_text(
        ABOUT_BOT_MESSAGE,
        reply_markup=keyboard,
        parse_mode="HTML",
        disable_web_page_preview=True
    )

@router.callback_query(lambda c: c.data == "collaboration")
async def collaboration_callback(callback: types.CallbackQuery):
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="📝 Подать заявку", callback_data="apply_collab"),
            InlineKeyboardButton(text="📋 Требования", callback_data="collab_requirements")
        ],
        [
            InlineKeyboardButton(text="❓ FAQ", callback_data="collab_faq"),
            InlineKeyboardButton(text="◀️ Назад", callback_data="back_to_start")
        ]
    ])
    
    await callback.message.edit_text(
        "💎 Информация о сотрудничестве:\n\n"
        "- Условия сотрудничества\n"
        "- Требования к контенту\n"
        "- Контактные данные\n\n"
        "Для получения дополнительной информации, пожалуйста,\n"
        "свяжитесь с администратором.",
        reply_markup=keyboard,
        parse_mode="HTML"
    )

@router.callback_query(lambda c: c.data == "collab_requirements")
async def show_requirements(callback: types.CallbackQuery):
    requirements_text = (
        "📋 <b>Требования для сотрудничества:</b>\n\n"
        "🎥 <b>YouTube:</b>\n"
        "• От 1000 просмотров в среднем на Rust-контенте\n"
        "• Регулярные выпуски видео\n"
        "• Качественный монтаж и звук\n\n"
        "📱 <b>Shorts/TikTok:</b>\n"
        "• От 3000 просмотров на видео по Rust\n"
        "• Активная публикация контента\n"
        "• Креативный подход к съемке\n\n"
        "🎮 <b>Twitch:</b>\n"
        "• Стабильно 20+ зрителей на стриме\n"
        "• Регулярные стримы по Rust\n"
        "• Взаимодействие с аудиторией\n\n"
        "🌐 <b>Другие площадки:</b>\n"
        "• Обсуждаются индивидуально\n"
        "• Важен охват и вовлеченность аудитории"
    )
    
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="📝 Подать заявку", callback_data="apply_collab")],
        [InlineKeyboardButton(text="◀️ Назад", callback_data="collaboration")]
    ])
    
    await callback.message.edit_text(
        requirements_text,
        reply_markup=keyboard,
        parse_mode="HTML",
        disable_web_page_preview=True
    )

@router.callback_query(lambda c: c.data == "collab_faq")
async def show_faq(callback: types.CallbackQuery):
    faq_text = (
        "❓ <b>Часто задаваемые вопросы:</b>\n\n"
        "1️⃣ <b>Как часто нужно выпускать контент?</b>\n"
        "• Минимум 2-3 видео/стрима в месяц\n"
        "• Для Shorts/TikTok желательно 2-3 видео в неделю\n\n"
        "2️⃣ <b>Какие требования к баннеру/интеграции?</b>\n"
        "• Баннер должен быть хорошо виден\n"
        "• Не должен перекрываться интерфейсом\n"
        "• Минимальное время показа - 8 секунд\n\n"
        "3️⃣ <b>Как происходит оплата?</b>\n"
        "• Индивидуальные условия\n"
        "• Зависит от охвата и качества контента\n"
        "• Обсуждается после одобрения заявки\n\n"
        "4️⃣ <b>Можно ли совмещать с другими проектами?</b>\n"
        "• Да, если это не конкурирующие проекты\n"
        "• Обсуждается индивидуально"
    )
    
    keyboard = InlineKeyboardButton(text="📝 Подать заявку", callback_data="apply_collab")
    inline_buttons = [
        [InlineKeyboardButton(text="◀️ Назад", callback_data="collaboration")],
        [keyboard]
    ]
    keyboard = InlineKeyboardMarkup(inline_keyboard=inline_buttons)
    
    await callback.message.edit_text(
        faq_text,
        reply_markup=keyboard,
        parse_mode="HTML",
        disable_web_page_preview=True
    )

@router.callback_query(F.data == "cancel_application")
async def cancel_application(callback: types.CallbackQuery, state: FSMContext):
    # Очищаем состояние пользователя
    await state.clear()
    
    # Создаем базовые кнопки для неавторизованного пользователя
    inline_buttons = [
        [InlineKeyboardButton(text="🤝 Сотрудничество", callback_data="collaboration")],
        [InlineKeyboardButton(text="ℹ️ О боте", callback_data="about")]
    ]
    
    keyboard = InlineKeyboardMarkup(inline_keyboard=inline_buttons)
    
    # Отправляем новое сообщение вместо редактирования старого
    await callback.message.delete()  # Удаляем старое сообщение
    await callback.message.answer(
        START_MESSAGE,
        reply_markup=keyboard,
        parse_mode="HTML",
        disable_web_page_preview=True
    )

@router.callback_query(F.data == "platform_twitch")
async def process_twitch_platform(callback: types.CallbackQuery, state: FSMContext):
    await state.update_data(platform="twitch")
    await state.set_state(CollaborationStates.waiting_for_link)
    
    await callback.message.edit_text(
        "2️⃣ Отправьте ссылку на ваш Twitch-канал:\n\n"
        "Пример: https://twitch.tv/your_channel",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="❌ Отменить", callback_data="cancel_application")]
        ])
    )

@router.message(CollaborationStates.waiting_for_link, lambda m: m.text and "twitch.tv" in m.text.lower())
async def process_twitch_link(message: types.Message, state: FSMContext):
    # Проверяем формат ссылки
    if not is_valid_platform_link("twitch", message.text):
        await message.answer(
            LINK_ERROR_MESSAGES["twitch"],
            reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text="❌ Отменить", callback_data="cancel_application")]
            ])
        )
        return

    await state.update_data(current_link=message.text)
    await state.set_state(CollaborationStates.waiting_for_viewers)  # Новое состояние для Twitch
    
    await message.answer(
        "3️⃣ Укажите среднее количество зрителей на стриме:",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="❌ Отменить", callback_data="cancel_application")]
        ])
    )

@router.message(CollaborationStates.waiting_for_viewers)
async def process_twitch_viewers(message: types.Message, state: FSMContext):
    try:
        viewers = int(message.text)
        
        # Проверяем на отрицательное число
        if viewers < 0:
            raise ValueError("Negative number")
        
        # Проверяем минимальные требования (20+ зрителей)
        if viewers < 20:
            await message.answer(
                "❌ К сожалению, ваш канал пока не соответствует требованиям.\n\n"
                "Для сотрудничества необходимо минимум 20 зрителей в среднем на стриме.\n"
                "Попробуйте подать заявку позже, когда ваша аудитория вырастет!",
                reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                    [InlineKeyboardButton(text="❌ Отменить", callback_data="cancel_application")]
                ])
            )
            return
            
        await state.update_data(current_viewers=viewers)
        await state.set_state(CollaborationStates.waiting_for_views)
        
        await message.answer(
            "4️⃣ Укажите среднее количество просмотров VOD (видео) за последний месяц:",
            reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text="❌ Отменить", callback_data="cancel_application")]
            ])
        )
        
    except ValueError:
        await message.answer(
            "❌ Пожалуйста, введите корректное число зрителей\n\n"
            "✅ Примеры правильного формата:\n"
            "• 20\n"
            "• 50\n"
            "• 100\n\n"
            "❌ Примеры неправильного формата:\n"
            "• 20к\n"
            "• много\n"
            "• ~20",
            reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text="❌ Отменить", callback_data="cancel_application")]
            ])
        )

@router.callback_query(F.data == "finish_application")
async def finish_application(callback: types.CallbackQuery, state: FSMContext):
    """Обработчик для завершения подачи заявки"""
    data = await state.get_data()
    
    try:
        # Получаем или создаем пользователя
        user_id = callback.from_user.id
        username = callback.from_user.username or str(user_id)
        telegram_user_id = await router.database.get_or_create_user(user_id, username)
        
        # Сохраняем заявку со всеми данными
        channel_id = await router.database.add_channel(
            telegram_id=user_id,
            platform=data['platform'],
            channel_link=data['current_link'],
            channel_name=data['current_link'],  # Используем ссылку как имя канала
            views_count=int(data['current_views']),
            experience=data['current_experience'],
            frequency=data['current_frequency'],
            promo_code=data['promo_code']
        )
        
        # Если это Twitch, сохраняем также количество зрителей
        if data['platform'].lower() == 'twitch' and 'current_viewers' in data:
            await router.database.update_channel_viewers(
                channel_id=channel_id,
                viewers_count=int(data['current_viewers'])
            )
        
        if not channel_id:
            await callback.answer("❌ Ошибка при сохранении заявки", show_alert=True)
            return
        
        # Очищаем состояние
        await state.clear()
        
        # Отправляем сообщение об успехе
        await callback.message.edit_text(
            "✅ Ваша заявка успешно отправлена!\n\n"
            "Мы рассмотрим её в течение 48 часов и свяжемся с вами.\n"
            "Спасибо за интерес к сотрудничеству с HARDWAY!",
            reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                [
                    InlineKeyboardButton(text="📝 Подать новую заявку", callback_data="apply_collab"),
                    InlineKeyboardButton(text="◀️ В меню", callback_data="back_to_start")
                ]
            ])
        )
        
    except Exception as e:
        logger.error(f"Error saving application: {e}")
        await callback.answer(
            "❌ Произошла ошибка при сохранении заявки.\n"
            "Пожалуйста, попробуйте позже или обратитесь в поддержку.",
            show_alert=True
        )

def register_media_handlers(dp, db: Database):
    router.database = db  # Устанавливаем базу данных для роутера
    dp.include_router(router) 