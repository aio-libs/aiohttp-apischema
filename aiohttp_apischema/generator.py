import functools
import inspect
import sys
from collections.abc import Awaitable, Callable, Mapping
from functools import partial
from http import HTTPStatus
from pathlib import Path
from types import UnionType
from typing import (Any, Annotated, Concatenate, Generic, Iterable, Literal, ParamSpec,
                    Protocol, TypeGuard, TypeVar, cast, get_args, get_origin, get_type_hints)

from aiohttp import web
from aiohttp.hdrs import METH_ALL
from aiohttp.typedefs import Handler
from pydantic import Json, TypeAdapter, ValidationError

from aiohttp_apischema.response import APIResponse

if sys.version_info >= (3, 12):
    from typing import TypedDict
else:
    from typing_extensions import TypedDict

if sys.version_info >= (3, 11):
    from typing import NotRequired, Required
else:
    from typing_extensions import NotRequired, Required

OPENAPI_METHODS = frozenset({"get", "put", "post", "delete", "options", "head", "patch", "trace"})

_T = TypeVar("_T")
_U = TypeVar("_U")
_P = ParamSpec("_P")
_Resp = TypeVar("_Resp", bound=APIResponse[Any, Any], covariant=True)
_View = TypeVar("_View", bound=web.View)
OpenAPIMethod = Literal["get", "put", "post", "delete", "options", "head", "patch", "trace"]
__ModelKey = tuple[str, OpenAPIMethod, _T, _U]
_ModelKey = (
    __ModelKey[Literal["requestBody"], None]
    | __ModelKey[Literal["parameter"], tuple[str, bool]]
    | __ModelKey[Literal["response"], int]
)

class _APIHandler(Protocol, Generic[_Resp]):
    def __call__(self, request: web.Request, *, query: Any) -> Awaitable[_Resp]:
        ...


APIHandler = (
    Callable[[web.Request], Awaitable[_Resp]]
    | Callable[[web.Request, Any], Awaitable[_Resp]]
    | _APIHandler[_Resp]
)


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
    query: TypeAdapter[dict[str, object]]
    query_raw: dict[str, object]
    resps: dict[int, TypeAdapter[object]]
    summary: str
    tags: list[str]

class _Endpoint(TypedDict, total=False):
    desc: str
    meths: Required[dict[str | None, _EndpointData]]
    summary: str

class _Components(TypedDict, total=False):
    schemas: Mapping[str, object]

class _MediaTypeObject(TypedDict, total=False):
    schema: object

# in is a reserved keyword.
_ParameterObject = TypedDict("_ParameterObject", {
    "deprecated": bool,
    "description": str,
    "name": Required[str],
    "in": Required[Literal["query", "header", "path", "cookie"]],
    "required": bool,
    "schema": object
}, total=False)

class _RequestBodyObject(TypedDict, total=False):
    content: Required[dict[str, _MediaTypeObject]]

class _ResponseObject(TypedDict, total=False):
    content: dict[str, _MediaTypeObject]
    description: Required[str]

class _OperationObject(TypedDict, total=False):
    description: str
    operationId: str
    parameters: list[_ParameterObject]
    requestBody: _RequestBodyObject
    responses: dict[str, _ResponseObject]
    summary: str
    tags: list[str]

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

_Wrapper = Callable[[APIHandler[_Resp], web.Request], Awaitable[_Resp]]

def is_openapi_method(method: str) -> TypeGuard[OpenAPIMethod]:
    return method in OPENAPI_METHODS

def make_wrapper(ep_data: _EndpointData, wrapped: APIHandler[_Resp], handler: Callable[Concatenate[_Wrapper[_Resp], APIHandler[_Resp], _P], Awaitable[_Resp]]) -> Callable[_P, Awaitable[_Resp]] | None:
    # Only these keys need a wrapper created.
    if not {"body", "query_raw"} & ep_data.keys():
        return None

    async def _wrapper(handler: APIHandler[_Resp], request: web.Request) -> _Resp:
        inner_handler: Callable[..., Awaitable[_Resp]] = handler

        if body_ta := ep_data.get("body"):
            try:
                request_body = body_ta.validate_python(await request.read())
            except ValidationError as e:
                raise web.HTTPBadRequest(text=e.json(), content_type="application/json")
            inner_handler = partial(inner_handler, request_body)

        if query_ta := ep_data.get("query"):
            try:
                query = query_ta.validate_python(request.query)
            except ValidationError as e:
                raise web.HTTPBadRequest(text=e.json(), content_type="application/json")
            inner_handler = partial(inner_handler, query=query)

        return await inner_handler()

    # To handle both web.View methods and regular handlers (with different ways to get the
    # request object), this outer_wrapper() is needed with a custom handler lambda.

    @functools.wraps(wrapped)
    async def outer_wrapper(*args: _P.args, **kwargs: _P.kwargs) -> _Resp:  # type: ignore[misc]
        return await handler(_wrapper, wrapped, *args, **kwargs)

    return outer_wrapper

