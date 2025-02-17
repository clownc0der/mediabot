from aiogram import Router, F
from aiogram.types import Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from datetime import datetime, timedelta
from .states import PaidContentStates
from config.messages import START_MESSAGE, PAID_CONTENT_MESSAGE
import re

# Константы
MIN_VIEWS = 1000  # Минимальное количество просмотров для подачи заявки
MIN_VIEWS_SHORTS = 1000  # Минимум для шортсов/тиктоков
MIN_VIEWS_VIDEO = 3000   # Минимум для обычных видео
MIN_VIEWS_STREAM = 20    # Минимум зрителей для стримов

router = Router()
router.database = None  # Будет установлено в main.py

# Обработчик для кнопки "Контент на оплату"
@router.callback_query(F.data == "paid_content")
async def show_paid_content_menu(callback: CallbackQuery):
    # Получаем ID и username пользователя
    user_id = callback.from_user.id
    username = callback.from_user.username or str(user_id)
    
    # Проверяем, является ли пользователь одобренным блогером
    is_approved = await router.database.is_approved_blogger(username)
    
    if not is_approved:
        # Создаем базовые кнопки для неавторизованного пользователя
        inline_buttons = [
            [InlineKeyboardButton(text="🤝 Сотрудничество", callback_data="collaboration")],
            [InlineKeyboardButton(text="ℹ️ О боте", callback_data="about")]
        ]
        
        keyboard = InlineKeyboardMarkup(inline_keyboard=inline_buttons)
        
        # Тихо возвращаем в базовое меню
        await callback.message.edit_text(
            START_MESSAGE,
            reply_markup=keyboard,
            parse_mode="HTML",
            disable_web_page_preview=True
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
    
    await callback.message.edit_text(text, reply_markup=keyboard, parse_mode="HTML", disable_web_page_preview=True)

# Заглушки для кнопок (потом заменим на реальный функционал)
@router.callback_query(F.data == "submit_paid_content")
async def submit_paid_content(callback: CallbackQuery):
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="YouTube", callback_data="submit_youtube")],
        [InlineKeyboardButton(text="Shorts", callback_data="submit_shorts")],
        [InlineKeyboardButton(text="TikTok", callback_data="submit_tiktok")],
        [InlineKeyboardButton(text="Twitch", callback_data="submit_twitch")],
        [InlineKeyboardButton(text="Другое", callback_data="submit_other")],
        [InlineKeyboardButton(text="◀️ Назад", callback_data="paid_content")]
    ])
    
    text = (
        "📤 <b>Подача заявки на оплату контента</b>\n\n"
        "Выберите платформу, на которой размещен контент:"
    )
    
    await callback.message.edit_text(text, reply_markup=keyboard, parse_mode="HTML", disable_web_page_preview=True)

@router.callback_query(F.data == "my_paid_content")
async def my_paid_content(callback: CallbackQuery):
    """Показывает меню выбора категории заявок"""
    stats = await router.database.get_user_applications_stats(callback.from_user.id)
    
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text=f"💰 Оплаченные ({stats['paid']})", callback_data="show_paid_apps")],
        [InlineKeyboardButton(text=f"⏳ Ожидают оплаты ({stats['unpaid']})", callback_data="show_unpaid_apps")],
        [InlineKeyboardButton(text="◀️ В меню", callback_data="paid_content")]
    ])
    
    await callback.message.edit_text(
        "📋 <b>Мои заявки</b>\n\n"
        "Выберите категорию для просмотра:",
        reply_markup=keyboard,
        parse_mode="HTML",
        disable_web_page_preview=True
    )

@router.callback_query(F.data.in_(["show_paid_apps", "show_unpaid_apps"]))
async def show_applications_by_status(callback: CallbackQuery, state: FSMContext):
    is_paid = callback.data == "show_paid_apps"
    status = "paid" if is_paid else "pending"
    
    # Получаем заявки с фильтром по статусу
    applications, total = await router.database.get_user_applications_by_status(
        user_id=callback.from_user.id,
        status=status
    )
    
    if not applications:
        text = "💰 У вас пока нет оплаченных заявок." if is_paid else "⏳ У вас пока нет заявок в ожидании."
        await callback.message.edit_text(
            text,
            reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text="📤 Подать заявку", callback_data="submit_paid_content")],
                [InlineKeyboardButton(text="◀️ Назад", callback_data="my_paid_content")]
            ]),
            disable_web_page_preview=True
        )
        return

    # Показываем первую заявку
    await state.update_data(current_index=0, status=status)
    await show_application(callback.message, applications[0], 0, total, status)

async def show_application(message: Message, app: dict, current_index: int, total: int, status: str):
    """Показывает одну заявку с расширенными кнопками навигации"""
    payment_status = "💰 Оплачено" if app['status'] == 'paid' else "⏳ Ожидание"
    
    # Преобразуем дату в нужный формат
    created_at = datetime.strptime(app['created_at'], "%Y-%m-%d %H:%M:%S")
    formatted_date = created_at.strftime("%d.%m.%Y %H:%M")
    
    # Базовый текст заявки
    text = (
        f"📋 <b>Заявка №{app['id']}</b>\n\n"
        f"🔗 <a href='{app['link']}'>Открыть</a>\n"
        f"📊 Тип: {app['content_type']}\n"
        f"📅 Дата публикации: {app['publish_date']}\n"
    )
    
    # Добавляем информацию о просмотрах и оплате в зависимости от статуса
    if app['status'] == 'paid':
        text += (
            f"👁 Начальные просмотры: {app['views_count']:,}\n"
            f"👁 Конечные просмотры: {app['current_views']:,}\n"
            f"💰 Сумма выплаты: {app['payment_amount']:,.2f} ₽\n"
        )
    else:
        text += f"👁 Просмотры: {app['views_count']:,}\n"
    
    text += (
        f"💳 Оплата: {payment_status}\n"
        f"📝 Примечание: {app['note']}\n"
        f"📅 Подана: {formatted_date}\n\n"
        f"Страница {current_index + 1} из {total}"
    )
    
    # Создаем расширенные кнопки навигации
    keyboard = []
    nav_row = []
    
    # Кнопка в начало списка
    if current_index > 0:
        nav_row.append(InlineKeyboardButton(text="⏮", callback_data=f"show_app:0:{status}"))
    
    # Кнопка назад
    if current_index > 0:
        nav_row.append(InlineKeyboardButton(text="◀️", callback_data=f"show_app:{current_index-1}:{status}"))
    
    # Кнопка вперед
    if current_index < total - 1:
        nav_row.append(InlineKeyboardButton(text="▶️", callback_data=f"show_app:{current_index+1}:{status}"))
    
    # Кнопка в конец списка
    if current_index < total - 1:
        nav_row.append(InlineKeyboardButton(text="⏭", callback_data=f"show_app:{total-1}:{status}"))
    
    if nav_row:
        keyboard.append(nav_row)
    
    keyboard.extend([
        [InlineKeyboardButton(text="📋 К списку категорий", callback_data="my_paid_content")],
        [InlineKeyboardButton(text="◀️ В меню", callback_data="paid_content")]
    ])
    
    await message.edit_text(
        text,
        reply_markup=InlineKeyboardMarkup(inline_keyboard=keyboard),
        parse_mode="HTML",
        disable_web_page_preview=True
    )

