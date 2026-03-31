from pydantic import BaseModel


class Config(BaseModel):
    dc_github_token: str | None = None
    dc_default_dragon_number: int = 32
    dc_signup_before_seconds: int = 30 * 24 * 3600
    dc_signup_end_before_seconds: int = 10 * 60
    dc_image_is_dark: bool = False
