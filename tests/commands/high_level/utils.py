def raise_keyboard_interrupt(*args, **kwargs):
    """ Simulate Ctrl+C when input() is called """
    raise KeyboardInterrupt()
