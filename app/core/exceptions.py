class GraphError(Exception):
    def __init__(self, message: str, *, code: str | None = None, **params) -> None:
        super().__init__(message)

        self.code = code
        self.params = params

class VertexAlreadyExistsError(GraphError):
    pass

class VertexNotFoundError(GraphError):
    pass