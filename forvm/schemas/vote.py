from typing import Literal

from pydantic import BaseModel


class VoteCreate(BaseModel):
    value: Literal[-1, 1]


class VoteResult(BaseModel):
    upvotes: int
    downvotes: int
