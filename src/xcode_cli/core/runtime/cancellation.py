"""CancellationToken for cancellation boundaries."""
from __future__ import annotations

import threading
from typing import Callable


class CancellationToken:
    """Token for cancelling operations.

    Thread-safe cancellation token that can be checked by long-running operations.
    """

    def __init__(self) -> None:
        self._cancelled = False
        self._lock = threading.Lock()
        self._callbacks: list[Callable[[], None]] = []

    @property
    def is_cancelled(self) -> bool:
        """Check if the token is cancelled."""
        with self._lock:
            return self._cancelled

    def cancel(self) -> None:
        """Cancel the token."""
        with self._lock:
            if not self._cancelled:
                self._cancelled = True
                for callback in self._callbacks:
                    try:
                        callback()
                    except Exception:
                        pass  # Ignore callback errors

    def register_callback(self, callback: Callable[[], None]) -> None:
        """Register a callback to be called when cancelled.

        If already cancelled, the callback is called immediately.

        Args:
            callback: The callback to register.
        """
        with self._lock:
            if self._cancelled:
                try:
                    callback()
                except Exception:
                    pass
            else:
                self._callbacks.append(callback)

    def check(self) -> None:
        """Check if cancelled and raise if so.

        Raises:
            CancelledError: If the token is cancelled.
        """
        if self.is_cancelled:
            raise CancelledError("Operation was cancelled")


class CancelledError(Exception):
    """Raised when an operation is cancelled."""
    pass


class CancellationTokenSource:
    """Source for creating and managing cancellation tokens."""

    def __init__(self) -> None:
        self._token = CancellationToken()

    @property
    def token(self) -> CancellationToken:
        """Get the cancellation token."""
        return self._token

    def cancel(self) -> None:
        """Cancel the token."""
        self._token.cancel()
