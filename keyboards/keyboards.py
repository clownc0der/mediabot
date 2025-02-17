from aiogram.types import ReplyKeyboardMarkup, KeyboardButton

def get_main_keyboard() -> ReplyKeyboardMarkup:
    keyboard = ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="Сотрудничество")],
            [KeyboardButton(text="Контент на оплату")],
            [KeyboardButton(text="О боте")]
        ],
        resize_keyboard=True
    )
    return keyboard 