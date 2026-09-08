"""Microsoft Graph mailbox adapter with memory-only OAuth tokens."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Iterator, Mapping, TYPE_CHECKING

from O365 import Account
from O365.utils.token import MemoryTokenBackend

if TYPE_CHECKING:
    from read_mailbox import AcquisitionConfig


class GraphError(RuntimeError):
    def __init__(self, code: str):
        self.code = code
        super().__init__(code)


@dataclass(frozen=True)
class MessageMetadata:
    graph_message_id: str
    received_datetime_utc: datetime
    sender: str
    subject: str


class GraphMailbox:
    """Read-only O365 adapter that never exposes SDK message objects."""

    def __init__(
        self,
        *,
        config: "AcquisitionConfig",
        credentials: Mapping[str, str],
        account_factory=Account,
    ):
        try:
            account = account_factory(
                (credentials["O365_AUTH_ID"], credentials["O365_AUTH_SECRET"]),
                auth_flow_type="credentials",
                tenant_id=credentials["TENANT_ID"],
                token_backend=MemoryTokenBackend(),
            )
            if not account.authenticate(
                requested_scopes=["https://graph.microsoft.com/.default"]
            ):
                raise GraphError("graph_auth_failed")
            mailbox = account.mailbox(resource=config.mailbox)
            self._folder = mailbox.get_folder(folder_name=config.folder)
            self._messages: dict[str, object] = {}
        except GraphError:
            raise
        except Exception:
            raise GraphError("graph_auth_failed") from None

    def iter_metadata(self, cutoff_utc: datetime) -> Iterator[MessageMetadata]:
        try:
            query = self._folder.new_query("receivedDateTime").greater_equal(cutoff_utc)
            query = query.select("id", "receivedDateTime", "sender", "subject")
            messages = self._folder.get_messages(
                limit=None,
                batch=999,
                query=query,
                download_attachments=False,
            )
            for message in messages:
                message_id = str(message.object_id)
                received = message.received
                if received.tzinfo is None:
                    raise GraphError("graph_scan_failed")
                sender = getattr(message.sender, "address", message.sender)
                self._messages[message_id] = message
                yield MessageMetadata(
                    graph_message_id=message_id,
                    received_datetime_utc=received.astimezone(timezone.utc),
                    sender=str(sender),
                    subject=str(message.subject),
                )
        except GraphError:
            raise
        except Exception:
            raise GraphError("graph_scan_failed") from None

    def get_mime_content(self, graph_message_id: str) -> bytes:
        try:
            content = self._messages[graph_message_id].get_mime_content()
            if not isinstance(content, bytes):
                raise GraphError("graph_scan_failed")
            return content
        except GraphError:
            raise
        except Exception:
            raise GraphError("graph_scan_failed") from None
