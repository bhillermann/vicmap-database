"""Microsoft Graph mailbox adapter with memory-only OAuth tokens."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
import logging
from typing import Iterator, Mapping, TYPE_CHECKING

from O365 import Account
from O365.utils.token import MemoryTokenBackend

if TYPE_CHECKING:
    from read_mailbox import AcquisitionConfig


class GraphFailure(RuntimeError):
    """Closed Graph boundary failure containing project-owned values only."""

    def __init__(self, stage: str, reason: str):
        self.stage = stage
        self.reason = reason
        self.code = reason
        super().__init__(reason)


class GraphAuthenticationFailed(GraphFailure):
    def __init__(self):
        super().__init__("authentication", "authentication_failed")


class MailboxAccessFailed(GraphFailure):
    def __init__(self):
        super().__init__("mailbox", "mailbox_access_failed")


class GraphScanFailed(GraphFailure):
    def __init__(self):
        super().__init__("scan", "graph_scan_failed")


# Plan 01 established this import for the acquisition controller. Keep it as a
# compatibility name while exposing the more precise failure hierarchy.
GraphError = GraphFailure


@dataclass(frozen=True)
class MessageMetadata:
    graph_message_id: str
    received_datetime_utc: datetime
    sender: str
    subject: str


def _is_nonblank(value: object) -> bool:
    return isinstance(value, str) and bool(value.strip())


def _suppress_provider_logging() -> None:
    """Prevent dependency HTTP diagnostics from bypassing project redaction."""

    for logger_name in ("O365", "o365", "msal", "requests", "urllib3"):
        logger = logging.getLogger(logger_name)
        logger.setLevel(logging.CRITICAL + 1)
        logger.propagate = False


class GraphMailbox:
    """Read-only O365 adapter that never exposes SDK message objects."""

    def __init__(
        self,
        credentials: tuple[str, str] | Mapping[str, str] | None = None,
        tenant_id: str | None = None,
        mailbox_address: str | None = None,
        folder_name: str = "Inbox",
        account_factory=Account,
        *,
        config: "AcquisitionConfig | None" = None,
    ):
        if config is not None:
            mailbox_address = config.mailbox
            folder_name = config.folder

        if isinstance(credentials, Mapping):
            credential_pair = (
                credentials.get("O365_AUTH_ID"),
                credentials.get("O365_AUTH_SECRET"),
            )
            tenant_id = credentials.get("TENANT_ID", tenant_id)
        else:
            credential_pair = credentials

        if (
            not isinstance(credential_pair, tuple)
            or len(credential_pair) != 2
            or not all(_is_nonblank(value) for value in credential_pair)
            or not _is_nonblank(tenant_id)
            or not _is_nonblank(mailbox_address)
            or folder_name != "Inbox"
        ):
            raise GraphAuthenticationFailed()

        _suppress_provider_logging()
        try:
            self._account = account_factory(
                credential_pair,
                auth_flow_type="credentials",
                tenant_id=tenant_id,
                token_backend=MemoryTokenBackend(),
            )
        except Exception:
            raise GraphAuthenticationFailed() from None

        self._mailbox_address = mailbox_address
        self._folder_name = folder_name
        self._folder = None
        self._messages: dict[str, object] = {}

    def authenticate_and_confirm(self) -> str:
        """Authenticate if necessary and confirm the configured Inbox resource."""

        if self._folder is not None:
            return self._mailbox_address

        try:
            authenticated = bool(self._account.is_authenticated)
            if not authenticated:
                authenticated = self._account.authenticate(
                    requested_scopes=["https://graph.microsoft.com/.default"]
                )
        except Exception:
            raise GraphAuthenticationFailed() from None
        if not authenticated:
            raise GraphAuthenticationFailed()

        try:
            mailbox = self._account.mailbox(resource=self._mailbox_address)
            folder = mailbox.get_folder(folder_name=self._folder_name)
            if folder is None:
                raise MailboxAccessFailed()
        except MailboxAccessFailed:
            raise
        except Exception:
            raise MailboxAccessFailed() from None

        self._folder = folder
        return self._mailbox_address

    def _confirmed_folder(self):
        self.authenticate_and_confirm()
        return self._folder

    def iter_metadata(self, cutoff_utc: datetime) -> Iterator[MessageMetadata]:
        try:
            folder = self._confirmed_folder()
            query = folder.new_query("receivedDateTime").greater_equal(cutoff_utc)
            query = query.select("id", "receivedDateTime", "sender", "subject")
            messages = folder.get_messages(
                limit=None,
                batch=999,
                query=query,
                download_attachments=False,
            )
            for message in messages:
                message_id = str(message.object_id)
                received = message.received
                if received.tzinfo is None:
                    raise GraphScanFailed()
                sender = getattr(message.sender, "address", message.sender)
                self._messages[message_id] = message
                yield MessageMetadata(
                    graph_message_id=message_id,
                    received_datetime_utc=received.astimezone(timezone.utc),
                    sender=str(sender),
                    subject=str(message.subject),
                )
        except GraphFailure:
            raise
        except Exception:
            raise GraphScanFailed() from None

    def get_mime_content(self, graph_message_id: str) -> bytes:
        try:
            content = self._messages[graph_message_id].get_mime_content()
            if not isinstance(content, bytes):
                raise GraphScanFailed()
            return content
        except GraphFailure:
            raise
        except Exception:
            raise GraphScanFailed() from None
