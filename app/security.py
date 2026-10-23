from secrets import compare_digest
from typing import Annotated

from fastapi import Depends, HTTPException, Path, Request
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

bearer = HTTPBearer(auto_error=False)


def authorize_customer(
    request: Request,
    customer_id: Annotated[int, Path(gt=0)],
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(bearer)],
):
    """Temporary local demo identity. Replace with verified login for deployment."""
    settings = request.app.state.settings
    expected = settings.demo_api_token.get_secret_value()
    if not expected or credentials is None or not compare_digest(
        credentials.credentials.encode(), expected.encode()
    ):
        raise HTTPException(401, "Vyžaduje sa platný Bearer token.", headers={"WWW-Authenticate": "Bearer"})
    if customer_id != settings.demo_customer_id:
        raise HTTPException(403, "K tomuto zákazníkovi nemáte prístup.")
