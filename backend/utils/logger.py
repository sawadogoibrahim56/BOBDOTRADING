"""BTF – Logger d'audit immuable."""
import logging
from sqlalchemy.ext.asyncio import AsyncSession
from backend.models.models import SystemLog

logger = logging.getLogger("btf.audit")

async def log_action(
    db: AsyncSession,
    user_id,
    action: str,
    module: str,
    ip_address: str = None,
    severity: str = "info",
    data: dict = None,
):
    log = SystemLog(
        user_id=user_id,
        action=action,
        module=module,
        ip_address=ip_address,
        severity=severity,
        data=data,
    )
    db.add(log)
    try:
        await db.flush()
    except Exception as e:
        logger.error(f"Erreur log: {e}")
