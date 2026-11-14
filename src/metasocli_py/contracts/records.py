"""Strict persisted identities; verification does not coerce or rewrite records."""
from typing import Annotated, Literal

from pydantic import Field, StringConstraints

from .story import Asset, Count, Hash, Id, Segment, StrictModel, parse

Uuid = Annotated[str, StringConstraints(pattern=r'^[a-f0-9]{8}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{12}$')]


class Hashed(StrictModel):
    hashVersion: Literal['jcs-sha256-v1']
    hash: Hash


class ErrorDetail(StrictModel):
    code: str
    message: str
    httpStatus: int | None = None


class Output(StrictModel):
    path: str
    sha256: Hash
    bytes: Count
    width: int
    height: int
    duration: float


class VideoJob(Hashed):
    schemaVersion: Literal[1]
    operationId: Uuid
    projectId: Uuid
    planId: Uuid
    planHash: Hash
    episodeId: Id
    segmentId: Id
    requestHash: Hash
    inputHash: Hash
    status: Literal['prepared', 'submitting', 'submit_unknown', 'query_unknown', 'queued', 'running', 'generated', 'downloaded', 'failed', 'cancelled']
    attempt: Annotated[int, Field(ge=1)]
    recordVersion: Annotated[int, Field(ge=1)]
    createdAt: str
    updatedAt: str
    timings: dict[str, float]
    taskId: Annotated[str, Field(min_length=1)] | None = None
    submittedAt: str | None = None
    retryOf: Uuid | None = None
    unknownRetry: bool | None = None
    resultUrl: str | None = None
    output: Output | None = None
    error: ErrorDetail | None = None


class IrOperation(Hashed):
    operationId: Uuid
    projectId: Uuid
    planId: Uuid
    planHash: Hash
    episodeId: Id
    segmentId: Id
    requestHash: Hash
    baseInputHash: Hash
    attempt: Annotated[int, Field(ge=1)]
    retryOf: Uuid | None = None
    status: Literal['submitting', 'submit_unknown', 'queued', 'running', 'query_unknown', 'enhanced', 'failed', 'cancelled']
    createdAt: str
    taskId: Annotated[str, Field(min_length=1)] | None = None
    resultPath: str | None = None
    promptHash: Hash | None = None
    recoveredManually: bool | None = None
    error: ErrorDetail | None = None


class Snapshot(StrictModel):
    episodeId: Id
    segmentId: Id
    segment: Segment
    assets: list[Asset]
    requestHash: Hash
    inputHash: Hash
    derivedPrompt: str | None = None
    sourceRequestHash: Hash | None = None


class VideoPlan(StrictModel):
    schemaVersion: Literal[1]
    batchId: Uuid
    planId: Uuid
    projectId: Uuid
    scopeHash: Hash
    revision: Count
    manifestHash: Hash
    createdAt: str
    concurrency: Annotated[int, Field(ge=1, le=4)]
    workflow: Literal['h3-inline-ir', 'h3-context-ir', 'h3-context-ir-derived']
    segments: Annotated[list[Snapshot], Field(min_length=1)]
    hashVersion: Literal['jcs-sha256-v1']
    batchHash: Hash
    preparePlanId: Uuid | None = None
    irOperationId: Uuid | None = None
    reviewHash: Hash | None = None
    reviewPath: str | None = None


class DecisionBasis(StrictModel):
    version: Count
    reason: str
    evidence: Hash
    decidedAt: str
    sourceEvidence: Hash | None = None


class Decision(DecisionBasis):
    policy: Literal['R3']
    state: Literal['held', 'released']
    reason: Literal['reserved', 'create_accepted', 'remote_active_recovered', 'create_ended_without_id',
                    'submitter_exited_without_id', 'query_unavailable', 'source_unavailable', 'provider_terminal']
    issued: Count
    applied: Count
    terminal: bool
    lastRelease: DecisionBasis | None = None
    lastRestore: DecisionBasis | None = None


class Slot(StrictModel):
    operationId: Uuid
    projectId: Uuid
    root: str
    requestHash: Hash
    inputHash: Hash
    owner: str
    taskId: str | None = None
    capacity: Decision


class Ticket(StrictModel):
    ticketId: Uuid
    root: str
    projectId: Uuid
    batchId: Uuid
    scopeHash: Hash
    limit: Annotated[int, Field(ge=1, le=4)]
    remaining: Count
    owner: str
    enteredAt: str


class Ledger(Hashed):
    schemaVersion: Literal[1]
    slots: dict[Uuid, Slot]
    tickets: list[Ticket]


class RunAuthorization(StrictModel):
    batchHash: Hash
    authorizedAt: str
    authorizedOrders: list[Count] | None = None


class RunItem(StrictModel):
    operationId: Uuid | None = None
    retryOf: Uuid | None = None


class VideoRun(Hashed):
    schemaVersion: Literal[1]
    batchId: Uuid
    batchHash: Hash
    runtimeRoot: str
    authorization: RunAuthorization
    items: list[RunItem]


def validate_record(schema, value: dict) -> dict:
    parse(schema, value)
    return value
