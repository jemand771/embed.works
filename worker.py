import enum
import json
import os
import redis
import requests
import typing

import ufys.util
from ufys import telemetry
from ufys.model import UfysError, UfysResponse


class ResponseMode(enum.Enum):
    auto_embed = "auto"
    embed = "embed"
    direct = "direct"
    original = "redirect"
    oembed = "oembed"
    auto_debug = "debug"
    embed_debug = "debug-embed"
    raw_debug = "debug-raw"


class InvalidUfysReponse(Exception):
    code = "invalid-ufys-response"
    message = "received an invalid response from a backend service"


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
    def get_info(self, url: str) -> list[UfysResponse | UfysError]:
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
    def json_to_resp(json_: list[dict] | typing.Any) -> list[UfysResponse | UfysError]:
        if not isinstance(json_, list) or not all(isinstance(entry, dict) for entry in json_):
            raise InvalidUfysReponse()
        class_map = dict(
            UfysResponse=UfysResponse,
            UfysError=UfysError,
        )
        results = []
        for dict_result in json_:
            if dict_result.get("_class") not in class_map:
                continue
            results.append(
                ufys.util.dataclass_from_dict(
                    # TODO we should do the _class type check inside ufys, not here
                    class_map[dict_result["_class"]],
                    dict_result
                )
            )
        if not results:
            raise InvalidUfysReponse()
        return results
