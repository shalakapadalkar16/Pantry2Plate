"""
Error handling.

Service methods raise typed exceptions that already know their HTTP status.
Views no longer catch them or hand-build error bodies — DRF routes them
through custom_exception_handler, which produces one response shape for
every error in the system.
"""

from rest_framework import status
from rest_framework.exceptions import APIException
from rest_framework.views import exception_handler


class DuplicateResourceError(APIException):
    status_code = status.HTTP_409_CONFLICT
    default_detail = "That resource already exists."
    default_code = "duplicate"


class ResourceNotFoundError(APIException):
    status_code = status.HTTP_404_NOT_FOUND
    default_detail = "Resource not found."
    default_code = "not_found"


def custom_exception_handler(exc, context):
    """
    Wrap every error in a single shape:

        {"error": {"message": str, "code": str, "status_code": int,
                   "fields": {field: [messages]} | None}}

    'fields' preserves per-field validation detail so the frontend can
    attach errors to the right inputs. Collapsing everything to one
    string, as the previous version did, made that impossible.
    """
    response = exception_handler(exc, context)
    if response is None:
        return None

    original = response.data
    fields = original if isinstance(original, dict) and "detail" not in original else None

    response.data = {
        "error": {
            "message": _extract_message(original),
            "code": getattr(exc, "default_code", "error"),
            "status_code": response.status_code,
            "fields": fields,
        }
    }
    return response


def _extract_message(data) -> str:
    """Best single-sentence summary. Full detail stays in 'fields'."""
    if isinstance(data, dict):
        if "detail" in data:
            return str(data["detail"])
        for key, value in data.items():
            if isinstance(value, (list, tuple)) and value:
                return f"{key}: {value[0]}"
            return f"{key}: {value}"
        return "Invalid request."
    if isinstance(data, (list, tuple)) and data:
        return str(data[0])
    return str(data)