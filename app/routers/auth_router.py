import os
import secrets
from typing import Literal
from fastapi import APIRouter, Depends, HTTPException, status, Request, Response
from pydantic import BaseModel, Field, model_validator
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session
from app.config import PERSISTENT_DATABASE
from app.database import get_db
from app.models import User, BuildingAssignment, Building, AuditEvent
from app.schemas import UserLogin, Token
from app.auth import (
    verify_password, create_access_token, get_current_user, require_role,
    record_audit_event, hash_password
)

router = APIRouter(prefix="/api/auth", tags=["Authentication"])


class UserProvisionRequest(BaseModel):
    username: str = Field(min_length=3, max_length=50, pattern=r"^[A-Za-z0-9._-]+$")
    email: str = Field(min_length=6, max_length=100, pattern=r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
    full_name: str = Field(min_length=1, max_length=100)
    role: Literal["ELECTRICIAN", "MANAGEMENT"]
    assign_all_buildings: bool = False
    building_codes: list[str] = Field(default_factory=list)

    @model_validator(mode="after")
    def validate_building_assignments(self):
        if not self.full_name.strip():
            raise ValueError("Full name cannot be blank.")
        if self.role == "ELECTRICIAN":
            if not self.assign_all_buildings and not self.building_codes:
                raise ValueError("Electricians must be assigned at least one building.")
            if self.assign_all_buildings and self.building_codes:
                raise ValueError("Specify all buildings or building codes, not both.")
        elif self.assign_all_buildings or self.building_codes:
            raise ValueError("Building assignments are only valid for electricians.")
        return self


@router.post("/login", response_model=Token)
def login(login_data: UserLogin, request: Request, response: Response, db: Session = Depends(get_db)):
    user = db.query(User).filter(User.username == login_data.username).first()
    if not user or not verify_password(login_data.password, user.hashed_password):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect username or password."
        )
    if not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="User account is deactivated. Contact campus system administrator."
        )

    access_token = create_access_token(
        data={"sub": user.username, "role": user.role, "user_id": user.id}
    )

    # Set secure HTTP-only cookie for browser navigation
    response.set_cookie(
        key="dss_token",
        value=access_token,
        httponly=False,  # Accessible for JS client
        samesite="lax",
        max_age=60 * 60 * 12
    )

    # Record login audit event
    record_audit_event(
        db=db,
        user_id=user.id,
        role=user.role,
        event_type="LOGIN",
        entity_type="USER",
        entity_id=str(user.id),
        action_details={"username": user.username, "role": user.role},
        ip_address=request.client.host if request.client else "127.0.0.1"
    )
    return {
        "access_token": access_token,
        "token_type": "bearer",
        "role": user.role,
        "username": user.username,
        "full_name": user.full_name,
        "user_id": user.id
    }


@router.post("/users", status_code=status.HTTP_201_CREATED)
def provision_user(
    request_data: UserProvisionRequest,
    request: Request,
    current_user: User = Depends(require_role(["ADMIN"])),
    db: Session = Depends(get_db)
):
    if os.getenv("VERCEL") and not PERSISTENT_DATABASE:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Configure a persistent PostgreSQL DATABASE_URL before creating production accounts."
        )

    username = request_data.username.strip()
    email = str(request_data.email).strip().lower()
    if db.query(User).filter(User.username == username).first():
        raise HTTPException(status_code=409, detail="Username is already in use.")
    if db.query(User).filter(User.email == email).first():
        raise HTTPException(status_code=409, detail="Email is already in use.")

    if request_data.role == "ELECTRICIAN":
        if request_data.assign_all_buildings:
            buildings = db.query(Building).order_by(Building.id).all()
        else:
            codes = list(dict.fromkeys(code.strip() for code in request_data.building_codes))
            buildings = db.query(Building).filter(Building.code.in_(codes)).all()
            found_codes = {building.code for building in buildings}
            missing_codes = sorted(set(codes) - found_codes)
            if missing_codes:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=f"Unknown building codes: {', '.join(missing_codes)}"
                )
        if not buildings:
            raise HTTPException(status_code=400, detail="No buildings are available to assign.")
    else:
        buildings = []

    initial_password = secrets.token_urlsafe(24)
    user = User(
        username=username,
        email=email,
        full_name=request_data.full_name.strip(),
        role=request_data.role,
        hashed_password=hash_password(initial_password),
        is_active=True
    )
    user.assignments = [BuildingAssignment(building=building) for building in buildings]
    db.add(user)
    try:
        db.flush()
        db.add(AuditEvent(
            user_id=current_user.id,
            role=current_user.role,
            event_type="USER_CREATED",
            entity_type="USER",
            entity_id=str(user.id),
            action_details={
                "username": user.username,
                "email": user.email,
                "role": user.role,
                "assigned_building_codes": [building.code for building in buildings]
            },
            ip_address=request.client.host if request.client else "127.0.0.1",
            is_immutable=True
        ))
        db.commit()
        db.refresh(user)
    except IntegrityError:
        db.rollback()
        raise HTTPException(status_code=409, detail="Username or email is already in use.")

    return {
        "id": user.id,
        "username": user.username,
        "email": user.email,
        "full_name": user.full_name,
        "role": user.role,
        "assigned_buildings": [
            {"id": building.id, "name": building.name, "code": building.code}
            for building in buildings
        ],
        "initial_password": initial_password,
        "password_note": "This password is shown only in this response. Copy it securely and share it directly with the new user."
    }


@router.get("/me")
def get_me(current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    assigned_buildings = []
    if current_user.role == "ELECTRICIAN":
        assignments = db.query(BuildingAssignment).filter(BuildingAssignment.user_id == current_user.id).all()
        b_ids = [a.building_id for a in assignments]
        buildings = db.query(Building).filter(Building.id.in_(b_ids)).all()
        assigned_buildings = [{"id": b.id, "name": b.name, "code": b.code} for b in buildings]
    else:
        # Management / Admin can access all buildings
        buildings = db.query(Building).all()
        assigned_buildings = [{"id": b.id, "name": b.name, "code": b.code} for b in buildings]

    return {
        "id": current_user.id,
        "username": current_user.username,
        "email": current_user.email,
        "full_name": current_user.full_name,
        "role": current_user.role,
        "assigned_buildings": assigned_buildings
    }

@router.post("/logout")
def logout(request: Request, response: Response, current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    response.delete_cookie("dss_token")
    record_audit_event(
        db=db,
        user_id=current_user.id,
        role=current_user.role,
        event_type="LOGOUT",
        entity_type="USER",
        entity_id=str(current_user.id),
        action_details={"username": current_user.username},
        ip_address=request.client.host if request.client else "127.0.0.1"
    )
    return {"message": "Successfully logged out."}
