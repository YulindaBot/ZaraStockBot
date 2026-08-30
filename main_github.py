import json
import os
import time
import subprocess
import requests

from datetime import datetime
from zoneinfo import ZoneInfo
from playwright.sync_api import sync_playwright, TimeoutError as PlaywrightTimeoutError


CONFIG_FILE = os.getenv("CONFIG_FILE", "config1.json")


def load_config():
    try:
        with open(CONFIG_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception as e:
        print(f"❌ Config load error: {e}")
        return None


def save_config(config):
    try:
        with open(CONFIG_FILE, "w", encoding="utf-8") as f:
            json.dump(config, f, indent=2, ensure_ascii=False)

        if os.getenv("GITHUB_ACTIONS"):
            subprocess.run(
                ["git", "config", "--global", "user.name", "Stock Checker Bot"],
                check=True,
                capture_output=True
            )

            subprocess.run(
                ["git", "config", "--global", "user.email", "actions@github.com"],
                check=True,
                capture_output=True
            )

            subprocess.run(
                ["git", "add", CONFIG_FILE],
                check=True,
                capture_output=True
            )

            result = subprocess.run(
                ["git", "diff", "--staged", "--quiet"],
                capture_output=True
            )

            if result.returncode != 0:
                subprocess.run(
                    ["git", "commit", "-m", "Auto-remove found Zara item"],
                    check=True,
                    capture_output=True
                )

                subprocess.run(
                    ["git", "push"],
                    check=True,
                    capture_output=True
                )

                print(f"✅ {CONFIG_FILE} updated in GitHub")

        return True

    except Exception as e:
        print(f"⚠️ Config save/push error: {e}")
        return False


def remove_item_from_config(config, item):
    before = len(config.get("urls", []))

    config["urls"] = [
        x for x in config.get("urls", [])
        if x.get("url") != item.get("url")
    ]

    if len(config["urls"]) < before:
        return save_config(config)

    return False


def telegram_setup():
    bot_api = os.getenv("BOT_API")
    chat_id = os.getenv("CHAT_ID")
    return bot_api, chat_id


def send_telegram(message, bot_api, chat_id):
    if not bot_api or not chat_id:
        print("⚠️ Telegram credentials missing")
        return

    try:
        response = requests.post(
            f"https://api.telegram.org/bot{bot_api}/sendMessage",
            data={
                "chat_id": chat_id,
                "text": message,
                "parse_mode": "HTML",
                "disable_web_page_preview": False
            },
            timeout=10
        )

        response.raise_for_status()
        print("✅ Telegram sent")

    except Exception as e:
        print(f"❌ Telegram error: {e}")


def normalize_size(text):
    return (
        text.replace("\n", " ")
        .replace("\t", " ")
        .strip()
        .upper()
    )


def check_zara(page, url, wanted_sizes):
    print(f"🌐 Opening: {url}")

    try:
        page.goto(
            url,
            wait_until="domcontentloaded",
            timeout=15000
        )
    except PlaywrightTimeoutError:
        print("⚠️ Page load timeout, continuing...")

    # Allow Zara JS a moment to render the product controls.
    page.wait_for_timeout(1200)

    # Cookies
    try:
        cookie = page.locator("#onetrust-accept-btn-handler")

        if cookie.count() > 0 and cookie.first.is_visible():
            cookie.first.click(timeout=2000)
            print("🍪 Cookies accepted")
            page.wait_for_timeout(300)
    except Exception:
        pass

    # Find ADD button using several methods.
    add_selectors = [
        "button[data-qa-action='add-to-cart']",
        "[data-qa-action='add-to-cart']",
        "button:has-text('Dodaj')",
        "[role='button']:has-text('Dodaj')"
    ]

    add_button = None

    for selector in add_selectors:
        try:
            locator = page.locator(selector)

            for i in range(locator.count()):
                candidate = locator.nth(i)

                if candidate.is_visible():
                    add_button = candidate
                    print(f"✅ Add button found: {selector}")
                    break

            if add_button:
                break

        except Exception:
            continue

    if not add_button:
        print("❌ ADD BUTTON NOT FOUND")
        return []

    try:
        add_button.click(timeout=5000, force=True)
        print("🛒 Add button clicked")
    except Exception as e:
        print(f"❌ Add button click failed: {e}")
        return []

    # Wait for Zara size options.
    try:
        page.wait_for_selector(
            "[data-qa-action^='size-'], .size-selector-sizes-size",
            timeout=6000
        )
    except PlaywrightTimeoutError:
        print("❌ SIZE SELECTOR NOT FOUND")
        return []

    page.wait_for_timeout(400)

    wanted = [normalize_size(x) for x in wanted_sizes]
    available = []

    print(f"🔍 Requested sizes: {', '.join(wanted)}")

    # Primary method: Zara buttons with stock action.
    size_buttons = page.locator("[data-qa-action^='size-']")

    print(f"📦 Size-action elements found: {size_buttons.count()}")

    checked = set()

    for i in range(size_buttons.count()):
        button = size_buttons.nth(i)

        try:
            action = button.get_attribute("data-qa-action") or ""

            # Get text from the button and its closest parent.
            text = normalize_size(button.inner_text())

            if not text:
                try:
                    text = normalize_size(
                        button.locator("xpath=ancestor::*[self::li or self::div][1]").inner_text()
                    )
                except Exception:
                    pass

            matched_size = None

            for size in wanted:
                parts = text.split()

                if size == text or size in parts:
                    matched_size = size
                    break

            if not matched_size:
                continue

            if matched_size in checked:
                continue

            checked.add(matched_size)

            print(
                f"📏 {matched_size} → "
                f"{action if action else 'unknown'}"
            )

            if action in ("size-in-stock", "size-low-on-stock"):
                available.append(matched_size)
                print(f"✅ {matched_size} AVAILABLE")
            else:
                print(f"❌ {matched_size} unavailable")

        except Exception as e:
            print(f"⚠️ Size parse error: {e}")

    # Fallback: inspect Zara size containers.
    if len(checked) < len(wanted):
        containers = page.locator(".size-selector-sizes-size")

        for i in range(containers.count()):
            item = containers.nth(i)

            try:
                text = normalize_size(item.inner_text())

                matched_size = None

                for size in wanted:
                    if size in checked:
                        continue

                    parts = text.split()

                    if size == text or size in parts:
                        matched_size = size
                        break

                if not matched_size:
                    continue

                checked.add(matched_size)

                actions = item.locator("[data-qa-action]")
                action = ""

                if actions.count() > 0:
                    action = (
                        actions.first.get_attribute("data-qa-action")
                        or ""
                    )

                print(
                    f"📏 {matched_size} → "
                    f"{action if action else 'unknown'}"
                )

                if action in ("size-in-stock", "size-low-on-stock"):
                    if matched_size not in available:
                        available.append(matched_size)

                    print(f"✅ {matched_size} AVAILABLE")
                else:
                    print(f"❌ {matched_size} unavailable")

            except Exception:
                continue

    for size in wanted:
        if size not in checked:
            print(f"⚠️ {size} was not found in Zara size list")

    print(
        "🟢 AVAILABLE: "
        + (", ".join(available) if available else "NONE")
    )

    return available


def check_item(page, item, config, bot_api, chat_id):
    store = item.get("store", "").lower()
    url = item.get("url")
    sizes = item.get("sizes", [])
    person = item.get("person", "Yulia")

    if store != "zara":
        print(f"⚠️ Unsupported store: {store}")
        return False

    print("\n" + "=" * 50)
    print(f"📋 Checking ZARA | sizes: {', '.join(sizes)}")

    available = check_zara(page, url, sizes)

    if not available:
        print(f"❌ No stock: {', '.join(sizes)}")
        return False

    removed = remove_item_from_config(config, item)

    sizes_text = ", ".join(available)

    warsaw_time = datetime.now(
        ZoneInfo("Europe/Warsaw")
    ).strftime("%H:%M:%S")

    message = (
        "🛍️ <b>ТОВАР З'ЯВИВСЯ!</b>\n\n"
        f"👤 <b>{person}</b>\n"
        f"📏 Розміри: <b>{sizes_text}</b>\n"
        "🏪 Магазин: <b>ZARA</b>\n"
        f"🔗 <a href='{url}'>Відкрити товар</a>\n"
        f"⏰ Час: <b>{warsaw_time}</b>\n\n"
    )

    if removed:
        message += "🗑️ Товар автоматично видалено зі списку відстеження"

    send_telegram(
        message,
        bot_api,
        chat_id
    )

    print(f"🎉 FOUND: {sizes_text}")
    return True


def main():
    start = time.time()

    print("🎭 PLAYWRIGHT ZARA STOCK CHECKER")
    print(f"📄 Config: {CONFIG_FILE}")

    config = load_config()

    if not config:
        return

    items = list(config.get("urls", []))

    if not items:
        print("🎯 No items in config")
        return

    bot_api, chat_id = telegram_setup()

    found = 0

    with sync_playwright() as p:
        browser = p.chromium.launch(
            headless=True,
            args=[
                "--no-sandbox",
                "--disable-dev-shm-usage"
            ]
        )

        context = browser.new_context(
            locale="pl-PL",
            timezone_id="Europe/Warsaw",
            viewport={
                "width": 1280,
                "height": 900
            }
        )

        page = context.new_page()

        for index, item in enumerate(items, start=1):
            print(
                f"\n📦 ITEM {index}/{len(items)}"
            )

            if check_item(
                page,
                item,
                config,
                bot_api,
                chat_id
            ):
                found += 1

        browser.close()

    elapsed = time.time() - start

    print("\n⚡ SUMMARY")
    print(f"✅ Checked: {len(items)}")
    print(f"🛍️ Found: {found}")
    print(f"⏱️ Total time: {elapsed:.1f} sec")


if __name__ == "__main__":
    main()
