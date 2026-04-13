# apifoxcli 原生执行架构设计文档

## 1. 文档目的

本文面向 `pytest-auto-api2` 的后续产品化重构，目标是设计一套新的 `apifoxcli`：

- 用资源化 CLI 抽象 Apifox 的核心能力
- 以单一 canonical YAML 作为唯一持久化资源
- 通过原生执行器直接运行测试，不再依赖 `gen -> test_case/*.py -> pytest`
- 对 AI 与人工都保持低门槛、可审查、可维护
- 在第一阶段尽量复用当前仓库中的成熟能力，但不再保留第二套长期持久化模型

本文是设计文档，不直接包含实现代码。

## 2. 设计结论

本次设计确认以下结论：

- 持久化资源只有一套，即 `apifox/` 下的 canonical YAML
- 不保留 `data/*.yaml` 作为长期主存储
- 不保留 `test_case/*.py` 作为主执行入口
- 新 CLI 采用资源导向命令风格
- 新执行入口采用 `apifoxcli suite run` 原生执行
- YAML 只负责声明测试资源与数据，不直接承载执行器内部结构
- 执行逻辑由独立执行器封装，运行态状态只存在于内存上下文
- 第一阶段聚焦 HTTP/HTTPS，不追求一次性覆盖所有协议
- canonical YAML 允许直接写真实账号、密码、token、webhook 等敏感信息
- canonical YAML 保持声明式，禁止内嵌任意 Python 或脚本

## 3. 产品定位

`apifoxcli` 的定位不是“把 Swagger 转成 YAML 再跑 pytest”的工具，而是：

`一个 AI 原生、资源导向、可持久化、可审查的接口测试 CLI`

它需要同时满足三类使用场景：

- 人工在命令行内完成接口设计、测试编排、环境管理、Mock、断言、数据驱动
- AI agent 通过稳定命令和稳定资源模型自动生成、修改、执行测试资产
- 当前 `pytest-auto-api2` 项目逐步演进到新内核，而不是继续围绕历史 `YAML -> pytest 文件生成` 链路扩展

## 4. 设计原则

### 4.1 单一事实来源

磁盘上只允许一套权威测试资源模型，即 canonical YAML。任何 legacy 结构都只能是：

- 一次性迁移输入
- 运行时临时适配对象

不能再作为第二套长期持久化格式。

### 4.2 资源与执行分离

canonical YAML 只描述：

- 资源是什么
- 资源之间如何引用
- 测试数据是什么

执行器负责：

- 变量求值
- 认证注入
- 请求发送
- 依赖关联
- 提取
- 断言
- Mock
- Hook
- 报告

### 4.3 资源导向 CLI

命令语法统一为：

```bash
apifoxcli <resource> <action> [id] [flags]
```

资源导向比动作导向更适合 AI，原因是：

- 对象边界稳定
- 命令可预测
- 便于脚本和代理编排
- 更容易做权限、校验、补全和审计

### 4.4 声明式 DSL

canonical YAML 只允许：

- 常量值
- 资源引用
- 有限变量表达式
- 有限内置函数

不允许：

- 任意 Python
- shell 代码
- lambda
- 任意脚本片段
- 不受控动态表达式

### 4.5 先建立执行内核，再做协议扩展

第一阶段先把 HTTP/HTTPS 的资源模型、执行器、运行上下文、Suite 编排做正确。gRPC、WebSocket、MQTT、SSE 等协议作为后续扩展，不进入第一阶段 MVP。

## 5. 第一阶段范围

### 5.1 包含范围

第一阶段包含以下能力：

- HTTP/HTTPS 请求发送
- 接口资源的增删改查
- 环境与环境变量
- 鉴权
- 接口关联
- 提取与上下文变量
- 前置与后置 Hook
- 断言
- OpenAPI / legacy YAML 导入
- OpenAPI 导出
- Mock 最小能力
- Suite 组装与执行
- 数据驱动测试
- 终端输出与 JSON 输出
- 报告能力的执行器接入

### 5.2 暂不包含

第一阶段暂不包含：

- gRPC 原生执行
- WebSocket 原生执行
- MQTT 原生执行
- SSE 原生执行
- 图形化界面
- 任意脚本插件系统
- 分布式执行平台

## 6. canonical YAML 资源模型

### 6.1 统一顶层结构

所有资源统一采用以下形态：

```yaml
kind: api
id: user.login
name: 用户登录
meta: {}
spec: {}
```

字段约定：

- `kind`：资源类型
- `id`：全局唯一稳定标识
- `name`：对人展示的名称
- `meta`：展示、标签、分类、治理信息
- `spec`：真正业务配置

