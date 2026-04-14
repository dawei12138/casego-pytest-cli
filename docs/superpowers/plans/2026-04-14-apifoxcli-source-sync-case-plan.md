# apifoxcli Source Sync And Case-First Refactor Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Refactor the current `apifoxcli` MVP into a case-first canonical runner where `api` is machine-managed OpenAPI contract data, `case` is the direct executable test asset, `flow` chains `caseRef`, `suite` orchestrates `caseRef` and `flowRef`, and OpenAPI import defaults to full sync through `source`.

**Architecture:** Reuse the existing `pytest_auto_api2.apifoxcli` package in place instead of adding a second model layer. Introduce `source` and `case` resources, move execution from `api` to a contract-aware `case` executor that resolves `api.spec.contract` at runtime, then replace direct OpenAPI-to-API writes with a two-phase sync pipeline: normalize upstream operations, diff them against local `api` resources, and apply only machine-managed changes plus impact reporting. Canonical YAML remains the only persisted source of truth; the executor is a runtime abstraction over those YAML resources.

**Tech Stack:** Python 3.8+, argparse, Pydantic v2, PyYAML, requests, pytest

---

## Scope Lock-In

Current repo baseline:

- `pytest_auto_api2/apifoxcli/openapi_importer.py` imports OpenAPI directly into `api` YAML.
- `pytest_auto_api2/apifoxcli/runner.py` executes `api` resources directly.
- `pytest_auto_api2/apifoxcli/planner.py` expands `apiRef` in `flow` and `suite`.
- phase4 tests already cover `api send`, `flow run`, `suite run`, auth chaining, and basic OpenAPI import.

Target state for this plan:

- canonical persisted resources are unique and human-readable under `apifox/`
- `source` manages OpenAPI sync configuration
- `api` stores contract data only
- `case` stores executable request, assertions, extracts, hooks, and dataset expansion inputs
- `flow` references `caseRef` only
- `suite` references `caseRef` and `flowRef`
- `apifoxcli suite run` reads canonical YAML and executes through a case executor
- OpenAPI import defaults to full sync grouped by tag module
- repeated sync updates only `api`, never rewrites `case.spec`
- sync emits machine-readable impact reports for `case`, `flow`, and `suite`

Out of scope for this plan:

- non-HTTP protocol executors
- mock server runtime implementations
- secret masking or external secret managers
- Allure adapters or HTML reporting beyond YAML sync reports

## File Structure Lock-In

**Create:**

- `pytest_auto_api2/apifoxcli/contract.py`
- `pytest_auto_api2/apifoxcli/source_sync.py`
- `pytest_auto_api2/apifoxcli/sync_report.py`
- `tests_phase4/unit/test_apifoxcli_source_case_loader.py`
- `tests_phase4/unit/test_apifoxcli_case_runner.py`
- `tests_phase4/unit/test_apifoxcli_source_sync_plan.py`
- `tests_phase4/unit/test_apifoxcli_case_source_cli.py`
- `tests_phase4/unit/test_apifoxcli_sync_impact.py`
- `tests_phase4/integration/test_apifoxcli_case_flow_suite.py`
- `tests_phase4/integration/test_apifoxcli_source_sync_apply.py`
- `tests_phase4/integration/test_apifoxcli_project_import_openapi_full_sync.py`

**Modify:**

- `pytest_auto_api2/apifoxcli/models.py`
- `pytest_auto_api2/apifoxcli/scaffold.py`
- `pytest_auto_api2/apifoxcli/loader.py`
- `pytest_auto_api2/apifoxcli/validator.py`
- `pytest_auto_api2/apifoxcli/context.py`
- `pytest_auto_api2/apifoxcli/resolver.py`
- `pytest_auto_api2/apifoxcli/planner.py`
- `pytest_auto_api2/apifoxcli/runner.py`
- `pytest_auto_api2/apifoxcli/cli.py`
- `pytest_auto_api2/apifoxcli/openapi_importer.py`
- `pytest_auto_api2/apifoxcli/transport/http.py`
- `tests_phase4/unit/test_apifoxcli_models.py`
- `tests_phase4/unit/test_apifoxcli_loader_validator.py`
- `tests_phase4/unit/test_apifoxcli_openapi_import.py`
- `tests_phase4/integration/test_apifoxcli_flow_auth_chain.py`
- `tests_phase4/integration/test_apifoxcli_suite_run.py`

### Task 1: Add `source` and `case` canonical resources

**Files:**
- Modify: `pytest_auto_api2/apifoxcli/models.py`
- Modify: `pytest_auto_api2/apifoxcli/scaffold.py`
- Modify: `pytest_auto_api2/apifoxcli/loader.py`
- Modify: `pytest_auto_api2/apifoxcli/validator.py`
- Modify: `tests_phase4/unit/test_apifoxcli_models.py`
- Modify: `tests_phase4/unit/test_apifoxcli_loader_validator.py`
- Test: `tests_phase4/unit/test_apifoxcli_source_case_loader.py`

- [ ] **Step 1: Write the failing model, scaffold, loader, and validator tests**

```python
from pytest_auto_api2.apifoxcli.cli import main
from pytest_auto_api2.apifoxcli.loader import load_project
from pytest_auto_api2.apifoxcli.validator import validate_project


def test_project_init_creates_sources_and_cases_layout(tmp_path):
    root = tmp_path / "demo"
    assert main(["project", "init", "--project-root", str(root)]) == 0
    assert (root / "apifox" / "sources").exists()
    assert (root / "apifox" / "cases").exists()


def test_loader_reads_source_case_and_case_refs(tmp_path):
    apifox = tmp_path / "apifox"
    for rel in ("sources", "envs", "apis", "cases", "flows", "suites"):
        (apifox / rel).mkdir(parents=True, exist_ok=True)

    (apifox / "project.yaml").write_text(
        "kind: project\nid: default\nname: demo\nspec:\n  defaultEnv: qa\n",
        encoding="utf-8",
    )
    (apifox / "sources" / "demo-openapi.yaml").write_text(
        "kind: source\nid: demo-openapi\nname: demo\nspec:\n  type: openapi\n  url: https://demo.example/openapi.json\n  syncMode: full\n  includePaths: []\n  excludePaths: []\n  tagMap: {}\n  guards:\n    maxRemoveCount: 20\n    maxRemoveRatio: 0.2\n",
        encoding="utf-8",
    )
    (apifox / "envs" / "qa.yaml").write_text(
        "kind: env\nid: qa\nname: QA\nspec:\n  baseUrl: https://demo.example/dev-api\n  headers: {}\n  variables: {}\n",
        encoding="utf-8",
    )
    (apifox / "apis" / "auth" / "login.yaml").parent.mkdir(parents=True, exist_ok=True)
    (apifox / "apis" / "auth" / "login.yaml").write_text(
        "kind: api\nid: auth.login\nname: login\nmeta:\n  module: auth\n  sync:\n    sourceId: demo-openapi\n    syncKey: login_post\n    lifecycle: active\nspec:\n  protocol: http\n  contract:\n    request:\n      method: POST\n      path: /login\n      contentType: application/x-www-form-urlencoded\n      formSchema:\n        username:\n          type: string\n          required: true\n        password:\n          type: string\n          required: true\n    responses:\n      '200': {}\n",
        encoding="utf-8",
    )
    (apifox / "cases" / "auth" / "login-success.yaml").parent.mkdir(parents=True, exist_ok=True)
    (apifox / "cases" / "auth" / "login-success.yaml").write_text(
        "kind: case\nid: auth.login.success\nname: login success\nspec:\n  apiRef: auth.login\n  envRef: qa\n  request:\n    form:\n      username: guest\n      password: 123456\n  expect:\n    status: 200\n    assertions: []\n  extract: []\n",
        encoding="utf-8",
    )
    (apifox / "flows" / "auth-bootstrap.yaml").write_text(
        "kind: flow\nid: auth.bootstrap\nname: auth bootstrap\nspec:\n  envRef: qa\n  steps:\n    - caseRef: auth.login.success\n",
        encoding="utf-8",
    )
    (apifox / "suites" / "smoke.yaml").write_text(
        "kind: suite\nid: smoke\nname: smoke\nspec:\n  envRef: qa\n  failFast: true\n  concurrency: 1\n  items:\n    - caseRef: auth.login.success\n    - flowRef: auth.bootstrap\n",
        encoding="utf-8",
    )

    project = load_project(tmp_path)
    assert "demo-openapi" in project.sources
    assert "auth.login.success" in project.cases
    assert project.flows["auth.bootstrap"].spec.steps[0].caseRef == "auth.login.success"
    assert project.suites["smoke"].spec.items[0].caseRef == "auth.login.success"


def test_validator_rejects_missing_case_reference(tmp_path):
    apifox = tmp_path / "apifox"
    for rel in ("envs", "flows", "suites"):
        (apifox / rel).mkdir(parents=True, exist_ok=True)

    (apifox / "project.yaml").write_text(
        "kind: project\nid: default\nname: demo\nspec:\n  defaultEnv: qa\n",
        encoding="utf-8",
    )
    (apifox / "envs" / "qa.yaml").write_text(
        "kind: env\nid: qa\nname: QA\nspec:\n  baseUrl: http://example.com\n  headers: {}\n  variables: {}\n",
        encoding="utf-8",
    )
    (apifox / "flows" / "broken.yaml").write_text(
        "kind: flow\nid: broken\nname: broken\nspec:\n  steps:\n    - caseRef: missing.case\n",
        encoding="utf-8",
    )

    project = load_project(tmp_path)
    errors = validate_project(project)
    assert any("caseRef not found" in item for item in errors)
```

