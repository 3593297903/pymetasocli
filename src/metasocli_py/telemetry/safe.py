import re
from typing import Any


def redact(value: Any, secrets: tuple[str, ...] = ()) -> Any:
    if isinstance(value, str):
        for secret in secrets:
            if secret:
                value = value.replace(secret, '[secret]')
        return re.sub(r'https?://[^\s"<>]+|data:[^\s"<>]+|Bearer\s+\S+', '[redacted]', value, flags=re.I)
    if isinstance(value, list):
        return [redact(v, secrets) for v in value]
    if isinstance(value, dict):
        return {k: '[secret]' if re.search(r'authorization|api.?key|token|cookie|secret', k, re.I)
                else redact(v, secrets) for k, v in value.items()}
    return value
