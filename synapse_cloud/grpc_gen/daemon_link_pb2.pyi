from google.protobuf.internal import containers as _containers
from google.protobuf import descriptor as _descriptor
from google.protobuf import message as _message
from collections.abc import Iterable as _Iterable, Mapping as _Mapping
from typing import ClassVar as _ClassVar, Optional as _Optional, Union as _Union

DESCRIPTOR: _descriptor.FileDescriptor

class DaemonMessage(_message.Message):
    __slots__ = ("seq", "daemon_id", "register", "heartbeat", "ack", "event")
    SEQ_FIELD_NUMBER: _ClassVar[int]
    DAEMON_ID_FIELD_NUMBER: _ClassVar[int]
    REGISTER_FIELD_NUMBER: _ClassVar[int]
    HEARTBEAT_FIELD_NUMBER: _ClassVar[int]
    ACK_FIELD_NUMBER: _ClassVar[int]
    EVENT_FIELD_NUMBER: _ClassVar[int]
    seq: int
    daemon_id: str
    register: RegisterDaemon
    heartbeat: Heartbeat
    ack: Ack
    event: Envelope
    def __init__(self, seq: _Optional[int] = ..., daemon_id: _Optional[str] = ..., register: _Optional[_Union[RegisterDaemon, _Mapping]] = ..., heartbeat: _Optional[_Union[Heartbeat, _Mapping]] = ..., ack: _Optional[_Union[Ack, _Mapping]] = ..., event: _Optional[_Union[Envelope, _Mapping]] = ...) -> None: ...

class CloudMessage(_message.Message):
    __slots__ = ("seq", "ack", "command", "close")
    SEQ_FIELD_NUMBER: _ClassVar[int]
    ACK_FIELD_NUMBER: _ClassVar[int]
    COMMAND_FIELD_NUMBER: _ClassVar[int]
    CLOSE_FIELD_NUMBER: _ClassVar[int]
    seq: int
    ack: Ack
    command: Command
    close: CloseStream
    def __init__(self, seq: _Optional[int] = ..., ack: _Optional[_Union[Ack, _Mapping]] = ..., command: _Optional[_Union[Command, _Mapping]] = ..., close: _Optional[_Union[CloseStream, _Mapping]] = ...) -> None: ...

class RegisterDaemon(_message.Message):
    __slots__ = ("name", "tags", "platform", "version", "hostname", "os_version", "e2e_public_key")
    NAME_FIELD_NUMBER: _ClassVar[int]
    TAGS_FIELD_NUMBER: _ClassVar[int]
    PLATFORM_FIELD_NUMBER: _ClassVar[int]
    VERSION_FIELD_NUMBER: _ClassVar[int]
    HOSTNAME_FIELD_NUMBER: _ClassVar[int]
    OS_VERSION_FIELD_NUMBER: _ClassVar[int]
    E2E_PUBLIC_KEY_FIELD_NUMBER: _ClassVar[int]
    name: str
    tags: _containers.RepeatedScalarFieldContainer[str]
    platform: str
    version: str
    hostname: str
    os_version: str
    e2e_public_key: str
    def __init__(self, name: _Optional[str] = ..., tags: _Optional[_Iterable[str]] = ..., platform: _Optional[str] = ..., version: _Optional[str] = ..., hostname: _Optional[str] = ..., os_version: _Optional[str] = ..., e2e_public_key: _Optional[str] = ...) -> None: ...

class Heartbeat(_message.Message):
    __slots__ = ("cpu", "mem")
    CPU_FIELD_NUMBER: _ClassVar[int]
    MEM_FIELD_NUMBER: _ClassVar[int]
    cpu: float
    mem: float
    def __init__(self, cpu: _Optional[float] = ..., mem: _Optional[float] = ...) -> None: ...

class Ack(_message.Message):
    __slots__ = ("acked_seq", "ok", "error")
    ACKED_SEQ_FIELD_NUMBER: _ClassVar[int]
    OK_FIELD_NUMBER: _ClassVar[int]
    ERROR_FIELD_NUMBER: _ClassVar[int]
    acked_seq: int
    ok: bool
    error: str
    def __init__(self, acked_seq: _Optional[int] = ..., ok: bool = ..., error: _Optional[str] = ...) -> None: ...

