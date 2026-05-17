from aiogram.fsm.state import State, StatesGroup


class Registration(StatesGroup):
    name = State()
    age = State()
    gender = State()
    looking_for = State()
    age_min = State()
    age_max = State()
    city = State()
    goal = State()
    bio = State()
    photo = State()


class EditProfile(StatesGroup):
    name = State()
    age = State()
    city = State()
    goal = State()
    bio = State()
    photo = State()
    age_min = State()
    age_max = State()
