class LowerMinDateError(ValueError):
    def __init__(self):
        super().__init__("Data é menor do que a mínima permitida.")
