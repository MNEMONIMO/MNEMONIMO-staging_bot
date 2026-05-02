from aiogram.fsm.state import State, StatesGroup


class ProjectForm(StatesGroup):
    """Main project creation form states."""
    room_type = State()
    area = State()
    ceiling_height = State()
    style = State()
    budget = State()
    free_space = State()
    keep_items = State()
    remove_items = State()
    extra_notes = State()
    photos = State()
    confirmation = State()


class PaymentFlow(StatesGroup):
    """Payment flow states."""
    tariff_selection = State()
    waiting_payment = State()


class AdminFlow(StatesGroup):
    """Admin commands flow."""
    waiting_broadcast_text = State()
    waiting_project_id = State()
