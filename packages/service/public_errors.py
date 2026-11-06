"""Translate internal exceptions to an explicit public error vocabulary."""


def public_error(exc: Exception, allowed: tuple[str, ...], fallback: str) -> str:
    # Return a trusted constant, never the exception text (which may contain
    # paths, parser inputs, credentials or diagnostics from a dependency).
    message = str(exc)
    return next((code for code in allowed if code == message), fallback)
