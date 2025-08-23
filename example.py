from datetime import datetime
from typing import Annotated, Literal

from aiohttp import web
from aiohttp_apischema import APIResponse, SchemaGenerator
from pydantic import Field


from typing_extensions import TypedDict

class Choice(TypedDict):
    """An answer to a poll."""

    choice: str
    votes: int


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
CHOICES1: tuple[Choice, ...] = ({"choice": "Not much", "votes": 0},
                                {"choice": "The sky", "votes": 5},
                                {"choice": "Just hacking again", "votes": 2})


SCHEMA = SchemaGenerator()
NotFound = APIResponse[None, Literal[404]]

POLLS = {1: POLL1}
CHOICES = {1: list(CHOICES1)}


@SCHEMA.api()
async def list_polls(request: web.Request) -> APIResponse[tuple[Poll, ...], Literal[200]]:
    """List available polls.

    Return a list of objects containing details about each poll.
    """
    return APIResponse((POLL1,))


@SCHEMA.api()
async def add_choice(request: web.Request, message: str) -> APIResponse[int, Literal[201]] | NotFound:
    """Edit a choice.

    Return the ID of the new choice.
    """
    poll_id = int(request.match_info["id"])
    choices = CHOICES.get(poll_id)
    if choices:
        choices.append({"choice": message, "votes": 0})
        return APIResponse[int, Literal[201]](len(choices) - 1, status=201)
    return APIResponse[None, Literal[404]](None, status=404)


class GetQuery(TypedDict):
    """Define our query arguments for the get endpoint."""
    results: Annotated[bool, Field(default=True)]


class GetPollResult(Poll, total=False):
    results: list[Choice]


@SCHEMA.api_view()
class PollView(web.View):
    """Endpoints for individual polls."""

    async def get(self, *, query: GetQuery) -> APIResponse[GetPollResult, Literal[200]] | NotFound:
        """Fetch a poll by ID."""
        poll_id = int(self.request.match_info["id"])
        poll = POLLS.get(poll_id)
        if poll:
            poll_result: GetPollResult = poll.copy()  # type: ignore[assignment]
            if query["results"]:
                poll_result["results"] = CHOICES[poll_id]
            return APIResponse(poll_result)
        return APIResponse[None, Literal[404]](None, status=404)

    async def put(self, body: NewPoll) -> APIResponse[int]:
        """Set value for poll.

        Return ID for newly created poll.
        """
        poll_id = max(POLLS.keys()) + 1
        POLLS[poll_id] = {"id": poll_id, "question": body["question"], "pub_date": datetime.now().isoformat()}
        CHOICES[poll_id] = [{"choice": c, "votes": 0} for c in body["choices"]]
        return APIResponse(poll_id)


def init_app() -> web.Application:
    app = web.Application()
    app.router.add_get("/polls", list_polls)
    app.router.add_view(r"/poll/{id:\d+}", PollView)
    app.router.add_put(r"/poll/{id:\d+}/choice", add_choice)

    SCHEMA.setup(app)

    return app


if __name__ == "__main__":
    web.run_app(init_app())
