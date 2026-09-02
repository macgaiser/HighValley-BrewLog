import os
import secrets

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPBasic, HTTPBasicCredentials

security = HTTPBasic()


def get_current_user(credentials: HTTPBasicCredentials = Depends(security)) -> str:
    expected_user = os.environ.get("APP_USERNAME", "admin")
    expected_pass = os.environ.get("APP_PASSWORD", "brewlog")

    correct_username = secrets.compare_digest(credentials.username, expected_user)
    correct_password = secrets.compare_digest(credentials.password, expected_pass)

    if not (correct_username and correct_password):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Ungültige Zugangsdaten",
            headers={"WWW-Authenticate": "Basic"},
        )
    return credentials.username
