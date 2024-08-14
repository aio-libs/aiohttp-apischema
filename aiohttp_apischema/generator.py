import functools
import inspect
import sys
from collections.abc import Awaitable, Callable, Mapping
from http import HTTPStatus
from pathlib import Path
from types import UnionType
from typing import Any, Literal, TypedDict, TypeGuard, TypeVar, cast, get_args, get_origin

from aiohttp import web
from aiohttp.hdrs import METH_ALL
from aiohttp.typedefs import Handler
from pydantic import Json, TypeAdapter, ValidationError

from aiohttp_apischema.response import APIResponse

if sys.version_info >= (3, 11):
    from typing import Required
else:
    from typing_extensions import Required

OPENAPI_METHODS = frozenset({"get", "put", "post", "delete", "options", "head", "patch", "trace"})

_T = TypeVar("_T")
_Resp = TypeVar("_Resp", bound=APIResponse[Any, Any])
_View = TypeVar("_View", bound=web.View)
APIHandler = (
    Callable[[web.Request], Awaitable[_Resp]]
    | Callable[[web.Request, Any], Awaitable[_Resp]]
)
OpenAPIMethod = Literal["get", "put", "post", "delete", "options", "head", "patch", "trace"]

class Contact(TypedDict, total=False):
    name: str
    url: str
    email: str

class _LicenseID(TypedDict, total=False):
    name: Required[str]
    identifier: str

class _LicenseURL(TypedDict):
    name: str
    url: str

License = _LicenseID | _LicenseURL

class Info(TypedDict, total=False):
    title: Required[str]
    version: Required[str]
    summary: str
    description: str
    termsOfService: str
    contact: Contact
    license: License

class _EndpointData(TypedDict, total=False):
    body: TypeAdapter[object]
    desc: str
    resps: dict[int, TypeAdapter[Any]]
    summary: str

class _Endpoint(TypedDict, total=False):
    desc: str
    meths: Required[dict[str | None, _EndpointData]]
    summary: str

class _Components(TypedDict, total=False):
    schemas: Mapping[str, object]

class _MediaTypeObject(TypedDict, total=False):
    schema: object

class _RequestBodyObject(TypedDict, total=False):
    content: Required[dict[str, _MediaTypeObject]]

class _ResponseObject(TypedDict, total=False):
    content: dict[str, _MediaTypeObject]
    description: Required[str]

class _OperationObject(TypedDict, total=False):
    description: str
    operationId: str
    requestBody: _RequestBodyObject
    responses: dict[str, _ResponseObject]
    summary: str

class _PathObject(TypedDict, total=False):
    delete: _OperationObject
    description: str
    get: _OperationObject
    head: _OperationObject
    options: _OperationObject
    patch: _OperationObject
    post: _OperationObject
    put: _OperationObject
    summary: str
    trace: _OperationObject

class _OpenApi(TypedDict, total=False):
    components: _Components
    info: Required[Info]
    openapi: Required[Literal["3.1.0"]]
    paths: Mapping[str, _PathObject]

INDEX_HTML = """<!DOCTYPE html>
<html lang="en">
  <head>
    <meta charset="UTF-8">
    <title>Swagger UI</title>
    <script src="./swagger-ui-bundle.js" defer></script>
    <script src="./swagger-ui-standalone-preset.js" defer></script>
    <script src="./swagger-initializer.js" defer></script>
    <link rel="stylesheet" type="text/css" href="./swagger-ui.css" />
    <link rel="stylesheet" type="text/css" href="index.css" />
    <link rel="icon" type="image/png" href="./favicon-32x32.png" sizes="32x32" />
    <link rel="icon" type="image/png" href="./favicon-16x16.png" sizes="16x16" />
  </head>

  <body>
    <div id="swagger-ui" data-url="{}"></div>
  </body>
</html>"""
SWAGGER_PATH = Path(__file__).parent / "swagger-ui"

def is_openapi_method(method: str) -> TypeGuard[OpenAPIMethod]:
    return method in OPENAPI_METHODS

def create_view_wrapper(handler: Callable[[_View, _T], Awaitable[_Resp]], ta: TypeAdapter[_T]) -> Callable[[_View], Awaitable[_Resp]]:
    @functools.wraps(handler)
    async def wrapper(self: _View) -> _Resp:  # type: ignore[misc]
        try:
            request_body = ta.validate_python(await self.request.read())
        except ValidationError as e:
            raise web.HTTPBadRequest(text=e.json(), content_type="application/json")
        return await handler(self, request_body)
    return wrapper

