#!/usr/bin/env python3
from __future__ import annotations

import argparse
import csv
import json
import os
import re
import subprocess
import sys
import time
import traceback
from datetime import datetime
from pathlib import Path
from typing import Any
from urllib.parse import urljoin

from bs4 import BeautifulSoup

try:
    from selenium import webdriver
    from selenium.webdriver.chrome.service import Service as ChromeService
    from selenium.webdriver.common.by import By
    from selenium.webdriver.support import expected_conditions as EC
    from selenium.webdriver.support.ui import Select, WebDriverWait
    from selenium.webdriver.common.selenium_manager import SeleniumManager
except ImportError as exc:  # pragma: no cover
    raise SystemExit("Missing dependencies. Install selenium and beautifulsoup4 before running.") from exc

SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

DEFAULT_COLS = [
    "校区", "考场校区", "考试场次", "课程代码", "课程名称", "授课教师", "考试时间", "考场", "类别", "考生数"
]

COURSE_SCHEDULE_COLS = [
    "星期",
    "节次",
    "时间",
    "课程名称",
    "周次",
    "教室",
    "班级",
    "人数",
    "附加信息",
]

BY_MAP = {
    "id": By.ID,
    "xpath": By.XPATH,
    "css": By.CSS_SELECTOR,
    "name": By.NAME,
}


def load_config(path: str) -> dict[str, Any]:
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def get_teacher_creds(config: dict[str, Any], teacher_name: str) -> dict[str, Any]:
    teachers = config.get("teachers", {})
    current_teacher = config.get("current_teacher")
    normalized = (teacher_name or "").strip()
    if normalized and normalized not in {"默认", "default", "current"}:
        return teachers.get(normalized) or {}
    return (
        (teachers.get(current_teacher) if current_teacher else None)
        or teachers.get("默认")
        or {}
    )


def ensure_teacher_creds(config_path: str, teacher_name: str) -> dict[str, Any]:
    config = load_config(config_path)
    creds = get_teacher_creds(config, teacher_name)
    if creds:
        return creds
    raise RuntimeError(json.dumps({
        "error_code": "MISSING_TEACHER_CREDENTIALS",
        "teacher": teacher_name,
        "message": f"未找到老师账号信息：{teacher_name}",
    }, ensure_ascii=False))


def build_driver(chromedriver_path: str | None = None, headless: bool = False):
    chromedriver_path = chromedriver_path or os.getenv("CHROMEDRIVER_PATH")
    options = webdriver.ChromeOptions()
    options.add_argument("--disable-gpu")
    options.add_argument("--no-sandbox")
    options.add_argument("--disable-dev-shm-usage")
    if headless:
        options.add_argument("--headless=new")

    browser_binary = os.getenv("GOOGLE_CHROME_BIN") or "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"
    if Path(browser_binary).exists():
        options.binary_location = browser_binary

    if chromedriver_path:
        service = ChromeService(executable_path=chromedriver_path)
        return webdriver.Chrome(service=service, options=options)

    service_env = os.environ.copy()
    path_parts = [p for p in service_env.get("PATH", "").split(os.pathsep) if p and p != "/usr/local/bin"]
    service_env["PATH"] = os.pathsep.join(path_parts)

    try:
        sm_args = ["--browser", "chrome", "--skip-driver-in-path"]
        if Path(browser_binary).exists():
            sm_args.extend(["--browser-path", browser_binary])
        driver_info = SeleniumManager().binary_paths(sm_args)
        driver_path = driver_info.get("driver_path")
        if driver_path:
            service = ChromeService(executable_path=driver_path, env=service_env)
            return webdriver.Chrome(service=service, options=options)
    except Exception:
        pass

    service = ChromeService(env=service_env)
    return webdriver.Chrome(service=service, options=options)


def locate(driver, selector: dict[str, str], wait: int = 15, clickable: bool = False):
    if not selector or not selector.get("value"):
        raise ValueError("Missing selector value in config")
    by = BY_MAP[selector["by"]]
    value = selector["value"]
    condition = EC.element_to_be_clickable((by, value)) if clickable else EC.presence_of_element_located((by, value))
    return WebDriverWait(driver, wait, poll_frequency=0.5).until(condition)


