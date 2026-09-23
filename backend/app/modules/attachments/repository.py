from app.modules.attachments.models import Attachment
from app.shared.base_repository import BaseRepository


class AttachmentRepository(BaseRepository[Attachment]):
    model = Attachment
