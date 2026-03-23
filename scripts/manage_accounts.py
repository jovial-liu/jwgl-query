#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

MASK = "******"


def print_json(payload: dict[str, Any], exit_code: int = 0) -> None:
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    raise SystemExit(exit_code)


def load_config(path: Path) -> dict[str, Any]:
    with path.open("r", encoding="utf-8") as f:
        return json.load(f)


def save_config(path: Path, config: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as f:
        json.dump(config, f, ensure_ascii=False, indent=2)
        f.write("\n")


def ensure_teachers(config: dict[str, Any]) -> dict[str, Any]:
    teachers = config.setdefault("teachers", {})
    if not isinstance(teachers, dict):
        print_json(
            {
                "ok": False,
                "error_code": "INVALID_CONFIG",
                "message": "config.json 中的 teachers 必须是对象",
            },
            exit_code=2,
        )
    return teachers


def mask_teacher(teacher: dict[str, Any]) -> dict[str, Any]:
    masked = dict(teacher)
    if masked.get("password"):
        masked["password"] = MASK
    return masked


def normalize_teacher_fields(previous: dict[str, Any] | None = None, *, username: str | None = None, password: str | None = None, email: str | None = None, phone: str | None = None) -> dict[str, Any]:
    teacher = dict(previous or {})
    if username is not None:
        teacher["username"] = username
    if password is not None:
        teacher["password"] = password
    if email is not None:
        teacher["email"] = email
    if phone is not None:
        teacher["phone"] = phone
    if not teacher.get("username") or not teacher.get("password"):
        print_json(
            {
                "ok": False,
                "error_code": "MISSING_REQUIRED_FIELDS",
                "message": "老师账号或密码为空，无法保存",
                "required": ["teacher", "username", "password"],
            },
            exit_code=2,
        )
    return teacher


def require_teacher_name(teacher: str | None, *, action: str) -> str:
    name = (teacher or "").strip()
    if not name:
        print_json(
            {
                "ok": False,
                "error_code": "MISSING_TEACHER_NAME",
                "message": f"缺少老师名称，无法执行{action}",
                "required": ["teacher"],
                "action": action,
            },
            exit_code=2,
        )
    return name


def require_existing_teacher(teachers: dict[str, Any], teacher: str, *, action: str) -> dict[str, Any]:
    if teacher not in teachers:
        print_json(
            {
                "ok": False,
                "error_code": "TEACHER_NOT_FOUND",
                "message": f"老师 {teacher} 不存在，无法执行{action}",
                "teacher": teacher,
                "action": action,
            },
            exit_code=3,
        )
    return teachers[teacher]


def cmd_list(args: argparse.Namespace) -> None:
    config = load_config(Path(args.config))
    teachers = ensure_teachers(config)
    print_json(
        {
            "ok": True,
            "action": "list",
            "current_teacher": config.get("current_teacher"),
            "count": len(teachers),
            "teachers": {name: mask_teacher(info if isinstance(info, dict) else {}) for name, info in teachers.items()},
        }
    )


def cmd_add(args: argparse.Namespace) -> None:
    path = Path(args.config)
    config = load_config(path)
    teachers = ensure_teachers(config)
    teacher_name = require_teacher_name(args.teacher, action="add")
    previous = teachers.get(teacher_name)
    if previous and not args.force:
        print_json(
            {
                "ok": False,
                "error_code": "TEACHER_ALREADY_EXISTS",
                "message": f"老师 {teacher_name} 已存在",
                "teacher": teacher_name,
                "action": "add",
            },
            exit_code=3,
        )
    teachers[teacher_name] = normalize_teacher_fields(
        previous,
        username=args.username,
        password=args.password,
        email=args.email if args.email is not None else (previous or {}).get("email", ""),
        phone=args.phone if args.phone is not None else (previous or {}).get("phone", ""),
    )
    if args.set_current or not config.get("current_teacher"):
        config["current_teacher"] = teacher_name
    save_config(path, config)
    print_json({"ok": True, "action": "add", "teacher": teacher_name, "set_current": config.get("current_teacher") == teacher_name})


def cmd_update(args: argparse.Namespace) -> None:
    path = Path(args.config)
    config = load_config(path)
    teachers = ensure_teachers(config)
    teacher_name = require_teacher_name(args.teacher, action="update")
    previous = require_existing_teacher(teachers, teacher_name, action="update")
    teachers[teacher_name] = normalize_teacher_fields(
        previous,
        username=args.username if args.username is not None else previous.get("username"),
        password=args.password if args.password is not None else previous.get("password"),
        email=args.email if args.email is not None else previous.get("email", ""),
        phone=args.phone if args.phone is not None else previous.get("phone", ""),
    )
    if args.set_current:
        config["current_teacher"] = teacher_name
    save_config(path, config)
    print_json({"ok": True, "action": "update", "teacher": teacher_name, "set_current": config.get("current_teacher") == teacher_name})


def cmd_remove(args: argparse.Namespace) -> None:
    path = Path(args.config)
    config = load_config(path)
    teachers = ensure_teachers(config)
    teacher_name = require_teacher_name(args.teacher, action="remove")
    require_existing_teacher(teachers, teacher_name, action="remove")
    del teachers[teacher_name]
    if config.get("current_teacher") == teacher_name:
        config["current_teacher"] = next(iter(teachers.keys()), "")
    save_config(path, config)
    print_json({"ok": True, "action": "remove", "teacher": teacher_name, "current_teacher": config.get("current_teacher", "")})


def cmd_set_current(args: argparse.Namespace) -> None:
    path = Path(args.config)
    config = load_config(path)
    teachers = ensure_teachers(config)
    teacher_name = require_teacher_name(args.teacher, action="set-current")
    require_existing_teacher(teachers, teacher_name, action="set-current")
    config["current_teacher"] = teacher_name
    save_config(path, config)
    print_json({"ok": True, "action": "set_current", "teacher": teacher_name})


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="管理 jwgl-query 的老师账号配置（执行接口）")
    parser.add_argument("--config", default="config.json")
    subparsers = parser.add_subparsers(dest="command", required=True)

    p_list = subparsers.add_parser("list", help="列出已保存的老师账号")
    p_list.set_defaults(func=cmd_list)

    def add_common_fields(p: argparse.ArgumentParser, require_teacher: bool = False) -> None:
        p.add_argument("--teacher", required=require_teacher, help="老师名称")
        p.add_argument("--username", help="登录账号")
        p.add_argument("--password", help="登录密码")
        p.add_argument("--email", help="邮箱（可选）")
        p.add_argument("--phone", help="手机号（可选）")
        p.add_argument("--set-current", action="store_true", help="保存后设为当前老师")

    p_add = subparsers.add_parser("add", help="新增老师账号")
    add_common_fields(p_add)
    p_add.add_argument("--force", action="store_true", help="老师已存在时允许覆盖")
    p_add.set_defaults(func=cmd_add)

    p_update = subparsers.add_parser("update", help="更新老师账号")
    add_common_fields(p_update)
    p_update.set_defaults(func=cmd_update)

    p_remove = subparsers.add_parser("remove", help="删除老师账号")
    p_remove.add_argument("--teacher", required=False, help="老师名称")
    p_remove.set_defaults(func=cmd_remove)

    p_set = subparsers.add_parser("set-current", help="设置当前老师")
    p_set.add_argument("--teacher", required=False, help="老师名称")
    p_set.set_defaults(func=cmd_set_current)

    return parser


def main() -> None:
    parser = build_parser()
    args = parser.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
