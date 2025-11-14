from random import shuffle
from string import ascii_letters

__all__ = ('BASE_URL', 'API_TOKEN')


BASE_URL = "https://articha.ru/api"
letters = [*ascii_letters]
shuffle(letters)
API_TOKEN = ''.join(letters)