- [ ] **Step 2: Run tests to verify they fail**

Run:

```bash
pytest tests_phase4/unit/test_apifoxcli_models.py tests_phase4/unit/test_apifoxcli_loader_validator.py tests_phase4/unit/test_apifoxcli_source_case_loader.py -v
```

Expected:

- `ValidationError` or `AttributeError` because `source` and `case` models do not exist
- validator still checks `apiRef` for flows and suites instead of `caseRef`
- scaffold does not create `sources/` or `cases/`

- [ ] **Step 3: Write minimal implementation**

```python
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


class ApiSpec(BaseModel):
    protocol: Literal["http"] = "http"
    contract: Dict[str, object]


class CaseSpec(BaseModel):
    apiRef: str
    envRef: Optional[str] = None
    datasetRef: Optional[str] = None
    request: Dict[str, object] = Field(default_factory=dict)
    expect: Dict[str, object] = Field(default_factory=dict)
    extract: List[Dict[str, object]] = Field(default_factory=list)
    hooks: Dict[str, List[Dict[str, object]]] = Field(default_factory=lambda: {"before": [], "after": []})


class FlowStep(BaseModel):
    caseRef: str


class SuiteItem(BaseModel):
    caseRef: Optional[str] = None
    flowRef: Optional[str] = None


class SourceResource(ResourceBase):
    kind: Literal["source"]
    spec: SourceSpec


class CaseResource(ResourceBase):
    kind: Literal["case"]
    spec: CaseSpec


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
```

Implementation details to apply in the same step:

- `scaffold.init_project()` creates `sources/` and `cases/`
- `loader.load_project()` loads `sources/**/*.yaml` and `cases/**/*.yaml`
- `validator.validate_project()` validates `case.apiRef`, `flow.step.caseRef`, and `suite.item.caseRef`

- [ ] **Step 4: Run tests to verify they pass**

Run:

```bash
pytest tests_phase4/unit/test_apifoxcli_models.py tests_phase4/unit/test_apifoxcli_loader_validator.py tests_phase4/unit/test_apifoxcli_source_case_loader.py -v
```

Expected:

- all three files pass
- no regression to the existing `RequestSpec` alias warning coverage

- [ ] **Step 5: Commit**

```bash
git -c safe.directory=D:/code/project/pytest-auto-api2 add pytest_auto_api2/apifoxcli/models.py pytest_auto_api2/apifoxcli/scaffold.py pytest_auto_api2/apifoxcli/loader.py pytest_auto_api2/apifoxcli/validator.py tests_phase4/unit/test_apifoxcli_models.py tests_phase4/unit/test_apifoxcli_loader_validator.py tests_phase4/unit/test_apifoxcli_source_case_loader.py
git -c safe.directory=D:/code/project/pytest-auto-api2 commit -m "feat(apifoxcli): add source and case resources"
```

### Task 2: Add contract-aware case preparation and validation

**Files:**
- Create: `pytest_auto_api2/apifoxcli/contract.py`
- Modify: `pytest_auto_api2/apifoxcli/context.py`
- Modify: `pytest_auto_api2/apifoxcli/resolver.py`
- Modify: `pytest_auto_api2/apifoxcli/transport/http.py`
- Modify: `pytest_auto_api2/apifoxcli/validator.py`
- Test: `tests_phase4/unit/test_apifoxcli_case_runner.py`

- [ ] **Step 1: Write the failing contract preparation tests**

```python
from pytest_auto_api2.apifoxcli.context import RunContext
from pytest_auto_api2.apifoxcli.contract import build_case_request, validate_case_contract
from pytest_auto_api2.apifoxcli.models import ApiResource, CaseResource


def test_build_case_request_merges_env_headers_and_case_form():
    api = ApiResource.model_validate(
        {
            "kind": "api",
            "id": "auth.login",
            "name": "login",
            "spec": {
                "protocol": "http",
                "contract": {
                    "request": {
                        "method": "POST",
                        "path": "/login",
                        "contentType": "application/x-www-form-urlencoded",
                        "formSchema": {
                            "username": {"type": "string", "required": True},
                            "password": {"type": "string", "required": True},
                        },
                    },
                    "responses": {"200": {}},
                },
            },
        }
    )
    case = CaseResource.model_validate(
        {
            "kind": "case",
            "id": "auth.login.success",
            "name": "login success",
            "spec": {
                "apiRef": "auth.login",
                "request": {"form": {"username": "${dataset.username}", "password": "123456"}},
                "expect": {"status": 200, "assertions": []},
                "extract": [],
            },
        }
    )
    context = RunContext(
        env={"baseUrl": "https://demo.example/dev-api", "headers": {"Authorization": "Bearer ${context.token}"}, "variables": {}},
        dataset={"username": "guest"},
        values={"token": "abc"},
    )

    prepared = build_case_request(case, api, context)
    assert prepared.method == "POST"
    assert prepared.path == "/login"
    assert prepared.headers["Authorization"] == "Bearer abc"
    assert prepared.form == {"username": "guest", "password": "123456"}


def test_validate_case_contract_reports_missing_required_input():
    api = ApiResource.model_validate(
        {
            "kind": "api",
            "id": "auth.login",
            "name": "login",
            "spec": {
                "protocol": "http",
                "contract": {
                    "request": {
                        "method": "POST",
                        "path": "/login",
                        "contentType": "application/x-www-form-urlencoded",
                        "formSchema": {
                            "username": {"type": "string", "required": True},
                            "password": {"type": "string", "required": True},
                        },
                    },
                    "responses": {"200": {}},
                },
            },
        }
    )
    case = CaseResource.model_validate(
        {
            "kind": "case",
            "id": "auth.login.invalid",
            "name": "login invalid",
            "spec": {
                "apiRef": "auth.login",
                "request": {"form": {"username": "guest"}},
                "expect": {"status": 200, "assertions": []},
                "extract": [],
            },
        }
    )

    errors = validate_case_contract(case, api)
    assert errors == ["missing required form field: password"]
```

- [ ] **Step 2: Run test to verify it fails**

Run:

```bash
pytest tests_phase4/unit/test_apifoxcli_case_runner.py -v
```

Expected:

- import failure for `contract.py`
- or missing `build_case_request` / `validate_case_contract`

- [ ] **Step 3: Write minimal implementation**