@router.callback_query(F.data.startswith("show_app:"))
async def handle_application_navigation(callback: CallbackQuery, state: FSMContext):
    _, new_index, status = callback.data.split(":")
    new_index = int(new_index)
    
    applications, total = await router.database.get_user_applications_by_status(
        user_id=callback.from_user.id,
        status=status
    )
    
    if 0 <= new_index < total:
        await state.update_data(current_index=new_index)
        await show_application(callback.message, applications[new_index], new_index, total, status)

@router.callback_query(F.data == "check_banner")
async def check_banner(callback: CallbackQuery):
    await callback.answer("В разработке: Проверка баннера")

@router.callback_query(F.data == "back_to_start")
async def back_to_start_callback(callback: CallbackQuery):
    # Проверяем, является ли пользователь одобренным блогером
    user_id = callback.from_user.id
    username = callback.from_user.username or str(user_id)
    is_approved = await router.database.is_approved_blogger(username)
    
    # Создаем список кнопок в зависимости от статуса пользователя
    inline_buttons = [
        [InlineKeyboardButton(text="🤝 Сотрудничество", callback_data="collaboration")],
        [InlineKeyboardButton(text="ℹ️ О боте", callback_data="about")]
    ]
    
    if is_approved:
        inline_buttons.insert(1, [InlineKeyboardButton(text="💰 Контент на оплату", callback_data="paid_content")])
    
    keyboard = InlineKeyboardMarkup(inline_keyboard=inline_buttons)
    
    try:
        await callback.message.edit_text(
            START_MESSAGE,
            reply_markup=keyboard,
            parse_mode="HTML",
            disable_web_page_preview=True
        )
    except Exception as e:
        print(f"Error in back_to_start_callback: {e}")
        # Если не удалось отредактировать сообщение, отправляем новое
        await callback.message.answer(
            START_MESSAGE,
            reply_markup=keyboard,
            parse_mode="HTML",
            disable_web_page_preview=True
        )

@router.callback_query(F.data == "info_for_cutters")
async def show_info_for_cutters(callback: CallbackQuery):
    info_text = (
        "📋 <b>Правила и условия оплаты контента</b>\n\n"
        "⚠️ <b>ВАЖНО:</b> Расчеты за 16:9 ролики и стримы в индивидуальном порядке\n\n"
        "🎬 <b>Технические требования к ролику:</b>\n"
        "• Баннер должен быть размещен по центру, сверху или снизу\n"
        "• Баннер не должен перекрываться интерфейсом приложения\n"
        "• Минимальная длительность ролика: 8 секунд\n"
        "• Запрещено удалять ролики в течение 3 месяцев\n\n"
        "💰 <b>Система выплат:</b>\n"
        "• Выплаты производятся при накоплении 500 000 просмотров\n"
        "• Просмотры фиксируются на 14-й день после публикации\n"
        "• Минимальное количество просмотров для подачи: 1000\n\n"
        "📈 <b>Пример расчета просмотров:</b>\n"
        "Дата публикации: 10.02.2025\n"
        "Дата фиксации просмотров: 24.02.2025\n"
        "<i>Просмотры после даты фиксации не учитываются</i>\n\n"
        "⭐️ <b>Возможности увеличения CPM:</b>\n"
        "• Мотивируйте зрителей использовать ВАШ промокод\n"
        "• Мы отслеживаем статистику введенных промокодов\n"
        "• CPM повышается для авторов с высокой конверсией промокодов"
    )
    
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="📤 Подать заявку", callback_data="submit_paid_content")],
        [InlineKeyboardButton(text="◀️ Назад", callback_data="paid_content")]
    ])
    
    await callback.message.edit_text(info_text, reply_markup=keyboard, parse_mode="HTML", disable_web_page_preview=True)

@router.callback_query(F.data == "info_functionality")
async def show_functionality_info(callback: CallbackQuery):
    functionality_text = (
        "📌 <b>О функционале кнопок</b>\n\n"
        "📤 <b>Подать заявку:</b>\n"
        "• Прикрепление ссылки на шортс/видео/стрим\n"
        "• Указание количества просмотров/прикрепление статистики\n"
        "• Указание даты публикации\n\n"
        "📋 <b>Мои заявки:</b>\n"
        "• Просмотр списка ваших заявок\n"
        "• Просмотр статуса заявки (оплачено/в ожидании)\n\n"
        "🔍 <b>Проверить баннер:</b>\n"
        "• Ссылка на ваш актуальный баннер\n"
        "• По приходу рассылки о новом баннере, необходимо скачать баннер по ссылке"
    )
    
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="◀️ Назад", callback_data="paid_content")]
    ])
    
    await callback.message.edit_text(functionality_text, reply_markup=keyboard, parse_mode="HTML", disable_web_page_preview=True)

