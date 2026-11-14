import hashlib
import json
import math
import re
from typing import Any

import rfc8785
import yaml

from ..domain.errors import AppError
from ..domain.text import valid_unicode

HASH_VERSION = 'jcs-sha256-v1'
MAX_RECORD = 8 * 1024 * 1024
MAX_INT = 2**53 - 1


def sha256(value: bytes | str) -> str:
    return hashlib.sha256(value.encode('utf-8') if isinstance(value, str) else value).hexdigest()


def validate_values(value: Any) -> None:
    if isinstance(value, str):
        valid_unicode(value)
    elif type(value) is int and abs(value) > MAX_INT:
        raise AppError('INTEGER_RANGE', 'Integer exceeds the interoperable safe range; use a string identifier.')
    elif isinstance(value, float) and not math.isfinite(value):
        raise AppError('INVALID_NUMBER', 'Non-finite numbers are forbidden.')
    elif isinstance(value, dict):
        for key, child in value.items():
            if not isinstance(key, str):
                raise AppError('INVALID_INPUT', 'Object keys must be strings.')
            valid_unicode(key)
            validate_values(child)
    elif isinstance(value, list):
        for child in value:
            validate_values(child)


def canonical(value: Any) -> bytes:
    validate_values(value)
    try:
        return rfc8785.dumps(value)
    except (ValueError, TypeError):
        raise AppError('HASH_INPUT', 'Record cannot be represented by RFC 8785.') from None


def digest(value: Any, *, exclude: tuple[str, ...] = ()) -> str:
    if exclude:
        value = {k: v for k, v in value.items() if k not in exclude}
    return sha256(canonical(value))


def pairs(items: list[tuple]) -> dict:
    result = {}
    for key, value in items:
        if key in result:
            raise AppError('DUPLICATE_FIELD', 'Duplicate object field.')
        result[key] = value
    return result


class RestrictedLoader(yaml.CSafeLoader):
    pass


# JSON-compatible implicit scalars only. In particular yes/on/dates are strings.
RestrictedLoader.yaml_implicit_resolvers = {
    key: [(tag, exp) for tag, exp in values if tag in {
        'tag:yaml.org,2002:null', 'tag:yaml.org,2002:bool',
        'tag:yaml.org,2002:int', 'tag:yaml.org,2002:float'}]
    for key, values in yaml.SafeLoader.yaml_implicit_resolvers.items()
}
RestrictedLoader.yaml_implicit_resolvers = {}
for tag, pattern, first in [
    ('null', r'^(?:null|~)$', ['n', '~']),
    ('bool', r'^(?:true|false)$', ['t', 'f']),
    ('int', r'^-?(?:0|[1-9][0-9]*)$', list('-0123456789')),
    ('float', r'^-?(?:0|[1-9][0-9]*)(?:\.[0-9]+(?:[eE][+-]?[0-9]+)?|[eE][+-]?[0-9]+)$', list('-0123456789')),
]:
    RestrictedLoader.add_implicit_resolver('tag:yaml.org,2002:' + tag, re.compile(pattern), first)


def mapping(loader: RestrictedLoader, node: yaml.MappingNode) -> dict:
    return pairs([(loader.construct_object(k), loader.construct_object(v)) for k, v in node.value])


RestrictedLoader.add_constructor('tag:yaml.org,2002:map', mapping)


def loads(data: bytes | str, *, yaml_input: bool = False, limit: int = MAX_RECORD) -> Any:
    raw = data.encode('utf-8') if isinstance(data, str) else data
    if len(raw) > limit:
        raise AppError('FILE_LIMIT', 'Structured input exceeds its size limit.')
    try:
        text = raw.decode('utf-8-sig', errors='strict')
        if yaml_input and text.lstrip().startswith('{'):
            try:
                value = json.loads(text, object_pairs_hook=pairs)
                validate_values(value)
                return value
            except json.JSONDecodeError:
                pass
        if yaml_input:
            for token in yaml.scan(text):
                if isinstance(token, (yaml.tokens.AnchorToken, yaml.tokens.AliasToken, yaml.tokens.TagToken)):
                    raise AppError('YAML_FEATURE', 'YAML anchors, aliases and explicit tags are forbidden.')
            value = yaml.load(text, Loader=RestrictedLoader)
        else:
            value = json.loads(text, object_pairs_hook=pairs,
                               parse_constant=lambda _: (_ for _ in ()).throw(AppError('INVALID_NUMBER', 'Non-finite number.')))
        validate_values(value)
        return value
    except (ValueError, UnicodeError, yaml.YAMLError, RecursionError, TypeError):
        raise AppError('INVALID_INPUT', 'Malformed or excessively nested structured input.') from None


def dumps(value: Any) -> bytes:
    validate_values(value)
    return (json.dumps(value, ensure_ascii=False, allow_nan=False, indent=2) + '\n').encode('utf-8')


def sealed(value: dict, field: str = 'hash') -> dict:
    result = {**value, 'hashVersion': HASH_VERSION}
    result[field] = digest(result, exclude=(field,))
    return result


def verify(value: dict, field: str = 'hash') -> dict:
    if value.get('hashVersion') != HASH_VERSION or value.get(field) != digest(value, exclude=(field,)):
        raise AppError('RECORD_INTEGRITY', 'Record identity hash is invalid.')
    return value