```python
@dataclass
class PreparedRequest:
    method: str
    path: str
    headers: Dict[str, str]
    query: Optional[Dict[str, object]]
    json_body: Optional[Dict[str, object]]
    form: Optional[Dict[str, object]]


def validate_case_contract(case, api) -> List[str]:
    errors: List[str] = []
    request_contract = ((api.spec.contract or {}).get("request") or {})
    form_schema = request_contract.get("formSchema") or {}
    provided_form = ((case.spec.request or {}).get("form") or {})
    for field_name, field_spec in form_schema.items():
        if field_spec.get("required") and field_name not in provided_form:
            errors.append(f"missing required form field: {field_name}")
    return errors


def build_case_request(case, api, context) -> PreparedRequest:
    request_contract = ((api.spec.contract or {}).get("request") or {})
    case_request = case.spec.request or {}
    headers = dict(context.env.get("headers") or {})
    headers.update(case_request.get("headers") or {})
    return PreparedRequest(
        method=request_contract["method"],
        path=request_contract["path"],
        headers=resolve_value(headers, context),
        query=resolve_value(case_request.get("query"), context) if case_request.get("query") else None,
        json_body=resolve_value(case_request.get("json"), context) if case_request.get("json") else None,
        form=resolve_value(case_request.get("form"), context) if case_request.get("form") else None,
    )
```

Implementation details to apply in the same step:

- `RunContext.values` remains the shared extraction/auth store
- `transport/http.py` accepts `PreparedRequest` instead of raw `api.spec.request`
- `validator.validate_project()` walks `case.spec.request` expressions, not `api.spec.request`

- [ ] **Step 4: Run test to verify it passes**

Run:

```bash
pytest tests_phase4/unit/test_apifoxcli_case_runner.py -v
```

Expected:

- both contract preparation tests pass

- [ ] **Step 5: Commit**

```bash
git -c safe.directory=D:/code/project/pytest-auto-api2 add pytest_auto_api2/apifoxcli/contract.py pytest_auto_api2/apifoxcli/context.py pytest_auto_api2/apifoxcli/resolver.py pytest_auto_api2/apifoxcli/transport/http.py pytest_auto_api2/apifoxcli/validator.py tests_phase4/unit/test_apifoxcli_case_runner.py
git -c safe.directory=D:/code/project/pytest-auto-api2 commit -m "feat(apifoxcli): add case contract preparation"
```

### Task 3: Migrate runner, flow, and suite to `caseRef`

**Files:**
- Modify: `pytest_auto_api2/apifoxcli/planner.py`
- Modify: `pytest_auto_api2/apifoxcli/runner.py`
- Modify: `pytest_auto_api2/apifoxcli/cli.py`
- Modify: `tests_phase4/integration/test_apifoxcli_flow_auth_chain.py`
- Modify: `tests_phase4/integration/test_apifoxcli_suite_run.py`
- Test: `tests_phase4/integration/test_apifoxcli_case_flow_suite.py`

- [ ] **Step 1: Write the failing planner and integration tests**

```python
import json
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer
from urllib.parse import parse_qs

from pytest_auto_api2.apifoxcli.cli import main


class DemoHandler(BaseHTTPRequestHandler):
    def do_POST(self):
        body = self.rfile.read(int(self.headers["Content-Length"])).decode("utf-8")
        form = parse_qs(body)
        encoded = json.dumps({"code": 200, "token": f"token-{form['username'][0]}"}).encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(encoded)))
        self.end_headers()
        self.wfile.write(encoded)

    def do_GET(self):
        encoded = json.dumps({"code": 200, "user": {"userName": "alice"}}).encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(encoded)))
        self.end_headers()
        self.wfile.write(encoded)

    def log_message(self, *_args):
        return


def test_case_flow_and_suite_run_use_case_refs(tmp_path):
    server = HTTPServer(("127.0.0.1", 0), DemoHandler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()

    try:
        apifox = tmp_path / "apifox"
        for rel in ("envs", "apis", "cases", "flows", "suites", "datasets"):
            (apifox / rel).mkdir(parents=True, exist_ok=True)

        (apifox / "project.yaml").write_text(
            "kind: project\nid: default\nname: demo\nspec:\n  defaultEnv: qa\n",
            encoding="utf-8",
        )
        (apifox / "envs" / "qa.yaml").write_text(
            f"kind: env\nid: qa\nname: QA\nspec:\n  baseUrl: http://127.0.0.1:{server.server_port}\n  headers:\n    Authorization: Bearer ${{context.token}}\n  variables: {{}}\n",
            encoding="utf-8",
        )
        (apifox / "apis" / "auth-login.yaml").write_text(
            "kind: api\nid: auth.login\nname: login\nspec:\n  protocol: http\n  contract:\n    request:\n      method: POST\n      path: /login\n      contentType: application/x-www-form-urlencoded\n      formSchema:\n        username:\n          type: string\n          required: true\n        password:\n          type: string\n          required: true\n    responses:\n      '200': {}\n",
            encoding="utf-8",
        )
        (apifox / "apis" / "auth-get-info.yaml").write_text(
            "kind: api\nid: auth.get-info\nname: get info\nspec:\n  protocol: http\n  contract:\n    request:\n      method: GET\n      path: /getInfo\n      contentType: application/json\n    responses:\n      '200': {}\n",
            encoding="utf-8",
        )
        (apifox / "cases" / "login-success.yaml").write_text(
            "kind: case\nid: auth.login.success\nname: login success\nspec:\n  apiRef: auth.login\n  request:\n    form:\n      username: ${dataset.username}\n      password: ${dataset.password}\n  expect:\n    status: 200\n    assertions:\n      - id: login-code\n        source: response\n        expr: $.code\n        op: ==\n        value: 200\n  extract:\n    - name: token\n      from: response\n      expr: $.token\n",
            encoding="utf-8",
        )
        (apifox / "cases" / "get-info.yaml").write_text(
            "kind: case\nid: auth.get-info.smoke\nname: get info\nspec:\n  apiRef: auth.get-info\n  request: {}\n  expect:\n    status: 200\n    assertions:\n      - id: user-name\n        source: response\n        expr: $.user.userName\n        op: ==\n        value: alice\n  extract: []\n",
            encoding="utf-8",
        )
        (apifox / "flows" / "bootstrap.yaml").write_text(
            "kind: flow\nid: auth.bootstrap\nname: bootstrap\nspec:\n  steps:\n    - caseRef: auth.login.success\n    - caseRef: auth.get-info.smoke\n",
            encoding="utf-8",
        )
        (apifox / "datasets" / "users.yaml").write_text(
            "kind: dataset\nid: auth.users\nname: users\nspec:\n  rows:\n    - username: alice\n      password: secret\n",
            encoding="utf-8",
        )
        (apifox / "suites" / "smoke.yaml").write_text(
            "kind: suite\nid: smoke\nname: smoke\nspec:\n  failFast: true\n  concurrency: 1\n  items:\n    - caseRef: auth.login.success\n      datasetRef: auth.users\n    - flowRef: auth.bootstrap\n      datasetRef: auth.users\n",
            encoding="utf-8",
        )

        assert main(["case", "run", "auth.login.success", "--project-root", str(tmp_path), "--dataset", "auth.users", "--json"]) == 0
        assert main(["flow", "run", "auth.bootstrap", "--project-root", str(tmp_path), "--dataset", "auth.users", "--json"]) == 0
        assert main(["suite", "run", "smoke", "--project-root", str(tmp_path), "--json"]) == 0
    finally:
        server.shutdown()
        thread.join()
```

- [ ] **Step 2: Run test to verify it fails**

Run:

```bash
pytest tests_phase4/integration/test_apifoxcli_case_flow_suite.py tests_phase4/integration/test_apifoxcli_flow_auth_chain.py tests_phase4/integration/test_apifoxcli_suite_run.py -v
```

Expected:

- parser does not know `case run`
- planner still expands `apiRef`
- runner still executes `api` resources directly