# Добавим общий обработчик отмены для всех состояний
@router.message(Command("cancel"))
@router.message(F.text.casefold() == "отмена")
async def cancel_handler(message: Message, state: FSMContext):
    current_state = await state.get_state()
    if current_state is None:
        return
    
    await state.clear()
    await message.answer(
        "❌ Подача заявки отменена.\n"
        "Вы можете начать заново, выбрав пункт «Подать заявку»",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="◀️ В меню", callback_data="paid_content")]
        ]),
        disable_web_page_preview=True
    )

# Обновим все обработчики состояний, добавив информацию о возможности отмены
@router.callback_query(F.data == "submit_shorts")
async def submit_shorts_content(callback: CallbackQuery, state: FSMContext):
    await state.set_state(PaidContentStates.waiting_for_link)
    await state.update_data(content_type='shorts')
    
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="◀️ Назад", callback_data="submit_paid_content")],
        [InlineKeyboardButton(text="❌ Отменить", callback_data="cancel_application")]
    ])
    
    await callback.message.edit_text(
        "📱 <b>Подача заявки на YouTube Shorts</b>\n\n"
        "Пожалуйста, отправьте ссылку на ваш ролик:\n\n"
        "📌 Пример правильной ссылки:\n"
        "• youtube.com/shorts/abcdef",
        reply_markup=keyboard,
        parse_mode="HTML",
        disable_web_page_preview=True
    )

@router.callback_query(F.data == "submit_tiktok")
async def submit_tiktok_content(callback: CallbackQuery, state: FSMContext):
    await state.set_state(PaidContentStates.waiting_for_link)
    await state.update_data(content_type='tiktok')
    
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="◀️ Назад", callback_data="submit_paid_content")],
        [InlineKeyboardButton(text="❌ Отменить", callback_data="cancel_application")]
    ])
    
    await callback.message.edit_text(
        "📱 <b>Подача заявки на TikTok</b>\n\n"
        "Пожалуйста, отправьте ссылку на ваш ролик:\n\n"
        "📌 Пример правильной ссылки:\n"
        "• tiktok.com/@user/video/123456789",
        reply_markup=keyboard,
        parse_mode="HTML",
        disable_web_page_preview=True
    )

@router.callback_query(F.data == "submit_twitch")
async def submit_twitch_content(callback: CallbackQuery, state: FSMContext):
    await state.set_state(PaidContentStates.waiting_for_link)
    await state.update_data(content_type='stream')
    
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="◀️ Назад", callback_data="submit_paid_content")],
        [InlineKeyboardButton(text="❌ Отменить", callback_data="cancel_application")]
    ])
    
    await callback.message.edit_text(
        "🎮 <b>Подача заявки на Twitch VOD</b>\n\n"
        "Пожалуйста, отправьте ссылку на запись стрима:\n\n"
        "📌 Пример правильной ссылки:\n"
        "• twitch.tv/videos/123456789",
        reply_markup=keyboard,
        parse_mode="HTML",
        disable_web_page_preview=True
    )

@router.callback_query(F.data == "submit_other")
async def submit_other_content(callback: CallbackQuery, state: FSMContext):
    await state.set_state(PaidContentStates.waiting_for_link)
    await state.update_data(content_type='other')
    
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="◀️ Назад", callback_data="submit_paid_content")],
        [InlineKeyboardButton(text="❌ Отменить", callback_data="cancel_application")]
    ])
    
    await callback.message.edit_text(
        "🌐 <b>Подача заявки на другой платформе</b>\n\n"
        "Пожалуйста, отправьте ссылку на ваш контент:\n\n"
        "📌 Требования к ссылке:\n"
        "• Должна начинаться с http:// или https://\n"
        "• Должна вести на конкретный контент\n"
        "• Контент должен быть публично доступен",
        reply_markup=keyboard,
        parse_mode="HTML",
        disable_web_page_preview=True
    )

def is_valid_link(link: str) -> bool:
    """Проверяет валидность ссылки на TikTok/YouTube Shorts."""
    tiktok_pattern = r'https?://(?:www\.)?(?:vt\.)?tiktok\.com/\S+'
    youtube_pattern = r'https?://(?:www\.)?youtube\.com/shorts/\S+'
    
    return bool(re.match(tiktok_pattern, link) or re.match(youtube_pattern, link))

def is_valid_twitch_link(link: str) -> bool:
    """Проверяет, является ли ссылка корректной ссылкой на Twitch."""
    twitch_patterns = [
        r'https?://(?:www\.)?twitch\.tv/[\w-]+/?',  # Для каналов
        r'https?://(?:www\.)?twitch\.tv/videos/\d+/?'  # Для видео
    ]
    return any(bool(re.match(pattern, link)) for pattern in twitch_patterns)

def is_valid_stream_link(link: str) -> bool:
    """Проверяет, является ли ссылка корректной ссылкой на стрим."""
    patterns = [
        # Twitch паттерны (только VOD)
        r'https?://(?:www\.)?twitch\.tv/videos/\d+/?',       # Только записи стримов
        # YouTube паттерны
        r'https?://(?:www\.)?youtube\.com/watch\?v=[\w-]+',  # Обычные видео
        r'https?://youtu\.be/[\w-]+',                        # Короткие ссылки
        r'https?://(?:www\.)?youtube\.com/live/[\w-]+',      # Прямые ссылки на стрим
        # TikTok паттерны
        r'https?://(?:www\.|vm\.|vt\.)?tiktok\.com/@[\w.]+/live/?',  # Ссылки на live
        r'https?://(?:www\.|vm\.|vt\.)?tiktok\.com/@[\w.]+/video/\d+' # Записи стримов
    ]
    return any(bool(re.match(pattern, link)) for pattern in patterns)

