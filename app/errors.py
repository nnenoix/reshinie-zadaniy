class InputError(Exception):
    """Ошибка во входных данных. field — поле формы, к которому относится сообщение."""

    def __init__(self, field: str | None, message: str):
        super().__init__(message)
        self.field = field
        self.message = message