### 6.2 资源类型

第一阶段定义以下一等资源：

- `project`
- `env`
- `auth`
- `api`
- `flow`
- `suite`
- `dataset`
- `mock`

### 6.3 建议目录结构

```text
apifox/
  project.yaml
  envs/
    qa.yaml
    prod.yaml
  auths/
    login-cookie.yaml
  apis/
    user/
      login.yaml
      profile.yaml
    collect/
      list.yaml
  flows/
    user/
      login-and-profile.yaml
  suites/
    smoke.yaml
    regression.yaml
  datasets/
    user/
      login-invalid.yaml
  mocks/
    collect/
      list.stub.yaml
```

一个资源一个文件。禁止在一个文件中混放多个同级资源。

### 6.4 示例

#### project

```yaml
kind: project
id: default
name: apifoxcli project
spec:
  defaultEnv: qa
  report:
    json: true
    allure: true
```

#### env

```yaml
kind: env
id: qa
name: 测试环境
spec:
  baseUrl: https://example.com
  variables:
    appId: demo-app
    tenant: default
```

#### auth

```yaml
kind: auth
id: login-cookie
name: 登录 Cookie
spec:
  type: login-flow
  apiRef: user.login
  extract:
    - name: login_cookie
      from: cookies
      expr: $.*
  apply:
    in: header
    key: Cookie
    value: ${context.auth.login_cookie}
```

#### api

```yaml
kind: api
id: user.login
name: 用户登录
meta:
  tags:
    - login
    - smoke
spec:
  protocol: http
  envRef: qa
  request:
    method: POST
    path: /user/login
    headers:
      Content-Type: application/json
    json:
      username: ${dataset.username}
      password: ${dataset.password}
  expect:
    status: 200
    assertions:
      - id: errorCode
        source: response
        expr: $.errorCode
        op: ==
        value: 0
  extract:
    - name: token
      from: response
      expr: $.data.token
```

#### flow

```yaml
kind: flow
id: user.login-and-profile
name: 登录并获取用户信息
spec:
  envRef: qa
  steps:
    - apiRef: user.login
    - apiRef: user.profile
      use:
        - value: Bearer ${context.token}
          to: request.headers.Authorization
```

#### suite

```yaml
kind: suite
id: smoke
name: 冒烟测试
spec:
  envRef: qa
  authRef: login-cookie
  failFast: true
  concurrency: 1
  items:
    - apiRef: user.login
    - flowRef: user.login-and-profile
```

#### dataset

```yaml
kind: dataset
id: user.login-invalid
name: 登录异常数据
spec:
  rows:
    - username: ""
      password: "123456"
      expectedErrorCode: -1
    - username: "18800000001"
      password: "wrong"
      expectedErrorCode: -1
```

#### mock

```yaml
kind: mock
id: collect.list.stub
name: 收藏列表本地桩
spec:
  mode: stub
  match:
    apiRef: collect.list
  response:
    status: 200
    headers:
      Content-Type: application/json
    json:
      errorCode: 0
      data:
        datas: []
```

## 7. 表达式约束

### 7.1 支持的表达式

第一阶段仅支持以下表达式来源：

- `${env.xxx}`
- `${context.xxx}`
- `${dataset.xxx}`
- `${fn.xxx()}`

### 7.2 建议的内置函数

第一阶段建议提供有限内置函数：

- `${fn.uuid()}`
- `${fn.now()}`
- `${fn.timestamp()}`
- `${fn.randomInt(1, 100)}`

### 7.3 禁止项

以下能力明确禁止：

- 嵌入 Python 代码
- 嵌入 shell 命令
- 引用外部脚本文件
- 使用 `eval`
- 在 YAML 中定义复杂函数体

## 8. CLI 设计

### 8.1 一级资源

第一阶段建议暴露以下一级命令：

- `project`
- `api`
- `env`
- `auth`
- `flow`
- `suite`
- `dataset`
- `mock`
- `import`
- `export`
- `validate`

### 8.2 典型命令

```bash
apifoxcli project init
apifoxcli project doctor

apifoxcli api create user.login
apifoxcli api get user.login
apifoxcli api list
apifoxcli api send user.login --env qa --json

apifoxcli env set qa
apifoxcli auth test login-cookie --env qa

apifoxcli flow run user.login-and-profile --env qa --json
apifoxcli suite run smoke --env qa --json

apifoxcli validate
apifoxcli import openapi ./openapi.json
apifoxcli import legacy-yaml ./data
apifoxcli export openapi ./exports/openapi.json
```