class SchemaGenerator:
    def __init__(self, info: Info | None = None):
        self._endpoints: dict[web.View | Handler, _Endpoint] = {}
        if info is None:
            info = {"title": "API", "version": "1.0"}
        self._openapi: _OpenApi = {"openapi": "3.1.0", "info": info}

    def _save_handler(self, handler: APIHandler[APIResponse[object, int]], tags: list[str]) -> _EndpointData:
        ep_data: _EndpointData = {}
        docs = inspect.getdoc(handler)
        if docs:
            summary, *descs = docs.split("\n", maxsplit=1)
            desc = descs[0].strip() if descs else None

            if summary:
                ep_data["summary"] = summary
            if desc:
                ep_data["desc"] = desc
            if tags:
                ep_data["tags"] = tags

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

        query_param = sig.parameters.get("query")
        if query_param and query_param.kind is query_param.KEYWORD_ONLY:
            ep_data["query_raw"] = query_param.annotation

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

    def api_view(self, tags: Iterable[str] = ()) -> Callable[[type[_View]], type[_View]]:
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
                ep_data = self._save_handler(func, tags=list(tags))
                self._endpoints[view]["meths"][method] = ep_data
                wrapper = make_wrapper(ep_data, func, lambda w, f, self: w(partial(f, self), self.request))
                if wrapper is not None:
                    setattr(view, method, wrapper)

            return view

        return decorator

    def api(self, tags: Iterable[str] = ()) -> Callable[[APIHandler[_Resp]], Callable[[web.Request], Awaitable[_Resp]]]:
        def decorator(handler: APIHandler[_Resp]) -> Callable[[web.Request], Awaitable[_Resp]]:
            ep_data = self._save_handler(handler, tags=list(tags))
            wrapper = make_wrapper(ep_data, handler, lambda w, f, r: w(partial(f, r), r))
            if wrapper is not None:
                self._endpoints[wrapper] = {"meths": {None: ep_data}}
                return wrapper

            handler = cast(Callable[[web.Request], Awaitable[_Resp]], handler)
            self._endpoints[handler] = {"meths": {None: ep_data}}
            return handler

        return decorator

    async def _on_startup(self, app: web.Application) -> None:
        #assert app.router.frozen
        models: list[tuple[_ModelKey, Literal["serialization", "validation"], TypeAdapter[object]]] = []
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
                tags = endpoints.get("tags")

                if summary:
                    operation["summary"] = summary
                if desc:
                    operation["description"] = desc
                if tags:
                    operation["tags"] = tags

                path_data[method] = operation

                body = endpoints.get("body")
                key: _ModelKey
                if body:
                    key = (path, method, "requestBody", None)
                    models.append((key, "validation", body))
                if query := endpoints.get("query_raw"):
                    # We need separate schemas for each key of the TypedDict.
                    td = {}
                    for param_name, param_type in get_type_hints(query).items():
                        required = param_name in query.__required_keys__  # type: ignore[attr-defined]
                        key = (path, method, "parameter", (param_name, required))

                        extracted_type = param_type
                        while get_origin(extracted_type) in {Annotated, Literal, Required, NotRequired}:
                            extracted_type = get_args(param_type)[0]
                        try:
                            is_str = issubclass(extracted_type, str)
                        except TypeError:
                            is_str = isinstance(extracted_type, str)  # Literal

                        # We also need to convert values to Json for runtime checking.
                        ann_type = param_type if is_str else Json[param_type]  # type: ignore[misc,valid-type]
                        models.append((key, "validation", TypeAdapter(ann_type)))
                        td[param_name] = Required[ann_type] if required else NotRequired[ann_type]
                    endpoints["query"] = TypeAdapter(TypedDict(query.__name__, td))  # type: ignore[attr-defined,operator]
                for code, model in endpoints["resps"].items():
                    key = (path, method, "response", code)
                    models.append((key, "serialization", model))

        elems, defs = TypeAdapter.json_schemas(models, ref_template="#/components/schemas/{model}")
        if defs:
            self._openapi["components"] = {"schemas": defs["$defs"]}

        # TODO: default response
        key_type: str
        for (key, mode), schema in elems.items():
            if key[2] == "requestBody":
                path, method, key_type, _ = key
                assert mode == "validation"
                paths[path][method]["requestBody"] = {"content": {"application/json": {"schema": schema}}}
            elif key[2] == "parameter":
                path, method, key_type, (param_name, required) = key
                assert mode == "validation"
                parameter: _ParameterObject = {
                    "name": param_name, "in": "query", "required": required, "schema": schema}
                paths[path][method].setdefault("parameters", []).append(parameter)
            else:
                path, method, key_type, code = key
                assert key_type == "response"
                assert mode == "serialization"
                responses = paths[path][method].setdefault("responses", {})
                content: dict[str, _MediaTypeObject] = {"application/json": {"schema": schema}}
                reason = HTTPStatus(code).phrase
                responses[str(code)] = {"description": reason, "content": content}
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
