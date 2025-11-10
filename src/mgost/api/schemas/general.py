from datetime import datetime

from pydantic import BaseModel


class TokenInfo(BaseModel):
    name: str
    owner: str
    created: datetime
    modified: datetime
    expires: datetime | None = None
    accessed: datetime | None = None