def is_valid_youtube_video_link(link: str) -> bool:
    """Проверяет, является ли ссылка корректной ссылкой на YouTube видео."""
    patterns = [
        r'https?://(?:www\.)?youtube\.com/watch\?v=[\w-]+',  # Стандартная ссылка
        r'https?://youtu\.be/[\w-]+',                        # Короткая ссылка
        r'https?://(?:www\.)?youtube\.com/v/[\w-]+',         # Альтернативный формат
    ]
    return any(bool(re.match(pattern, link)) for pattern in patterns)

def is_valid_screenshot_link(link: str) -> bool:
    """Проверяет, является ли ссылка корректной ссылкой на скриншот."""
    image_hosting_patterns = [
        # PostImage
        r'https?://(?:www\.)?postimg\.cc/\w+',
        r'https?://(?:www\.)?i\.postimg\.cc/\w+/[\w-]+\.(?:jpg|jpeg|png|gif)',
        # ImgBB
        r'https?://(?:www\.)?ibb\.co/\w+',
        r'https?://(?:www\.)?i\.ibb\.co/\w+/[\w-]+\.(?:jpg|jpeg|png|gif)',
        # PostImages
        r'https?://(?:www\.)?postimages\.org/\w+',
        r'https?://(?:www\.)?i\.postimages\.org/\w+/[\w-]+\.(?:jpg|jpeg|png|gif)',
        # Прямые ссылки на изображения
        r'https?://\S+\.(?:jpg|jpeg|png|gif)$'
    ]
    return any(bool(re.match(pattern, link, re.IGNORECASE)) for pattern in image_hosting_patterns)

@router.message(PaidContentStates.waiting_for_link)
async def process_link(message: Message, state: FSMContext):
    # Получаем текущие данные состояния
    data = await state.get_data()
    content_type = data.get('content_type')

    if not message.text.startswith(('http://', 'https://')):
        keyboard = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="◀️ Назад", callback_data=f"submit_{content_type}")],
            [InlineKeyboardButton(text="❌ Отменить", callback_data="cancel_application")]
        ])
        
        await message.answer(
            "❌ Ошибка: Отсутствует протокол\n\n"
            "Ссылка должна начинаться с:\n"
            "• http://\n"
            "• https://\n\n"
            "✅ Поддерживаемые форматы:\n"
            "• postimg.cc/код\n"
            "• ibb.co/код\n"
            "• postimages.org/код\n"
            "• Прямые ссылки на изображения (заканчивающиеся на .jpg, .png и т.д.)",
            reply_markup=keyboard,
            disable_web_page_preview=True
        )
        return

    # Для стримов проверяем ссылки на все поддерживаемые платформы
    if content_type == 'stream':
        if not is_valid_stream_link(message.text):
            keyboard = InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text="◀️ Назад", callback_data="submit_stream")],
                [InlineKeyboardButton(text="❌ Отменить", callback_data="cancel_application")]
            ])
            
            await message.answer(
                "❌ Ошибка: Неверный формат ссылки\n\n"
                "✅ Принимаются ссылки:\n"
                "<b>Twitch:</b>\n"
                "• twitch.tv/videos/123456789 (запись стрима)\n\n"
                "<b>YouTube:</b>\n"
                "• youtube.com/watch?v=abcdef\n"
                "• youtu.be/abcdef\n"
                "• youtube.com/live/abcdef\n\n"
                "<b>TikTok:</b>\n"
                "• tiktok.com/@user/live\n"
                "• tiktok.com/@user/video/123456789\n\n"
                "❗️ Отправьте корректную ссылку на запись стрима",
                parse_mode="HTML",
                disable_web_page_preview=True,
                reply_markup=keyboard
            )
            return
        
        await state.update_data(link=message.text)
        await state.set_state(PaidContentStates.waiting_for_screenshot)
        
        keyboard = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="❌ Отменить", callback_data="cancel_application")]
        ])
        
        await message.answer(
            "2️⃣ Отправьте ссылку на скриншот статистики стрима\n\n"
            "📊 На скриншоте должны быть видны:\n"
            "• Количество зрителей\n"
            "• Дата стрима\n"
            "• Продолжительность\n\n"
            "✅ Разрешенные фотохостинги:\n"
            "• imgur.com\n"
            "• imgbb.com\n"
            "• postimages.org\n\n"
            "❗️ Загрузите скриншот на один из сервисов\n"
            "и отправьте прямую ссылку на изображение",
            reply_markup=keyboard,
            disable_web_page_preview=True
        )
    elif content_type == 'shorts':
        # Проверяем, не является ли это ссылкой на профиль TikTok
        tiktok_profile_patterns = [
            r'https?://(?:www\.|vm\.|vt\.)?tiktok\.com/@[\w.]+/?$',  # Формат @username
            r'https?://(?:www\.|vm\.|vt\.)?tiktok\.com/[\w.]+/?$',   # Короткий формат
        ]
        
        # Если это ссылка на профиль - отклоняем
        if any(bool(re.match(pattern, message.text)) for pattern in tiktok_profile_patterns):
            keyboard = InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text="◀️ Назад", callback_data=f"submit_{content_type}")],
                [InlineKeyboardButton(text="❌ Отменить", callback_data="cancel_application")]
            ])
            
            await message.answer(
                "❌ Ошибка: Отправлена ссылка на профиль\n\n"
                "Примеры правильных ссылок:\n"
                "• TikTok: tiktok.com/@user/video/123..\n"
                "• Shorts: youtube.com/shorts/abc..\n\n"
                "❗️ Отправьте ссылку на конкретное видео",
                reply_markup=keyboard,
                disable_web_page_preview=True
            )
            return
        
        # Проверяем, является ли это корректной ссылкой на видео
        tiktok_video_patterns = [
            r'https?://(?:www\.|vm\.|vt\.)?tiktok\.com/@[\w.]+/video/\d+',  # Полный формат видео
            r'https?://(?:www\.|vm\.|vt\.)?tiktok\.com/v/\d+',              # Короткий формат видео
            r'https?://(?:www\.)?youtube\.com/shorts/[\w-]+'                 # YouTube Shorts
        ]
        
        if not any(bool(re.match(pattern, message.text)) for pattern in tiktok_video_patterns):
            keyboard = InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text="❌ Отменить", callback_data="cancel_application")]
            ])
            
            await message.answer(
                "❌ Неверный формат ссылки\n\n"
                "Примеры правильных ссылок:\n"
                "• TikTok: tiktok.com/@user/video/123..\n"
                "• Shorts: youtube.com/shorts/abc..\n\n"
                "❗️ Отправьте ссылку на конкретное видео",
                reply_markup=keyboard,
                disable_web_page_preview=True
            )
            return
        
        await state.update_data(link=message.text)
        await state.set_state(PaidContentStates.waiting_for_date)
        
        keyboard = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="❌ Отменить", callback_data="cancel_application")]
        ])
        
        await message.answer(
            "📅 Укажите дату публикации в формате ДД.ММ.ГГГГ\n"
            "Например: 25.02.2024",
            reply_markup=keyboard
        )
    else:
        # Для обычных видео
        if not is_valid_youtube_video_link(message.text):
            keyboard = InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text="❌ Отменить", callback_data="cancel_application")]
            ])
            
            await message.answer(
                "❌ Неверный формат ссылки\n\n"
                "Примеры правильных ссылок:\n"
                "• youtube.com/watch?v=abcdef\n"
                "• youtu.be/abcdef\n\n"
                "❗️ Отправьте ссылку на видео YouTube",
                reply_markup=keyboard,
                disable_web_page_preview=True
            )
            return
        
        await state.update_data(link=message.text)
        await state.set_state(PaidContentStates.waiting_for_date)
        
        keyboard = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="❌ Отменить", callback_data="cancel_application")]
        ])
        
        await message.answer(
            "📅 Укажите дату публикации в формате ДД.ММ.ГГГГ\n"
            "Например: 25.02.2024",
            reply_markup=keyboard
        )

