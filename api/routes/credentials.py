"""
Exchange Credentials Routes.

CRUD operations for exchange API credentials.
"""

from datetime import datetime
from typing import Literal
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from api.core.database import get_db
from api.core.dependencies import get_current_user
from api.models.orm import User
from api.services.credential_service import (
    CredentialService,
    CredentialValidationError,
)

router = APIRouter()


# =============================================================================
# Schemas
# =============================================================================


class CredentialCreate(BaseModel):
    """Credential creation request."""

    exchange: Literal["binance", "mexc", "bybit"]
    api_key: str = Field(..., min_length=1)
    api_secret: str = Field(..., min_length=1)
    is_testnet: bool = False


class CredentialPermissions(BaseModel):
    """Credential permissions info."""

    trade: bool
    withdraw: bool
    is_safe: bool  # True if withdraw is disabled


class CredentialResponse(BaseModel):
    """Credential response (without secrets)."""

    id: UUID
    exchange: str
    is_testnet: bool
    permissions: CredentialPermissions
    created_at: datetime
    updated_at: datetime

    class Config:
        """Pydantic config."""

        from_attributes = True


class CredentialCreateResponse(BaseModel):
    """Response after creating credential."""

    credential: CredentialResponse
    warnings: list[str] = []


class CredentialListResponse(BaseModel):
    """Credential list with pagination."""

    credentials: list[CredentialResponse]
    total: int
    limit: int
    offset: int


class MarketsResponse(BaseModel):
    """Markets list response."""

    exchange: str
    markets: list[str]
    count: int


# =============================================================================
# Endpoints
# =============================================================================


@router.post(
    "/",
    response_model=CredentialCreateResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Add exchange credentials",
    responses={
        201: {"description": "Credentials validated and saved"},
        400: {"description": "Invalid credentials or missing trade permission"},
        409: {"description": "Credential for this exchange already exists"},
    },
)
async def create_credential(
    credential: CredentialCreate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> CredentialCreateResponse:
    """
    Add new exchange API credentials.

    - Validates credentials with the exchange
    - Requires trade permission enabled
    - Encrypts API key and secret before storage
    - Warns if withdraw permission is enabled
    """
    credential_service = CredentialService(db)

    try:
        new_credential, validation = await credential_service.create(
            user_id=current_user.id,
            exchange=credential.exchange,
            api_key=credential.api_key,
            api_secret=credential.api_secret,
            is_testnet=credential.is_testnet,
        )
    except CredentialValidationError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e),
        )

    # Build response
    warnings = []
    if validation.can_withdraw:
        warnings.append(
            "WARNING: This API key has withdraw permission enabled. "
            "For security, we recommend creating a new key without withdraw access."
        )

    permissions = CredentialPermissions(
        trade=new_credential.permissions.get("trade", False),
        withdraw=new_credential.permissions.get("withdraw", False),
        is_safe=new_credential.permissions.get("is_safe", True),
    )

    return CredentialCreateResponse(
        credential=CredentialResponse(
            id=new_credential.id,
            exchange=new_credential.exchange,
            is_testnet=new_credential.is_testnet,
            permissions=permissions,
            created_at=new_credential.created_at,
            updated_at=new_credential.updated_at,
        ),
        warnings=warnings,
    )


@router.get(
    "/",
    response_model=CredentialListResponse,
    summary="List credentials",
)
async def list_credentials(
    limit: int = Query(default=50, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> CredentialListResponse:
    """List all exchange credentials for the authenticated user."""
    credential_service = CredentialService(db)

    credentials, total = await credential_service.list_by_user(
        current_user.id, limit=limit, offset=offset
    )

    responses = []
    for cred in credentials:
        permissions = CredentialPermissions(
            trade=cred.permissions.get("trade", False),
            withdraw=cred.permissions.get("withdraw", False),
            is_safe=cred.permissions.get("is_safe", True),
        )
        responses.append(
            CredentialResponse(
                id=cred.id,
                exchange=cred.exchange,
                is_testnet=cred.is_testnet,
                permissions=permissions,
                created_at=cred.created_at,
                updated_at=cred.updated_at,
            )
        )

    return CredentialListResponse(
        credentials=responses,
        total=total,
        limit=limit,
        offset=offset,
    )


@router.get(
    "/{credential_id}",
    response_model=CredentialResponse,
    summary="Get credential details",
)
async def get_credential(
    credential_id: UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> CredentialResponse:
    """Get credential details by ID."""
    credential_service = CredentialService(db)

    credential = await credential_service.get_by_id_for_user(
        credential_id, current_user.id
    )

    if credential is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Credential not found",
        )

    permissions = CredentialPermissions(
        trade=credential.permissions.get("trade", False),
        withdraw=credential.permissions.get("withdraw", False),
        is_safe=credential.permissions.get("is_safe", True),
    )

    return CredentialResponse(
        id=credential.id,
        exchange=credential.exchange,
        is_testnet=credential.is_testnet,
        permissions=permissions,
        created_at=credential.created_at,
        updated_at=credential.updated_at,
    )


@router.delete(
    "/{credential_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Delete credential",
)
async def delete_credential(
    credential_id: UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> None:
    """Delete an exchange credential."""
    credential_service = CredentialService(db)

    deleted = await credential_service.delete(credential_id, current_user.id)

    if not deleted:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Credential not found",
        )


@router.post(
    "/{credential_id}/refresh-markets",
    response_model=MarketsResponse,
    summary="Refresh available markets",
)
async def refresh_markets(
    credential_id: UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> MarketsResponse:
    """
    Refresh and return available markets from the exchange.

    Connects to the exchange and fetches the current list of trading pairs.
    """
    credential_service = CredentialService(db)

    credential = await credential_service.get_by_id_for_user(
        credential_id, current_user.id
    )

    if credential is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Credential not found",
        )

    try:
        markets = await credential_service.refresh_markets(
            credential_id, current_user.id
        )
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"Failed to connect to exchange: {str(e)}",
        )

    return MarketsResponse(
        exchange=credential.exchange,
        markets=markets,
        count=len(markets),
    )