class SchemaGenerator:
    def __init__(self, info: Info | None = None):
        self._endpoints: dict[web.View | Handler, _Endpoint] = {}
        if info is None:
            info = {"title": "API", "version": "1.0"}
        self._openapi: _OpenApi = {"openapi": "3.1.0", "info": info}

    def _save_handler(self, handler: APIHandler[APIResponse[object, int]]) -> _EndpointData:
        ep_data: _EndpointData = {}
        docs = inspect.getdoc(handler)
        if docs:
            summary, *descs = docs.split("\n", maxsplit=1)
            desc = descs[0].strip() if descs else None

            if summary:
                ep_data["summary"] = summary
            if desc:
                ep_data["desc"] = desc

        sig = inspect.signature(handler, eval_str=True)
        params = iter(sig.parameters.values())
        body = next(params)
        try:
            if body.name in {"self", "cls"} or body.annotation is body.empty:
                body = next(params)
            if body.name == "request" or body.annotation is web.Request:
                body = next(params)
        except StopIteration:
            pass
        else:
            if body.kind in {body.POSITIONAL_ONLY, body.POSITIONAL_OR_KEYWORD}:
                ep_data["body"] = TypeAdapter(Json[body.annotation])  # type: ignore[misc,name-defined]

        ep_data["resps"] = {}
        if get_origin(sig.return_annotation) is UnionType:
            resps = get_args(sig.return_annotation)
        else:
            resps = (sig.return_annotation,)
        for resp in resps:
            args = get_args(resp)
            try:
                code = get_args(args[1])[0]  # Value of Literal
            except IndexError:
                code = 200
            ep_data["resps"][code] = TypeAdapter(args[0])

        return ep_data

    def api_view(self) -> Callable[[type[_View]], type[_View]]:
        def decorator(view: type[_View]) -> type[_View]:
            self._endpoints[view] = {"meths": {}}

            docs = inspect.getdoc(view)
            if docs:
                summary, *descs = docs.split("\n", maxsplit=1)
                desc = descs[0].strip() if descs else None

                if summary:
                    self._endpoints[view]["summary"] = summary
                if desc:
                    self._endpoints[view]["desc"] = desc

            methods = ((getattr(view, m), m) for m in map(str.lower, METH_ALL) if hasattr(view, m))
            for func, method in methods:
                ep_data = self._save_handler(func)
                self._endpoints[view]["meths"][method] = ep_data
                ta = ep_data.get("body")
                if ta:
                    setattr(view, method, create_view_wrapper(func, ta))

            return view

        return decorator

    def api(self) -> Callable[[APIHandler[_Resp]], Callable[[web.Request], Awaitable[_Resp]]]:
        def decorator(handler: APIHandler[_Resp]) -> Callable[[web.Request], Awaitable[_Resp]]:
            ep_data = self._save_handler(handler)
            ta = ep_data.get("body")
            if ta:
                @functools.wraps(handler)
                async def wrapper(request: web.Request) -> _Resp:  # type: ignore[misc]
                    nonlocal handler
                    try:
                        request_body = ta.validate_python(await request.read())
                    except ValidationError as e:
                        raise web.HTTPBadRequest(text=e.json(), content_type="application/json")
                    handler = cast(Callable[[web.Request, Any], Awaitable[_Resp]], handler)
                    return await handler(request, request_body)

                self._endpoints[wrapper] = {"meths": {None: ep_data}}
                return wrapper

            handler = cast(Callable[[web.Request], Awaitable[_Resp]], handler)
            self._endpoints[handler] = {"meths": {None: ep_data}}
            return handler

        return decorator

    async def _on_startup(self, app: web.Application) -> None:
        #assert app.router.frozen
        models: list[tuple[tuple[str, OpenAPIMethod, int | Literal["requestBody"]], Literal["serialization", "validation"], TypeAdapter[object]]] = []
        paths: dict[str, _PathObject] = {}
        for route in app.router.routes():
            ep_data = self._endpoints.get(route.handler)
            if not ep_data:
                continue

            assert route.resource  # Won't get a SystemRoute here.
            path = route.resource.canonical
            path_data = paths.setdefault(path, {})

            summary = ep_data.get("summary")
            desc = ep_data.get("desc")
            if summary:
                path_data["summary"] = summary
            if desc:
                path_data["description"] = desc

            for method, endpoints in ep_data["meths"].items():
                method = (method or route.method).lower()
                if method == "head":
                    # Skip these for now as they're added automatically by aiohttp.
                    continue
                if not is_openapi_method(method):
                    raise ValueError("HTTP method not support by OpenAPI: {}".format(method.upper()))
                # TODO: Fix operationId for class views.
                operation: _OperationObject = {"operationId": route.handler.__name__}
                summary = endpoints.get("summary")
                desc = endpoints.get("desc")
                if summary:
                    operation["summary"] = summary
                if desc:
                    operation["description"] = desc
                path_data[method] = operation

                body = endpoints.get("body")
                key: tuple[str, OpenAPIMethod, int | Literal["requestBody"]]
                if body:
                    key = (path, method, "requestBody")
                    models.append((key, "validation", body))
                for code, model in endpoints["resps"].items():
                    key = (path, method, code)
                    models.append((key, "serialization", model))

        elems, defs = TypeAdapter.json_schemas(models, ref_template="#/components/schemas/{model}")
        if defs:
            self._openapi["components"] = {"schemas": defs["$defs"]}

        # TODO: default response
        for ((path, method, code_or_key), mode), schema in elems.items():
            if code_or_key == "requestBody":
                assert mode == "validation"
                paths[path][method][code_or_key] = {"content": {"application/json": {"schema": schema}}}
            else:
                assert isinstance(code_or_key, int)
                assert mode == "serialization"
                responses = paths[path][method].setdefault("responses", {})
                content: dict[str, _MediaTypeObject] = {"application/json": {"schema": schema}}
                reason = HTTPStatus(code_or_key).phrase
                responses[str(code_or_key)] = {"description": reason, "content": content}
        if paths:
            self._openapi["paths"] = paths

    def setup(self, app: web.Application) -> None:
        app.on_startup.append(self._on_startup)
        app.router.add_get("/schema", self._schema)
        app.router.add_get("/swagger/", self._view)
        app.router.add_static("/swagger", SWAGGER_PATH)

    async def _schema(self, request: web.Request) -> web.Response:
        return web.json_response(self._openapi)

    async def _view(self, request: web.Request) -> web.Response:
        return web.Response(text=INDEX_HTML.format("/schema"), content_type="text/html")
