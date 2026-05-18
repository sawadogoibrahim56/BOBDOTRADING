"""BTF – Scheduler (tâches périodiques)"""
import logging
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger

logger = logging.getLogger("btf.scheduler")
_scheduler = AsyncIOScheduler(timezone="UTC")


async def start_scheduler():
    from backend.services.risk_manager import DrawdownMonitor
    from backend.utils.database import AsyncSessionLocal
    from backend.models.models import User
    from sqlalchemy import select

    async def daily_drawdown_reset():
        """Réinitialise le drawdown quotidien à minuit UTC."""
        async with AsyncSessionLocal() as db:
            result = await db.execute(select(User).where(User.is_active == True))
            users = result.scalars().all()
            for u in users:
                await DrawdownMonitor.reset_daily(str(u.id), db)
        logger.info("✅ Reset drawdown quotidien effectué.")

    async def cleanup_expired_trials():
        """Marque les essais expirés."""
        from datetime import datetime, timezone
        from backend.models.models import UserStatus
        from sqlalchemy import update
        async with AsyncSessionLocal() as db:
            now = datetime.now(timezone.utc)
            await db.execute(
                update(User)
                .where(User.status == UserStatus.TRIAL, User.trial_ends_at < now)
                .values(status=UserStatus.EXPIRED)
            )
            await db.commit()
        logger.info("✅ Essais expirés mis à jour.")

    async def cleanup_expired_subscriptions():
        """Marque les abonnements expirés."""
        from datetime import datetime, timezone
        from backend.models.models import UserStatus
        from sqlalchemy import update
        async with AsyncSessionLocal() as db:
            now = datetime.now(timezone.utc)
            await db.execute(
                update(User)
                .where(User.status == UserStatus.ACTIVE, User.subscription_ends_at < now)
                .values(status=UserStatus.EXPIRED, autonomous_enabled=False)
            )
            await db.commit()
        logger.info("✅ Abonnements expirés mis à jour.")

    # Reset drawdown à minuit UTC
    _scheduler.add_job(daily_drawdown_reset,      CronTrigger(hour=0, minute=0),  id="reset_drawdown")
    # Vérification essais toutes les heures
    _scheduler.add_job(cleanup_expired_trials,    CronTrigger(minute=30),          id="cleanup_trials")
    # Vérification abonnements toutes les heures
    _scheduler.add_job(cleanup_expired_subscriptions, CronTrigger(minute=45),      id="cleanup_subs")

    _scheduler.start()
    logger.info("⏰ Scheduler démarré – 3 tâches actives")
