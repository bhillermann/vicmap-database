# API Coverage — Microsoft Graph and artifact HTTPS

> Full coverage by default. Opt-outs are explicit, reasoned decisions. Capability identifiers are prefixed by integration so the matrix remains unique and machine-checkable.

| capability | decision | reason |
|---|---|---|
| graph.client-credentials-authentication | INTEGRATE | |
| graph.memory-only-token-backend | INTEGRATE | |
| graph.configured-mailbox-resource | INTEGRATE | |
| graph.inbox-folder-resolution | INTEGRATE | |
| graph.received-time-filter | INTEGRATE | |
| graph.message-metadata-select | INTEGRATE | |
| graph.complete-pagination | INTEGRATE | |
| graph.single-message-mime-value | INTEGRATE | |
| graph.message-body-expansion-in-list | OPT-OUT | Metadata-first retrieval is required so non-qualifying message bodies do not cross the application boundary. |
| graph.attachments | OPT-OUT | DataShare delivery is an HTTPS body link, not a Graph attachment. |
| graph.send-reply-forward | OPT-OUT | The phase is read-only acquisition and sends no mailbox content. |
| graph.message-mutation | OPT-OUT | Mailbox folders, read flags, categories, moves, and deletes are not workflow state in this phase. |
| graph.non-inbox-folders | OPT-OUT | The locked phase boundary names the configured Inbox only. |
| graph.delta-query | OPT-OUT | Durable scan watermarks and replay state are explicitly deferred. |
| graph.change-notifications-webhooks | OPT-OUT | Unattended/event-driven operation is outside the one-run acquisition proof. |
| graph.batch-endpoint | OPT-OUT | One bounded paginated Inbox query plus selective MIME reads covers the deliberately bounded mail surface. |
| graph.confirmation-message-lookup | OPT-OUT | D-03 says the ready message qualifies without a corresponding confirmation email. |
| artifact.https-get | INTEGRATE | |
| artifact.manual-redirect-hop | INTEGRATE | |
| artifact.relative-location-resolution | INTEGRATE | |
| artifact.status-and-expiry-classification | INTEGRATE | |
| artifact.content-length-precheck | INTEGRATE | |
| artifact.identity-content-encoding | INTEGRATE | |
| artifact.streamed-response-body | INTEGRATE | |
| artifact.connect-timeout | INTEGRATE | |
| artifact.stalled-read-timeout | INTEGRATE | |
| artifact.tls-certificate-verification | INTEGRATE | |
| artifact.observed-byte-ceiling | INTEGRATE | |
| artifact.incremental-sha256 | INTEGRATE | |
| artifact.private-temporary-file | INTEGRATE | |
| artifact.atomic-no-overwrite-finalization | INTEGRATE | |
| artifact.head-request | OPT-OUT | The bounded GET validates declared and observed sizes without a separate request or trust decision. |
| artifact.range-resume | OPT-OUT | Interruption retry and resume policy is explicitly deferred from this one-artifact proof. |
| artifact.upload-and-non-get-methods | OPT-OUT | Acquisition only reads one artifact and performs no remote mutation. |
| artifact.proxy-netrc-ambient-auth | OPT-OUT | The clean artifact session must not inherit credentials or proxy routing from the Graph environment. |
| artifact.alternate-hostnames | OPT-OUT | D-13 initially permits only the exact host `s3.ap-southeast-2.amazonaws.com`. |
| artifact.archive-extraction | OPT-OUT | Archive inspection and extraction belong to Phase 2. |

## Boundary note

This matrix covers the Microsoft Graph verbs used to authenticate, address the configured mailbox, enumerate the complete received-time window, and retrieve MIME only for header-qualified messages. It separately covers the unauthenticated HTTPS response/redirect/stream surface used to acquire the selected artifact. PostGIS, archive extraction, mail mutation, scheduling, durable delta state, and replay processing are intentionally outside Phase 1.
