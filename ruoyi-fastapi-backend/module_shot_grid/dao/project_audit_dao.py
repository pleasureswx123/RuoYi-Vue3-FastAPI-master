import json
from datetime import datetime
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from module_admin.dao.log_dao import OperationLogDao
from module_admin.entity.vo.log_vo import OperLogModel


class ShotGridProjectAuditDao:
    """使用业务会话直接写平台操作日志，确保与领域写入同事务。"""

    @classmethod
    async def add_success_log(
        cls,
        db: AsyncSession,
        *,
        title: str,
        business_type: int,
        method: str,
        request_method: str,
        oper_name: str,
        dept_name: str | None,
        oper_url: str,
        oper_param: dict[str, Any],
        result: dict[str, Any],
    ) -> None:
        await OperationLogDao.add_operation_log_dao(
            db,
            OperLogModel(
                title=title,
                businessType=business_type,
                method=method,
                requestMethod=request_method,
                operatorType=1,
                operName=oper_name,
                deptName=dept_name,
                operUrl=oper_url,
                operParam=json.dumps(oper_param, ensure_ascii=False, separators=(',', ':'))[:2000],
                jsonResult=json.dumps(result, ensure_ascii=False, separators=(',', ':'))[:2000],
                status=0,
                operTime=datetime.now(),
                costTime=0,
            ),
        )
