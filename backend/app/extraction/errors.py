"""Errors the extraction layer raises. Their messages are written for the person
uploading and never contain anything read from the file."""


class UnsupportedFile(ValueError):
    """The file can't be read: wrong type, damaged, locked, or over a limit."""