### 8.3 命令设计原则

- 命令短而稳定
- 默认对 AI 友好
- 默认输出适合审查
- 自动化场景优先支持 `--json`
- 路径、环境、过滤条件尽量收敛为统一参数

## 9. 原生执行器设计

### 9.1 执行链路

新的执行链路定义为：

```text
canonical YAML
  -> loader
  -> validator
  -> domain objects
  -> planner
  -> execution graph
  -> executor
  -> report/artifacts
```

### 9.2 模块职责

#### loader

负责：

- 扫描 `apifox/`
- 读取 YAML
- 基础反序列化
- 建立资源索引

不负责业务执行。

#### validator

负责：

- schema 校验
- `id` 唯一性校验
- 引用存在性校验
- 环引用与循环依赖校验
- 表达式来源校验
- 资源边界校验

#### domain

定义正式对象：

- `Project`
- `Env`
- `Auth`
- `Api`
- `Flow`
- `Suite`
- `Dataset`
- `Mock`

domain 层只表达资源语义，不承担执行逻辑。

#### planner

把用户命令转成执行计划，例如：

```text
apifoxcli suite run smoke --env qa
```

planner 负责：

- 解析 suite
- 展开 item
- 绑定 env
- 绑定 auth
- 展开 dataset
- 生成执行顺序
- 构建失败策略

#### execution graph

负责把执行计划转成有依赖关系的图结构。

第一阶段的执行约束固定为：

- `flow` 严格串行
- `suite` 默认串行
- `suite` 可显式声明并行

#### executor

负责：

- 请求组装
- 鉴权注入
- 变量替换
- 上下文读写
- 请求发送
- 提取
- 断言
- Hook
- Mock
- 结果收集

#### report/artifacts

负责：

- 终端摘要
- JSON 报告
- Allure 报告
- 调试工件

## 10. 执行器内部组件

### 10.1 RunContext

执行器维护统一运行上下文，只在内存中存在，作为运行态状态容器。

建议包含：

- 当前环境
- 当前鉴权状态
- 当前变量集
- 当前数据集行
- 提取结果
- Mock 命中记录
- 已执行步骤结果
- 工件索引

### 10.2 VariableResolver

统一负责：

- 环境变量替换
- 上下文变量替换
- 数据集变量替换
- 内置函数求值

所有动态替换都从这里走，不允许把替换逻辑散在请求器、断言器、Hook 中。

### 10.3 AuthProvider

统一负责鉴权：

- `none`
- `apiKey`
- `bearer`
- `basic`
- `cookie`
- `login-flow`

当前仓库中写在 `test_case/conftest.py` 的登录初始化逻辑需要迁到这里。

### 10.4 RequestExecutor

负责真正发送请求。

第一阶段聚焦 HTTP/HTTPS，后续多协议通过扩展传输层实现，不改 domain 模型。

### 10.5 ExtractionEngine

负责从：

- response
- request
- cookies
- headers
- context

中提取值，并写入 `RunContext`。

### 10.6 AssertionEngine

负责执行：

- 响应断言
- 请求断言
- 上下文断言
- 数据库断言
- 状态码断言

### 10.7 HookEngine

负责：

- before hook
- after hook
- setup
- teardown
- 延时
- 清理动作

### 10.8 MockEngine

第一阶段只支持：

- `stub`
- `record-replay`

先做最小能力，不构建复杂代理平台。

### 10.9 DatasetExpander

负责把：

- `api + dataset`
- `flow + dataset`
- `suite + dataset`

展开成具体执行实例。

### 10.10 SuiteRunner

负责：

- 编排整个 suite
- 失败处理
- 并发策略
- 汇总结果
- 报告输出

## 11. 当前仓库的重构策略

### 11.1 总体方向

本次重构不是继续扩展当前 `YAML -> 生成 pytest 文件 -> pytest 执行` 链路，而是把项目重构为：

```text
资源层
  -> 领域层
  -> 规划层
  -> 执行器
  -> 报告层
```

### 11.2 建议的新模块结构

```text
pytest_auto_api2/
  cli/
    commands/
  storage/
  domain/
  planner/
  executor/
    context/
    auth/
    transport/
    extract/
    assert/
    hook/
    mock/
  reporter/
  legacy_import/
```

### 11.3 现有代码迁移建议

#### 可借鉴迁移的能力

- `pytest_auto_api2/utils/requests_tool/request_control.py`
  - 可作为 HTTP 执行器重构参考
- `pytest_auto_api2/utils/assertion/assert_control.py`
  - 可作为断言引擎重构参考
