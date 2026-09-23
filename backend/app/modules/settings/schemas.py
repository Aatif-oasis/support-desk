from pydantic import BaseModel, Field


class BusinessHoursDay(BaseModel):
    open: str | None = None  # "09:00", null = closed
    close: str | None = None


class SettingsUpdateRequest(BaseModel):
    """
    All optional, merge semantics — updating theme doesn't wipe
    business_hours. Matches the "Theme customization" / "Business hours" /
    "Widget customization" admin features from the original spec.
    """
    business_hours: dict[str, BusinessHoursDay] | None = None
    theme_primary_color: str | None = Field(default=None, pattern="^#[0-9A-Fa-f]{6}$")
    theme_logo_url: str | None = None
    widget_greeting_message: str | None = None


class SettingsResponse(BaseModel):
    business_hours: dict = Field(default_factory=dict)
    theme_primary_color: str | None = None
    theme_logo_url: str | None = None
    widget_greeting_message: str | None = None