def is_valid_date_format(date_str: str) -> bool:
    """Проверяет формат даты ДД.ММ.ГГГГ"""
    try:
        datetime.strptime(date_str, '%d.%m.%Y')
        return True
    except ValueError:
        return False

def is_valid_views_count(views_str: str) -> bool:
    """Проверяет, является ли строка корректным числом просмотров"""
    try:
        # Удаляем пробелы и запятые
        clean_str = views_str.replace(',', '').replace(' ', '')
        # Проверяем, что строка содержит только цифры
        if not clean_str.isdigit():
            return False
        # Проверяем, что число положительное
        views = int(clean_str)
        return views > 0
    except ValueError:
        return False

@router.message(PaidContentStates.waiting_for_date)
async def process_video_date(message: Message, state: FSMContext):
    # Проверяем формат даты
    if not is_valid_date_format(message.text):
        data = await state.get_data()
        content_type = data.get('content_type')
        
        keyboard = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="◀️ Назад", callback_data=f"submit_{content_type}")],
            [InlineKeyboardButton(text="❌ Отменить", callback_data="cancel_application")]
        ])
        
        await message.answer(
            "❌ Ошибка: Неверный формат даты\n\n"
            "Пожалуйста, укажите дату в формате ДД.ММ.ГГГГ\n"
            "Например: 25.02.2024",
            reply_markup=keyboard,
            disable_web_page_preview=True
        )
        return
    
    try:
        # Парсим дату из сообщения
        input_date = datetime.strptime(message.text, '%d.%m.%Y')
        current_date = datetime.now()
        
        # Проверяем, что дата не в будущем
        if input_date > current_date:
            await message.answer(
                "❌ Ошибка: Указана будущая дата\n\n"
                "Дата публикации не может быть в будущем.\n"
                "Пожалуйста, укажите корректную дату в формате ДД.ММ.ГГГГ",
                reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                    [InlineKeyboardButton(text="❌ Отменить", callback_data="cancel_application")]
                ]),
                disable_web_page_preview=True
            )
            return
        
        # Проверяем, что дата не слишком старая (например, не старше 3 месяцев)
        three_months_ago = current_date - timedelta(days=90)
        if input_date < three_months_ago:
            await message.answer(
                "❌ Ошибка: Указана слишком старая дата\n\n"
                "Принимаются заявки только на контент не старше 3 месяцев.\n"
                "Пожалуйста, укажите более свежую дату в формате ДД.ММ.ГГГГ",
                reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                    [InlineKeyboardButton(text="❌ Отменить", callback_data="cancel_application")]
                ]),
                disable_web_page_preview=True
            )
            return
        
        # Если все проверки пройдены, сохраняем дату
        await state.update_data(date=message.text)
        await state.set_state(PaidContentStates.waiting_for_views)
        
        keyboard = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="❌ Отменить", callback_data="cancel_application")]
        ])
        
        data = await state.get_data()
        content_type = data.get('content_type')
        min_views = {
            'stream': MIN_VIEWS_STREAM,
            'shorts': MIN_VIEWS_SHORTS,
            'video': MIN_VIEWS_VIDEO
        }.get(content_type, MIN_VIEWS)
        
        # Изменяем текст в зависимости от типа контента
        if content_type == 'stream':
            await message.answer(
                f"👥 Укажите количество зрителей на стриме\n"
                f"Минимальное количество: {min_views:,}\n"
                "(введите число без пробелов и запятых)",
                reply_markup=keyboard,
                disable_web_page_preview=True
            )
        else:
            await message.answer(
                f"👁 Укажите количество просмотров\n"
                f"Минимальное количество: {min_views:,}\n"
                "(введите число без пробелов и запятых)",
                reply_markup=keyboard,
                disable_web_page_preview=True
            )
    except ValueError:
        keyboard = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="❌ Отменить", callback_data="cancel_application")]
        ])
        
        await message.answer(
            "❌ Ошибка: Неверный формат даты\n\n"
            "✅ Корректный формат: ДД.ММ.ГГГГ\n"
            "❌ Некорректные форматы:\n"
            "• 2024.02.25\n"
            "• 25/02/2024\n"
            "• 25-02-2024\n\n"
            "Пожалуйста, используйте формат ДД.ММ.ГГГГ\n"
            "Например: 25.02.2024",
            reply_markup=keyboard,
            disable_web_page_preview=True
        )

