from datetime import datetime, timezone
import uuid


def generate_uuid() -> str:
    """Generate string representation of UUID4."""
    return str(uuid.uuid4())


def get_utc_now() -> datetime:
    """Return timezone aware UTC datetime."""
    return datetime.now(timezone.utc)
