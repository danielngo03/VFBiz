from fastapi import FastAPI

from app.main import app


def test_fastapi_entrypoint_is_declared_application() -> None:
    assert isinstance(app, FastAPI)
    assert app.title == "VFBiz AI Platform"
    assert app.version == "0.1.0"