- `pytest_auto_api2/utils/requests_tool/dependent_case.py`
  - 可作为上下文绑定与提取逻辑参考
- `pytest_auto_api2/utils/requests_tool/teardown_control.py`
  - 可作为 Hook/teardown 引擎参考
- `pytest_auto_api2/utils/other_tools/allure_data/*`
  - 可作为报告适配参考

#### 需要降级或废弃的部分

- `data/` 作为主设计目录
- `test_case/` 作为主执行入口
- `case_automatic_control.py` 的 pytest 生成职责
- `test_case/conftest.py` 中承载的业务语义

#### 明确迁移目标

- 登录与鉴权逻辑迁到 `executor/auth/`
- 变量与缓存逻辑迁到 `executor/context/`
- 请求发送迁到 `executor/transport/`
- 断言迁到 `executor/assert/`
- teardown 迁到 `executor/hook/`
- CLI 从单文件 `pytest_auto_api2/cli.py` 拆到 `cli/commands/`

### 11.4 legacy 能力的定位

legacy 结构只保留两个职责：

- `legacy import` 的导入来源
- 回归行为对照样本

不再作为长期权威模型。

## 12. 数据驱动、鉴权、Mock、Suite 的分层规则

### 12.1 数据驱动

数据驱动必须是独立 `dataset` 资源，不与 `api` 文件混写。

`api` 或 `flow` 通过引用数据集实现展开，不直接承载多行测试数据。

### 12.2 鉴权

鉴权必须是独立 `auth` 资源，不允许继续依赖 `pytest fixture` 作为主入口。

### 12.3 Mock

Mock 必须是独立 `mock` 资源，Suite 或命令决定是否启用。

### 12.4 Suite

Suite 是自动化测试装配层，负责：

- 选择哪些 API / Flow
- 绑定什么环境
- 使用什么鉴权
- 使用哪些数据集
- 采用什么并发和失败策略

## 13. 导入与导出

### 13.1 导入

第一阶段支持：

- `import openapi`
- `import legacy-yaml`

导入后的目标都是 canonical YAML。

### 13.2 导出

第一阶段支持：

- `export openapi`

后续可根据需要扩展 `export postman`、`export legacy-yaml`，但导出产物始终不是权威持久化资源。

## 14. 报告与输出

第一阶段建议统一支持：

- 终端人类可读摘要
- 结构化 JSON 输出
- Allure 报告接入

原则如下：

- CLI 默认适合人类阅读
- 自动化与 AI 编排优先使用 `--json`
- 报告产物是运行结果，不反写到 canonical YAML

## 15. 风险与权衡

### 15.1 接受的权衡

本设计明确接受以下权衡：

- 第一阶段不覆盖所有协议
- 第一阶段允许敏感信息明文写入 YAML
- 第一阶段可以借鉴部分旧执行能力，但不保留双持久化模型

### 15.2 主要风险

- 从历史单文件 CLI 迁移到分层架构，重构量较大
- 当前很多业务语义藏在 `conftest.py` 与 legacy YAML 字段中，迁移时要重新建模
- 原生执行器落地前期成本高于继续扩展历史生成链路

## 16. 分阶段实施建议

### Phase 1：建立最小内核

- 建立 canonical YAML 资源目录
- 实现 loader、validator、domain、planner
- 实现 HTTP RequestExecutor、RunContext、AssertionEngine 基础能力
- 打通 `apifoxcli suite run`

### Phase 2：迁移高阶能力

- 迁移 auth
- 迁移 dataset
- 迁移 hook
- 接入 Allure
- 增加 JSON 输出稳定协议

### Phase 3：导入导出与治理

- 完成 OpenAPI 导入
- 完成 legacy YAML 导入
- 完成 OpenAPI 导出
- 增加 doctor / validate / audit 类命令

### Phase 4：多协议与扩展

- 评估 gRPC
- 评估 WebSocket
- 评估 MQTT
- 评估插件机制

## 17. 推荐实施结论

推荐方案为：

`单一 canonical YAML + 原生执行器 + 资源导向 CLI + 渐进重构当前项目`

这意味着：

- 新资源模型是长期稳定基础
- 新执行器是未来能力承载核心
- 历史 YAML 与 pytest 生成链路不再作为主路径
- 当前项目应围绕 `storage/domain/planner/executor/reporter` 五层逐步重构

---

本文档面向后续实现阶段，作为 `apifoxcli` 的设计基线。后续如果进入实现计划阶段，应以本文为唯一设计依据展开详细拆解。
