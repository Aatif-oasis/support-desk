from app.modules.departments.models import Department
from app.shared.base_repository import BaseRepository


class DepartmentRepository(BaseRepository[Department]):
    model = Department
