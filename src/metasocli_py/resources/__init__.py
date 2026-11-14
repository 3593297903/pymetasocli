"""Wheel-owned resources, independent of cwd and source checkout."""


def append_denoise(kind: str, prompt: str) -> str:
    from ..domain.errors import AppError
    from ..media.denoise import ValidationError, compose_prompt
    try:
        return compose_prompt(prompt, kind)
    except ValidationError:
        raise AppError('DENOISE_INVALID', 'Recipe has invalid or duplicate type-specific denoise text.') from None