- [ ] **Step 3: Write minimal implementation**

```python
def build_case_plan(project: LoadedProject, case_id: str, env_override: Optional[str], dataset_ref: Optional[str] = None) -> ExecutionPlan:
    case = project.cases[case_id]
    env_id = env_override or case.spec.envRef or project.project.spec.defaultEnv
    rows = _expand_dataset(project, dataset_ref or case.spec.datasetRef)
    return ExecutionPlan(
        nodes=[
            PlanNode(
                kind="case",
                resource_id=case_id,
                env_id=env_id,
                dataset=row,
                context_key=f"case:{case_id}:{row_index}",
            )
            for row_index, row in enumerate(rows)
        ]
    )


def run_case(project, case_id: str, env_override: Optional[str] = None, dataset_ref: Optional[str] = None) -> RunSummary:
    return _execute_plan(project, build_case_plan(project, case_id, env_override, dataset_ref))


def _execute_case_node(project, node: PlanNode, contexts: Dict[str, RunContext]) -> Dict[str, object]:
    case = project.cases[node.resource_id]
    api = project.apis[case.spec.apiRef]
    context = contexts.setdefault(
        node.context_key,
        RunContext(env=project.envs[node.env_id].spec.model_dump(), dataset=node.dataset),
    )
    context.dataset = node.dataset
    contract_errors = validate_case_contract(case, api)
    if contract_errors:
        raise AssertionError("; ".join(contract_errors))
    prepared = build_case_request(case, api, context)
    response = execute_http_api(prepared, context)
    assert_response(case.spec.expect, response, context.values)
    apply_extractors(case.spec.extract, response, context)
    return {"resource_id": node.resource_id, "status_code": response.status_code}
```

Implementation details to apply in the same step:

- `planner.build_flow_plan()` expands `flow.spec.steps[*].caseRef`
- `planner.build_suite_plan()` expands `suite.spec.items[*].caseRef` and `flowRef`
- `cli.build_parser()` adds `case run`
- existing integration fixtures in `test_apifoxcli_flow_auth_chain.py` and `test_apifoxcli_suite_run.py` are rewritten from `api` execution to `case` execution

- [ ] **Step 4: Run tests to verify they pass**

Run:

```bash
pytest tests_phase4/unit/test_apifoxcli_case_runner.py tests_phase4/integration/test_apifoxcli_case_flow_suite.py tests_phase4/integration/test_apifoxcli_flow_auth_chain.py tests_phase4/integration/test_apifoxcli_suite_run.py -v
```

Expected:

- all case, flow, and suite execution tests pass through `caseRef`
- extracted token continues to flow through `context.token`

- [ ] **Step 5: Commit**

```bash
git -c safe.directory=D:/code/project/pytest-auto-api2 add pytest_auto_api2/apifoxcli/planner.py pytest_auto_api2/apifoxcli/runner.py pytest_auto_api2/apifoxcli/cli.py tests_phase4/integration/test_apifoxcli_case_flow_suite.py tests_phase4/integration/test_apifoxcli_flow_auth_chain.py tests_phase4/integration/test_apifoxcli_suite_run.py
git -c safe.directory=D:/code/project/pytest-auto-api2 commit -m "refactor(apifoxcli): run flow and suite through case refs"
```

### Task 4: Add OpenAPI normalization and full-sync diff planning

**Files:**
- Create: `pytest_auto_api2/apifoxcli/source_sync.py`
- Modify: `pytest_auto_api2/apifoxcli/openapi_importer.py`
- Test: `tests_phase4/unit/test_apifoxcli_source_sync_plan.py`

- [ ] **Step 1: Write the failing sync planning tests**

```python
from pathlib import Path

from pytest_auto_api2.apifoxcli.loader import load_project
from pytest_auto_api2.apifoxcli.source_sync import normalize_openapi_document, plan_source_sync


def test_plan_source_sync_detects_created_updated_and_removed_api(tmp_path):
    apifox = tmp_path / "apifox"
    for rel in ("sources", "envs", "apis"):
        (apifox / rel).mkdir(parents=True, exist_ok=True)

    (apifox / "project.yaml").write_text(
        "kind: project\nid: default\nname: demo\nspec:\n  defaultEnv: qa\n",
        encoding="utf-8",
    )
    (apifox / "sources" / "demo-openapi.yaml").write_text(
        "kind: source\nid: demo-openapi\nname: demo\nspec:\n  type: openapi\n  url: https://demo.example/openapi.json\n  syncMode: full\n  includePaths: []\n  excludePaths: []\n  tagMap:\n    登录模块: auth\n  guards:\n    maxRemoveCount: 20\n    maxRemoveRatio: 0.2\n",
        encoding="utf-8",
    )
    (apifox / "envs" / "qa.yaml").write_text(
        "kind: env\nid: qa\nname: QA\nspec:\n  baseUrl: https://demo.example/dev-api\n  headers: {}\n  variables: {}\n",
        encoding="utf-8",
    )
    (apifox / "apis" / "auth" / "login.yaml").parent.mkdir(parents=True, exist_ok=True)
    (apifox / "apis" / "auth" / "login.yaml").write_text(
        "kind: api\nid: auth.login\nname: Login\nmeta:\n  module: auth\n  tags:\n    - 登录模块\n  sync:\n    sourceId: demo-openapi\n    syncKey: login_post\n    upstreamMethod: POST\n    upstreamPath: /login\n    lifecycle: active\nspec:\n  protocol: http\n  contract:\n    request:\n      method: POST\n      path: /login\n      contentType: application/x-www-form-urlencoded\n      formSchema:\n        username:\n          type: string\n          required: true\n        password:\n          type: string\n          required: true\n    responses:\n      '200': {}\n",
        encoding="utf-8",
    )
    (apifox / "apis" / "auth" / "removed.yaml").write_text(
        "kind: api\nid: auth.removed\nname: Removed\nmeta:\n  module: auth\n  tags:\n    - 登录模块\n  sync:\n    sourceId: demo-openapi\n    syncKey: removed_get\n    upstreamMethod: GET\n    upstreamPath: /removed\n    lifecycle: active\nspec:\n  protocol: http\n  contract:\n    request:\n      method: GET\n      path: /removed\n      contentType: application/json\n    responses:\n      '200': {}\n",
        encoding="utf-8",
    )

    project = load_project(tmp_path)
    document = {
        "openapi": "3.0.3",
        "paths": {
            "/login": {
                "post": {
                    "operationId": "login_post",
                    "summary": "Login",
                    "tags": ["登录模块"],
                    "requestBody": {
                        "content": {
                            "application/x-www-form-urlencoded": {
                                "schema": {
                                    "type": "object",
                                    "required": ["username", "password", "tenantId"],
                                    "properties": {
                                        "username": {"type": "string"},
                                        "password": {"type": "string"},
                                        "tenantId": {"type": "string"},
                                    },
                                }
                            }
                        }
                    },
                    "responses": {"200": {"description": "ok"}},
                }
            },
            "/getInfo": {
                "get": {
                    "operationId": "get_info_get",
                    "summary": "Get Info",
                    "tags": ["登录模块"],
                    "responses": {"200": {"description": "ok"}},
                }
            },
        },
    }

    normalized = normalize_openapi_document(project.sources["demo-openapi"], document)
    plan = plan_source_sync(project, "demo-openapi", normalized)

    assert [item.api_id for item in plan.created] == ["auth.get-info"]
    assert [item.api_id for item in plan.updated] == ["auth.login"]
    assert [item.api_id for item in plan.upstream_removed] == ["auth.removed"]
    assert plan.updated[0].diffs[0].kind == "request.requiredAdded"
    assert plan.updated[0].diffs[0].field == "tenantId"
```

- [ ] **Step 2: Run test to verify it fails**

Run:

```bash
pytest tests_phase4/unit/test_apifoxcli_source_sync_plan.py -v
```

Expected:

- import failure for `source_sync.py`
- or missing `normalize_openapi_document` / `plan_source_sync`