@router.message(PaidContentStates.waiting_for_views)
async def process_video_views(message: Message, state: FSMContext):
    if not is_valid_views_count(message.text):
        data = await state.get_data()
        content_type = data.get('content_type')
        
        keyboard = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="◀️ Назад", callback_data=f"submit_{content_type}")],
            [InlineKeyboardButton(text="❌ Отменить", callback_data="cancel_application")]
        ])
        
        await message.answer(
            "❌ Пожалуйста, введите корректное число\n\n"
            "✅ Примеры правильного формата:\n"
            "• 1000\n"
            "• 10000\n"
            "• 100000\n\n"
            "❌ Примеры неправильного формата:\n"
            "• 1к\n"
            "• много\n"
            "• ~1000",
            reply_markup=keyboard,
            disable_web_page_preview=True
        )
        return
    
    try:
        views = int(message.text.replace(',', '').replace(' ', ''))
        data = await state.get_data()
        
        # Определяем минимум просмотров в зависимости от типа контента
        if data.get('content_type') == 'stream':
            min_views = MIN_VIEWS_STREAM
            views_text = "Средний онлайн"
        elif data.get('content_type') == 'shorts':
            min_views = MIN_VIEWS_SHORTS
            views_text = "просмотров"
        else:
            min_views = MIN_VIEWS_VIDEO
            views_text = "просмотров"
            
        if views < min_views:
            await message.answer(
                f"❌ Количество {views_text.lower()} должно быть не менее {min_views:,}.\n"
                f"Пожалуйста, подождите пока контент наберет необходимое количество {views_text.lower()}.",
                reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                    [InlineKeyboardButton(text="◀️ В меню", callback_data="paid_content")]
                ]),
                disable_web_page_preview=True
            )
            await state.clear()
            return
        
        await state.update_data(views=views)
        await state.set_state(PaidContentStates.waiting_for_note)
        
        keyboard = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="❌ Отменить", callback_data="cancel_application")]
        ])
        
        await message.answer(
            "📝 Укажите примечание или вопрос\n"
            "(если нет, напишите 0)",
            reply_markup=keyboard,
            disable_web_page_preview=True
        )
    except ValueError:
        keyboard = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="❌ Отменить", callback_data="cancel_application")]
        ])
        
        await message.answer(
            "❌ Пожалуйста, введите число без букв и специальных символов",
            reply_markup=keyboard,
            disable_web_page_preview=True
        )

def is_valid_note(note: str) -> bool:
    """Проверяет корректность примечания"""
    # Если пользователь отправил "0" - это валидное пустое примечание
    if note == "0":
        return True
    
    # Проверяем длину примечания (максимум 200 символов)
    if len(note) > 200:
        return False
    
    # Проверяем на допустимые символы (буквы, цифры и базовая пунктуация)
    allowed_chars = set("абвгдеёжзийклмнопрстуфхцчшщъыьэюяАБВГДЕЁЖЗИЙКЛМНОПРСТУФХЦЧШЩЪЫЬЭЮЯabcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789 .,!?()-_")
    return all(char in allowed_chars for char in note)

@router.message(PaidContentStates.waiting_for_note)
async def process_video_note(message: Message, state: FSMContext):
    # Проверяем валидность примечания
    if not is_valid_note(message.text):
        keyboard = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="❌ Отменить", callback_data="cancel_application")]
        ])
        
        await message.answer(
            "❌ Ошибка: Некорректное примечание\n\n"
            "✅ Требования к примечанию:\n"
            "• Максимум 200 символов\n"
            "• Только буквы, цифры и знаки пунктуации\n"
            "• Если примечания нет, отправьте 0\n\n"
            "Пожалуйста, отправьте корректное примечание",
            reply_markup=keyboard,
            disable_web_page_preview=True
        )
        return

    data = await state.update_data(note=message.text)
    
    # Определяем тип интеграции и формат сообщения в зависимости от типа контента
    if data.get('content_type') == 'stream':
        confirmation_text = (
            "📋 <b>Проверьте данные вашей заявки на стрим:</b>\n\n"
            f"🔗 Ссылка на стрим: {data['link']}\n"
            f"📊 Тип интеграции: Баннер\n"
            f"📅 Дата: {data['date']}\n"
            f"👁 Средний онлайн: {data['views']:,}\n"
            f"📝 Примечание: {data['note'] if data['note'] != '0' else 'Нет'}\n"
            f"📸 Скриншот статистики: <a href='{data['screenshot']}'>Открыть</a>"
        )
    elif data.get('content_type') == 'shorts':
        confirmation_text = (
            "📋 <b>Проверьте данные вашей заявки:</b>\n\n"
            f"🔗 Ссылка на видео: {data['link']}\n"
            f"📊 Тип интеграции: Баннер\n"
            f"📅 Дата: {data['date']}\n"
            f"👁 Просмотры: {data['views']:,}\n"
            f"📝 Примечание: {data['note'] if data['note'] != '0' else 'Нет'}"
        )
    else:
        # Для обычных видео
        confirmation_text = (
            "📋 <b>Проверьте данные вашей заявки:</b>\n\n"
            f"🔗 Ссылка на видео: {data['link']}\n"
            f"📊 Тип интеграции: Рекламная интеграция\n"
            f"📅 Дата: {data['date']}\n"
            f"👁 Просмотры: {data['views']:,}\n"
            f"📝 Примечание: {data['note'] if data['note'] != '0' else 'Нет'}"
        )
    
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="✅ Подтвердить", callback_data="confirm_paid_content"),
            InlineKeyboardButton(text="🔄 Изменить", callback_data="edit_paid_content")
        ],
        [InlineKeyboardButton(text="◀️ Назад", callback_data="paid_content")]
    ])
    
    await state.set_state(PaidContentStates.waiting_for_confirmation)
    await message.answer(confirmation_text, reply_markup=keyboard, parse_mode="HTML", disable_web_page_preview=True)

