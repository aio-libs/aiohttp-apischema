import json
import sys
from concurrent.futures import Executor
from typing import Generic, Literal, overload

from aiohttp import web
from aiohttp.typedefs import LooseHeaders

if sys.version_info >= (3, 13):
    from typing import TypeVar
else:
    from typing_extensions import TypeVar

_T = TypeVar("_T")
_Status = TypeVar("_Status", bound=int, default=Literal[200])


class APIResponse(web.Response, Generic[_T, _Status]):
    @overload
    def __init__(self, body: _T, *, reason: str | None = None,
                 headers: LooseHeaders | None = None, charset: str | None = None,
                 zlib_executor_size: int | None = None,
                 zlib_executor: Executor | None = None):
        ...
    @overload
    def __init__(self, body: _T, *, status: _Status, reason: str | None = None,
                 headers: LooseHeaders | None = None, charset: str | None = None,
                 zlib_executor_size: int | None = None,
                 zlib_executor: Executor | None = None):
        ...
    def __init__(self, body: _T, *, status: int = 200, reason: str | None = None,
                 headers: LooseHeaders | None = None, charset: str | None = None,
                 zlib_executor_size: int | None = None,
                 zlib_executor: Executor | None = None):
        super().__init__(text=json.dumps(body), content_type="application/json",
                         status=status, reason=reason, headers=headers, charset=charset,
                         zlib_executor_size=zlib_executor_size, zlib_executor=zlib_executor)
