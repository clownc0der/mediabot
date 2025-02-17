from aiogram.fsm.state import State, StatesGroup

class PaidContentStates(StatesGroup):
    waiting_for_link = State()
    waiting_for_screenshot = State()
    waiting_for_date = State()
    waiting_for_views = State()
    waiting_for_note = State()
    waiting_for_confirmation = State()

class ContentStates(StatesGroup):
    waiting_for_content = State()
    waiting_for_description = State()

class CollaborationStates(StatesGroup):
    waiting_for_platform = State()
    waiting_for_link = State()
    waiting_for_views = State()
    waiting_for_channel_name = State()
    waiting_for_confirmation = State()
    waiting_for_more = State()  # Для добавления дополнительных каналов

class PaymentStates(StatesGroup):
    waiting_for_channel = State()
    waiting_for_content_type = State()
    waiting_for_link = State()
    waiting_for_views = State()
    waiting_for_amount = State()
    waiting_for_confirmation = State()

class AdminStates(StatesGroup):
    waiting_for_views = State()
    waiting_for_amount = State()
    waiting_for_comment = State()
    waiting_for_confirmation = State() 