# 使用文档（Usage Guide）

## 1. 文档适用对象

本文件面向测试同学、自动化平台、AI Skills 编排调用者，目标是让你可以：
- 按规范编写 YAML 测试用例
- 使用 `casego` CLI 完成生成、校验、执行
- 获取稳定可解析的 JSON 结果

如果你要改框架代码，请看：`docs/development-guide.md`。
如果你要发版，请看：`docs/release-package-guide.md`。

## 2. 快速开始

### 2.1 安装

#### 方式 A：开发态（当前仓库）

```bash
pip install -r requirements.txt
pip install -e . --no-build-isolation --no-deps
casego --help
```

#### 方式 B：已发布包（PyPI）

```bash
pip install pytest-auto-api2-cli
casego --help
```

### 2.2 初始化项目骨架

```bash
mkdir my_api_project
cd my_api_project
casego init
```

会生成基础目录与模板文件：
- `common/config.yaml`
- `data/demo_banner.yaml`
- `test_case/__init__.py`
- `test_case/conftest.py`
- `pytest.ini`

如果目标目录非空，使用：

```bash
casego init --force
```

### 2.3 最短执行链路

```bash
casego validate --project-root my_api_project
casego gen --project-root my_api_project
casego run --project-root my_api_project
```

## 3. 配置文件说明（`common/config.yaml`）

| 字段 | 说明 |
| --- | --- |
| `project_name` | 项目名（用于日志/通知） |
| `env` | 环境名（test/stage/prod 等文本） |
| `tester_name` | 测试负责人标识 |
| `host` | 主 API 域名，`${{host()}}` 从这里读取 |
| `app_host` | 次级域名，`${{app_host()}}` 从这里读取 |
| `real_time_update_test_cases` | 是否实时覆盖生成的 `test_case` 文件 |
| `notification_type` | 通知类型（`0` 不通知；`1,2,3,4` 分别对应钉钉/企微/邮件/飞书） |
| `excel_report` | 是否输出失败用例 Excel |
| `mysql_db.*` | SQL 断言/SQL清理开关与连接参数 |
| `ding_talk/wechat/email/lark` | 各通知通道配置 |

建议：
- 公共仓库只保留模板值，不提交真实 token/password/webhook。
