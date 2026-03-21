from random import shuffle
from string import ascii_letters

from mgost.api import ArtichaAPI

__all__ = ('BASE_URL', 'API_TOKEN')


BASE_URL = ArtichaAPI._host
letters = [*ascii_letters]
shuffle(letters)
API_TOKEN = ''.join(letters)
