from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse


class ApiError(Exception):
    def __init__(self, status_code, reason, message, used_by=None):
        super().__init__(message)
        self.status_code = status_code
        self.reason = reason
        self.message = message
        self.used_by = used_by

    def body(self):
        body = {"reason": self.reason, "message": self.message}
        if self.used_by is not None:
            body["used_by"] = self.used_by
        return body


def not_found(kind, record_id):
    return ApiError(404, "not_found", f"{kind} {record_id} was not found")


def conflict(reason, message, used_by=None):
    return ApiError(409, reason, message, used_by=used_by)


def store_down(reason, message):
    return ApiError(503, reason, message)


def validation_error(message):
    return ApiError(422, "validation", message)


def _describe_validation_errors(errors):
    parts = []
    for error in errors:
        location = ".".join(str(part) for part in error.get("loc", ()) if part != "body")
        if location:
            parts.append(f"{location}: {error.get('msg', 'invalid value')}")
        else:
            parts.append(error.get("msg", "invalid value"))
    return "; ".join(parts) or "Invalid request"


async def _handle_api_error(request, exc):
    return JSONResponse(status_code=exc.status_code, content=exc.body())


async def _handle_validation_error(request, exc):
    return JSONResponse(
        status_code=422,
        content={"reason": "validation", "message": _describe_validation_errors(exc.errors())},
    )


async def _handle_unexpected_error(request, exc):
    return JSONResponse(
        status_code=500,
        content={"reason": "internal", "message": "Unexpected server error"},
    )


def install_error_handlers(app):
    app.add_exception_handler(ApiError, _handle_api_error)
    app.add_exception_handler(RequestValidationError, _handle_validation_error)
    app.add_exception_handler(Exception, _handle_unexpected_error)