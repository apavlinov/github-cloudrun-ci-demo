"""Minimal shared JSON response contract."""


def health_payload(service: str) -> dict[str, str]:
    return {"service": service, "status": "ok"}
