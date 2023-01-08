import enum
import functools
import time

import redis
import requests

import ufys.util
from ufys.model import UfysError, UfysResponse


class ResponseMode(enum.Enum):
    auto_embed = "auto"
    embed = "embed"
    direct = "direct"
    original = "redirect"


class EWUfysError(Exception):

    def __init__(self, code="unknown", message=""):
        self.code = code
        self.message = message

    @classmethod
    def from_model(cls, error: UfysError):
        return cls(code=error.code, message=error.message)


class Worker:

    def __init__(self, redis_: redis.Redis, ufys_url: str):
        self.redis = redis_
        self.ufys_url = ufys_url

    def get_info(self, url: str) -> UfysResponse:
        # amazing hack from https://stackoverflow.com/a/55900800/9145163
        return self._get_info(url, ttl_hash=time.time() // 3600)

    # TODO persistent cache
    @functools.cache
    def _get_info(self, url: str, ttl_hash) -> UfysResponse:
        resp_json = requests.post(
            self.ufys_url + "/video",
            json=dict(
                url=url
            )
        ).json()
        try:
            result = ufys.util.dataclass_from_dict(
                UfysResponse,
                resp_json
            )
        except TypeError:
            try:
                raise EWUfysError.from_model(
                    ufys.util.dataclass_from_dict(
                        UfysError,
                        resp_json
                    )
                )
            except TypeError:
                raise EWUfysError()
        return result
