from pydantic import BaseModel


class Config(BaseModel):
    dc_api_key: str | None = None
    dc_base_url: str | None = None
    dc_github_token: str | None = None
    dc_ai_model_name: str = "gpt-4o-mini"
    dc_default_dragon_number: int = 32
    dc_signup_before_seconds: int = 30 * 24 * 3600
    dc_signup_end_before_seconds: int = 10 * 60
    dc_image_is_dark: bool = False
    dc_battle_interval: int = 10
