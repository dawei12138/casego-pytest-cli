# apifoxcli Source Sync And Case Layer Design

## 1. 目标

本文定义 `apifoxcli` 在 Swagger/OpenAPI 导入与长期同步场景下的资源模型、同步策略和执行边界，解决以下问题：

- Swagger 文档默认按全量模式导入和更新
- `api` 资源按 `tag` 分模块存储，多次导入时稳定合并
- `api` 只作为 Swagger 合同 YAML 基座，不再承载完整测试语义
- `case` 作为带测试数据的可执行测试用例，直接交给执行器运行
- 重复导入时，系统能识别本地 `api` 与文档 `api` 的差异，并给出对 `case/flow/suite` 的影响报告

本文是设计文档，不包含实现代码。

## 2. 核心结论

- Swagger 导入默认是 `full` 全量导入模式
- 全量导入的作用域是某个 `source` 资源定义的全部 operation
- `api` 是 machine-managed 的 Swagger 合同基座
- `case` 是 human/AI-managed 的测试资产，直接可执行
- `flow` 优先串联 `caseRef`
- `suite` 组装 `caseRef` 和 `flowRef`
- 重复导入时只自动更新 `api`，不自动改写 `case`
- 差异影响通过结构化 `sync report` 传播到 `case/flow/suite`

## 3. 资源分层

### 3.1 source

`source` 用来描述 Swagger/OpenAPI 的来源和同步策略。

职责：

- 记录导入地址、server 选择、路径过滤、tag 映射
- 定义同步模式和删除策略
- 作为重复导入时的稳定作用域

示例：

```yaml
kind: source
id: demo-openapi
name: demo swagger
spec:
  type: openapi
  url: https://demo.1592653.xyz/openapi.json
  serverUrl: /dev-api
  includePaths: []
  excludePaths: []
  syncMode: full
  missingPolicy: markRemoved
  tagMap:
    登录模块: auth
    系统管理-用户管理: system-user
  guards:
    maxRemoveCount: 20
    maxRemoveRatio: 0.2
```

### 3.2 api

`api` 是 Swagger/OpenAPI 合同的一层 YAML 转换，是执行与测试设计的基座资源。

职责：

- 承载 method/path/content-type/参数结构/响应结构/security 等上游合同
- 记录来源、稳定身份和同步状态
- 作为 `case` 的被引用目标

边界：

- `api` 不直接承载业务测试数据
- `api` 不直接承载完整断言、提取、hook、mock 设计
- `api` 的 `spec.contract` 默认由 Swagger 同步覆盖

示例：

```yaml
kind: api
id: auth.login
name: Login
meta:
  module: auth
  tags:
    - 登录模块
  sync:
    sourceId: demo-openapi
    syncKey: login_login_post
    upstreamMethod: POST
    upstreamPath: /login
    upstreamHash: sha256:...
    lifecycle: active
    drift:
      level: none
      reasons: []
spec:
  protocol: http
  contract:
    request:
      method: POST
      path: /login
      contentType: application/x-www-form-urlencoded
      formSchema:
        username:
          type: string
          required: true
        password:
          type: string
          required: true
        code:
          type: string
          required: false
          default: ""
    responses:
      "200": {}
    security:
      bearer: true
```

### 3.3 case

`case` 是可直接执行的测试实体。

职责：

- 引用 `apiRef`
- 提供请求值
- 承载断言、提取、hook、mock 和可选数据驱动
- 直接交给执行器运行

边界：

- `case` 不负责声明上游接口合同
- `case` 中的请求值必须以 `api.contract` 为校验基准
- Swagger 导入不直接改写 `case.spec`

示例：

```yaml
kind: case
id: auth.login.success
name: login success
meta:
  module: auth
  audit:
    status: healthy
    reasons: []
spec:
  apiRef: auth.login
  envRef: qa
  request:
    form:
      username: guest
      password: 123456
  expect:
    status: 200
    assertions:
      - id: login-code
        source: response
        expr: $.code
        op: ==
        value: 200
  extract:
    - name: token
      from: response
      expr: $.token
  hooks:
    before: []
    after: []
```

### 3.4 flow

`flow` 负责串联 `caseRef`，在单条业务链内共享 runtime context。

示例：

```yaml
kind: flow
id: auth.bootstrap
name: auth bootstrap
meta:
  module: auth
spec:
  envRef: qa
  steps:
    - caseRef: auth.login.success
    - caseRef: auth.get-info.smoke
    - caseRef: auth.get-routers.smoke
```

### 3.5 suite

`suite` 负责调度与编排，不承载业务测试细节。

示例：

```yaml
kind: suite
id: smoke
name: smoke
spec:
  envRef: qa
  failFast: true
  concurrency: 1
  items:
    - caseRef: auth.login.success
    - flowRef: auth.bootstrap
```

## 4. 目录结构

建议目录如下：

