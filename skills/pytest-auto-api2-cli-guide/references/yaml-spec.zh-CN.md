## 4. YAML 用例规范（重点）

> Implementation note (code-first): in current runtime, dependency extraction for non-`self` cases is mainly `response`/`request`. Use `sqlData`/`cache` variants only after validating in your branch.

### 4.1 文件组织

- 建议按业务模块分目录，如：
  - `data/Login/login.yaml`
  - `data/UserInfo/get_user_info.yaml`
  - `data/Collect/collect_addtool.yaml`

- 每个 YAML 文件应包含：
  - 一个 `case_common`（Allure 元数据）
  - 多个具体 case（`case_id`）

### 4.2 顶层结构

```yaml
case_common:
  allureEpic: 项目名
  allureFeature: 模块名
  allureStory: 功能名

case_id_01:
  ...

case_id_02:
  ...
```

### 4.3 case 字段清单

#### 4.3.1 必填字段

以下字段由框架校验为“必须存在”：

| 字段 | 示例 | 说明 |
| --- | --- | --- |
| `host` | `${{host()}}` | 域名，可用动态函数 |
| `url` | `/user/login` | 接口路径 |
| `method` | `POST` | 请求方法（见 4.4） |
| `detail` | `正常登录` | 用例描述 |
| `is_run` | `true` / `false` / 空 | 是否执行；空通常视为执行 |
| `headers` | `{Content-Type: application/json}` | 请求头 |
| `requestType` | `DATA` | 请求体类型（见 4.5） |
| `data` | `{username: xx}` | 请求数据 |
| `dependence_case` | `true/false` | 是否有依赖 |
| `assert` | `...` | 断言块 |

#### 4.3.2 选填字段

| 字段 | 说明 |
| --- | --- |
| `dependence_case_data` | 依赖细节配置 |
| `current_request_set_cache` | 把当前请求/响应字段写入缓存 |
| `sql` | SQL 断言查询语句列表 |
| `setup_sql` | 前置 SQL |
| `teardown` | API 方式清理数据 |
| `teardown_sql` | SQL 方式清理数据 |
| `sleep` | 请求后等待秒数 |

### 4.4 `method` 支持值

支持以下 HTTP 方法（大小写不敏感）：
- `GET`
- `POST`
- `PUT`
- `PATCH`
- `DELETE`
- `HEAD`
- `OPTION`

### 4.5 `requestType` 支持值

支持（大小写不敏感）：
- `JSON`：以 json= 发送
- `PARAMS`：拼接 URL query
- `DATA`：表单/普通 data
- `FILE`：文件上传
- `EXPORT`：导出文件（会写入 `Files/`）
- `NONE`：无请求体

## 5. 动态变量与缓存语法

### 5.1 动态函数 `${{...}}`

格式：`${{function_name()}}`

常见内置函数：
- `${{host()}}`
- `${{app_host()}}`
- `${{random_int()}}`
- `${{get_phone()}}`
- `${{get_email()}}`
- `${{get_time()}}`
- `${{today_date()}}`
- `${{time_after_week()}}`

支持简单参数传递（按字符串分割传入）：
- `${{func(arg1,arg2)}}`

### 5.2 缓存引用 `$cache{...}`

格式：
- `$cache{token}`
- `$cache{int:user_id}`
- `$cache{float:amount}`

说明：
- 无类型前缀时按字符串替换
- 有类型前缀时按类型解释（`int/bool/list/dict/tuple/float`）

### 5.3 SQL 占位符 `$json(...)$`

用于 SQL 中引用接口响应 JSON 字段：

```yaml
teardown_sql:
  - DELETE FROM t_order WHERE order_id = '$json($.data.orderId)$'
```

## 6. 依赖与缓存写法

### 6.1 `dependence_case_data`（跨用例依赖）

```yaml
dependence_case: true
dependence_case_data:
  - case_id: login_01
    dependent_data:
      - dependent_type: response
        jsonpath: $.data.token
        set_cache: login_token
        replace_key: $.headers.Authorization
```

`dependent_type` 支持：
- `response`：从依赖用例响应提取
- `request`：从依赖用例请求提取
- `sqlData`：从 SQL 结果提取
- `cache`：从缓存提取

### 6.2 `current_request_set_cache`（当前请求写缓存）

```yaml
current_request_set_cache:
  - type: response
    jsonpath: $.data.id
    name: created_id
  - type: request
    jsonpath: $.data.username
    name: req_username
```

## 7. 断言写法

### 7.1 普通响应断言

```yaml
assert:
  errorCode:
    jsonpath: $.errorCode
    type: ==
    value: 0
    AssertType:
  status_code: 200
```

- `status_code` 是特殊断言，直接比 HTTP 状态码
- 其他断言项结构统一为：`jsonpath/type/value/AssertType`

### 7.2 `type` 支持值

当前支持：
- `==`
- `lt`
- `le`
- `gt`
- `ge`
- `not_eq`
- `str_eq`
- `len_eq`
- `len_gt`
- `len_ge`
- `len_lt`
- `len_le`
- `contains`
- `contained_by`
- `startswith`
- `endswith`

### 7.3 SQL 断言

```yaml
assert:
  db_username:
    jsonpath: $.data.username
    type: ==
    value: $.username
    AssertType: SQL
sql:
  - SELECT username FROM user WHERE id = 1
```

`AssertType` 常见值：
- 空 / `null`：普通响应断言
- `SQL` / `D_SQL`：响应值与 SQL 查询结果比较
- `R_SQL`：请求值与 SQL 查询结果比较

> 注意：仅当 `mysql_db.switch: true` 时 SQL 相关逻辑才生效。

## 8. teardown 清理写法

### 8.1 API 清理

```yaml
teardown:
  - case_id: delete_user_01
    send_request:
      - dependent_type: cache
        cache_data: created_id
        replace_key: $.data.id
```

### 8.2 先准备参数再请求

```yaml
teardown:
  - case_id: query_user_01
    param_prepare:
      - dependent_type: self_response
        jsonpath: $.data.id
        set_cache: delete_id
  - case_id: delete_user_01
    send_request:
      - dependent_type: cache
        cache_data: delete_id
        replace_key: $.data.id
```

### 8.3 SQL 清理

```yaml
teardown_sql:
  - DELETE FROM user WHERE id = '$json($.data.id)$'
```
