import functools
import os

import opentelemetry.trace
from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor


def get_endpoint():
    # test value for debugging with local tunnel:
    # http://localhost:4318/v1/traces
    return os.environ.get("OTEL_ENDPOINT")


def init():
    if (endpoint := get_endpoint()) is None:
        print("skipping trace initialization")
        return
    tracer = TracerProvider(
        resource=Resource(
            attributes={
                "service.name": "embed-works.web"
            }
        )
    )
    opentelemetry.trace.set_tracer_provider(tracer)
    tracer.add_span_processor(
        BatchSpanProcessor(
            OTLPSpanExporter(endpoint=endpoint)
        )
    )


def trace_function(func):
    @functools.wraps(func)
    def wrapper(*args, **kwargs):
        with opentelemetry.trace.get_tracer(__name__).start_as_current_span(
            func.__name__,
            attributes=kwargs
        ):
            return func(*args, **kwargs)

    return wrapper
