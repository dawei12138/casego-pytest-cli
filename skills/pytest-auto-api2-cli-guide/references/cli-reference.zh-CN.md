## 10. CLI 命令详解

## 10.1 总览

```bash
casego --help
# 子命令：gen / validate / run / all / init
```

### 10.2 `casego init`

初始化项目骨架。

```bash
casego init [--force]
```

### 10.3 `casego validate`

对 YAML 做预检查（推荐在 gen/run 前执行）。

```bash
casego validate --project-root .
casego validate --project-root . --json
casego validate --project-root . --json --fail-fast
```

当前校验覆盖：
- YAML 解析是否成功
- 根节点是否是对象
- 是否含 `case_common`
- `case_id` 是否重复
- 基础 schema 与字段可用性（通过 `CaseData(...).case_process`）

退出码：
- `0`：校验通过
- `2`：存在校验错误
- `1`：命令异常（参数/路径/运行时异常）

### 10.4 `casego gen`

从 YAML 生成 `test_case`。

```bash
casego gen --project-root .
casego gen --project-root . --force
casego gen --project-root . --data-dir data --test-dir test_case
```

说明：
- `--force` 会强制覆盖目标生成文件，不受 `real_time_update_test_cases` 限制。

### 10.5 `casego run`

执行 pytest。

```bash
casego run --project-root .
casego run --project-root . -k login
casego run --project-root . -m smoke
casego run --project-root . --maxfail 1
casego run --project-root . --json
casego run --project-root . --json tests_phase3/unit/test_cli_unit.py
```

常用参数：
- 路径类：`--project-root` / `--config` / `--data-dir` / `--test-dir`
- 过滤类：`-k` / `-m` / `--maxfail`
- 输出类：`--json` / `--no-capture`
- 报告类：`--allure` / `--clean-allure` / `--allure-dir` / `--allure-html-dir`
- 后处理：`--generate-report` / `--serve-report` / `--notify` / `--excel-report`

约束：
- `--clean-allure` 需要配合 `--allure`
- `--generate-report`、`--serve-report`、`--notify`、`--excel-report` 需要 `--allure`

### 10.6 `casego all`

先 `gen` 再 `run`。

```bash
casego all --project-root .
casego all --project-root . --force-gen
casego all --project-root . --json -k smoke
```

说明：
- `--force-gen` 仅影响前置生成步骤。

## 11. JSON 输出示例（AI/平台对接）

### 11.1 `validate --json` 示例

```json
{
  "command": "validate",
  "summary": {
    "ok": true,
    "error_count": 0,
    "total_yaml_files": 6,
    "total_cases": 15
  },
  "errors": []
}
```

### 11.2 `run --json` 示例

```json
{
  "command": "run",
  "ok": true,
  "exit_code": 0,
  "pytest": {
    "summary": {
      "collected": 4,
      "passed": 4,
      "failed": 0,
      "errors": 0,
      "skipped": 0
    },
    "failed_cases": [],
    "error_cases": []
  },
  "post_actions": {
    "report_generated": false,
    "report_served": false,
    "notified": false,
    "excel_report": false
  }
}
```

## 12. 环境变量覆盖（非必需）

可通过环境变量覆盖路径（与 CLI 参数等价）：

- `PYTEST_AUTO_API2_HOME`
- `PYTEST_AUTO_API2_CONFIG`
- `PYTEST_AUTO_API2_DATA_DIR`
- `PYTEST_AUTO_API2_TEST_DIR`

示例（Windows PowerShell）：

```powershell
$env:PYTEST_AUTO_API2_HOME = "D:\\project\\casego"
$env:PYTEST_AUTO_API2_CONFIG = "D:\\project\\casego\\common\\config.yaml"
casego run --json
```

## 13. 常见问题与排查

### 13.1 `validate` 失败（`missing_case_common`）
- 每个 YAML 顶层必须包含 `case_common`。

### 13.2 `duplicate_case_id`
- 全项目（`data/` 递归）范围内 `case_id` 必须唯一。

### 13.3 `run` 报错找不到文件/目录
- 检查 `--project-root`、`--data-dir`、`--test-dir` 是否对应实际路径。

### 13.4 生成后文件未更新
- 使用 `casego gen --force` 或 `casego all --force-gen`。

### 13.5 全量执行时网络失败
- 当前 `test_case/conftest.py` 可能含真实登录初始化（外网依赖）。
- 在离线/受限环境中，建议先跑局部目标或改造为可选 fixture。

### 13.6 SQL 断言不生效
- 检查 `common/config.yaml` 中 `mysql_db.switch` 是否为 `true`。
