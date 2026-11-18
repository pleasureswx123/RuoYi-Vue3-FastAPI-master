from sqlalchemy.ext.asyncio import AsyncSession

from module_realtime.service.realtime_publisher import publish_inbox_changed
from module_shot_grid.dao import feedback_message_dao


async def read_feedback_message(db: AsyncSession, user_id: int, message_id: int) -> None:
    try:
        await feedback_message_dao.mark_read(db, user_id, message_id)
        await db.commit()
    except Exception:
        await db.rollback()
        raise
    await publish_inbox_changed(user_id)
