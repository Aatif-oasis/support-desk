import uuid

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.rate_limit import identify_rate_limit
from app.modules.auth.dependencies import CurrentUser, require_roles
from app.modules.customers.schemas import (
    CustomerResponse,
    CustomerUpdateRequest,
    IdentifyRequest,
    IdentifyResponse,
    NoteAddRequest,
)
from app.modules.customers.service import CustomerService

# Deliberately separate from /api/v1/customers: this is the ONLY router in
# the app meant to be called directly from a customer's browser with no
# authentication at all. Rate limiting and origin/domain allowlisting
# belong here too, but that's a hardening-pass concern (see roadmap) —
# tracked, not yet implemented.
public_router = APIRouter(prefix="/api/v1/public/{org_slug}/customers", tags=["Public — Widget"])

router = APIRouter(prefix="/api/v1/customers", tags=["Customers"])


@public_router.post("/identify", response_model=IdentifyResponse, dependencies=[Depends(identify_rate_limit)])
async def identify_customer(
    org_slug: str, request: IdentifyRequest, db: AsyncSession = Depends(get_db)
) -> IdentifyResponse:
    organization_id = await CustomerService.resolve_organization_id(db, org_slug)
    customer = await CustomerService(db, organization_id).identify(request)
    return IdentifyResponse.model_validate(customer)


@router.get("", response_model=list[CustomerResponse])
async def list_customers(
    limit: int = Query(default=50, le=200),
    offset: int = Query(default=0, ge=0),
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser = Depends(require_roles("org_admin", "team_manager", "agent")),
) -> list[CustomerResponse]:
    customers = await CustomerService(db, current_user.organization_id).list_customers(
        limit, offset
    )
    return [CustomerResponse.model_validate(c) for c in customers]


@router.get("/{customer_id}", response_model=CustomerResponse)
async def get_customer(
    customer_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser = Depends(require_roles("org_admin", "team_manager", "agent")),
) -> CustomerResponse:
    customer = await CustomerService(db, current_user.organization_id).get_customer(customer_id)
    return CustomerResponse.model_validate(customer)


@router.patch("/{customer_id}", response_model=CustomerResponse)
async def update_customer(
    customer_id: uuid.UUID,
    request: CustomerUpdateRequest,
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser = Depends(require_roles("org_admin", "team_manager", "agent")),
) -> CustomerResponse:
    customer = await CustomerService(db, current_user.organization_id).update_customer(
        customer_id, request
    )
    return CustomerResponse.model_validate(customer)


@router.post("/{customer_id}/notes", response_model=CustomerResponse)
async def add_note(
    customer_id: uuid.UUID,
    request: NoteAddRequest,
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser = Depends(require_roles("org_admin", "team_manager", "agent")),
) -> CustomerResponse:
    customer = await CustomerService(db, current_user.organization_id).add_note(
        customer_id, request.text, current_user.id
    )
    return CustomerResponse.model_validate(customer)
