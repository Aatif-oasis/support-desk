from app.modules.quick_replies.models import QuickReply
from app.shared.base_repository import BaseRepository


class QuickReplyRepository(BaseRepository[QuickReply]):
    model = QuickReply