```text
apifox/
  project.yaml
  sources/
    demo-openapi.yaml
  apis/
    auth/
      login-login-post.yaml
      get-login-user-info-get.yaml
    system-user/
      get-system-user-list-get.yaml
  cases/
    auth/
      login-success.yaml
      get-info-smoke.yaml
  flows/
    auth/
      bootstrap.yaml
  suites/
    smoke.yaml
  reports/
    sync/
      2026-04-14-demo-openapi.yaml
```

规则：

- `apis/` 按模块分目录
- 模块默认来自 operation 的主 `tag`
- 同名 tag 多次导入，稳定落到同一模块目录
- `cases/` 可按模块分目录，但不要求必须与 `apis/` 同文件名

## 5. Tag 分模块规则

### 5.1 主模块选择

- operation 只有一个 tag 时，使用该 tag
- operation 有多个 tag 时，默认使用第一个 tag 作为主模块
- 其他 tag 保留在 `api.meta.tags`
- 无 tag 时进入 `_default`

### 5.2 tagMap

为了避免中文 tag 或目录名不稳定，允许 `source.spec.tagMap` 显式映射模块名。

示例：

```yaml
tagMap:
  登录模块: auth
  系统管理-用户管理: system-user
```

### 5.3 模块迁移

若某个 operation 的主 tag 变化：

- `api.meta.module` 更新
- `api` 文件移动到新模块目录
- `api.id` 不变
- 所有 `case.apiRef` 不受影响

## 6. 默认全量导入模式

### 6.1 定义

默认同步模式为 `full`。

`full` 的含义是：

- 对某个 `source` 的全部作用域 operation 做完整扫描
- 与本地该 `sourceId` 下全部 `api` 做全量比对
- 上游文档对 `api.spec.contract` 的 machine-managed 区域拥有最终解释权

### 6.2 作用域

`source` 的作用域由以下条件共同决定：

- 文档 URL
- 选定的 `serverUrl` 或 `serverDescription`
- `includePaths`
- `excludePaths`

作用域内所有 operation 都参与同步。

## 7. 重复导入的稳定匹配

重复导入时，必须先判断文档中的 operation 是否对应本地同一个 `api`。

匹配优先级：

1. `sourceId + operationId`
2. `sourceId + method + path`
3. 人工 `rebind`

处理规则：

- `operationId` 不变但 path 改了：视为同一个 `api`
- `operationId` 变了但 method/path 没变：标记 `suspectedRename`
- 两者都变：标记 `needsRebind`

`api.id` 一旦建立，应尽量稳定，不随 path 或 tag 自动重命名。

## 8. 同步写盘边界

Swagger 同步默认只改写以下内容：

- `sources/<source-id>.yaml`
- `api.meta.sync`
- `api.meta.module`
- `api.meta.tags`
- `api.spec.contract`
- `reports/sync/*.yaml`
- 可选的 `case.meta.audit`

Swagger 同步默认不改写：

- `case.spec.request`
- `case.spec.expect`
- `case.spec.extract`
- `flow.spec`
- `suite.spec`

## 9. 差异分类

### 9.1 接口级差异

- 新增接口
- 删除接口
- path 变化
- method 变化
- tag 变化
- operationId 变化

### 9.2 请求合同差异

- 参数新增
- 参数删除
- 参数改名
- `required` 变化
- 类型变化
- 参数位置变化
- `contentType` 变化

### 9.3 响应合同差异

- 响应码新增或删除
- 响应字段新增或删除
- 响应字段类型变化
- security 要求变化

## 10. 差异处理策略

### 10.1 接口新增

- 创建新 `api`
- 不自动创建 `case`
- 报告类型：`created`

### 10.2 接口删除

- 默认不直接删除 `api`
- 设置 `api.meta.sync.lifecycle = upstreamRemoved`
- 若仍被引用，报告为阻塞影响
- 只有显式 `--prune` 且无引用时才允许归档或删除

### 10.3 tag 变化

- 移动 `api` 到新模块目录
- 更新 `meta.module`
- `api.id` 不变
- `case.apiRef` 不变

### 10.4 可选字段新增

- 自动更新 `api.contract`
- `case` 默认不受影响
- 记为 `nonBreaking`

### 10.5 必填字段新增

- 自动更新 `api.contract`
- 所有引用该 `api` 的 `case` 标记 `missing_required_input`
- 不自动往 `case` 里填值

### 10.6 请求字段删除

- 从 `api.contract` 删除
- 使用了该字段的 `case` 标记 `orphan_input`

### 10.7 字段类型变化

- 更新 `api.contract`
- 对使用该字段的 `case` 标记 `type_mismatch`
- 不自动转换值类型

### 10.8 参数位置变化

- 更新 `api.contract`
- 使用该字段的 `case` 标记 `input_location_changed`

### 10.9 contentType 变化

- 更新 `api.contract`
- 相关 `case` 标记 `body_format_changed`

### 10.10 响应字段删除或改名

- 若命中 `case.expect.assertions`，标记 `broken_assertion`
- 若命中 `case.extract`，标记 `broken_extract`

