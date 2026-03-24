## 9. YAML 完整示例（可直接参考）

```yaml
case_common:
  allureEpic: Demo API
  allureFeature: Auth
  allureStory: Login + Profile

login_01:
  host: ${{host()}}
  url: /user/login
  method: POST
  detail: 正常登录
  headers:
    Content-Type: multipart/form-data;
  requestType: data
  is_run: true
  data:
    username: "18800000001"
    password: "123456"
  dependence_case: false
  dependence_case_data:
  current_request_set_cache:
    - type: response
      jsonpath: $.data.id
      name: login_user_id
  assert:
    errorCode:
      jsonpath: $.errorCode
      type: ==
      value: 0
      AssertType:
    status_code: 200
  sql:
  setup_sql:
  teardown:
  teardown_sql:

get_user_info_01:
  host: ${{host()}}
  url: /user/lg/userinfo/json
  method: GET
  detail: 获取个人信息
  headers:
    Content-Type: multipart/form-data;
    cookie: $cache{login_cookie}
  requestType: none
  is_run: true
  data:
  dependence_case: false
  dependence_case_data:
  assert:
    errorCode:
      jsonpath: $.errorCode
      type: ==
      value: 0
      AssertType:
    status_code: 200
  sql:
  setup_sql:
  teardown:
  teardown_sql:
```
