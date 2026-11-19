from __future__ import annotations

import logging
import smtplib
import ssl
from dataclasses import dataclass
from email.message import EmailMessage
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)


@dataclass
class EmailNotifyConfig:
    enabled: bool = False
    smtp_host: str = "smtp.qq.com"
    smtp_port: int = 465
    smtp_user: str = ""
    smtp_password: str = ""
    mail_to: str = ""
    use_ssl: bool = True


@dataclass
class EmailSendResult:
    ok: bool
    stage: str
    error: str | None = None
    detail: dict[str, Any] | None = None


def build_email_message(
    *,
    subject: str,
    mail_from: str,
    mail_to: str,
    body_text: str,
    body_html: str | None = None,
    attachment_path: Path | None = None,
    attachment_name: str | None = None,
    extra_attachments: list[tuple[Path, str]] | None = None,
    inline_images: list[tuple[Path, str]] | None = None,
) -> EmailMessage | EmailSendResult:
    """
    Build multipart email. HTML + CID images use multipart/related.
    Returns EmailMessage on success, or EmailSendResult on attach errors.
    """
    msg = EmailMessage()
    msg["Subject"] = subject
    msg["From"] = mail_from
    msg["To"] = mail_to
    msg.set_content(body_text, charset="utf-8")
    if body_html:
        msg.add_alternative(body_html, subtype="html", charset="utf-8")
        html_part = msg.get_payload()[-1]
        for path, cid in inline_images or []:
            path = Path(path)
            if not path.is_file():
                return EmailSendResult(
                    ok=False,
                    stage="attach",
                    error=f"inline image missing: {path}",
                )
            data = path.read_bytes()
            # cid without angle brackets; clients resolve cid:xxx from HTML
            html_part.add_related(
                data,
                maintype="image",
                subtype="png",
                cid=cid,
                filename=path.name,
            )

    attached: list[str] = []

    def _attach_file(path: Path, name: str) -> EmailSendResult | None:
        if not path.is_file():
            return EmailSendResult(
                ok=False,
                stage="attach",
                error=f"attachment missing: {path}",
            )
        data = path.read_bytes()
        lower = name.lower()
        if lower.endswith(".html") or lower.endswith(".htm"):
            msg.add_attachment(
                data,
                maintype="text",
                subtype="html",
                filename=name,
            )
        elif lower.endswith(".md"):
            msg.add_attachment(
                data,
                maintype="text",
                subtype="markdown",
                filename=name,
            )
        elif lower.endswith(".png"):
            msg.add_attachment(
                data,
                maintype="image",
                subtype="png",
                filename=name,
            )
        else:
            msg.add_attachment(
                data,
                maintype="application",
                subtype="octet-stream",
                filename=name,
            )
        attached.append(name)
        return None

    if attachment_path is not None:
        err = _attach_file(
            Path(attachment_path),
            attachment_name or Path(attachment_path).name,
        )
        if err is not None:
            return err

    for path, name in extra_attachments or []:
        err = _attach_file(Path(path), name)
        if err is not None:
            return err

    # Stash attach list for send detail (non-standard but handy for tests)
    msg._aistock_attached = attached  # type: ignore[attr-defined]
    msg._aistock_inline = [c for _, c in (inline_images or [])]  # type: ignore[attr-defined]
    return msg


def send_email_with_attachment(
    cfg: EmailNotifyConfig,
    *,
    subject: str,
    body_text: str,
    body_html: str | None = None,
    attachment_path: Path | None = None,
    attachment_name: str | None = None,
    extra_attachments: list[tuple[Path, str]] | None = None,
    inline_images: list[tuple[Path, str]] | None = None,
) -> EmailSendResult:
    """Send via SMTP. Prefer HTML body for mobile QQ/HarmonyOS. Never log smtp_password."""
    if not cfg.enabled:
        return EmailSendResult(
            ok=False,
            stage="config",
            error="email notify disabled",
        )
    if not cfg.smtp_user or not cfg.smtp_password:
        return EmailSendResult(
            ok=False,
            stage="config",
            error="smtp_user/smtp_password missing",
        )
    mail_to = cfg.mail_to or cfg.smtp_user
    if not mail_to:
        return EmailSendResult(
            ok=False,
            stage="config",
            error="mail_to missing",
        )

    built = build_email_message(
        subject=subject,
        mail_from=cfg.smtp_user,
        mail_to=mail_to,
        body_text=body_text,
        body_html=body_html,
        attachment_path=attachment_path,
        attachment_name=attachment_name,
        extra_attachments=extra_attachments,
        inline_images=inline_images,
    )
    if isinstance(built, EmailSendResult):
        return built
    msg = built
    attached = list(getattr(msg, "_aistock_attached", []) or [])
    inline_cids = list(getattr(msg, "_aistock_inline", []) or [])

    detail = {
        "smtp_host": cfg.smtp_host,
        "smtp_port": cfg.smtp_port,
        "mail_from": cfg.smtp_user,
        "mail_to": mail_to,
        "subject": subject,
        "has_html": bool(body_html),
        "attachments": attached,
        "inline_cids": inline_cids,
    }

    try:
        if cfg.use_ssl or cfg.smtp_port == 465:
            context = ssl.create_default_context()
            with smtplib.SMTP_SSL(
                cfg.smtp_host, cfg.smtp_port, context=context, timeout=60
            ) as server:
                try:
                    server.login(cfg.smtp_user, cfg.smtp_password)
                except smtplib.SMTPAuthenticationError as exc:
                    return EmailSendResult(
                        ok=False,
                        stage="auth",
                        error=f"{type(exc).__name__}: {exc}",
                        detail=detail,
                    )
                try:
                    server.send_message(msg)
                except Exception as exc:  # noqa: BLE001
                    return EmailSendResult(
                        ok=False,
                        stage="send",
                        error=f"{type(exc).__name__}: {exc}",
                        detail=detail,
                    )
        else:
            with smtplib.SMTP(cfg.smtp_host, cfg.smtp_port, timeout=60) as server:
                server.ehlo()
                server.starttls(context=ssl.create_default_context())
                server.ehlo()
                try:
                    server.login(cfg.smtp_user, cfg.smtp_password)
                except smtplib.SMTPAuthenticationError as exc:
                    return EmailSendResult(
                        ok=False,
                        stage="auth",
                        error=f"{type(exc).__name__}: {exc}",
                        detail=detail,
                    )
                try:
                    server.send_message(msg)
                except Exception as exc:  # noqa: BLE001
                    return EmailSendResult(
                        ok=False,
                        stage="send",
                        error=f"{type(exc).__name__}: {exc}",
                        detail=detail,
                    )
    except (OSError, smtplib.SMTPException, TimeoutError) as exc:
        return EmailSendResult(
            ok=False,
            stage="connect",
            error=f"{type(exc).__name__}: {exc}",
            detail=detail,
        )

    logger.info(
        "email sent host=%s to=%s subject=%s html=%s attachments=%s inline=%s",
        cfg.smtp_host,
        mail_to,
        subject,
        bool(body_html),
        attached,
        inline_cids,
    )
    return EmailSendResult(ok=True, stage="send", detail=detail)
