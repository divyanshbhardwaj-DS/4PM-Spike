import datetime
from typing import Optional, List
import bcrypt
from jose import JWTError, jwt
from fastapi import Depends, HTTPException, status, Request
from fastapi.security import OAuth2PasswordBearer
from sqlalchemy.orm import Session

from app.config import SECRET_KEY, ALGORITHM, ACCESS_TOKEN_EXPIRE_MINUTES
from app.database import get_db
from app.models import User, AuditEvent, BuildingAssignment

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/auth/login", auto_error=False)

def hash_password(password: str) -> str:
    pwd_bytes = password.encode('utf-8')
    salt = bcrypt.gensalt()
    return bcrypt.hashpw(pwd_bytes, salt).decode('utf-8')

def verify_password(plain_password: str, hashed_password: str) -> bool:
    try:
        return bcrypt.checkpw(plain_password.encode('utf-8'), hashed_password.encode('utf-8'))
    except Exception:
        return False

def create_access_token(data: dict, expires_delta: Optional[datetime.timedelta] = None) -> str:
    to_encode = data.copy()
    if expires_delta:
        expire = datetime.datetime.now(datetime.timezone.utc) + expires_delta
    else:
        expire = datetime.datetime.now(datetime.timezone.utc) + datetime.timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    to_encode.update({"exp": expire})
    encoded_jwt = jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)
    return encoded_jwt

def get_token_from_request(request: Request, header_token: Optional[str] = Depends(oauth2_scheme)) -> Optional[str]:
    if header_token:
        return header_token
    # Fallback to cookie
    cookie_token = request.cookies.get("dss_token")
    if cookie_token:
        return cookie_token
    # Fallback to query param for file downloads (e.g. export)
    query_token = request.query_params.get("token")
    if query_token:
        return query_token
    return None

def get_current_user(
    request: Request,
    token: Optional[str] = Depends(get_token_from_request),
    db: Session = Depends(get_db)
) -> User:
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials or session expired.",
        headers={"WWW-Authenticate": "Bearer"},
    )
    if not token:
        raise credentials_exception

    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        username: str = payload.get("sub")
        if username is None:
            raise credentials_exception
    except JWTError:
        raise credentials_exception

    user = db.query(User).filter(User.username == username).first()
    if user is None or not user.is_active:
        raise credentials_exception
    return user

def require_role(allowed_roles: List[str]):
    def role_checker(current_user: User = Depends(get_current_user)) -> User:
        if current_user.role not in allowed_roles:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Access denied. Required roles: {allowed_roles}. Current role: {current_user.role}"
            )
        return current_user
    return role_checker

def verify_electrician_building_access(user: User, building_id: int, db: Session) -> bool:
    """Verifies that an electrician is assigned to the requested building."""
    if user.role in ["MANAGEMENT", "ADMIN"]:
        return True
    assignment = db.query(BuildingAssignment).filter(
        BuildingAssignment.user_id == user.id,
        BuildingAssignment.building_id == building_id
    ).first()
    return assignment is not None

def record_audit_event(
    db: Session,
    user_id: Optional[int],
    role: Optional[str],
    event_type: str,
    entity_type: Optional[str],
    entity_id: Optional[str],
    action_details: dict,
    ip_address: str = "127.0.0.1"
) -> AuditEvent:
    audit = AuditEvent(
        user_id=user_id,
        role=role,
        event_type=event_type,
        entity_type=entity_type,
        entity_id=str(entity_id) if entity_id is not None else None,
        action_details=action_details,
        ip_address=ip_address,
        is_immutable=True
    )
    db.add(audit)
    db.commit()
    db.refresh(audit)
    return audit

