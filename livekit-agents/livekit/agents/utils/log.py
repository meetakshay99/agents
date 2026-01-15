import asyncio
import functools
import logging
from typing import Any, Callable, TypeVar, cast

F = TypeVar("F", bound=Callable[..., Any])


def log_exceptions(msg: str = "", logger: logging.Logger = logging.getLogger()) -> Callable[[F], F]:  # noqa: B008
    def deco(fn: F) -> F:
        if asyncio.iscoroutinefunction(fn):

            @functools.wraps(fn)
            async def async_fn_logs(*args: Any, **kwargs: Any) -> Any:
                try:
                    return await fn(*args, **kwargs)
                except Exception:
                    err = f"Error in {fn.__name__}"
                    if msg:
                        err += f" – {msg}"
                    logger.exception(err)
                    raise

            return cast(F, async_fn_logs)

        else:

            @functools.wraps(fn)
            def fn_logs(*args: Any, **kwargs: Any) -> Any:
                try:
                    return fn(*args, **kwargs)
                except Exception:
                    err = f"Error in {fn.__name__}"
                    if msg:
                        err += f" – {msg}"
                    logger.exception(err)
                    raise

            return cast(F, fn_logs)

    return deco


def log_exceptions_hot_path(msg: str = "", logger: logging.Logger = logging.getLogger()) -> Callable[[F], F]:  # noqa: B008
    """
    Lightweight decorator for hot-path functions (frame processing loops).

    This is a no-op decorator that returns the function unmodified to eliminate
    per-call overhead in performance-critical code paths.

    Exceptions still propagate normally and will be caught by:
    1. Parent task exception handlers
    2. Global async exception handlers (asyncio.loop.set_exception_handler)
    3. Python's default uncaught exception handler

    Use this ONLY for functions that:
    - Process individual frames/samples (called 50-100+ times/second)
    - Are performance-critical hot paths
    - Have exception handling in their callers or global handlers

    Use regular @log_exceptions for all other functions (setup, teardown, infrequent operations).

    Args:
        msg: Unused (kept for API compatibility with log_exceptions)
        logger: Unused (kept for API compatibility with log_exceptions)

    Returns:
        A decorator that returns the function unmodified (no wrapper overhead)
    """
    def deco(fn: F) -> F:
        # No wrapper - return function as-is for maximum performance
        return fn
    return deco
