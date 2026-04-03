"""Persist admin pipeline operator actions (#277)."""

from __future__ import annotations

import json
import logging
from typing import Any, Dict, List, Optional

from fastapi import Request

from app.db import session_scope
from app.deps import get_client_ip
from app.orm_models import OperatorAction

logger = logging.getLogger(__name__)


def record_operator_action(
    *,
    request: Request,
    action_type: str,
    details: Optional[Dict[str, Any]] = None,
) -> None:
    """Best-effort audit insert; failures are logged and not propagated."""
    label = (
        request.headers.get("X-Operator-Label")
        or request.headers.get("X-Operator-Id")
        or ""
    ).strip() or None
    ip = get_client_ip(request)
    payload = details or {}
    try:
        with session_scope() as session:
            session.add(
                OperatorAction(
                    action_type=action_type[:64],
                    details_json=json.dumps(payload) if payload else None,
                    operator_label=(label[:256] if label else None),
                    client_ip=(ip[:64] if ip else None),
                )
            )
    except Exception as e:
        logger.warning("operator audit insert failed: %s", e, exc_info=True)


def list_recent_operator_actions(limit: int = 50) -> List[Dict[str, Any]]:
    from sqlalchemy import desc

    with session_scope() as session:
        rows = (
            session.query(OperatorAction)
            .order_by(desc(OperatorAction.created_at))
            .limit(limit)
            .all()
        )
        out = []
        for r in rows:
            out.append(
                {
                    "id": r.id,
                    "created_at": r.created_at.isoformat() if r.created_at else None,
                    "action_type": r.action_type,
                    "details": json.loads(r.details_json) if r.details_json else None,
                    "operator_label": r.operator_label,
                    "client_ip": r.client_ip,
                }
            )
        return out
