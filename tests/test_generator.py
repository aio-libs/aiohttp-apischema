import json
import sys
from datetime import datetime
from typing import Annotated, Literal

import pytest
from aiohttp import web
from aiohttp.pytest_plugin import AiohttpClient
from aiohttp_apischema import APIResponse, SchemaGenerator
from aiohttp_apischema.generator import Contact, Info, License
from pydantic import Field

if sys.version_info >= (3, 11):
    from typing import NotRequired
else:
    from typing_extensions import NotRequired


from typing_extensions import TypedDict


class Poll(TypedDict):
    """A question to be voted on."""

    id: int
    question: str
    pub_date: str


class NewPoll(TypedDict):
    """Details to create a new poll."""

    question: str
    choices: Annotated[tuple[str, ...], Field(min_length=2)]


POLL1: Poll = {"id": 1, "question": "What's new?", "pub_date": datetime(2015, 12, 15, 17, 17, 49).isoformat()}


async def test_default_info(aiohttp_client: AiohttpClient) -> None:
    schema_gen = SchemaGenerator()

    app = web.Application()
    schema_gen.setup(app)

    client = await aiohttp_client(app)
    async with client.get("/schema") as resp:
        assert resp.ok
        schema = await resp.json()

    assert schema == {"openapi": "3.1.0", "info": {"title": "API", "version": "1.0"}}

async def test_custom_info(aiohttp_client: AiohttpClient) -> None:
    c: Contact = {"name": "Foo Bar", "url": "https://me.example", "email": "me@me.example"}
    l: License = {"name": "AGPLv3+", "identifier": "AGPL-3.0-or-later"}
    info: Info = {"title": "T", "version": "2", "summary": "sum", "description": "desc",
                  "termsOfService": "https://tos.example/foo", "contact": c, "license": l}
    schema_gen = SchemaGenerator(info)

    app = web.Application()
    schema_gen.setup(app)

    client = await aiohttp_client(app)
    async with client.get("/schema") as resp:
        assert resp.ok
        schema = await resp.json()

    assert schema["info"] == info

async def test_response(aiohttp_client: AiohttpClient) -> None:
    schema_gen = SchemaGenerator()

    @schema_gen.api()
    async def list_polls(request: web.Request) -> APIResponse[tuple[Poll, ...], Literal[200]]:
        """Summary here.

        This
        is
        a

        long
          description.
        """
        return APIResponse((POLL1,))  # pragma: no cover

    app = web.Application()
    schema_gen.setup(app)
    app.router.add_get("/polls", list_polls)

    client = await aiohttp_client(app)
    async with client.get("/schema") as resp:
        assert resp.ok
        schema = await resp.json()

    schemas = {"Poll": {"description": "A question to be voted on.",
                        "properties": {
                            "id": {"title": "Id", "type": "integer"},
                            "pub_date": {"title": "Pub Date", "type": "string"},
                            "question": {"title": "Question", "type": "string"}},
                        "required": ["id", "question", "pub_date"],
                        "title": "Poll", "type": "object"}}
    paths = {"/polls": {"get": {
        "description": "This\nis\na\n\nlong\n  description.",
        "operationId": "list_polls",
        "responses": {"200": {
            "content": {"application/json": {"schema": {
                "items": {"$ref": "#/components/schemas/Poll"}, "type": "array"}}},
            "description": "OK"}},
        "summary": "Summary here."}}}
    assert schema["components"]["schemas"] == schemas
    assert schema["paths"] == paths