def click(driver, selector: dict[str, str], wait: int = 15, js_fallback: bool = True):
    elem = locate(driver, selector, wait=wait, clickable=True)
    try:
        return elem.click()
    except Exception:
        if js_fallback:
            return driver.execute_script("arguments[0].click();", elem)
        raise


def switch_to_frame(driver, selector: dict[str, str], wait: int = 15):
    by = BY_MAP[selector["by"]]
    value = selector["value"]
    WebDriverWait(driver, wait, poll_frequency=0.5).until(EC.frame_to_be_available_and_switch_to_it((by, value)))


def switch_to_visible_content_frame(driver, wait: int = 20):
    def _find_visible_frame(d):
        frames = d.find_elements(By.CSS_SELECTOR, "iframe[id^='Frame']")
        for frame in frames:
            try:
                if frame.is_displayed():
                    d.switch_to.frame(frame)
                    return True
            except Exception:
                continue
        return False

    WebDriverWait(driver, wait, poll_frequency=0.5).until(_find_visible_frame)


def scrape_table(driver, table_id: str) -> list[dict[str, str]]:
    soup = BeautifulSoup(driver.page_source, "html.parser")
    table = soup.find("table", id=table_id)
    if not table:
        return []
    tbody = table.find("tbody") or table
    all_trs = tbody.find_all("tr")
    if not all_trs:
        return []
    headers = [cell.get_text(strip=True) for cell in all_trs[0].find_all(["th", "td"])]
    rows: list[dict[str, str]] = []
    for tr in all_trs[1:]:
        cells = tr.find_all("td")
        if len(cells) != len(headers):
            continue
        values = [cell.get_text(strip=True) for cell in cells]
        rows.append(dict(zip(headers, values)))
    return rows


def parse_course_cell(cell) -> list[dict[str, str]]:
    blocks = cell.find_all("div", class_=re.compile(r"\bkbcontent\b"))
    candidates: list[dict[str, str]] = []
    for block in blocks:
        text = block.get_text("\n", strip=True).replace("\xa0", " ").strip()
        if not text or text == "&nbsp;":
            continue
        lines = [line.strip() for line in text.splitlines() if line.strip() and line.strip() != "&nbsp;"]
        if not lines:
            continue
        course_name = lines[0]
        week_text = ""
        room_text = ""
        class_text = ""
        headcount = ""
        extras: list[str] = []
        for line in lines[1:]:
            if line.endswith("周") and not week_text:
                week_text = line
            elif "[" in line and "]节" in line and not room_text:
                room_text = line
            elif re.search(r":\d+$", line) and not class_text:
                class_text = line
                parts = line.rsplit(":", 1)
                if len(parts) == 2 and parts[1].isdigit():
                    headcount = parts[1]
            else:
                extras.append(line)
        candidates.append(
            {
                "课程名称": course_name,
                "周次": week_text,
                "教室": room_text,
                "班级": class_text,
                "人数": headcount,
                "附加信息": "；".join(extras),
            }
        )

    merged: dict[tuple[str, str, str, str], dict[str, str]] = {}
    for item in candidates:
        dedupe_key = (item["课程名称"], item["周次"], item["教室"], item["班级"])
        existing = merged.get(dedupe_key)
        if not existing:
            merged[dedupe_key] = item
            continue
        if not existing.get("人数") and item.get("人数"):
            existing["人数"] = item["人数"]
        extras = [x for x in [existing.get("附加信息", ""), item.get("附加信息", "")] if x]
        if extras:
            uniq_extras = []
            seen_extra = set()
            for extra_block in extras:
                for part in [p.strip() for p in extra_block.split("；") if p.strip()]:
                    if part not in seen_extra:
                        seen_extra.add(part)
                        uniq_extras.append(part)
            existing["附加信息"] = "；".join(uniq_extras)

    refined: dict[tuple[str, str, str], dict[str, str]] = {}
    for item in merged.values():
        coarse_key = (item["课程名称"], item["周次"], item["教室"])
        existing = refined.get(coarse_key)
        if not existing:
            refined[coarse_key] = item
            continue
        if not existing.get("班级") and item.get("班级"):
            existing["班级"] = item["班级"]
        if not existing.get("人数") and item.get("人数"):
            existing["人数"] = item["人数"]
        extras = [x for x in [existing.get("附加信息", ""), item.get("附加信息", "")] if x]
        if extras:
            uniq_extras = []
            seen_extra = set()
            for extra_block in extras:
                for part in [p.strip() for p in extra_block.split("；") if p.strip()]:
                    if part not in seen_extra:
                        seen_extra.add(part)
                        uniq_extras.append(part)
            existing["附加信息"] = "；".join(uniq_extras)

    return list(refined.values())