- [ ] **Step 3: Write minimal implementation**

```python
@dataclass
class NormalizedOperation:
    api_id: str
    module: str
    sync_key: str
    method: str
    path: str
    tags: List[str]
    contract: Dict[str, object]


@dataclass
class SyncDiff:
    kind: str
    field: str
    breaking: bool


@dataclass
class SyncCandidate:
    api_id: str
    module: str
    sync_key: str
    contract: Dict[str, object]
    diffs: List[SyncDiff]


@dataclass
class SyncPlan:
    created: List[SyncCandidate] = field(default_factory=list)
    updated: List[SyncCandidate] = field(default_factory=list)
    upstream_removed: List[SyncCandidate] = field(default_factory=list)
    unchanged: List[SyncCandidate] = field(default_factory=list)


def plan_source_sync(project: LoadedProject, source_id: str, operations: List[NormalizedOperation]) -> SyncPlan:
    local_apis = {
        api.id: api
        for api in project.apis.values()
        if ((api.meta or {}).get("sync") or {}).get("sourceId") == source_id
    }
    by_sync_key = {((api.meta or {}).get("sync") or {}).get("syncKey"): api for api in local_apis.values()}
    plan = SyncPlan()
    seen_api_ids: Set[str] = set()
    for operation in operations:
        local_api = by_sync_key.get(operation.sync_key)
        if local_api is None:
            plan.created.append(SyncCandidate(api_id=operation.api_id, module=operation.module, sync_key=operation.sync_key, contract=operation.contract, diffs=[]))
            continue
        seen_api_ids.add(local_api.id)
        diffs = diff_api_contract(local_api.spec.contract, operation.contract)
        target = plan.unchanged if not diffs else plan.updated
        target.append(SyncCandidate(api_id=local_api.id, module=operation.module, sync_key=operation.sync_key, contract=operation.contract, diffs=diffs))
    for api_id, api in local_apis.items():
        if api_id not in seen_api_ids:
            plan.upstream_removed.append(
                SyncCandidate(
                    api_id=api_id,
                    module=(api.meta or {}).get("module", "_default"),
                    sync_key=((api.meta or {}).get("sync") or {}).get("syncKey", ""),
                    contract=api.spec.contract,
                    diffs=[],
                )
            )
    return plan


def diff_api_contract(current: Dict[str, object], incoming: Dict[str, object]) -> List[SyncDiff]:
    diffs: List[SyncDiff] = []
    current_schema = (((current or {}).get("request") or {}).get("formSchema") or {})
    incoming_schema = (((incoming or {}).get("request") or {}).get("formSchema") or {})
    for field_name, field_spec in incoming_schema.items():
        if field_name not in current_schema and field_spec.get("required"):
            diffs.append(SyncDiff(kind="request.requiredAdded", field=field_name, breaking=True))
    for field_name in current_schema:
        if field_name not in incoming_schema:
            diffs.append(SyncDiff(kind="request.fieldRemoved", field=field_name, breaking=True))
    return diffs
```

Implementation details to apply in the same step:

- `openapi_importer.py` keeps document loading, server selection, and schema normalization helpers
- `normalize_openapi_document()` maps tags to module folders via `source.spec.tagMap`
- stable matching order is `sourceId + operationId`, then `sourceId + method + path`, then explicit rebind mapping from the `source` resource

- [ ] **Step 4: Run test to verify it passes**

Run:

```bash
pytest tests_phase4/unit/test_apifoxcli_source_sync_plan.py -v
```

Expected:

- sync plan test passes with one created, one updated, and one upstream removed API

- [ ] **Step 5: Commit**

```bash
git -c safe.directory=D:/code/project/pytest-auto-api2 add pytest_auto_api2/apifoxcli/source_sync.py pytest_auto_api2/apifoxcli/openapi_importer.py tests_phase4/unit/test_apifoxcli_source_sync_plan.py
git -c safe.directory=D:/code/project/pytest-auto-api2 commit -m "feat(apifoxcli): plan full source sync"
```

### Task 5: Apply full sync, tag-module writes, and sync reports

**Files:**
- Modify: `pytest_auto_api2/apifoxcli/source_sync.py`
- Create: `pytest_auto_api2/apifoxcli/sync_report.py`
- Test: `tests_phase4/integration/test_apifoxcli_source_sync_apply.py`

- [ ] **Step 1: Write the failing sync apply integration test**

```python
from pathlib import Path

import yaml

from pytest_auto_api2.apifoxcli.loader import load_project
from pytest_auto_api2.apifoxcli.source_sync import apply_source_sync, normalize_openapi_document, plan_source_sync


def test_apply_source_sync_writes_tag_modules_and_marks_removed_without_touching_cases(tmp_path):
    apifox = tmp_path / "apifox"
    for rel in ("sources", "envs", "apis", "cases", "reports/sync"):
        (apifox / rel).mkdir(parents=True, exist_ok=True)

    (apifox / "project.yaml").write_text(
        "kind: project\nid: default\nname: demo\nspec:\n  defaultEnv: qa\n",
        encoding="utf-8",
    )
    (apifox / "sources" / "demo-openapi.yaml").write_text(
        "kind: source\nid: demo-openapi\nname: demo\nspec:\n  type: openapi\n  url: https://demo.example/openapi.json\n  syncMode: full\n  includePaths: []\n  excludePaths: []\n  tagMap:\n    登录模块: auth\n  guards:\n    maxRemoveCount: 20\n    maxRemoveRatio: 0.2\n",
        encoding="utf-8",
    )
    (apifox / "envs" / "qa.yaml").write_text(
        "kind: env\nid: qa\nname: QA\nspec:\n  baseUrl: https://demo.example/dev-api\n  headers: {}\n  variables: {}\n",
        encoding="utf-8",
    )
    (apifox / "apis" / "auth" / "login.yaml").parent.mkdir(parents=True, exist_ok=True)
    (apifox / "apis" / "auth" / "login.yaml").write_text(
        "kind: api\nid: auth.login\nname: Login\nmeta:\n  module: auth\n  tags:\n    - 登录模块\n  sync:\n    sourceId: demo-openapi\n    syncKey: login_post\n    lifecycle: active\nspec:\n  protocol: http\n  contract:\n    request:\n      method: POST\n      path: /login\n      contentType: application/x-www-form-urlencoded\n      formSchema:\n        username:\n          type: string\n          required: true\n        password:\n          type: string\n          required: true\n    responses:\n      '200': {}\n",
        encoding="utf-8",
    )
    (apifox / "cases" / "login-success.yaml").write_text(
        "kind: case\nid: auth.login.success\nname: login success\nmeta:\n  audit:\n    status: healthy\n    reasons: []\nspec:\n  apiRef: auth.login\n  request:\n    form:\n      username: guest\n      password: 123456\n  expect:\n    status: 200\n    assertions: []\n  extract: []\n",
        encoding="utf-8",
    )

    project = load_project(tmp_path)
    document = {
        "openapi": "3.0.3",
        "paths": {
            "/login": {
                "post": {
                    "operationId": "login_post",
                    "summary": "Login",
                    "tags": ["登录模块"],
                    "requestBody": {
                        "content": {
                            "application/x-www-form-urlencoded": {
                                "schema": {
                                    "type": "object",
                                    "required": ["username", "password", "tenantId"],
                                    "properties": {
                                        "username": {"type": "string"},
                                        "password": {"type": "string"},
                                        "tenantId": {"type": "string"},
                                    },
                                }
                            }
                        }
                    },
                    "responses": {"200": {"description": "ok"}},
                }
            }
        },
    }

    normalized = normalize_openapi_document(project.sources["demo-openapi"], document)
    plan = plan_source_sync(project, "demo-openapi", normalized)
    report = apply_source_sync(project, "demo-openapi", plan)

    login_yaml = yaml.safe_load((apifox / "apis" / "auth" / "login.yaml").read_text(encoding="utf-8"))
    case_yaml = yaml.safe_load((apifox / "cases" / "login-success.yaml").read_text(encoding="utf-8"))
    assert login_yaml["meta"]["module"] == "auth"
    assert login_yaml["meta"]["sync"]["lifecycle"] == "active"
    assert "tenantId" in login_yaml["spec"]["contract"]["request"]["formSchema"]
    assert case_yaml["spec"]["request"]["form"] == {"username": "guest", "password": 123456}
    assert report.summary["updatedApis"] == 1
    assert (apifox / "reports" / "sync").exists()
```