### 10.11 安全要求变化

- 更新 `api.contract.security`
- 若环境和鉴权默认策略可满足，记为 `auto_resolved`
- 否则标记 `auth_required`

## 11. 影响传播

同步后必须做影响传播：

1. 找到变更的 `api`
2. 找到直接引用它的 `case`
3. 找到引用这些 `case` 的 `flow`
4. 找到引用这些 `case/flow` 的 `suite`

输出应至少包含：

- impacted cases
- impacted flows
- impacted suites

`case.meta.audit` 可记录最近一次分析结论：

```yaml
meta:
  audit:
    status: impacted
    reasons:
      - type: missing_required_input
        field: password2
      - type: broken_extract
        expr: $.token
    lastCheckedAt: 2026-04-14T12:00:00+08:00
```

## 12. 执行器模型

执行链定义如下：

1. 读取 `case`
2. 通过 `apiRef` 载入 `api.contract`
3. 校验 `case.request` 是否满足 `api.contract`
4. 合并环境头、鉴权、变量
5. 执行请求
6. 执行断言和提取

因此主执行入口应为：

- `apifoxcli case run <case-id>`
- `apifoxcli flow run <flow-id>`
- `apifoxcli suite run <suite-id>`

`api send` 保留为调试入口，不再作为主测试执行入口。

## 13. 数据驱动

数据驱动的最小执行单元仍然是 `case`。

支持两种形式：

- `case` 内联固定请求值
- `case` 通过 `datasetRef` 做展开

示例：

```yaml
kind: case
id: auth.login.ddt
name: login ddt
spec:
  apiRef: auth.login
  datasetRef: auth.login-users
  request:
    form:
      username: ${dataset.username}
      password: ${dataset.password}
  expect:
    status: 200
```

## 14. 命令设计

### 14.1 便捷导入入口

```bash
apifoxcli project import-openapi --source <url-or-file> ...
```

职责：

- 初始化或更新 `source`
- 默认执行一次 `full sync`

### 14.2 长期治理入口

```bash
apifoxcli source sync <source-id> --plan
apifoxcli source sync <source-id> --apply
apifoxcli source sync <source-id> --apply --prune
apifoxcli source status <source-id>
apifoxcli source rebind <source-id> --from <api-id> --to <sync-key>
```

规则：

- 默认不带参数时等价于 `--plan`
- `--apply` 才允许写盘
- `--prune` 只处理安全可清理的 `upstreamRemoved api`

## 15. sync report 结构

建议每次同步落一份结构化报告：

```yaml
kind: sync-report
id: demo-openapi-2026-04-14T12-00-00
spec:
  sourceId: demo-openapi
  mode: full
  summary:
    createdApis: 3
    updatedApis: 12
    movedApis: 1
    unchangedApis: 85
    upstreamRemovedApis: 2
    breakingApis: 4
    impactedCases: 6
    impactedFlows: 2
    impactedSuites: 1
  apis:
    created: []
    updated: []
    moved: []
    upstreamRemoved: []
    needsRebind: []
  impacts:
    cases: []
    flows: []
    suites: []
```

该报告既给人看，也给 AI 直接消费。

## 16. prune 规则

默认 `full sync` 不物理删除 API。

`--prune` 仅允许处理同时满足以下条件的 `api`：

- `lifecycle == upstreamRemoved`
- 无任何 `case` 引用
- 无任何 `flow` 引用
- 无任何 `suite` 间接引用

建议优先归档到：

```text
apifox/archive/apis/<source-id>/...
```

而不是直接删除。

## 17. 与当前仓库现状的演进顺序

为避免一次性推翻现有 `apifoxcli` MVP，建议分阶段演进：

1. 引入 `source` 资源和 `source sync --plan/--apply`
2. 将 `api` 收敛为纯合同层
3. 引入一等 `case`
4. 执行器改为以 `case` 为主入口
5. `flow/suite` 改为引用 `caseRef`
6. 最后补齐 `rebind`、`prune` 和完整 impact report

## 18. 风险与约束

- 上游 OpenAPI 文档不一定完全可信，尤其是响应结构可能与真实返回不一致
- 请求侧合同差异通常可自动分析
- 响应侧差异应允许 `confirmed_safe`、`confirmed_breaking` 和 `unknown_risk` 三种结论
- 绝不能因一次上游异常同步直接删除本地已被引用的 `api`

## 19. 最终结论

本方案确立如下长期结构：

- `source` 管 Swagger 全量同步
- `api` 管按 tag 分模块的合同基座
- `case` 管可直接执行的测试用例
- `flow` 串联 `caseRef`
- `suite` 组装 `caseRef/flowRef`
- 同步默认只改 `api`，不改 `case`
- 所有 breaking drift 通过 report 传播到 `case/flow/suite`

这套结构支持：

- 重复导入
- 同源全量更新
- 按 tag 合并模块
- 稳定保留测试资产
- 后续 AI 自动修 case
