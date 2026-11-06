"""Task policy errors shared with infrastructure adapters."""


class JobError(ValueError):
    def __init__(self, code, message):
        self.code = code
        super().__init__(message)