@router.callback_query(F.data == "confirm_paid_content")
async def confirm_paid_content(callback: CallbackQuery, state: FSMContext):
    data = await state.get_data()
    
    # Сохраняем в базу данных
    application_id = await router.database.save_paid_content_application(
        user_id=callback.from_user.id,
        username=callback.from_user.username,  # Может быть None
        content_type=data['content_type'],
        link=data['link'],
        publish_date=data['date'],
        note=data['note'],
        views_count=data['views']
    )
    
    await state.clear()
    await callback.message.edit_text(
        "✅ <b>Ваша заявка успешно отправлена!</b>\n\n"
        "Вы можете отслеживать статус в разделе «Мои заявки»",
        parse_mode="HTML",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="📋 Мои заявки", callback_data="my_paid_content")],
            [InlineKeyboardButton(text="◀️ В меню", callback_data="paid_content")]
        ]),
        disable_web_page_preview=True
    )

@router.callback_query(F.data == "edit_paid_content")
async def edit_paid_content(callback: CallbackQuery, state: FSMContext):
    await state.set_state(PaidContentStates.waiting_for_link)
    await callback.message.edit_text(
        "📱 <b>Подача заявки на Shorts/TikTok</b>\n\n"
        "Пожалуйста, отправьте ссылку на ваш ролик заново:",
        parse_mode="HTML",
        disable_web_page_preview=True
    )

@router.callback_query(F.data == "submit_stream")
async def submit_stream_content(callback: CallbackQuery, state: FSMContext):
    await state.set_state(PaidContentStates.waiting_for_link)
    await state.update_data(content_type='stream')
    
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="◀️ Назад", callback_data="submit_paid_content")],
        [InlineKeyboardButton(text="❌ Отменить", callback_data="cancel_application")]
    ])
    
    await callback.message.edit_text(
        "🎮 <b>Подача заявки на стрим</b>\n\n"
        "Пожалуйста, отправьте ссылку на ваш стрим:",
        reply_markup=keyboard,
        parse_mode="HTML",
        disable_web_page_preview=True
    )

@router.callback_query(F.data == "submit_video")
async def submit_video_content(callback: CallbackQuery, state: FSMContext):
    await state.set_state(PaidContentStates.waiting_for_link)
    await state.update_data(content_type='video')
    
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="❌ Отменить", callback_data="cancel_application")]
    ])
    
    await callback.message.edit_text(
        "🎥 <b>Подача заявки на видео</b>\n\n"
        "Пожалуйста, отправьте ссылку на ваше видео:",
        reply_markup=keyboard,
        parse_mode="HTML",
        disable_web_page_preview=True
    )

# Добавляем обработчик отмены через inline кнопку
@router.callback_query(F.data == "cancel_application")
async def cancel_application(callback: CallbackQuery, state: FSMContext):
    await state.clear()
    await callback.message.edit_text(
        "❌ Подача заявки отменена.\n"
        "Вы можете начать заново, выбрав пункт «Подать заявку»",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="◀️ В меню", callback_data="paid_content")]
        ]),
        disable_web_page_preview=True
    )

# Обновляем обработчик для скриншота
@router.message(PaidContentStates.waiting_for_screenshot)
async def process_stream_screenshot(message: Message, state: FSMContext):
    # Проверяем, является ли сообщение ссылкой
    if not message.text.startswith(('http://', 'https://')):
        await message.answer(
            "❌ Ошибка: Отсутствует протокол\n\n"
            "Ссылка должна начинаться с:\n"
            "• http://\n"
            "• https://\n\n"
            "✅ Поддерживаемые форматы:\n"
            "• postimg.cc/код\n"
            "• ibb.co/код\n"
            "• postimages.org/код\n"
            "• Прямые ссылки на изображения (заканчивающиеся на .jpg, .png и т.д.)",
            reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text="❌ Отменить", callback_data="cancel_application")]
            ]),
            disable_web_page_preview=True
        )
        return
    
    # Проверяем, является ли ссылка корректной ссылкой на изображение
    if not is_valid_screenshot_link(message.text):
        await message.answer(
            "❌ Ошибка: Неверный формат ссылки\n\n"
            "✅ Примеры правильных ссылок:\n"
            "• https://postimg.cc/abcd1234\n"
            "• https://ibb.co/abcd1234\n"
            "• https://postimages.org/abcd1234\n"
            "• https://example.com/image.jpg\n\n"
            "❗️ Убедитесь, что вы копируете прямую ссылку на изображение\n"
            "или ссылку для просмотра с сервиса загрузки",
            reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text="❌ Отменить", callback_data="cancel_application")]
            ]),
            disable_web_page_preview=True
        )
        return
    
    # Сохраняем ссылку на скриншот
    await state.update_data(screenshot=message.text)
    await state.set_state(PaidContentStates.waiting_for_date)
    
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="❌ Отменить", callback_data="cancel_application")]
    ])
    
    await message.answer(
        "📅 Укажите дату стрима в формате ДД.ММ.ГГГГ\n"
        "Например: 25.02.2024",
        reply_markup=keyboard,
        disable_web_page_preview=True
    )

# Добавим обработчики пагинации
@router.callback_query(F.data.in_(["next_page", "prev_page"]))
async def handle_pagination(callback: CallbackQuery, state: FSMContext):
    # Здесь будет логика пагинации
    # Нужно хранить текущую страницу в state
    await callback.answer("В разработке: пагинация списка заявок")

