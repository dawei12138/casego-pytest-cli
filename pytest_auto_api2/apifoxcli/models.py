from __future__ import annotations

from pathlib import Path
from typing import Dict, List, Literal, Optional

from pydantic import BaseModel, Field


class ProjectSpec(BaseModel):
    defaultEnv: str


class EnvSpec(BaseModel):
    baseUrl: str
    variables: Dict[str, object] = Field(default_factory=dict)


class RequestSpec(BaseModel):
    method: str
    path: str
    headers: Dict[str, str] = Field(default_factory=dict)
    query: Optional[Dict[str, object]] = None
    json: Optional[Dict[str, object]] = None
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
    envRef: Optional[str] = None
    request: RequestSpec
    expect: ExpectSpec
    extract: List[ExtractSpec] = Field(default_factory=list)


class FlowStep(BaseModel):
    apiRef: str


class FlowSpec(BaseModel):
    envRef: Optional[str] = None
    steps: List[FlowStep]


class SuiteItem(BaseModel):
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


class EnvResource(ResourceBase):
    kind: Literal["env"]
    spec: EnvSpec


class ApiResource(ResourceBase):
    kind: Literal["api"]
    spec: ApiSpec


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
    envs: Dict[str, EnvResource] = Field(default_factory=dict)
    apis: Dict[str, ApiResource] = Field(default_factory=dict)
    flows: Dict[str, FlowResource] = Field(default_factory=dict)
    suites: Dict[str, SuiteResource] = Field(default_factory=dict)
    datasets: Dict[str, DatasetResource] = Field(default_factory=dict)
