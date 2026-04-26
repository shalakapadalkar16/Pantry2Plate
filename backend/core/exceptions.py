from rest_framework.views import exception_handler


def custom_exception_handler(exc, context):
    """Wraps all DRF errors in: {"error": {"message": "...", "status_code": 400}}"""
    response = exception_handler(exc, context)

    if response is not None:
        response.data = {
            "error": {
                "message": _extract_message(response.data),
                "status_code": response.status_code,
            }
        }

    return response


def _extract_message(data) -> str:
    if isinstance(data, dict):
        for key, value in data.items():
            if isinstance(value, list) and value:
                return f"{key}: {value[0]}"
            return str(value)
    if isinstance(data, list) and data:
        return str(data[0])
    return str(data)