# Обработчики для кнопок "Назад"
@router.callback_query(F.data.startswith("submit_"))
async def handle_back_button(callback: CallbackQuery, state: FSMContext):
    # Получаем текущее состояние
    current_state = await state.get_state()
    
    # Если нажата кнопка "Назад" в состоянии ожидания ссылки
    if current_state == PaidContentStates.waiting_for_link:
        # Возвращаемся к выбору типа контента
        keyboard = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="📱 Shorts/TikTok", callback_data="submit_shorts")],
            [InlineKeyboardButton(text="🎮 Стрим", callback_data="submit_stream")],
            [InlineKeyboardButton(text="🎥 Видео", callback_data="submit_video")],
            [InlineKeyboardButton(text="◀️ Назад", callback_data="paid_content")]
        ])
        
        text = (
            "📤 <b>Подача заявки на оплату контента</b>\n\n"
            "Выберите тип контента для подачи заявки:"
        )
        
        await callback.message.edit_text(text, reply_markup=keyboard, parse_mode="HTML")
        await state.clear()
    
    # Если нажата кнопка "Назад" в состоянии ожидания даты или просмотров
    elif current_state in [PaidContentStates.waiting_for_date, PaidContentStates.waiting_for_views]:
        data = await state.get_data()
        content_type = data.get('content_type')
        
        # Возвращаемся к вводу ссылки
        if content_type == 'shorts':
            await submit_shorts_content(callback, state)
        elif content_type == 'stream':
            await submit_stream_content(callback, state)
        else:
            # Для обычных видео
            keyboard = InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text="◀️ Назад", callback_data="submit_paid_content")],
                [InlineKeyboardButton(text="❌ Отменить", callback_data="cancel_application")]
            ])
            
            await callback.message.edit_text(
                "🎥 <b>Подача заявки на видео</b>\n\n"
                "Пожалуйста, отправьте ссылку на ваше видео:",
                reply_markup=keyboard,
                parse_mode="HTML",
                disable_web_page_preview=True
            )
            await state.set_state(PaidContentStates.waiting_for_link)
            await state.update_data(content_type='video')

@router.callback_query(F.data == "submit_youtube")
async def submit_youtube_content(callback: CallbackQuery, state: FSMContext):
    await state.set_state(PaidContentStates.waiting_for_link)
    await state.update_data(content_type='video')
    
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="◀️ Назад", callback_data="submit_paid_content")],
        [InlineKeyboardButton(text="❌ Отменить", callback_data="cancel_application")]
    ])
    
    await callback.message.edit_text(
        "🎥 <b>Подача заявки на YouTube видео</b>\n\n"
        "Пожалуйста, отправьте ссылку на ваше видео:\n\n"
        "📌 Примеры правильных ссылок:\n"
        "• youtube.com/watch?v=abcdef\n"
        "• youtu.be/abcdef",
        reply_markup=keyboard,
        parse_mode="HTML",
        disable_web_page_preview=True
    )

@router.callback_query(F.data == "submit_shorts")
async def submit_shorts_content(callback: CallbackQuery, state: FSMContext):
    await state.set_state(PaidContentStates.waiting_for_link)
    await state.update_data(content_type='shorts')
    
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="◀️ Назад", callback_data="submit_paid_content")],
        [InlineKeyboardButton(text="❌ Отменить", callback_data="cancel_application")]
    ])
    
    await callback.message.edit_text(
        "📱 <b>Подача заявки на YouTube Shorts</b>\n\n"
        "Пожалуйста, отправьте ссылку на ваш ролик:\n\n"
        "📌 Пример правильной ссылки:\n"
        "• youtube.com/shorts/abcdef",
        reply_markup=keyboard,
        parse_mode="HTML",
        disable_web_page_preview=True
    )

@router.callback_query(F.data == "submit_tiktok")
async def submit_tiktok_content(callback: CallbackQuery, state: FSMContext):
    await state.set_state(PaidContentStates.waiting_for_link)
    await state.update_data(content_type='tiktok')
    
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="◀️ Назад", callback_data="submit_paid_content")],
        [InlineKeyboardButton(text="❌ Отменить", callback_data="cancel_application")]
    ])
    
    await callback.message.edit_text(
        "📱 <b>Подача заявки на TikTok</b>\n\n"
        "Пожалуйста, отправьте ссылку на ваш ролик:\n\n"
        "📌 Пример правильной ссылки:\n"
        "• tiktok.com/@user/video/123456789",
        reply_markup=keyboard,
        parse_mode="HTML",
        disable_web_page_preview=True
    )

@router.callback_query(F.data == "submit_twitch")
async def submit_twitch_content(callback: CallbackQuery, state: FSMContext):
    await state.set_state(PaidContentStates.waiting_for_link)
    await state.update_data(content_type='stream')
    
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="◀️ Назад", callback_data="submit_paid_content")],
        [InlineKeyboardButton(text="❌ Отменить", callback_data="cancel_application")]
    ])
    
    await callback.message.edit_text(
        "🎮 <b>Подача заявки на Twitch VOD</b>\n\n"
        "Пожалуйста, отправьте ссылку на запись стрима:\n\n"
        "📌 Пример правильной ссылки:\n"
        "• twitch.tv/videos/123456789",
        reply_markup=keyboard,
        parse_mode="HTML",
        disable_web_page_preview=True
    )

@router.callback_query(F.data == "submit_other")
async def submit_other_content(callback: CallbackQuery, state: FSMContext):
    await state.set_state(PaidContentStates.waiting_for_link)
    await state.update_data(content_type='other')
    
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="◀️ Назад", callback_data="submit_paid_content")],
        [InlineKeyboardButton(text="❌ Отменить", callback_data="cancel_application")]
    ])
    
    await callback.message.edit_text(
        "🌐 <b>Подача заявки на другой платформе</b>\n\n"
        "Пожалуйста, отправьте ссылку на ваш контент:\n\n"
        "📌 Требования к ссылке:\n"
        "• Должна начинаться с http:// или https://\n"
        "• Должна вести на конкретный контент\n"
        "• Контент должен быть публично доступен",
        reply_markup=keyboard,
        parse_mode="HTML",
        disable_web_page_preview=True
    ) 