- [ ] **Step 2: Run test to verify it fails**

Run:

```bash
pytest tests_phase4/integration/test_apifoxcli_source_sync_apply.py -v
```

Expected:

- no `apply_source_sync`
- no sync report writer
- no tag-module file writer

- [ ] **Step 3: Write minimal implementation**

```python
@dataclass
class SyncReport:
    source_id: str
    summary: Dict[str, int]
    impacts: Dict[str, List[Dict[str, object]]]


def apply_source_sync(project: LoadedProject, source_id: str, plan: SyncPlan, prune: bool = False) -> SyncReport:
    root = project.root / "apifox"
    for item in plan.created + plan.updated:
        payload = render_api_resource(project, source_id, item)
        write_api_resource(root / "apis", item.module, item.api_id, payload)
    for item in plan.upstream_removed:
        api = project.apis[item.api_id]
        api.meta.setdefault("sync", {})["lifecycle"] = "upstreamRemoved"
        write_api_resource(root / "apis", (api.meta or {}).get("module", "_default"), api.id, api.model_dump(by_alias=True, exclude_none=True))
    report = build_sync_report(project, source_id, plan)
    if prune:
        report.summary["prunedApis"] = 0
    write_sync_report(root / "reports" / "sync", report)
    return report


def write_api_resource(root: Path, module: str, api_id: str, payload: Dict[str, object]) -> None:
    module_root = root / module
    module_root.mkdir(parents=True, exist_ok=True)
    file_name = api_id.split(".")[-1].replace("_", "-")
    path = module_root / f"{file_name}.yaml"
    path.write_text(yaml.safe_dump(payload, allow_unicode=True, sort_keys=False), encoding="utf-8")


def render_api_resource(project: LoadedProject, source_id: str, item: SyncCandidate) -> Dict[str, object]:
    existing = project.apis.get(item.api_id)
    payload = existing.model_dump(by_alias=True, exclude_none=True) if existing else {"kind": "api", "id": item.api_id, "name": item.api_id, "meta": {}, "spec": {"protocol": "http"}}
    payload.setdefault("meta", {})
    payload["meta"]["module"] = item.module
    payload["meta"]["sync"] = {
        "sourceId": source_id,
        "syncKey": item.sync_key,
        "lifecycle": "active",
    }
    payload["spec"]["contract"] = item.contract
    return payload


def build_sync_report(project: LoadedProject, source_id: str, plan: SyncPlan) -> SyncReport:
    impact = analyze_sync_impact(project, plan)
    return SyncReport(
        source_id=source_id,
        summary={
            "createdApis": len(plan.created),
            "updatedApis": len(plan.updated),
            "upstreamRemovedApis": len(plan.upstream_removed),
            "impactedCases": len(impact.cases),
            "impactedFlows": len(impact.flows),
            "impactedSuites": len(impact.suites),
            "prunedApis": 0,
        },
        impacts={"cases": impact.cases, "flows": impact.flows, "suites": impact.suites},
    )


def write_sync_report(root: Path, report: SyncReport) -> None:
    root.mkdir(parents=True, exist_ok=True)
    path = root / f"{report.source_id}.latest.yaml"
    payload = {"source_id": report.source_id, "summary": report.summary, "impacts": report.impacts}
    path.write_text(yaml.safe_dump(payload, allow_unicode=True, sort_keys=False), encoding="utf-8")
```

Implementation details to apply in the same step:

- created and updated APIs are written under `apifox/apis/<module>/`
- same tag on repeated imports always lands in the same module directory
- `upstreamRemoved` marks lifecycle in `api.meta.sync.lifecycle`; it does not delete the file
- `cases/` are not rewritten during sync

- [ ] **Step 4: Run test to verify it passes**

Run:

```bash
pytest tests_phase4/unit/test_apifoxcli_source_sync_plan.py tests_phase4/integration/test_apifoxcli_source_sync_apply.py -v
```

Expected:

- sync plan and apply tests pass
- generated report YAML exists under `apifox/reports/sync/`

- [ ] **Step 5: Commit**

```bash
git -c safe.directory=D:/code/project/pytest-auto-api2 add pytest_auto_api2/apifoxcli/source_sync.py pytest_auto_api2/apifoxcli/sync_report.py tests_phase4/integration/test_apifoxcli_source_sync_apply.py
git -c safe.directory=D:/code/project/pytest-auto-api2 commit -m "feat(apifoxcli): apply source sync and emit reports"
```

### Task 6: Add `source` and `case` CLI commands and rewire `project import-openapi`

**Files:**
- Modify: `pytest_auto_api2/apifoxcli/cli.py`
- Modify: `pytest_auto_api2/apifoxcli/openapi_importer.py`
- Modify: `pytest_auto_api2/apifoxcli/source_sync.py`
- Test: `tests_phase4/unit/test_apifoxcli_case_source_cli.py`
- Test: `tests_phase4/integration/test_apifoxcli_project_import_openapi_full_sync.py`

- [ ] **Step 1: Write the failing CLI and bootstrap integration tests**

```python
import json

from pytest_auto_api2.apifoxcli.cli import build_parser, main
from pytest_auto_api2.apifoxcli.loader import load_project


def test_build_parser_supports_case_and_source_commands():
    parser = build_parser()
    case_args = parser.parse_args(["case", "run", "auth.login.success", "--env", "qa", "--dataset", "auth.users"])
    sync_args = parser.parse_args(["source", "sync", "demo-openapi", "--apply"])
    status_args = parser.parse_args(["source", "status", "demo-openapi"])
    rebind_args = parser.parse_args(["source", "rebind", "demo-openapi", "--api-id", "auth.login", "--sync-key", "login_post"])

    assert case_args.resource == "case"
    assert case_args.action == "run"
    assert sync_args.resource == "source"
    assert sync_args.action == "sync"
    assert sync_args.apply is True
    assert status_args.action == "status"
    assert rebind_args.action == "rebind"


def test_project_import_openapi_bootstraps_source_and_full_sync(tmp_path):
    root = tmp_path / "demo"
    assert main(["project", "init", "--project-root", str(root)]) == 0
    spec = {
        "openapi": "3.0.3",
        "servers": [{"url": "https://demo.example/dev-api", "description": "qa"}],
        "paths": {
            "/login": {
                "post": {
                    "operationId": "login_post",
                    "summary": "Login",
                    "tags": ["登录模块"],
                    "requestBody": {
                        "content": {
                            "application/x-www-form-urlencoded": {
                                "schema": {
                                    "type": "object",
                                    "required": ["username", "password"],
                                    "properties": {
                                        "username": {"type": "string"},
                                        "password": {"type": "string"},
                                    },
                                }
                            }
                        }
                    },
                    "responses": {"200": {"description": "ok"}},
                }
            }
        },
    }
    source_path = tmp_path / "openapi.json"
    source_path.write_text(json.dumps(spec), encoding="utf-8")

    exit_code = main(
        [
            "project",
            "import-openapi",
            "--project-root",
            str(root),
            "--source",
            str(source_path),
            "--source-id",
            "demo-openapi",
            "--server-description",
            "qa",
        ]
    )

    project = load_project(root)
    assert exit_code == 0
    assert "demo-openapi" in project.sources
    assert "auth.login" in project.apis
```

- [ ] **Step 2: Run test to verify it fails**

Run:

```bash
pytest tests_phase4/unit/test_apifoxcli_case_source_cli.py tests_phase4/integration/test_apifoxcli_project_import_openapi_full_sync.py -v
```

Expected:

- parser does not support `source sync`, `source status`, or `source rebind`
- `project import-openapi` still bypasses `source` and writes `api` files directly

- [ ] **Step 3: Write minimal implementation**

```python
def _cmd_project_import_openapi(args: argparse.Namespace) -> int:
    bootstrap_openapi_source(
        root=Path(args.project_root),
        source_id=args.source_id,
        source=args.source,
        server_description=args.server_description,
        server_url=args.server_url,
        include_paths=args.include_path,
    )
    return _cmd_source_sync(
        argparse.Namespace(
            project_root=args.project_root,
            resource_id=args.source_id,
            apply=True,
            plan=False,
            prune=False,
        )
    )


def _cmd_source_sync(args: argparse.Namespace) -> int:
    project = load_project(Path(args.project_root))
    source = project.sources[args.resource_id]
    document = load_openapi_document(source.spec.url)
    normalized = normalize_openapi_document(source, document)
    plan = plan_source_sync(project, args.resource_id, normalized)
    report = apply_source_sync(project, args.resource_id, plan, prune=args.prune) if args.apply else build_sync_report(project, args.resource_id, plan)
    if args.json:
        _emit_json(report)
    return 0


def _cmd_source_status(args: argparse.Namespace) -> int:
    report = read_latest_sync_report(Path(args.project_root), args.resource_id)
    if args.json:
        _emit_json(report)
    return 0


def _cmd_source_rebind(args: argparse.Namespace) -> int:
    upsert_source_rebind(Path(args.project_root), args.resource_id, args.api_id, args.sync_key)
    return 0


def _cmd_case_run(args: argparse.Namespace) -> int:
    project = load_project(Path(args.project_root))
    summary = run_case(project, args.resource_id, args.env, args.dataset)
    if args.json:
        _emit_json(summary)
    return 0 if summary.failed == 0 else 1


def bootstrap_openapi_source(root: Path, source_id: str, source: str, server_description: Optional[str], server_url: Optional[str], include_paths: List[str]) -> None:
    upsert_source_resource(
        root=root,
        source_id=source_id,
        source=source,
        server_description=server_description,
        server_url=server_url,
        include_paths=include_paths,
    )


def upsert_source_resource(root: Path, source_id: str, source: str, server_description: Optional[str], server_url: Optional[str], include_paths: List[str]) -> None:
    apifox = root / "apifox" / "sources"
    apifox.mkdir(parents=True, exist_ok=True)
    payload = {
        "kind": "source",
        "id": source_id,
        "name": source_id,
        "spec": {
            "type": "openapi",
            "url": source,
            "serverDescription": server_description,
            "serverUrl": server_url,
            "syncMode": "full",
            "includePaths": include_paths,
            "excludePaths": [],
            "tagMap": {},
            "guards": {"maxRemoveCount": 20, "maxRemoveRatio": 0.2},
            "rebinds": {},
        },
    }
    (apifox / f"{source_id}.yaml").write_text(yaml.safe_dump(payload, allow_unicode=True, sort_keys=False), encoding="utf-8")


def upsert_source_rebind(root: Path, source_id: str, api_id: str, sync_key: str) -> None:
    path = root / "apifox" / "sources" / f"{source_id}.yaml"
    payload = yaml.safe_load(path.read_text(encoding="utf-8"))
    payload.setdefault("spec", {}).setdefault("rebinds", {})[sync_key] = api_id
    path.write_text(yaml.safe_dump(payload, allow_unicode=True, sort_keys=False), encoding="utf-8")


def read_latest_sync_report(root: Path, source_id: str) -> Dict[str, object]:
    path = root / "apifox" / "reports" / "sync" / f"{source_id}.latest.yaml"
    return yaml.safe_load(path.read_text(encoding="utf-8"))


def load_openapi_document(source: str) -> Dict[str, object]:
    return _load_document(source)
```

Implementation details to apply in the same step:

- `source sync` defaults to plan mode when `--apply` is absent
- `source status` reads the latest sync report for one source
- `source rebind` persists a sync-key to api-id override on the `source` YAML
- `project import-openapi` becomes a bootstrap convenience command built on the same sync engine

- [ ] **Step 4: Run test to verify it passes**

Run:

```bash
pytest tests_phase4/unit/test_apifoxcli_case_source_cli.py tests_phase4/integration/test_apifoxcli_project_import_openapi_full_sync.py tests_phase4/unit/test_apifoxcli_source_sync_plan.py tests_phase4/integration/test_apifoxcli_source_sync_apply.py -v
```

Expected:

- parser recognizes `case` and `source` commands
- `project import-openapi` creates or updates `source` YAML and performs one full sync

- [ ] **Step 5: Commit**

```bash
git -c safe.directory=D:/code/project/pytest-auto-api2 add pytest_auto_api2/apifoxcli/cli.py pytest_auto_api2/apifoxcli/openapi_importer.py pytest_auto_api2/apifoxcli/source_sync.py tests_phase4/unit/test_apifoxcli_case_source_cli.py tests_phase4/integration/test_apifoxcli_project_import_openapi_full_sync.py
git -c safe.directory=D:/code/project/pytest-auto-api2 commit -m "feat(apifoxcli): add source sync and case run commands"
```

### Task 7: Add impact propagation, audit updates, and prune safety

**Files:**
- Modify: `pytest_auto_api2/apifoxcli/source_sync.py`
- Modify: `pytest_auto_api2/apifoxcli/sync_report.py`
- Modify: `pytest_auto_api2/apifoxcli/validator.py`
- Modify: `tests_phase4/unit/test_apifoxcli_openapi_import.py`
- Test: `tests_phase4/unit/test_apifoxcli_sync_impact.py`

- [ ] **Step 1: Write the failing impact and prune tests**

```python
from pytest_auto_api2.apifoxcli.loader import load_project
from pytest_auto_api2.apifoxcli.source_sync import analyze_sync_impact, apply_source_sync, normalize_openapi_document, plan_source_sync


def test_sync_impact_marks_case_flow_suite_and_blocks_prune_for_referenced_api(tmp_path):
    apifox = tmp_path / "apifox"
    for rel in ("sources", "envs", "apis", "cases", "flows", "suites"):
        (apifox / rel).mkdir(parents=True, exist_ok=True)

    (apifox / "project.yaml").write_text(
        "kind: project\nid: default\nname: demo\nspec:\n  defaultEnv: qa\n",
        encoding="utf-8",
    )
    (apifox / "sources" / "demo-openapi.yaml").write_text(
        "kind: source\nid: demo-openapi\nname: demo\nspec:\n  type: openapi\n  url: https://demo.example/openapi.json\n  syncMode: full\n  includePaths: []\n  excludePaths: []\n  tagMap:\n    登录模块: auth\n  guards:\n    maxRemoveCount: 20\n    maxRemoveRatio: 0.2\n",
        encoding="utf-8",
    )
    (apifox / "envs" / "qa.yaml").write_text(
        "kind: env\nid: qa\nname: QA\nspec:\n  baseUrl: https://demo.example/dev-api\n  headers: {}\n  variables: {}\n",
        encoding="utf-8",
    )
    (apifox / "apis" / "auth-login.yaml").write_text(
        "kind: api\nid: auth.login\nname: Login\nmeta:\n  module: auth\n  sync:\n    sourceId: demo-openapi\n    syncKey: login_post\n    lifecycle: active\nspec:\n  protocol: http\n  contract:\n    request:\n      method: POST\n      path: /login\n      contentType: application/x-www-form-urlencoded\n      formSchema:\n        username:\n          type: string\n          required: true\n        password:\n          type: string\n          required: true\n    responses:\n      '200': {}\n",
        encoding="utf-8",
    )
    (apifox / "cases" / "login-success.yaml").write_text(
        "kind: case\nid: auth.login.success\nname: login success\nmeta:\n  audit:\n    status: healthy\n    reasons: []\nspec:\n  apiRef: auth.login\n  request:\n    form:\n      username: guest\n      password: 123456\n  expect:\n    status: 200\n    assertions: []\n  extract: []\n",
        encoding="utf-8",
    )
    (apifox / "flows" / "bootstrap.yaml").write_text(
        "kind: flow\nid: auth.bootstrap\nname: bootstrap\nspec:\n  steps:\n    - caseRef: auth.login.success\n",
        encoding="utf-8",
    )
    (apifox / "suites" / "smoke.yaml").write_text(
        "kind: suite\nid: smoke\nname: smoke\nspec:\n  failFast: true\n  concurrency: 1\n  items:\n    - flowRef: auth.bootstrap\n",
        encoding="utf-8",
    )

    project = load_project(tmp_path)
    document = {
        "openapi": "3.0.3",
        "paths": {
            "/login": {
                "post": {
                    "operationId": "login_post",
                    "summary": "Login",
                    "tags": ["登录模块"],
                    "requestBody": {
                        "content": {
                            "application/x-www-form-urlencoded": {
                                "schema": {
                                    "type": "object",
                                    "required": ["username", "password", "tenantId"],
                                    "properties": {
                                        "username": {"type": "string"},
                                        "password": {"type": "string"},
                                        "tenantId": {"type": "string"},
                                    },
                                }
                            }
                        }
                    },
                    "responses": {"200": {"description": "ok"}},
                }
            }
        },
    }

    normalized = normalize_openapi_document(project.sources["demo-openapi"], document)
    plan = plan_source_sync(project, "demo-openapi", normalized)
    impact = analyze_sync_impact(project, plan)

    assert impact.cases[0]["caseId"] == "auth.login.success"
    assert impact.cases[0]["reasons"][0]["type"] == "missing_required_input"
    assert impact.flows[0]["flowId"] == "auth.bootstrap"
    assert impact.suites[0]["suiteId"] == "smoke"

    report = apply_source_sync(project, "demo-openapi", plan, prune=True)
    assert report.summary["prunedApis"] == 0
    assert report.summary["impactedCases"] == 1
```

