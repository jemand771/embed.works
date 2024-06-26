import dataclasses
import flask
import json
import opentelemetry.trace
import os
import pygments.formatters.img
import pygments.lexers
import pygments.styles
import re
import redis
import requests.models
from flask import Flask, jsonify, redirect, render_template, request
from opentelemetry.instrumentation.flask import FlaskInstrumentor
from opentelemetry.instrumentation.redis import RedisInstrumentor
from opentelemetry.instrumentation.requests import RequestsInstrumentor
# noinspection PyPackageRequirements
from werkzeug.middleware.proxy_fix import ProxyFix

import static
import worker
from ufys import telemetry
from ufys.model import UfysError, UfysResponse
from worker import ResponseMode

MODE_PARAM_KEY = "ew-mode"
TRACE_PARAM_KEY = "ew-trace"

APP = Flask(__name__)
APP.wsgi_app = ProxyFix(APP.wsgi_app)
APP.config["JSONIFY_PRETTYPRINT_REGULAR"] = True

telemetry.init(service_name="embed-works.web")
FlaskInstrumentor().instrument_app(APP)
RedisInstrumentor().instrument()
RequestsInstrumentor().instrument()

BASE_HOSTS = os.environ.get("BASE_HOSTS", "").split(",")
WK = worker.Worker(
    redis.Redis(host=os.environ.get("REDIS_HOST", "localhost")),
    ufys_url=os.environ["UFYS_URL"]
)

ERROR_TITLE = "oh no! something went wrong (╯°□°)╯︵ ┻━┻"


class DataClassJSONEncoder(json.JSONEncoder):
    def default(self, obj):
        if dataclasses.is_dataclass(obj):
            return dataclasses.asdict(obj)
        return super().default(obj)


@APP.get("/favicon.ico")
def favicon():
    return "shush", 404


# TODO parallel requests
@APP.get("/", defaults=dict(path=""))
@APP.get("/<path:path>")
def all_requests(path):
    host = request.host.split(":")[0]
    if host in BASE_HOSTS:
        # discord turns bla/https://blub into bla/https:/blub
        fixed_url = re.sub(r"^(https?:/)([^/])", r"\1/\2", path)
        return handle_url(fixed_url)
    for base in BASE_HOSTS:
        host_parts = host.split(".")
        match_parts = base.split(".")
        while True:
            if host_parts.pop() != match_parts.pop():
                break
            if not match_parts:
                # subdomain a la tiktok.com.embed.works detected
                # rewrite tiktok.embed.works to tiktok.com.embed.works in the reverse proxy to support shorter syntax
                full_domain = ".".join(host_parts)
                return handle_url(f"https://{full_domain}/{path}")
    return "unable to parse url", 400


@telemetry.trace_function
def handle_url(url: str):
    mode = determine_response_mode()
    full_url = attach_current_request_query_params(url)
    if mode == ResponseMode.original:
        return redirect(full_url, code=302)
    infos = WK.get_info(full_url)
    # TODO format selection
    assert infos
    if mode == ResponseMode.raw_debug:
        return jsonify(infos)
    if mode == ResponseMode.embed_debug:
        return render_debug_embed(infos)
    info = infos[0]
    if not isinstance(info, UfysResponse):
        assert isinstance(info, UfysError)
        return display_fancy_error(infos)
    creator_str = info.creator
    if info.site:
        if creator_str:
            creator_str += f" on {info.site}"
        else:
            creator_str = info.site
    if mode == ResponseMode.oembed:
        return jsonify(build_oembed(creator_str, full_url))
    # TODO auto redirect check (user agent)
    if mode == ResponseMode.direct:
        return redirect(info.video_url, code=302)
    return render_template(
        "embed.html",
        color=static.EXTRACTOR_COLOR.get(info.site),
        creator_str=creator_str,
        info=info,
        video_url=get_mode_url(request.url, ResponseMode.direct),
        oembed_url=get_mode_url(request.url, ResponseMode.oembed),
        original_url=get_mode_url(request.url, ResponseMode.original)
    )


def determine_response_mode() -> ResponseMode:
    mode = ResponseMode.auto_embed
    try:
        mode = ResponseMode(request.args[MODE_PARAM_KEY])
    except (KeyError, ValueError):
        pass
    is_bot = static.is_bot(request)
    if mode == ResponseMode.auto_embed:
        mode = ResponseMode.embed if is_bot else ResponseMode.original
    if mode == ResponseMode.auto_debug:
        mode = ResponseMode.embed_debug if is_bot else ResponseMode.raw_debug
    return mode


def attach_current_request_query_params(url: str) -> str:
    req = requests.models.PreparedRequest()
    req.prepare_url(
        url, {
            key: value
            for key, value
            in request.args.items()
            if not key.startswith("ew-")
        }
    )
    return req.url


def build_oembed(creator_str: str, requested_url: str) -> dict[str, str]:
    trace_id = opentelemetry.trace.format_trace_id(
        opentelemetry.trace.get_current_span().get_span_context().trace_id
    )
    provider = "embed.works"
    if TRACE_PARAM_KEY in request.args:
        provider += f" - trace {trace_id}"
    data = dict(
        provider_name=provider,
        author_url=requested_url
    )
    if creator_str is not None:
        data["author_name"] = creator_str
    return data


def get_mode_url(url, mode: ResponseMode):
    req = requests.models.PreparedRequest()
    req.prepare_url(url, {MODE_PARAM_KEY: mode.value})
    return req.url


def render_debug_embed(infos: list[UfysResponse | UfysError]):
    text = json.dumps(infos, cls=DataClassJSONEncoder, indent=2, ensure_ascii=False)
    lexer = pygments.lexers.get_lexer_by_name("json")
    formatter = pygments.formatters.img.ImageFormatter(
        line_numbers=False,
        style=pygments.styles.get_style_by_name("one-dark")
    )
    image = pygments.highlight(text, lexer, formatter)
    response = flask.make_response(image)
    response.headers.set("Content-Type", "image/png")
    return response


def error_to_line(error: UfysError):
    return f"{error.code}: {error.message}"


def display_fancy_error(errors: list[UfysError]) -> str:
    assert errors
    lines = [error_to_line(err) for err in errors]
    return render_template(
        "error.html",
        title=ERROR_TITLE,
        message_html="<br>".join(lines),
        message_embed="\n".join(lines),
    )


# TODO *even* better errors
@APP.errorhandler(worker.InvalidUfysReponse)
def handle_ufys_error(ex: worker.InvalidUfysReponse):
    return display_fancy_error(
        [
            UfysError(
                code=ex.code,
                message=ex.message,
            )
        ]
    )


@APP.errorhandler(Exception)
def handle_any_error(ex):
    return display_fancy_error(
        [
            UfysError(
                code="unknown error",
                message=f"something went REALLY wrong ({str(ex)})",
            )
        ]
    )


if __name__ == '__main__':
    APP.run(host="0.0.0.0", port=5000, debug=True)
