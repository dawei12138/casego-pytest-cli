---
name: pytest-auto-api2-cli-guide
description: pytest-auto-api2-cli 中文使用技能。用于指导 YAML 用例编写、校验、生成、执行，以及 conftest 登录鉴权（Cookie/Token）实践。
---

# pytest-auto-api2-cli 中文指南技能

## 适用范围

- `casego` / `python -m pytest_auto_api2.cli` 命令使用与排错
- YAML 用例规范、依赖配置、缓存写入、断言写法
- `test_case/conftest.py` 的登录鉴权实践（Cookie / Token）
- `casego init` 初始化模板内容说明

文档冲突时，以当前仓库代码行为为准。

## 阅读顺序

1. `references/quickstart.zh-CN.md`
2. `references/yaml-summary.zh-CN.md`
3. `references/yaml-spec.zh-CN.md`
4. `references/yaml-examples.zh-CN.md`
5. `references/conftest-auth-examples.zh-CN.md`
6. `references/cli-reference.zh-CN.md`

## 必须遵循

1. 命令优先使用 `casego`，模块入口 `python -m pytest_auto_api2.cli` 仅作为兜底。
2. 明确说明 `ini/init` 是在“当前目录”初始化模板工程。
3. 严格执行 YAML 硬规则：
   - 顶层必须存在 `case_common`
   - 必填字段必须完整
   - `data/` 下 `case_id` 必须全局唯一
   - `dependence_case: true` 时，`dependence_case_data` 不能为空
4. 给出登录鉴权方案时，优先提供 `conftest.py` 的 `session` 级 fixture，并明确缓存键和 YAML `headers` 的使用方式。
5. 模板与示例中只能使用占位值，不得写入真实账号、密码、token、webhook。
6. 自动化/脚本集成场景优先建议 `--json` 输出。

## 快速建议

- Cookie 鉴权：登录后拼接 cookie 字符串，缓存为 `login_cookie`，YAML 中通过 `cookie: $cache{login_cookie}` 使用。
- Token 鉴权：登录后提取 token，缓存为 `login_token` 或 `login_bearer_token`，YAML 中通过 `Authorization` 头使用。
- Bearer 前缀：可以直接缓存 `Bearer xxx`，也可以结合 `replace_value` 组装。

## 参考资料

- `references/quickstart.zh-CN.md`
- `references/yaml-summary.zh-CN.md`
- `references/yaml-spec.zh-CN.md`
- `references/yaml-examples.zh-CN.md`
- `references/conftest-auth-examples.zh-CN.md`
- `references/cli-reference.zh-CN.md`
