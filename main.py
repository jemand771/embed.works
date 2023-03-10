import os

import redis
from flask import Flask, redirect, render_template, request

import worker
from worker import ResponseMode

APP = Flask(__name__)

BASE_HOSTS = os.environ.get("BASE_HOSTS", "").split(",")
WK = worker.Worker(
    redis.Redis(),
    ufys_url=os.environ["UFYS_URL"]
)


@APP.get("/favicon.ico")
def favicon():
    return "shush", 404


# TODO parallel requests
@APP.get("/", defaults=dict(path=""))
@APP.get("/<path:path>")
def all_requests(path):
    host = request.host.split(":")[0]
    if host in BASE_HOSTS:
        return handle_url(path)
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


def handle_url(url: str):
    mode = ResponseMode.embed
    try:
        mode = ResponseMode(request.args["ew-mode"])
    except (KeyError, ValueError):
        pass
    full_url = url + (f"?{request.query_string.decode()}" if request.query_string else "")
    if mode == ResponseMode.original:
        return redirect(full_url, code=307)
    info = WK.get_info(full_url)
    # TODO auto redirect check (user agent)
    if mode == ResponseMode.direct:
        return redirect(info.video_url, code=307)
    return render_template("embed.html", info=info)


# TODO better errors
@APP.errorhandler(worker.EWUfysError)
def handle_ufys_error(ex: worker.EWUfysError):
    return render_template("error.html", code=ex.code, message=ex.message)


@APP.errorhandler(Exception)
def handle_any_error(_):
    return render_template(
        "error.html",
        code="unknown error",
        message="something went REALLY wrong"
    )


if __name__ == '__main__':
    APP.run(host="0.0.0.0", port=5000, debug=True)
