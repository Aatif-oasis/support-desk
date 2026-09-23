import uuid

from pydantic import BaseModel


class AttachmentResponse(BaseModel):
    id: uuid.UUID
    message_id: uuid.UUID
    original_filename: str
    content_type: str
    size_bytes: int

    model_config = {"from_attributes": True}
