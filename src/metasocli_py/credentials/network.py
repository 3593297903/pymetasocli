from typing import Literal
from urllib.parse import urlsplit

from pydantic import model_validator

from ..contracts.story import StrictModel, parse
from ..domain.errors import AppError
from ..persistence.files import read_json
from .config import config_dir


class Network(StrictModel):
    mode: Literal['direct', 'proxy', 'environment'] = 'direct'
    proxy: str | None = None

    @model_validator(mode='after')
    def valid_proxy(self):
        if (self.mode == 'proxy') != bool(self.proxy):
            raise ValueError('Proxy mode requires an explicit proxy URL')
        if self.proxy:
            parts = urlsplit(self.proxy)
            if parts.scheme not in ('http', 'https') or not parts.hostname or parts.fragment or parts.query or parts.path not in ('', '/'):
                raise ValueError('Invalid proxy URL')
        return self


def network(provider: str) -> dict:
    if provider not in ('metaso', 'images'):
        raise AppError('NETWORK_CONFIG', 'Unknown provider network configuration.')
    file = config_dir()/f'{provider}-network.json'
    value = parse(Network, read_json(file)) if file.exists() else {}
    return {'mode': value.get('mode', 'direct'), 'proxy': value.get('proxy')}