def parse_course_schedule_html(html: str) -> list[dict[str, str]]:
    soup = BeautifulSoup(html, "html.parser")
    table = soup.find("table", id="kbtable")
    if not table:
        return []
    tbody = table.find("tbody") or table
    trs = tbody.find_all("tr")
    if len(trs) < 2:
        return []
    headers = [th.get_text(strip=True) for th in trs[0].find_all(["th", "td"])]
    weekdays = headers[1:8]
    rows: list[dict[str, str]] = []
    for tr in trs[1:]:
        th = tr.find("th")
        tds = tr.find_all("td")
        if not th or len(tds) < 7:
            continue
        period_lines = [line.strip() for line in th.get_text("\n", strip=True).splitlines() if line.strip()]
        if not period_lines:
            continue
        period = period_lines[0]
        time_range = period_lines[1] if len(period_lines) > 1 else ""
        for idx, day in enumerate(weekdays):
            cell_entries = parse_course_cell(tds[idx])
            for entry in cell_entries:
                rows.append(
                    {
                        "星期": day,
                        "节次": period,
                        "时间": time_range,
                        **entry,
                    }
                )
    return rows


def infer_current_week_from_calendar(config_path: str, teacher_name: str, headless: bool = True) -> str:
    config = load_config(config_path)
    creds = get_teacher_creds(config, teacher_name)
    if not creds:
        return ""
    login = config.get("selectors", {}).get("login", {})
    driver = build_driver(headless=headless)
    try:
        driver.get(config["login_url"])
        username = locate(driver, login["username"])
        username.clear()
        username.send_keys(creds["username"])
        password = locate(driver, login["password"])
        password.clear()
        password.send_keys(creds["password"])
        try:
            driver.execute_script("if (typeof submitForm1 === 'function' && submitForm1()) { document.getElementById('Form1').submit(); }")
        except Exception:
            click(driver, login["login_button"])
        WebDriverWait(driver, 30, poll_frequency=0.5).until(lambda d: 'jsMain.jsp' in d.current_url or '教学一体化服务平台' in d.title)
        time.sleep(2)

        click(driver, {"by": "xpath", "value": "//div[@id='onesidebar']//li[@data-code='NEW_JSD_WDZM']"})
        time.sleep(1)
        child = locate(driver, {"by": "xpath", "value": "//aside[contains(@class,'main-sidebar')]//li[@data-code='NEW_JSD_WDZM_JSZL']//li[@data-url='/jxzl/jxzl_query']"}, wait=20, clickable=False)
        driver.execute_script("arguments[0].click();", child)
        time.sleep(2)

        driver.switch_to.default_content()
        switch_to_visible_content_frame(driver)
        html = driver.page_source
        soup = BeautifulSoup(html, "html.parser")
        today = datetime.now().day
        month = datetime.now().month
        for tr in (soup.find("table", id="kbtable") or soup).find_all("tr"):
            first_td = tr.find("td")
            if not first_td:
                continue
            week_no = first_td.get_text(strip=True)
            tds = tr.find_all("td")
            for td in tds[1:8]:
                title = (td.get("title") or "").strip()
                if f"年{month:02d}月{today:02d}" in title or f"年{month}月{today:02d}" in title or f"年{month}月{today}" in title:
                    return week_no
        return ""
    except Exception:
        return ""
    finally:
        driver.quit()


