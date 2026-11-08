class GraphError(ValueError):
    def __init__(self, message: str) -> None:
        super().__init__(f"Ошибка: {message}")


class VertexAlreadyExistsError(GraphError):
    pass


class VertexNotFoundError(GraphError):
    pass