from fastapi import APIRouter, Depends, HTTPException, status, Request, Response
from sqlalchemy.orm import Session
from app.database import get_db
from app.models import User, BuildingAssignment, Building
from app.schemas import UserLogin, Token, UserResponse
from app.auth import verify_password, create_access_token, get_current_user, record_audit_event

router = APIRouter(prefix="/api/auth", tags=["Authentication"])

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

