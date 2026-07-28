"""Exceptions raised by the Sorel Connect API client."""


class SorelAuthError(Exception):
    """Raised when login is rejected by the controller."""


class SorelConnectionError(Exception):
    """Raised on network or HTTP failures talking to the controller."""
