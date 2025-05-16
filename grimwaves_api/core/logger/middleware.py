import json
import time
from collections.abc import Awaitable
from typing import Callable

from fastapi import Request, Response
from starlette.middleware.base import BaseHTTPMiddleware
from typing_extensions import override

from grimwaves_api.core.logger.logger import get_logger

logger = get_logger("middleware")


class BytesAlreadyRead:
    """Class for emulating reading of request body that has already been read."""

    def __init__(self, body: bytes) -> None:
        self._body: bytes = body

    async def __call__(self) -> bytes:
        return self._body


class RequestLoggingMiddleware(BaseHTTPMiddleware):
    @override
    async def dispatch(self, request: Request, call_next: Callable[[Request], Awaitable[Response]]) -> Response:
        start_time = time.time()

        # Save request body for /convert endpoint
        path = request.url.path
        method = request.method

        # For POST /convert request, save the request body
        request_body = None
        if method == "POST" and path == "/convert":
            try:
                # Reading request body
                body_bytes = await request.body()
                # Save a copy of the request body for subsequent use in call_next
                copied_body = body_bytes

                # Decode body for logging
                if body_bytes:
                    request_body = json.loads(body_bytes)

                # Replace the request's body() method with our own that returns the saved body
                request.scope["_body"] = copied_body
            except Exception:
                logger.exception("Error reading request body")

        # Process the request
        response = await call_next(request)
        process_time = (time.time() - start_time) * 1000

        # Get client information
        client_ip = request.headers.get(
            "x-forwarded-for",
            request.client.host if request.client else "unknown",
        )
        if "," in client_ip:
            client_ip = client_ip.split(",")[0].strip()

        # Get origin header
        origin = request.headers.get("origin", "no-origin")

        # Log standard request information
        log_message = (
            f"{method} {path} [{response.status_code}] {process_time:.2f}ms - IP: {client_ip} - Origin: {origin}"
        )

        # Add request body information for specific endpoints
        if request_body and method == "POST" and path == "/convert":
            logger.info("%s - Request Body: %s", log_message, request_body)
        else:
            logger.info(log_message)

        return response
