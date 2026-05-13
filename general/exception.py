class MissingArgumentError(ValueError):
    def __init__(self, argument_name: str):
        super().__init__(f"O argumento '{argument_name}' é obrigatório.")
