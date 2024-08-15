aiohttp-apischema
=================
.. image:: https://github.com/aio-libs/aiohttp-apischema/workflows/CI/badge.svg
    :target: https://github.com/aio-libs/aiohttp-apischema/actions?query=workflow%3ACI
.. image:: https://codecov.io/gh/aio-libs/aiohttp-apischema/branch/master/graph/badge.svg
    :target: https://codecov.io/gh/aio-libs/aiohttp-apischema
.. image:: https://img.shields.io/pypi/v/aiohttp-apischema.svg
    :target: https://pypi.python.org/pypi/aiohttp-apischema
.. image:: https://readthedocs.org/projects/aiohttp-apischema/badge/?version=latest
    :target: http://aiohttp-apischema.readthedocs.io/en/latest/?badge=latest


API schema generation and input validation for `aiohttp.web`__.


.. _aiohttp_web: https://aiohttp.readthedocs.io/en/latest/web.html

__ aiohttp_web_

Installation
------------
Install from PyPI::

    pip install aiohttp-apischema


Developing
----------

Install requirement and launch tests::

    pip install -r requirements-dev.txt
    pytest


Basic usage
-----------

First create a *SchemaGenerator* instance:

.. code-block:: python

    from aiohttp_apischema import SchemaGenerator
    SCHEMA = SchemaGenerator()

Then decorate endpoint handlers which should be included in the schema:

.. code-block:: python

    from aiohttp_apischema import APIResponse

    @SCHEMA.api()
    async def foo(request: web.Request) -> APIResponse[list[str], Literal[200]]:
        return APIResponse(["foo"])

Or for `Class Based Views <https://aiohttp.readthedocs.io/en/stable/web_quickstart.html#class-based-views>`__:

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

    async def handler(request: web.Request, body: dict[int, str]) -> APIResponse[int, Literal[200]]:
        # body has been validated, so we can be sure the keys are int now.
        return APIResponse(sum(body.keys()))


License
-------

``aiohttp_apischema`` is offered under the Apache 2 license.
