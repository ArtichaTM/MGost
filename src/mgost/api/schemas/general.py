from datetime import datetime

from pydantic import BaseModel


class TokenInfo(BaseModel):
    owner: str
    created: datetime
    modified: datetime
    expires: datetime | None = None