async def test_body(aiohttp_client: AiohttpClient) -> None:
    schema_gen = SchemaGenerator()

    @schema_gen.api()
    async def add_choices(request: web.Request, messages: tuple[str, ...]) -> APIResponse[tuple[str, ...], Literal[201]] | APIResponse[None, Literal[404]]:
        poll_id = int(request.match_info["id"])
        if poll_id == 1:
            return APIResponse[None, Literal[404]](None, status=404)
        return APIResponse[tuple[str, ...], Literal[201]](messages, status=201)

    app = web.Application()
    schema_gen.setup(app)
    app.router.add_put("/poll/{id:\\d+}/choice", add_choices)

    client = await aiohttp_client(app)
    async with client.get("/schema") as resp:
        assert resp.ok
        schema = await resp.json()

    paths = {"/poll/{id}/choice": {"put": {
        "operationId": "add_choices",
        "requestBody": {"content": {"application/json": {"schema": {
            "contentMediaType": "application/json", "contentSchema": {
                "items": {"type": "string"}, "type": "array"},
            "type": "string"}}}},
        "responses": {
            "201": {
                "content": {"application/json": {"schema": {
                    "items": {"type": "string"},
                    "type": "array"}}},
                "description": "Created"},
            "404": {
                "content": {"application/json": {"schema": {"type": "null"}}},
                "description": "Not Found"}}}}}
    assert schema["paths"] == paths

    async with client.put("/poll/1/choice", json=("foo", "bar")) as resp:
        assert resp.status == 404
        result = await resp.json()
        assert result is None

    async with client.put("/poll/2/choice", json=("foo", "bar")) as resp:
        assert resp.status == 201
        result = await resp.json()
        assert result == ["foo", "bar"]

    async with client.put("/poll/2/choice", json=(42,)) as resp:
        assert resp.status == 400
        result = await resp.json()
        assert len(result) == 1
        assert result[0]["loc"] == [0]
        assert result[0]["type"] == "string_type"

    async with client.put("/poll/2/choice", json=42) as resp:
        assert resp.status == 400
        result = await resp.json()
        assert len(result) == 1
        assert result[0]["loc"] == []
        assert result[0]["type"] == "tuple_type"

async def test_view(aiohttp_client: AiohttpClient) -> None:
    schema_gen = SchemaGenerator()

    @schema_gen.api_view()
    class PollView(web.View):
        """PollView class."""

        async def get(self) -> APIResponse[Poll, Literal[200]] | APIResponse[None, Literal[404]]:
            """Fetch poll."""

            poll_id = int(self.request.match_info["id"])
            if poll_id == 1:
                return APIResponse(POLL1)
            return APIResponse[None, Literal[404]](None, status=404)

        async def put(self, body: NewPoll) -> APIResponse[Poll]:
            return APIResponse({"id": 2, "question": body["question"],
                                "pub_date": "2024-07-29"})

    app = web.Application()
    schema_gen.setup(app)
    app.router.add_view("/poll/{id:\\d+}", PollView)

    client = await aiohttp_client(app)
    async with client.get("/schema") as resp:
        assert resp.ok
        schema = await resp.json()

    new_poll_schema = {
        "description": "Details to create a new poll.",
        "properties": {
            "choices": {"items": {"type": "string"}, "minItems": 2, "title": "Choices",
                        "type": "array"},
            "question": {"title": "Question", "type": "string"}},
        "required": ["question", "choices"],
        "title": "NewPoll",
        "type": "object"}
    paths = {"/poll/{id}": {
        "summary": "PollView class.",
        "get": {"operationId": "PollView",
                "summary": "Fetch poll.",
                "responses": {
                    "200": {
                        "content": {"application/json": {"schema": {
                            "$ref": "#/components/schemas/Poll"}}},
                        "description": "OK"},
                    "404": {
                        "content": {"application/json": {"schema": {"type": "null"}}},
                        "description": "Not Found"}}},
        "put": {"operationId": "PollView",
                "requestBody": {"content": {"application/json": {"schema": {
                    "contentMediaType": "application/json",
                    "contentSchema": {"$ref": "#/components/schemas/NewPoll"},
                    "type": "string"}}}},
                "responses": {"200": {
                    "content": {"application/json": {
                        "schema": {"$ref": "#/components/schemas/Poll"}}},
                    "description": "OK"}}}}}
    assert "Poll" in schema["components"]["schemas"]
    assert schema["components"]["schemas"]["NewPoll"] == new_poll_schema
    assert schema["paths"] == paths

    async with client.get("/poll/1") as resp:
        assert resp.status == 200
        result = await resp.json()
        assert result == POLL1

    async with client.get("/poll/2") as resp:
        assert resp.status == 404
        result = await resp.json()
        assert result is None

    r = {"question": "spam?", "choices": ("foo", "bar")}
    async with client.put("/poll/2", json=r) as resp:
        assert resp.status == 200
        result = await resp.json()
        assert result == {"id": 2, "question": "spam?", "pub_date": "2024-07-29"}

    r = {"question": "spam?", "choices": ("foo",)}
    async with client.put("/poll/2", json=r) as resp:
        assert resp.status == 400
        result = await resp.json()
        assert len(result) == 1
        assert result[0]["loc"] == ["choices"]
        assert result[0]["type"] == "too_short"


