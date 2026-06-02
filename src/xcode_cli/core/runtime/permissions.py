"""PermissionProvider interface for tool permission requests.

Defines permission request and decision types independent from prompt_toolkit/Textual.
"""
from __future__ import annotations

import threading
from dataclasses import dataclass
from typing import Literal, Protocol


@dataclass(frozen=True)
class PermissionRequest:
    """A permission request for a tool call."""
    request_id: str
    turn_id: str
    tool_call_id: str
    tool_name: str
    scope: str
    risk_summary: str


@dataclass(frozen=True)
class PermissionDecision:
    """A permission decision."""
    choice: Literal["yes", "no", "yes_all"]
    scope: str


class PermissionProvider(Protocol):
    """Protocol for permission providers."""

    def request(self, request: PermissionRequest) -> PermissionDecision:
        """Request permission for a tool call.

        Args:
            request: The permission request.

        Returns:
            The permission decision.
        """
        ...


class LegacyPermissionProvider:
    """Permission provider that uses existing ToolApprovalController."""

    def __init__(self, approval_controller: object) -> None:
        self._approval = approval_controller

    def request(self, request: PermissionRequest) -> PermissionDecision:
        """Request permission using legacy approval controller.

        Raises:
            NotImplementedError: Must be implemented to bridge to ToolApprovalController.
        """
        raise NotImplementedError(
            "LegacyPermissionProvider.request() must be implemented"
        )


class TextualPermissionProvider:
    """Permission provider for Textual UI.

    Emits PermissionRequestEvent and waits for PermissionDecisionCommand.
    """

    def __init__(self) -> None:
        self._pending_requests: dict[str, PermissionRequest] = {}
        self._decisions: dict[str, PermissionDecision] = {}
        self._wait_events: dict[str, threading.Event] = {}

    def request(self, request: PermissionRequest) -> PermissionDecision:
        """Request permission by emitting event and waiting for decision.

        This method blocks until a decision is submitted via submit_decision().

        Args:
            request: The permission request.

        Returns:
            The permission decision.
        """
        self._pending_requests[request.request_id] = request
        self._wait_events[request.request_id] = threading.Event()

        # Block until decision is submitted
        self._wait_events[request.request_id].wait()

        # Return the decision
        decision = self._decisions.pop(request.request_id)
        self._pending_requests.pop(request.request_id, None)
        self._wait_events.pop(request.request_id, None)
        return decision

    def submit_decision(self, request_id: str, decision: PermissionDecision) -> None:
        """Submit a permission decision (called from UI).

        Args:
            request_id: The request ID.
            decision: The permission decision.
        """
        self._decisions[request_id] = decision
        if request_id in self._wait_events:
            self._wait_events[request_id].set()

    def has_pending_request(self, request_id: str) -> bool:
        """Check if there is a pending request."""
        return request_id in self._pending_requests

    def clear_request(self, request_id: str) -> None:
        """Clear a pending request."""
        self._pending_requests.pop(request_id, None)
        self._decisions.pop(request_id, None)
        self._wait_events.pop(request_id, None)
