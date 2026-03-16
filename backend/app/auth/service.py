import os
from datetime import datetime, timedelta, timezone

import pandas as pd
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from jose import JWTError, jwt
from passlib.context import CryptContext

from app.config import settings

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")
security = HTTPBearer()
optional_security = HTTPBearer(auto_error=False)

CSV_COLUMNS = ["email", "hashed_password", "created_at"]


def _load_users() -> pd.DataFrame:
    if os.path.exists(settings.users_csv_path):
        return pd.read_csv(settings.users_csv_path)
    return pd.DataFrame(columns=CSV_COLUMNS)


def _save_users(df: pd.DataFrame):
    os.makedirs(os.path.dirname(settings.users_csv_path), exist_ok=True)
    df.to_csv(settings.users_csv_path, index=False)


def hash_password(password: str) -> str:
    return pwd_context.hash(password)


def verify_password(plain: str, hashed: str) -> bool:
    return pwd_context.verify(plain, hashed)


def create_token(email: str) -> str:
    expire = datetime.now(timezone.utc) + timedelta(hours=settings.jwt_expire_hours)
    payload = {"sub": email, "exp": expire}
    return jwt.encode(payload, settings.jwt_secret, algorithm=settings.jwt_algorithm)


def register_user(email: str, password: str) -> str:
    df = _load_users()
    if not df[df["email"] == email].empty:
        raise HTTPException(status_code=400, detail="Email already registered")

    new_row = pd.DataFrame([{
        "email": email,
        "hashed_password": hash_password(password),
        "created_at": datetime.now(timezone.utc).isoformat(),
    }])
    df = pd.concat([df, new_row], ignore_index=True)
    _save_users(df)
    return create_token(email)


def login_user(email: str, password: str) -> str:
    df = _load_users()
    user = df[df["email"] == email]
    if user.empty:
        raise HTTPException(status_code=401, detail="Invalid email or password")

    hashed = user.iloc[0]["hashed_password"]
    if not verify_password(password, hashed):
        raise HTTPException(status_code=401, detail="Invalid email or password")

    return create_token(email)


def get_optional_user(credentials: HTTPAuthorizationCredentials = Depends(optional_security)):
    """Return the authenticated user's email, or None if no valid token is provided."""
    if not credentials:
        return None
    try:
        payload = jwt.decode(credentials.credentials, settings.jwt_secret, algorithms=[settings.jwt_algorithm])
        email: str = payload.get("sub")
        return email if email else None
    except JWTError:
        return None


def get_current_user(credentials: HTTPAuthorizationCredentials = Depends(security)) -> str:
    token = credentials.credentials
    try:
        payload = jwt.decode(token, settings.jwt_secret, algorithms=[settings.jwt_algorithm])
        email: str = payload.get("sub")
        if email is None:
            raise HTTPException(status_code=401, detail="Invalid token")
        return email
    except JWTError:
        raise HTTPException(status_code=401, detail="Invalid token")
