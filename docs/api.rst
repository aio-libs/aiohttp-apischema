API
===

Describes the module API with detailed explanations of functions parameters.

.. module:: aiohttp_apischema
.. highlight:: python


SchemaGenerator
---------------


.. class:: SchemaGenerator(info=None)

   SchemaGenerator handles the automatic creation of the schema and modifying the
   app as needed.

   First, the :meth:`SchemaGenerator.api` and :meth:`SchemaGenerator.api_view`
   decorators should be applied to any handlers which should be documented.

   Second, the :meth:`SchemaGenerator.setup` method should be called to configure
   the :class:`aiohttp.web.Application` object.

   Then, on application startup, the SchemaGenerator will finish generating the schema
   with the finalised route information.

   :param info: dict-like object that overrides the OpenAPI schema's info object.
                The ``title`` and ``version`` keys are required.

                By default the value is ``{"title": "API", "version": "1.0"}``


   .. method:: api(tags=())

      Use as a decorator to register a handler function to be part of the API schema.

      The handler function must have an :class:`APIResponse` annotation as the return
      type and therefore return an instance of this class.

      The handler function may have an additional positional parameter (after the
      ``request`` parameter) whose type annotation defines the ``requestBody`` type
      in the schema. When the handler is executed, the request body will be read and
      validated against that type.

      The handler function can define a `query` keyword-only parameter whose type
      annotation must be a form of :class:`typing.TypedDict`. When the handler is
      executed, the query parameters will be validated against that type.

      :param tags: Sequence of strings used to specify tags to group endpoints.

   .. method:: api_view(tags=())

      Use as a decorator to register a :class:`aiohttp.web.View` class to be part of
      the API schema. This will register each endpoint method defined in the class.

      See :meth:`SchemaGenerator.api` for more information.

   .. method:: setup(app)

      Setup the provided :class:`aiohttp.web.Application` for schema generation.
      This will register an :attr:`aiohttp.web.Application.on_startup` function to
      finalise schema generation.

      It also registers a ``/schema`` endpoint for serving the schema as JSON and a
      ``/swagger/`` endpoint for viewing that schema in a Swagger interface.


APIResponse
---------------


.. class:: APIResponse(body, *, status=200, reason=None, headers=None, charset=None \
                       zlib_executor_size=None, zlib_executor=None)

   APIResponse is a subclass of :class:`aiohttp.web.Response` with additional typing
   information.

   The class uses :class:`typing.Generic` to define the expected output of an API
   response. The first parameter is used to define the response body type::

       APIResponse[int]

   The second parameter can be used to define the status code of a response::

       APIResponse[int, Literal[201]]

   :param body: This should be a JSONable object of the same type as the first generic
                parameter. APIResponse will then use :func:`json.dumps` to encode
                the object and return a JSON response, behaving similar to
                :func:`aiohttp.web.json_response`.

   All other parameters are passed through to :class:`aiohttp.web.Response`.

   Note that mypy, at time of writing, will not infer the :class:`typing.Literal`
   when creating an instance. To work around these type errors, the generic parameters
   must be duplicated::

       return APIResponse[int, Literal[201]](42, status=201)

   This is not needed when using the default for a 200 response::

       return APIResponse(42)
