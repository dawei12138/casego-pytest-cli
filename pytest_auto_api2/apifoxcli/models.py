from __future__ import annotations

from pathlib import Path
from typing import Dict, List, Literal, Optional

from pydantic import BaseModel, ConfigDict, Field


class ProjectSpec(BaseModel):
    defaultEnv: str


class EnvSpec(BaseModel):
    baseUrl: str
    headers: Dict[str, str] = Field(default_factory=dict)
    variables: Dict[str, object] = Field(default_factory=dict)


class SourceGuards(BaseModel):
    maxRemoveCount: int = 20
    maxRemoveRatio: float = 0.2


class SourceSpec(BaseModel):
    type: Literal["openapi"]
    url: str
    serverUrl: Optional[str] = None
    serverDescription: Optional[str] = None
    includePaths: List[str] = Field(default_factory=list)
    excludePaths: List[str] = Field(default_factory=list)
    syncMode: Literal["full"] = "full"
    missingPolicy: Literal["markRemoved"] = "markRemoved"
    tagMap: Dict[str, str] = Field(default_factory=dict)
    rebinds: Dict[str, str] = Field(default_factory=dict)
    guards: SourceGuards = Field(default_factory=SourceGuards)


class RequestSpec(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    method: str
    path: str
    headers: Dict[str, str] = Field(default_factory=dict)
    query: Optional[Dict[str, object]] = None
    json_body: Optional[Dict[str, object]] = Field(default=None, alias="json")
    form: Optional[Dict[str, object]] = None


class AssertionSpec(BaseModel):
    id: str
    source: Literal["response", "context", "dataset"] = "response"
    expr: str
    op: str
    value: object


class ExpectSpec(BaseModel):
    status: int
    assertions: List[AssertionSpec] = Field(default_factory=list)


class ExtractSpec(BaseModel):
    name: str
    from_: Literal["response"] = Field(alias="from")
    expr: str


class ApiSpec(BaseModel):
    protocol: Literal["http"] = "http"
    contract: Optional[Dict[str, object]] = None
    envRef: Optional[str] = None
    request: Optional[RequestSpec] = None
    expect: Optional[ExpectSpec] = None
    extract: List[ExtractSpec] = Field(default_factory=list)


class CaseSpec(BaseModel):
    apiRef: str
    envRef: Optional[str] = None
    datasetRef: Optional[str] = None
    data: Dict[str, object] = Field(default_factory=dict)
    request: Dict[str, object] = Field(default_factory=dict)
    expect: Dict[str, object] = Field(default_factory=dict)
    extract: List[Dict[str, object]] = Field(default_factory=list)
    hooks: Dict[str, List[Dict[str, object]]] = Field(
        default_factory=lambda: {"before": [], "after": []}
    )


class FlowStep(BaseModel):
    caseRef: Optional[str] = None
    apiRef: Optional[str] = None


class FlowSpec(BaseModel):
    envRef: Optional[str] = None
    steps: List[FlowStep]


class SuiteItem(BaseModel):
    caseRef: Optional[str] = None
    apiRef: Optional[str] = None
    flowRef: Optional[str] = None
    datasetRef: Optional[str] = None


class SuiteSpec(BaseModel):
    envRef: Optional[str] = None
    failFast: bool = False
    concurrency: int = 1
    items: List[SuiteItem]


class DatasetSpec(BaseModel):
    rows: List[Dict[str, object]] = Field(default_factory=list)


class ResourceBase(BaseModel):
    kind: str
    id: str
    name: str
    meta: Dict[str, object] = Field(default_factory=dict)


class ProjectResource(ResourceBase):
    kind: Literal["project"]
    spec: ProjectSpec


class SourceResource(ResourceBase):
    kind: Literal["source"]
    spec: SourceSpec


class EnvResource(ResourceBase):
    kind: Literal["env"]
    spec: EnvSpec


class ApiResource(ResourceBase):
    kind: Literal["api"]
    spec: ApiSpec


class CaseResource(ResourceBase):
    kind: Literal["case"]
    spec: CaseSpec


class FlowResource(ResourceBase):
    kind: Literal["flow"]
    spec: FlowSpec


class SuiteResource(ResourceBase):
    kind: Literal["suite"]
    spec: SuiteSpec


class DatasetResource(ResourceBase):
    kind: Literal["dataset"]
    spec: DatasetSpec


class LoadedProject(BaseModel):
    root: Path
    project: ProjectResource
    sources: Dict[str, SourceResource] = Field(default_factory=dict)
    envs: Dict[str, EnvResource] = Field(default_factory=dict)
    apis: Dict[str, ApiResource] = Field(default_factory=dict)
    cases: Dict[str, CaseResource] = Field(default_factory=dict)
    flows: Dict[str, FlowResource] = Field(default_factory=dict)
    suites: Dict[str, SuiteResource] = Field(default_factory=dict)
    datasets: Dict[str, DatasetResource] = Field(default_factory=dict)
