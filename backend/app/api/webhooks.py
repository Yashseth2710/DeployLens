import json
from typing import Annotated, Any

from fastapi import APIRouter, Depends, Header, HTTPException, Request, status

from app.api.deps import DbSession
from app.services import webhooks

router = APIRouter(prefix="/api/webhooks", tags=["webhooks"])


async def raw_body(request: Request) -> bytes:
    """The signature covers the exact bytes GitHub sent, so the body has to be read
    before anything parses or re-serialises it."""
    return await request.body()


RawBody = Annotated[bytes, Depends(raw_body)]


@router.post("/github", status_code=status.HTTP_202_ACCEPTED)
def receive_github_event(
    body: RawBody,
    db: DbSession,
    x_hub_signature_256: Annotated[str | None, Header()] = None,
    x_github_delivery: Annotated[str | None, Header()] = None,
    x_github_event: Annotated[str | None, Header()] = None,
) -> dict[str, str]:
    if not webhooks.signature_matches(body, x_hub_signature_256):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Signature does not match the payload")
    if not x_github_delivery or not x_github_event:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Delivery headers are missing")

    payload = _parse(body)
    if x_github_event == "ping":
        return {"result": "pong"}

    result = webhooks.record_delivery(db, x_github_delivery, x_github_event, payload)
    return {"result": result}


def _parse(body: bytes) -> dict[str, Any]:
    try:
        payload = json.loads(body)
    except json.JSONDecodeError as exc:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Payload is not JSON") from exc
    if not isinstance(payload, dict):
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Payload is not an object")
    return payload
