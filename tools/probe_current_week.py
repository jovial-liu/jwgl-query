#!/usr/bin/env python3
from __future__ import annotations

import json
import sys
import time
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

from crawl import load_config, build_driver, locate, click, switch_to_visible_content_frame
from selenium.webdriver.common.by import By


def main() -> None:
    config_path = Path(sys.argv[1]) if len(sys.argv) > 1 else Path("config.json")
    out_dir = Path(sys.argv[2]) if len(sys.argv) > 2 else Path("out/probe-week")
    out_dir.mkdir(parents=True, exist_ok=True)

    config = load_config(str(config_path))
    teacher = config["teachers"][config.get("current_teacher") or "默认"]
    login = config["selectors"]["login"]

    driver = build_driver(headless=True)
    try:
        driver.get(config["login_url"])
        locate(driver, login["username"]).send_keys(teacher["username"])
        locate(driver, login["password"]).send_keys(teacher["password"])
        try:
            driver.execute_script("if (typeof submitForm1 === 'function' && submitForm1()) { document.getElementById('Form1').submit(); }")
        except Exception:
            click(driver, login["login_button"])
        time.sleep(3)

        click(driver, {"by": "xpath", "value": "//div[@id='onesidebar']//li[@data-code='NEW_JSD_WDZM']"})
        time.sleep(1)
        child = locate(driver, {"by": "xpath", "value": "//aside[contains(@class,'main-sidebar')]//li[@data-code='NEW_JSD_WDZM_JSZL']//li[@data-url='/jxzl/jxzl_query']"}, wait=20, clickable=False)
        driver.execute_script("arguments[0].click();", child)
        time.sleep(3)

        driver.switch_to.default_content()
        switch_to_visible_content_frame(driver)
        time.sleep(2)
        page = driver.page_source
        (out_dir / "page.html").write_text(page, encoding="utf-8")
        driver.save_screenshot(str(out_dir / "page.png"))
        print(json.dumps({"ok": True, "title": driver.title, "url": driver.current_url}, ensure_ascii=False))
    finally:
        driver.quit()


if __name__ == "__main__":
    main()
