"""Opt-in, standalone friend-group library; importing this package does no I/O."""

API_VERSION = 1


class LibraryError(Exception):
    def __init__(self, status, message):
        super().__init__(message)
        self.status = status

