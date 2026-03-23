# Config format

## `config.json`

Create a local `config.json` in the skill root.

The structure is split into teacher credentials, login selectors, and per-query selectors. When the user provides a new teacher account/password, save it into the local `teachers` map for reuse.

```json
{
  "base_url": "https://jwgl.nustti.edu.cn",
  "login_url": "https://jwgl.nustti.edu.cn/jsxsd/framework/jsMain.jsp",
  "teachers": {
    "某老师": {
      "username": "teacher_account",
      "password": "REPLACE_ME"
    }
  },
  "selectors": {
    "login": {
      "username": { "by": "id", "value": "userAccount" },
      "password": { "by": "id", "value": "userPassword" },
      "login_button": { "by": "css", "value": "button.login_btn" }
    },
    "queries": {
      "invigilation": {
        "menu_parent": { "by": "xpath", "value": "..." },
        "menu_child": { "by": "xpath", "value": "..." },
        "query_frame": { "by": "id", "value": "Frame1" },
        "term_select": { "by": "id", "value": "xnxqid" },
        "query_button": { "by": "xpath", "value": "//*[@id='btn_query']" },
        "result_frame": { "by": "id", "value": "fcenter" },
        "table_id": "dataList"
      },
      "course_schedule": {
        "menu_parent": { "by": "xpath", "value": "..." },
        "menu_child": { "by": "xpath", "value": "..." },
        "query_frame": { "by": "id", "value": "..." },
        "term_select": { "by": "id", "value": "..." },
        "query_button": { "by": "xpath", "value": "..." },
        "result_frame": { "by": "id", "value": "..." },
        "table_id": "dataList"
      }
    }
  }
}
```

## Selector object format

```json
{ "by": "id|xpath|css|name", "value": "..." }
```

## Output model

- Prefer direct query output in chat.
- Use JSON during debugging.
- Add text summarization in OpenClaw orchestration rather than hardcoding messaging into the Python script.
