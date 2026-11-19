from datetime import datetime

from sqlalchemy import Select, case, func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from module_shot_grid.entity.do.feedback_message_do import ShotGridFeedbackMessage as Message
from module_shot_grid.entity.do.project_do import ShotGridProject, ShotGridProjectMember
from module_shot_grid.entity.do.task_do import ShotGridTask
from module_shot_grid.entity.do.version_do import ShotGridVersion, ShotGridVersionCandidate
from module_shot_grid.exceptions import shot_grid_error


def visible_messages(user_id: int) -> Select:
    return (
        select(Message, ShotGridProject.project_name, ShotGridTask.task_name, ShotGridVersion)
        .join(ShotGridVersion, ShotGridVersion.version_id == Message.version_id)
        .join(ShotGridTask, ShotGridTask.task_id == ShotGridVersion.task_id)
        .join(ShotGridProject, ShotGridProject.project_id == ShotGridVersion.project_id)
        .join(ShotGridProjectMember, ShotGridProjectMember.project_id == ShotGridProject.project_id)
        .where(
            Message.recipient_id == user_id,
            ShotGridProject.del_flag == '0',
            ShotGridTask.del_flag == '0',
            ShotGridProjectMember.user_id == user_id,
            ShotGridProjectMember.member_status == 'active',
            ShotGridProjectMember.has_role('creator'),
        )
    )


async def unread_summary(db: AsyncSession, user_id: int) -> dict:
    unread_id = case((Message.read_at.is_(None), Message.message_id))
    summary = visible_messages(user_id).with_only_columns(
        func.count(Message.message_id), func.count(unread_id), func.max(unread_id)
    )
    total, count, latest = (await db.execute(summary)).one()
    return {'count': count, 'latestId': latest, 'total': total}


async def list_messages(db: AsyncSession, user_id: int, page: int, size: int, focus: int | None) -> dict:
    query = visible_messages(user_id)
    if focus:
        newer = query.where(Message.message_id > focus).subquery()
        page = int(await db.scalar(select(func.count()).select_from(newer))) // size + 1
    total = await db.scalar(select(func.count()).select_from(query.subquery()))
    rows = (await db.execute(query.order_by(Message.message_id.desc()).offset((page - 1) * size).limit(size))).all()
    candidate_ids = {issue['candidateId'] for msg, *_ in rows for issue in msg.issues if issue.get('candidateId')}
    numbers = (
        dict(
            (
                await db.execute(
                    select(ShotGridVersionCandidate.candidate_id, ShotGridVersionCandidate.candidate_no).where(
                        ShotGridVersionCandidate.candidate_id.in_(candidate_ids)
                    )
                )
            ).all()
        )
        if candidate_ids
        else {}
    )
    return {
        'total': total,
        'page': page,
        'rows': [
            {
                'messageId': msg.message_id,
                'taskId': version.task_id,
                'projectId': version.project_id,
                'projectName': project,
                'taskName': task,
                'versionNumber': f'V{version.version_no:03d}',
                'senderName': msg.sender_name,
                'issues': [{**issue, 'candidateNo': numbers.get(issue.get('candidateId'))} for issue in msg.issues],
                'createdAt': msg.created_at.isoformat(),
                'readAt': msg.read_at.isoformat() if msg.read_at else None,
            }
            for msg, project, task, version in rows
        ],
    }


async def mark_read(db: AsyncSession, user_id: int, message_id: int) -> None:
    ids = visible_messages(user_id).with_only_columns(Message.message_id)
    result = await db.execute(
        update(Message)
        .where(Message.message_id == message_id, Message.message_id.in_(ids))
        .values(read_at=func.coalesce(Message.read_at, datetime.now()))
    )
    if not result.rowcount:
        raise shot_grid_error(404, 'SG_MESSAGE_NOT_FOUND', '消息不存在或无权访问')
