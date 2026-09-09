"""Microsoft Graph mailbox adapter with memory-only OAuth tokens."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
import logging
from typing import Iterator, Mapping, TYPE_CHECKING
from urllib.parse import quote

from O365 import Account
from O365.utils.token import MemoryTokenBackend

if TYPE_CHECKING:
    from read_mailbox import AcquisitionConfig


# The Graph MIME value endpoint for a single message: /messages/{id}/$value.
# This matches the installed O365 2.1.0 SDK's own Message.get_mime_content
# endpoint shape (see O365/message.py's `get_mime` entry), so a single
# connection-level GET here reaches exactly the same resource the SDK's own
# two-request path would have reached with its second request.
_MIME_VALUE_SUFFIX = "/$value"


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

    def iter_message_metadata(
        self, cutoff_utc: datetime
    ) -> Iterator[MessageMetadata]:
        """Stream minimal project-owned metadata through every Graph page."""

        try:
            if (
                not isinstance(cutoff_utc, datetime)
                or cutoff_utc.tzinfo is None
                or cutoff_utc.utcoffset() is None
                or cutoff_utc.utcoffset() != timezone.utc.utcoffset(cutoff_utc)
            ):
                raise GraphScanFailed()

            folder = self._confirmed_folder()
            query = folder.new_query("receivedDateTime").greater_equal(cutoff_utc)
            # O365 2.1.0 hydrates Message.sender from Graph's ``from`` field.
            query = query.select("id", "receivedDateTime", "from", "subject")
            messages = folder.get_messages(
                limit=None,
                batch=999,
                query=query,
            )
            for message in messages:
                message_id = message.object_id
                received = message.received
                sender_object = message.sender
                sender = getattr(sender_object, "address", sender_object)
                subject = message.subject
                if (
                    not _is_nonblank(message_id)
                    or not isinstance(received, datetime)
                    or received.tzinfo is None
                    or received.utcoffset() is None
                    or not _is_nonblank(sender)
                    or not isinstance(subject, str)
                ):
                    raise GraphScanFailed()
                yield MessageMetadata(
                    graph_message_id=message_id,
                    received_datetime_utc=received.astimezone(timezone.utc),
                    sender=sender,
                    subject=subject,
                )
        except GraphFailure:
            raise
        except Exception:
            raise GraphScanFailed() from None

    def iter_metadata(self, cutoff_utc: datetime) -> Iterator[MessageMetadata]:
        """Compatibility name consumed by the Plan 01 controller."""

        yield from self.iter_message_metadata(cutoff_utc)

    def _mime_url(self, graph_message_id: str) -> str:
        """Build the connection-level MIME value URL for one complete Graph ID.

        The complete opaque ID is percent-encoded with an empty safe set so a
        reserved character in the ID cannot split or malform the request path,
        and the URL is built through the confirmed folder's own ``build_url``
        so the mailbox resource segment stays exactly the ``users/{address}``
        scope ``authenticate_and_confirm`` already established.
        """

        folder = self._confirmed_folder()
        encoded_id = quote(graph_message_id, safe="")
        endpoint = f"/messages/{encoded_id}{_MIME_VALUE_SUFFIX}"
        return folder.build_url(endpoint)

    def get_message_mime(self, graph_message_id: str) -> bytes:
        """Retrieve MIME for one explicitly qualified complete Graph ID.

        Issues exactly one connection-level GET to the MIME value endpoint,
        using the same connection object the confirmed folder already owns —
        no ordinary message representation is fetched first.
        """

        try:
            if not _is_nonblank(graph_message_id):
                raise GraphScanFailed()
            folder = self._confirmed_folder()
            url = self._mime_url(graph_message_id)
            response = folder.con.get(url)
            status_code = getattr(response, "status_code", None)
            content = getattr(response, "content", None)
            if status_code != 200 or not isinstance(content, bytes):
                raise GraphScanFailed()
            return content
        except GraphFailure:
            raise
        except Exception:
            raise GraphScanFailed() from None

    def get_mime_content(self, graph_message_id: str) -> bytes:
        """Compatibility name consumed by the Plan 01 controller."""

        return self.get_message_mime(graph_message_id)