async def test_tags(aiohttp_client: AiohttpClient) -> None:
    schema_gen = SchemaGenerator()

    tags = ("a_tag", "b_tag")

    @schema_gen.api(tags=tags)
    async def get_number(
        request: web.Request,
    ) -> APIResponse[tuple[Poll, ...], Literal[200]]:
        """Number."""
        return APIResponse((POLL1,))  # pragma: no cover

    app = web.Application()
    schema_gen.setup(app)
    app.router.add_get("/number", get_number)

    client = await aiohttp_client(app)
    async with client.get("/schema") as resp:
        assert resp.ok
        schema = await resp.json()

    assert schema["paths"]["/number"]["get"]["tags"] == ["a_tag", "b_tag"]

@pytest.mark.skipif(sys.version_info < (3, 11), reason="Pydantic fails with typing_extensions")
async def test_query(aiohttp_client: AiohttpClient) -> None:
    schema_gen = SchemaGenerator()

    class Baz(TypedDict):
        foo: Literal["spam", "eggs"]

    class QueryArgs(TypedDict):
        foo: int
        bar: NotRequired[tuple[str, int, float]]
        baz: Baz
        spam: NotRequired[Literal["eggz"]]

    @schema_gen.api()
    async def handler(request: web.Request, *, query: QueryArgs) -> APIResponse[int]:
        assert isinstance(query["foo"], int)
        assert query["bar"] == ("spam", 42, 1.414)
        assert query["baz"]["foo"] == "eggs"
        assert query["spam"] == "eggz"
        return APIResponse(query["foo"])

    app = web.Application()
    schema_gen.setup(app)
    app.router.add_get("/foo", handler)

    client = await aiohttp_client(app)
    async with client.get("/schema") as resp:
        assert resp.ok
        schema = await resp.json()

    bar = {"maxItems": 3, "minItems": 3, "type": "array",
           "prefixItems": [{"type": "string"}, {"type": "integer"}, {"type": "number"}]}
    paths = {"/foo": {"get": {
        "operationId": "handler",
        "parameters": [{"name": "foo", "in": "query", "required": True, "schema": {
                            "contentMediaType": "application/json",
                            "contentSchema": {"type": "integer"}, "type": "string"}},
                       {"name": "bar", "in": "query", "required": False, "schema": {
                            "contentMediaType": "application/json",
                            "contentSchema": bar, "type": "string"}},
                       {"name": "baz", "in": "query", "required": True, "schema": {
                            "contentMediaType": "application/json",
                            "contentSchema": {"$ref": "#/components/schemas/Baz"},
                            "type": "string"}},
                       {"name": "spam", "in": "query", "required": False, "schema": {
                            "type": "string", "const": "eggz"}}],
        "responses": {
            "200": {
                "content": {"application/json": {"schema": {"type": "integer"}}},
                "description": "OK"}}}}}
    assert schema["paths"] == paths
    baz = {"properties": {"foo": {"title": "Foo", "type": "string", "enum": ["spam", "eggs"]}},
           "required": ["foo"], "title": "Baz", "type": "object"}
    assert schema["components"]["schemas"]["Baz"] == baz

    params = {"foo": "12", "bar": json.dumps(("spam", 42, 1.414)),
              "baz": json.dumps({"foo": "eggs"}), "spam": "eggz"}
    async with client.get("/foo", params=params) as resp:
        assert resp.status == 200
        result = await resp.json()
        assert result == 12

    params = {"foo": "abc", "bar": json.dumps((42, 42, 1.414)),
              "baz": json.dumps({"foo": "eggs"})}
    async with client.get("/foo", params=params) as resp:
        assert resp.status == 400
        result = await resp.json()
        assert len(result) == 2
        assert result[0]["loc"] == ["foo"]
        assert result[0]["type"] == "json_invalid"
        assert result[1]["loc"] == ["bar", 0]
        assert result[1]["type"] == "string_type"

async def test_extra_args(aiohttp_client: AiohttpClient) -> None:
    schema_gen = SchemaGenerator()

    @schema_gen.api()  # type: ignore[arg-type]  # <- Do not remove ignore
    async def foo(request: web.Request, *, foo: int) -> APIResponse[int]:
        """Test static typing error occurs in mypy."""
        assert False
