import enum
import json
import os

import redis
import requests

import telemetry
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

    @property
    def cache_ttl(self):
        try:
            return int(os.environ.get("CACHE_TTL", ""))
        except ValueError:
            return 60 * 60

    @telemetry.trace_function
    def get_info(self, url: str) -> UfysResponse:
        lock = self.redis.lock(f"ew-lock-{url}", timeout=30)
        cache_key = f"ew-data-{url}"
        lock.acquire()
        try:
            if (info_json_str := self.redis.get(cache_key)) is not None:
                return self.json_to_resp(json.loads(info_json_str))
            fresh_json = requests.post(
                self.ufys_url + "/video",
                json=dict(
                    url=url
                )
            ).json()
            self.redis.set(cache_key, json.dumps(fresh_json, ensure_ascii=False), ex=self.cache_ttl)
            return self.json_to_resp(fresh_json)
        finally:
            lock.release()

    @staticmethod
    def json_to_resp(json_):
        try:
            result = ufys.util.dataclass_from_dict(
                UfysResponse,
                json_
            )
        except TypeError:
            try:
                raise EWUfysError.from_model(
                    ufys.util.dataclass_from_dict(
                        UfysError,
                        json_
                    )
                )
            except TypeError:
                raise EWUfysError()
        return result