- [ ] **Step 2: Run test to verify it fails**

Run:

```bash
pytest tests_phase4/unit/test_apifoxcli_sync_impact.py -v
```

Expected:

- no `analyze_sync_impact`
- no case audit update
- no prune guard behavior

- [ ] **Step 3: Write minimal implementation**

```python
def analyze_sync_impact(project: LoadedProject, plan: SyncPlan) -> SyncImpact:
    impacted_case_ids: Set[str] = set()
    case_entries: List[Dict[str, object]] = []
    for item in plan.updated:
        reasons = []
        for diff in item.diffs:
            if diff.kind == "request.requiredAdded":
                reasons.append({"type": "missing_required_input", "field": diff.field})
        if not reasons:
            continue
        for case in project.cases.values():
            if case.spec.apiRef != item.api_id:
                continue
            impacted_case_ids.add(case.id)
            case_entries.append({"caseId": case.id, "reasons": reasons})
            case.meta.setdefault("audit", {})["status"] = "impacted"
            case.meta["audit"]["reasons"] = reasons
    flow_entries = [{"flowId": flow.id} for flow in project.flows.values() if any(step.caseRef in impacted_case_ids for step in flow.spec.steps)]
    suite_entries = [
        {"suiteId": suite.id}
        for suite in project.suites.values()
        if any((item.caseRef in impacted_case_ids) or (item.flowRef in {entry['flowId'] for entry in flow_entries}) for item in suite.spec.items)
    ]
    return SyncImpact(cases=case_entries, flows=flow_entries, suites=suite_entries)


def should_prune_api(project: LoadedProject, api_id: str) -> bool:
    referenced_cases = [case.id for case in project.cases.values() if case.spec.apiRef == api_id]
    return not referenced_cases


@dataclass
class SyncImpact:
    cases: List[Dict[str, object]] = field(default_factory=list)
    flows: List[Dict[str, object]] = field(default_factory=list)
    suites: List[Dict[str, object]] = field(default_factory=list)
```

Implementation details to apply in the same step:

- `apply_source_sync(..., prune=True)` only archives or deletes APIs whose lifecycle is `upstreamRemoved` and whose reference graph is empty
- `sync_report.summary` includes `impactedCases`, `impactedFlows`, `impactedSuites`, and `prunedApis`
- `validator.validate_project()` reports `case.meta.audit.status == impacted` with missing references as validation errors, not silent warnings

- [ ] **Step 4: Run tests to verify they pass**

Run:

```bash
pytest tests_phase4/unit/test_apifoxcli_sync_impact.py tests_phase4/unit/test_apifoxcli_openapi_import.py tests_phase4/unit/test_apifoxcli_case_source_cli.py tests_phase4/unit/test_apifoxcli_source_sync_plan.py tests_phase4/integration/test_apifoxcli_source_sync_apply.py -v
pytest tests_phase4 -v
```

Expected:

- impact and prune tests pass
- all phase4 tests pass on the case-first model

- [ ] **Step 5: Commit**

```bash
git -c safe.directory=D:/code/project/pytest-auto-api2 add pytest_auto_api2/apifoxcli/source_sync.py pytest_auto_api2/apifoxcli/sync_report.py pytest_auto_api2/apifoxcli/validator.py tests_phase4/unit/test_apifoxcli_openapi_import.py tests_phase4/unit/test_apifoxcli_sync_impact.py
git -c safe.directory=D:/code/project/pytest-auto-api2 commit -m "test(apifoxcli): add sync impact and prune coverage"
```

## Self-Review

### 1. Spec coverage

Covered by this plan:

- `source` as the persisted OpenAPI sync anchor
- `api` as machine-managed contract storage only
- `case` as the executable test unit
- `flow` referencing `caseRef`
- `suite` referencing `caseRef` and `flowRef`
- `apifoxcli case run`, `flow run`, and `suite run`
- `project import-openapi` bootstrapping `source` and then running full sync
- repeated import diffing by `sourceId + operationId`, then `sourceId + method + path`, then `source` rebind mapping
- tag-based module folders with same-tag merge behavior on repeated sync
- impact propagation from `api` changes to `case`, `flow`, and `suite`
- `upstreamRemoved` lifecycle instead of direct deletion
- guarded prune behavior

Explicitly deferred from the broader product vision, not from this source-sync refactor:

- non-HTTP protocol executors
- mock runtime backends
- secret storage abstractions
- rich report UI adapters

### 2. Placeholder scan

Required scan after saving the plan:

```bash
@'
$tokens = @(
  'T'+'BD',
  'TO'+'DO',
  'implement'+' later',
  'fill in'+' details',
  'similar'+' to',
  'appropriate'+' error handling',
  'edge'+' cases'
)
$path = 'docs/superpowers/plans/2026-04-14-apifoxcli-source-sync-case-plan.md'
$hits = foreach ($token in $tokens) { Select-String -Path $path -Pattern $token }
if ($hits) { $hits; exit 1 }
'@ | powershell -NoProfile -
```

Expected:

- no matches

### 3. Type consistency

Locked names across all tasks:

- resource models: `SourceResource`, `ApiResource`, `CaseResource`
- sync entry points: `normalize_openapi_document`, `plan_source_sync`, `apply_source_sync`, `analyze_sync_impact`
- runner entry points: `run_case`, `run_flow`, `run_suite`
- planner entry points: `build_case_plan`, `build_flow_plan`, `build_suite_plan`
- CLI actions: `case run`, `source sync`, `source status`, `source rebind`, `project import-openapi`
- report types: `SyncPlan`, `SyncReport`, `SyncImpact`

If any of these names drift during implementation, fix the plan first and then continue coding.

## Execution Handoff

Plan complete and saved to `docs/superpowers/plans/2026-04-14-apifoxcli-source-sync-case-plan.md`. Two execution options:

**1. Subagent-Driven (recommended)** - dispatch a fresh worker per task, review between tasks, and keep each commit isolated

**2. Inline Execution** - execute this plan in the current session with checkpoint reviews after each task batch

**Which approach?**