class Envelope(_message.Message):
    __slots__ = ("type", "payload_json", "idempotency_key", "run_id", "agent_id")
    TYPE_FIELD_NUMBER: _ClassVar[int]
    PAYLOAD_JSON_FIELD_NUMBER: _ClassVar[int]
    IDEMPOTENCY_KEY_FIELD_NUMBER: _ClassVar[int]
    RUN_ID_FIELD_NUMBER: _ClassVar[int]
    AGENT_ID_FIELD_NUMBER: _ClassVar[int]
    type: str
    payload_json: str
    idempotency_key: str
    run_id: str
    agent_id: str
    def __init__(self, type: _Optional[str] = ..., payload_json: _Optional[str] = ..., idempotency_key: _Optional[str] = ..., run_id: _Optional[str] = ..., agent_id: _Optional[str] = ...) -> None: ...

class Command(_message.Message):
    __slots__ = ("type", "payload_json", "idempotency_key")
    TYPE_FIELD_NUMBER: _ClassVar[int]
    PAYLOAD_JSON_FIELD_NUMBER: _ClassVar[int]
    IDEMPOTENCY_KEY_FIELD_NUMBER: _ClassVar[int]
    type: str
    payload_json: str
    idempotency_key: str
    def __init__(self, type: _Optional[str] = ..., payload_json: _Optional[str] = ..., idempotency_key: _Optional[str] = ...) -> None: ...

class CloseStream(_message.Message):
    __slots__ = ("reason",)
    REASON_FIELD_NUMBER: _ClassVar[int]
    reason: str
    def __init__(self, reason: _Optional[str] = ...) -> None: ...

class TelemetryFrame(_message.Message):
    __slots__ = ("daemon_id", "org_id", "run_id", "agent_id", "seq", "log", "metric", "trace")
    DAEMON_ID_FIELD_NUMBER: _ClassVar[int]
    ORG_ID_FIELD_NUMBER: _ClassVar[int]
    RUN_ID_FIELD_NUMBER: _ClassVar[int]
    AGENT_ID_FIELD_NUMBER: _ClassVar[int]
    SEQ_FIELD_NUMBER: _ClassVar[int]
    LOG_FIELD_NUMBER: _ClassVar[int]
    METRIC_FIELD_NUMBER: _ClassVar[int]
    TRACE_FIELD_NUMBER: _ClassVar[int]
    daemon_id: str
    org_id: str
    run_id: str
    agent_id: str
    seq: int
    log: LogLine
    metric: Metric
    trace: TraceChunk
    def __init__(self, daemon_id: _Optional[str] = ..., org_id: _Optional[str] = ..., run_id: _Optional[str] = ..., agent_id: _Optional[str] = ..., seq: _Optional[int] = ..., log: _Optional[_Union[LogLine, _Mapping]] = ..., metric: _Optional[_Union[Metric, _Mapping]] = ..., trace: _Optional[_Union[TraceChunk, _Mapping]] = ...) -> None: ...

class LogLine(_message.Message):
    __slots__ = ("level", "message", "fields_json")
    LEVEL_FIELD_NUMBER: _ClassVar[int]
    MESSAGE_FIELD_NUMBER: _ClassVar[int]
    FIELDS_JSON_FIELD_NUMBER: _ClassVar[int]
    level: str
    message: str
    fields_json: str
    def __init__(self, level: _Optional[str] = ..., message: _Optional[str] = ..., fields_json: _Optional[str] = ...) -> None: ...

class Metric(_message.Message):
    __slots__ = ("name", "value", "labels_json")
    NAME_FIELD_NUMBER: _ClassVar[int]
    VALUE_FIELD_NUMBER: _ClassVar[int]
    LABELS_JSON_FIELD_NUMBER: _ClassVar[int]
    name: str
    value: float
    labels_json: str
    def __init__(self, name: _Optional[str] = ..., value: _Optional[float] = ..., labels_json: _Optional[str] = ...) -> None: ...

class TraceChunk(_message.Message):
    __slots__ = ("seq", "role", "content")
    SEQ_FIELD_NUMBER: _ClassVar[int]
    ROLE_FIELD_NUMBER: _ClassVar[int]
    CONTENT_FIELD_NUMBER: _ClassVar[int]
    seq: int
    role: str
    content: str
    def __init__(self, seq: _Optional[int] = ..., role: _Optional[str] = ..., content: _Optional[str] = ...) -> None: ...

class TelemetryAck(_message.Message):
    __slots__ = ("frames_received", "last_seq")
    FRAMES_RECEIVED_FIELD_NUMBER: _ClassVar[int]
    LAST_SEQ_FIELD_NUMBER: _ClassVar[int]
    frames_received: int
    last_seq: int
    def __init__(self, frames_received: _Optional[int] = ..., last_seq: _Optional[int] = ...) -> None: ...
