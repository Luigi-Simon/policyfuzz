"""Request dependencies exposing the owned application container."""

from fastapi import Request

from app.container import AppContainer


def get_container(request: Request) -> AppContainer:
    return request.app.state.container


def json_command(model):
    """Validate decoded HTTP data with the domain's strict JSON semantics.

    FastAPI normally validates Python lists, which strict tuple/frozenset fields
    correctly reject. Re-entering JSON validation accepts JSON arrays while
    preserving strict numbers, booleans, strings and every domain validator.
    """
    import json

    from pydantic import WrapValidator

    def validate(value, handler):
        if not isinstance(value, dict):
            raise ValueError("The request must be a JSON object.")  # noqa: TRY004 - Pydantic catches ValueError, not TypeError.
        return model.model_validate_json(json.dumps(value, allow_nan=False))

    return WrapValidator(validate)
