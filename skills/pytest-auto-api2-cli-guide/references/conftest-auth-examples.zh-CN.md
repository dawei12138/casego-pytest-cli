# conftest 登录鉴权示例（Cookie / Token）

本文提供 `test_case/conftest.py` 的两种常用登录鉴权初始化方案。
建议使用 `session` 级 fixture，在一次测试会话内只登录一次。

## 1. Cookie 鉴权示例

```python
import pytest
import requests

from utils.cache_process.cache_control import CacheHandler


@pytest.fixture(scope="session", autouse=True)
def work_login_init():
    """Fetch login cookie once per session and cache it for dependent cases."""
    url = "https://www.wanandroid.com/user/login"
    data = {
        "username": 1910606,
        "password": 123456,
    }
    headers = {"Content-Type": "application/x-www-form-urlencoded"}

    res = requests.post(url=url, data=data, verify=True, headers=headers)
    response_cookie = res.cookies

    cookies = ""
    for key, value in response_cookie.items():
        cookies += f"{key}={value};"

    CacheHandler.update_cache(cache_name="login_cookie", value=cookies)
```

YAML 使用示例：

```yaml
headers:
  Content-Type: application/json
  cookie: $cache{login_cookie}
```

## 2. Token 鉴权示例

```python
import pytest
import requests

from utils.cache_process.cache_control import CacheHandler


@pytest.fixture(scope="session", autouse=True)
def work_login_token_init():
    """Fetch login token once per session and cache token/bearer values."""
    url = "https://api.example.com/user/login"
    json_data = {
        "username": "your_username",
        "password": "your_password",
    }
    headers = {"Content-Type": "application/json"}

    res = requests.post(url=url, json=json_data, verify=True, headers=headers)
    token = res.json()["data"]["token"]

    CacheHandler.update_cache(cache_name="login_token", value=token)
    CacheHandler.update_cache(cache_name="login_bearer_token", value=f"Bearer {token}")
```

YAML 使用示例（两选一）：

```yaml
# 写法一：模板中拼接 Bearer
headers:
  Authorization: Bearer $cache{login_token}

# 写法二：缓存中直接保存 Bearer 前缀
headers:
  Authorization: $cache{login_bearer_token}
```

## 3. 安全建议

- 账号密码、token 仅使用占位值示例，不要提交真实敏感信息。
- 生产/测试环境建议从环境变量读取账号密码，而不是硬编码到仓库。
