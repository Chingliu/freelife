"""Notify helpers for research playbook."""

from app.research.notify.chart_talk import (
    collect_inline_images,
    generate_chart_talk,
)
from app.research.notify.email_smtp import (
    EmailNotifyConfig,
    EmailSendResult,
    build_email_message,
    send_email_with_attachment,
)

__all__ = [
    "EmailNotifyConfig",
    "EmailSendResult",
    "build_email_message",
    "collect_inline_images",
    "generate_chart_talk",
    "send_email_with_attachment",
]
