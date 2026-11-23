from fastapi import FastAPI, Request
from fastapi.encoders import jsonable_encoder
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from sqlalchemy.exc import IntegrityError
from starlette.exceptions import HTTPException


class AppError(Exception):
    def __init__(self, status: int, code: str, message: str, details=None):
        self.status, self.code, self.message, self.details = status, code, message, details


def not_found(what: str) -> AppError:
    return AppError(404, f"{what.upper()}_NOT_FOUND", f"{what.capitalize()} not found")


def get_or_404(db, model, id: int, what: str, lock: bool = False):
    obj = db.get(model, id, with_for_update=lock)
    if obj is None:
        raise not_found(what)
    return obj


def _body(code, message, details=None):
    return {"code": code, "message": message, "details": jsonable_encoder(details)}


def install(app: FastAPI) -> None:
    @app.exception_handler(AppError)
    async def app_error(_: Request, e: AppError):
        return JSONResponse(_body(e.code, e.message, e.details), status_code=e.status)

    @app.exception_handler(RequestValidationError)
    async def validation_error(_: Request, e: RequestValidationError):
        return JSONResponse(_body("VALIDATION_ERROR", "Invalid request", e.errors()), status_code=422)

    @app.exception_handler(HTTPException)
    async def http_error(_: Request, e: HTTPException):
        return JSONResponse(_body(f"HTTP_{e.status_code}", str(e.detail)), status_code=e.status_code)

    @app.exception_handler(IntegrityError)
    async def integrity_error(_: Request, e: IntegrityError):
        constraint = getattr(getattr(e.orig, "diag", None), "constraint_name", None)
        return JSONResponse(_body("CONFLICT", "Conflicts with existing data", {"constraint": constraint}), status_code=409)