def week_matches(current_week: str, week_text: str) -> bool:
    if not current_week:
        return True
    if not week_text:
        return False
    week_num = int(current_week)
    normalized = week_text.replace("第", "").replace("周", "")
    parts = re.split(r"[;,，；\s]+", normalized)
    for part in parts:
        part = part.strip()
        if not part:
            continue
        if re.fullmatch(r"\d+", part):
            if int(part) == week_num:
                return True
            continue
        m = re.fullmatch(r"(\d+)-(\d+)", part)
        if m and int(m.group(1)) <= week_num <= int(m.group(2)):
            return True
    return False


def run_crawler(config_path: str, teacher_name: str, term: str, query_type: str, headless: bool = False, debug_dir: str | None = None) -> list[dict[str, str]]:
    config = load_config(config_path)
    creds = ensure_teacher_creds(config_path, teacher_name)

    login = config.get("selectors", {}).get("login", {})
    query = config.get("selectors", {}).get("queries", {}).get(query_type)
    login_url = config.get("login_url")
    if not login_url or not query:
        raise SystemExit(f"Missing login_url or query config for {query_type}")

    driver = build_driver(headless=headless)
    debug_path = Path(debug_dir) if debug_dir else None
    if debug_path:
        debug_path.mkdir(parents=True, exist_ok=True)
    try:
        def save_step(name: str):
            if not debug_path:
                return
            safe = name.replace('/', '_')
            try:
                (debug_path / f"{safe}.html").write_text(driver.page_source, encoding="utf-8")
            except Exception:
                pass
            try:
                driver.save_screenshot(str(debug_path / f"{safe}.png"))
            except Exception:
                pass

        try:
            driver.maximize_window()
        except Exception:
            pass

        driver.set_page_load_timeout(30)
        driver.get(login_url)
        save_step('01-login-page')
        username = locate(driver, login["username"])
        username.clear()
        username.send_keys(creds["username"])
        password = locate(driver, login["password"])
        password.clear()
        password.send_keys(creds["password"])
        try:
            driver.execute_script("if (typeof submitForm1 === 'function' && submitForm1()) { document.getElementById('Form1').submit(); }")
        except Exception:
            click(driver, login["login_button"])

        try:
            alert = WebDriverWait(driver, 3).until(EC.alert_is_present())
            alert.accept()
        except Exception:
            pass

        WebDriverWait(driver, 30, poll_frequency=0.5).until(lambda d: 'jsMain.jsp' in d.current_url or '教学一体化服务平台' in d.title)
        time.sleep(2)
        save_step('02-after-login')

        direct_path = query.get("direct_path")
        if direct_path:
            target_url = urljoin(config.get("base_url", login_url), direct_path)
            driver.get(target_url)
            time.sleep(2)
            save_step('03-direct-target')
        else:
            click(driver, query["menu_parent"])
            time.sleep(1)
            save_step('03-after-parent-click')
            child = locate(driver, query["menu_child"], wait=20, clickable=False)
            driver.execute_script("arguments[0].click();", child)
            time.sleep(2)
            save_step('04-after-child-click')

        driver.switch_to.default_content()
        switch_to_visible_content_frame(driver)
        save_step('05-in-visible-frame')

        if query_type == "course_schedule":
            target_term = term or locate(driver, query["term_select"], wait=20).get_attribute("value")
            if target_term:
                select_element = locate(driver, query["term_select"], wait=20)
                current_term = select_element.get_attribute("value")
                if current_term != target_term:
                    Select(select_element).select_by_value(target_term)
                    time.sleep(2)
                    save_step('06-after-term-select')
            current_week = infer_current_week_from_calendar(config_path, teacher_name, headless=headless)
            rows = parse_course_schedule_html(driver.page_source)
            if current_week:
                rows = [row for row in rows if week_matches(current_week, row.get("周次", ""))]
            if rows:
                return rows
        else:
            if query.get("term_select", {}).get("value"):
                select_element = locate(driver, query["term_select"], wait=20)
                Select(select_element).select_by_value(term)
                save_step('06-after-term-select')
            if query.get("query_button", {}).get("value"):
                click(driver, query["query_button"], wait=20)
                time.sleep(2)
                save_step('07-after-query-click')

            rows = scrape_table(driver, query.get("table_id", "dataList"))
            if rows:
                return rows

        if query.get("result_frame", {}).get("value"):
            driver.switch_to.default_content()
            switch_to_visible_content_frame(driver)
            switch_to_frame(driver, query["result_frame"], wait=20)
            WebDriverWait(driver, 20, poll_frequency=0.5).until(lambda d: d.execute_script("return document.readyState") == "complete")
            time.sleep(2)
            save_step('08-in-result-frame')
            rows = scrape_table(driver, query.get("table_id", "dataList"))
            if rows:
                return rows

        driver.switch_to.default_content()
        switch_to_visible_content_frame(driver)
        time.sleep(2)
        save_step('09-after-reenter-frame')
        if query_type == "course_schedule":
            return parse_course_schedule_html(driver.page_source)
        return scrape_table(driver, query.get("table_id", "dataList"))
    except Exception as exc:
        state = {
            "error": str(exc),
            "type": exc.__class__.__name__,
            "url": "",
            "title": "",
            "traceback": traceback.format_exc(),
        }
        try:
            parsed = json.loads(str(exc))
            if isinstance(parsed, dict) and parsed.get("error_code"):
                state.update(parsed)
        except Exception:
            pass
        try:
            state["url"] = driver.current_url
            state["title"] = driver.title
        except Exception:
            pass
        if debug_path:
            try:
                (debug_path / "page.html").write_text(driver.page_source, encoding="utf-8")
            except Exception:
                pass
            try:
                driver.save_screenshot(str(debug_path / "page.png"))
            except Exception:
                pass
            try:
                (debug_path / "error.json").write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8")
            except Exception:
                pass
        raise RuntimeError(json.dumps(state, ensure_ascii=False)) from exc
    finally:
        driver.quit()


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", default="config.json")
    parser.add_argument("--teacher", default="默认")
    parser.add_argument("--term", default="")
    parser.add_argument("--query-type", default="invigilation")
    parser.add_argument("--out", default="")
    parser.add_argument("--format", choices=["csv", "json"], default="json")
    parser.add_argument("--headless", action="store_true")
    parser.add_argument("--debug-dir", default="")
    args = parser.parse_args()

    if args.query_type == "exam_all":
        subtypes = ["invigilation", "exam_course_arrangement", "exam_info"]
        merged_rows: list[dict[str, str]] = []
        details: list[dict[str, Any]] = []
        for subtype in subtypes:
            rows = run_crawler(
                args.config,
                args.teacher,
                args.term,
                query_type=subtype,
                headless=args.headless,
                debug_dir=str(Path(args.debug_dir) / subtype) if args.debug_dir else None,
            )
            tagged = [{"_query_type": subtype, **row} for row in rows]
            merged_rows.extend(tagged)
            details.append({"query_type": subtype, "count": len(rows), "rows": rows})
        output = {
            "query_type": args.query_type,
            "teacher": args.teacher,
            "term": args.term,
            "count": len(merged_rows),
            "rows": merged_rows,
            "details": details,
        }
        print(json.dumps(output, ensure_ascii=False, indent=2))
        final_rows = merged_rows
    else:
        rows = run_crawler(args.config, args.teacher, args.term, query_type=args.query_type, headless=args.headless, debug_dir=args.debug_dir or None)
        print(json.dumps({"query_type": args.query_type, "teacher": args.teacher, "term": args.term, "count": len(rows), "rows": rows}, ensure_ascii=False, indent=2))
        final_rows = rows

    if args.out:
        out_path = Path(args.out)
        out_path.parent.mkdir(parents=True, exist_ok=True)
        if args.format == "json":
            out_path.write_text(json.dumps(final_rows, ensure_ascii=False, indent=2), encoding="utf-8")
        else:
            default_cols = COURSE_SCHEDULE_COLS if args.query_type == "course_schedule" else DEFAULT_COLS
            fieldnames = sorted({k for row in final_rows for k in row.keys()}) if final_rows else default_cols
            with out_path.open("w", newline="", encoding="utf-8") as f:
                writer = csv.DictWriter(f, fieldnames=fieldnames)
                writer.writeheader()
                writer.writerows(final_rows)


if __name__ == "__main__":
    main()
