"""Shared, finite request policy; safe to import without loading the SDK."""

DEFAULT_REQUEST_TIMEOUT = 120
MAX_REQUEST_TIMEOUT = 600


def validate_request_timeout(value: object) -> int:
    if isinstance(value, str) and value.isdecimal():
        value = int(value)
    if type(value) is not int or not 1 <= value <= MAX_REQUEST_TIMEOUT:
        raise ValueError("LLM request timeout must be an integer from 1 to 600 seconds.")
    return value
