from pydantic import BaseModel, Field

from grimwaves_api.core.settings import settings


class TextRequest(BaseModel):
    text: str
    style: str = Field(default="gothic", pattern=f"^({'|'.join(settings.available_styles)})$")
