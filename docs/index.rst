aiohttp-apischema
=================

.. currentmodule:: aiohttp_apischema
.. highlight:: python

API schema generation and input validation for aiohttp.



Basic usage
-----------

First create a :class:`aiohttp_apischema.SchemaGenerator` instance:

.. code-block:: python

    from aiohttp_apischema import SchemaGenerator
    SCHEMA = SchemaGenerator()

Then decorate endpoint handlers with :meth:`aiohttp_schema.SchemaGenerator.api`
which should be included in the schema and use :class:`aiohttp_schema.APIResponse` for
the return type:

.. code-block:: python

    from aiohttp_apischema import APIResponse

    @SCHEMA.api()
    async def foo(request: web.Request) -> APIResponse[list[str], Literal[200]]:
        return APIResponse(["foo"])

Or for :ref:`Class Based Views <aiohttp:aiohttp-web-class-based-views>`
the :meth:`aiohttp_apischema.SchemaGenerator.api_view` decorator can be used:

.. code-block:: python

    @SCHEMA.api_view()
    class Handler(web.View):
        async def get(self) -> APIResponse[int, Literal[200]] | APIResponse[None, Literal[404]]:
            bar_id = int(self.request.match_info["id"])
            if bar_id == 1:
                return APIResponse(42)
            return APIResponse[None, Literal[404]](None, status=404)

Then call the setup method when building your app:

.. code-block:: python

    app = web.Application()
    app.router.add_get("/foo", foo)
    app.router.add_view(r"/bar/{id:\d+}", Handler)
    SCHEMA.setup(app)


You can now view the docs under the */swagger/* path.

Validation usage
----------------

Validation of the request body is achieved by adding a positional parameter:

.. code-block:: python

    async def handler(request: web.Request, body: dict[int, str]) -> APIResponse[int]:
        # body has been validated, so we can be sure the keys are int now.
        return APIResponse(sum(body.keys()))

This will include the information in the schema's requestBody, plus it will validate
the input from the user. If validation fails it will return a 400 response with
information about what was incorrect.

Keyword-only parameters can be defined for ``query`` arguments:

.. code-block:: python

    class QueryArgs(TypedDict, total=False):
        sort: Literal["asc", "desc"]

    async def handler(request: web.Request, *, query: QueryArgs) -> APIResponse[int]:
        return sorted(results, reverse=query.get("sort", "asc") == "desc")

Pydantic options
----------------

You can add custom Pydantic options using :class:`typing.Annotated`:

.. code-block:: python

    class QueryArgs(TypedDict):
        sort: Annotated[Literal["asc", "desc"], pydantic.Field(default="asc")]

    async def handler(request: web.Request, *, query: QueryArgs) -> APIResponse[int]:
        return sorted(results, reverse=query["sort"] == "desc")

Customising schema generation
-----------------------------

Summary and description
+++++++++++++++++++++++

You can use docstrings to customise the summary and description shown in the schema:

.. code-block:: python

    async def handler(request: web.Request) -> APIResponse[int, Literal[200]]:
        """This will appear as the summary.

        This is a
        longer
        description.
        """

Tags
++++

Tags can be added to group endpoints using the ``tags`` parameter in the decorators
(see :meth:`aiohttp_schema.SchemaGenerator.api`).

Library Installation
--------------------

The :mod:`aiohttp_apischema` library can be installed with pip:

.. code-block:: sh

   $ pip install aiohttp-apischema

Source code
-----------

The project is hosted on `GitHub <https://github.com/aio-libs/aiohttp_apischema>`_.

Please feel free to file an issue on `bug tracker
<https://github.com/aio-libs/aiohttp_apischema/issues>`_ if you have found a bug
or have some suggestion for library improvements.


License
-------

:mod:`aiohttp_apischema` is offered under the Apache 2 license.

Contents
--------

.. toctree::
   :maxdepth: 2

   api


Indices and tables
------------------

* :ref:`genindex`
* :ref:`search`
