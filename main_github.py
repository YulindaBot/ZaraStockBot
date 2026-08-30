import json
import time
import subprocess
import os
import requests

from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.chrome.options import Options
from selenium.common.exceptions import TimeoutException
from webdriver_manager.chrome import ChromeDriverManager

from scraperHelpers import (
    check_stock_zara,
    check_stock_bershka,
    check_stock_stradivarius
)


CONFIG_FILE = os.getenv("CONFIG_FILE", "config1.json")


def load_config():
    try:
        with open(CONFIG_FILE, "r") as config_file:
            return json.load(config_file)
    except Exception as e:
        print(f"❌ Config load error: {e}")
        return None


def save_config(config):
    try:
        with open(CONFIG_FILE, "w") as config_file:
            json.dump(
                config,
                config_file,
                indent=2,
                ensure_ascii=False
            )

        if os.getenv("GITHUB_ACTIONS"):
            subprocess.run(
                [
                    "git",
                    "config",
                    "--global",
                    "user.name",
                    "Stock Checker Bot"
                ],
                check=True,
                capture_output=True
            )

            subprocess.run(
                [
                    "git",
                    "config",
                    "--global",
                    "user.email",
                    "actions@github.com"
                ],
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
                    [
                        "git",
                        "commit",
                        "-m",
                        "Auto-remove found Zara item"
                    ],
                    check=True,
                    capture_output=True
                )

                subprocess.run(
                    ["git", "push"],
                    check=True,
                    capture_output=True
                )

        return True

    except Exception as e:
        print(f"❌ Config save error: {e}")
        return False


def remove_item_from_config(config, item_to_remove):
    original_count = len(config.get("urls", []))

    config["urls"] = [
        item
        for item in config.get("urls", [])
        if item["url"] != item_to_remove["url"]
    ]

    if len(config["urls"]) < original_count:
        return save_config(config)

    return False


def setup_telegram():
    bot_api = os.getenv("BOT_API")
    chat_id = os.getenv("CHAT_ID")

    return (
        bool(bot_api and chat_id),
        bot_api,
        chat_id
    )


def send_telegram_message(message, bot_api, chat_id):
    try:
        response = requests.post(
            f"https://api.telegram.org/bot{bot_api}/sendMessage",
            data={
                "chat_id": chat_id,
                "text": message,
                "parse_mode": "HTML"
            },
            timeout=8
        )

        response.raise_for_status()
        return True

    except Exception as e:
        print(f"❌ Telegram error: {e}")
        return False


def setup_chrome_driver():
    chrome_options = Options()

    chrome_options.page_load_strategy = "eager"

    chrome_options.add_argument("--headless=new")
    chrome_options.add_argument("--no-sandbox")
    chrome_options.add_argument("--disable-dev-shm-usage")
    chrome_options.add_argument("--disable-gpu")
    chrome_options.add_argument("--disable-images")
    chrome_options.add_argument("--disable-fonts")
    chrome_options.add_argument("--disable-extensions")
    chrome_options.add_argument("--disable-notifications")
    chrome_options.add_argument("--disable-background-networking")
    chrome_options.add_argument("--mute-audio")
    chrome_options.add_argument("--window-size=1280,720")

    try:
        if os.path.exists("/usr/bin/chromedriver"):
            service = Service("/usr/bin/chromedriver")
        else:
            service = Service(
                ChromeDriverManager().install()
            )

        driver = webdriver.Chrome(
            service=service,
            options=chrome_options
        )

        driver.set_page_load_timeout(10)
        driver.implicitly_wait(0)

        return driver

    except Exception as e:
        print(f"❌ Chrome setup error: {e}")
        return None


def check_single_item(
    driver,
    item,
    telegram_enabled,
    bot_api,
    chat_id,
    config
):
    url = item.get("url")
    store = item.get("store", "").lower()
    sizes_to_check = item.get("sizes", [])
    person = item.get("person", "Yulia")

    print(
        f"\n📋 Checking {store.upper()} "
        f"| sizes: {', '.join(sizes_to_check)}"
    )

    try:
        try:
            driver.get(url)
        except TimeoutException:
            print("⚡ Page timeout - checking DOM.")

        available_sizes = []

        if store == "zara":
            available_sizes = check_stock_zara(
                driver,
                sizes_to_check
            )

        elif store == "bershka":
            available_sizes = check_stock_bershka(
                driver,
                sizes_to_check
            )

        elif store == "stradivarius":
            available_sizes = check_stock_stradivarius(
                driver,
                sizes_to_check
            )

        if not available_sizes:
            print(
                f"❌ No stock: "
                f"{', '.join(sizes_to_check)}"
            )
            return False

        print(
            "🎉 STOCK FOUND: "
            + ", ".join(available_sizes)
        )

        removed = remove_item_from_config(
            config,
            item
        )

        sizes_text = ", ".join(available_sizes)

        message = (
            f"🛍️ <b>ТОВАР З'ЯВИВСЯ!</b>\n\n"
            f"👤 <b>{person}</b>\n"
            f"📏 Розміри: <b>{sizes_text}</b>\n"
            f"🏪 Магазин: <b>{store.upper()}</b>\n"
            f"🔗 <a href='{url}'>Відкрити товар</a>\n\n"
        )

        if removed:
            message += (
                "🗑️ Товар автоматично видалено "
                "зі списку відстеження"
            )

        if telegram_enabled:
            send_telegram_message(
                message,
                bot_api,
                chat_id
            )

        return True

    except Exception as e:
        print(f"❌ Item error: {e}")
        return False


def main():
    start_time = time.time()

    print("⚡ FAST Zara Stock Checker")
    print(f"📄 Config: {CONFIG_FILE}")

    config = load_config()

    if not config:
        return

    urls_to_check = list(
        config.get("urls", [])
    )

    if not urls_to_check:
        print("🎯 No items to check.")
        return

    telegram_enabled, bot_api, chat_id = (
        setup_telegram()
    )

    driver = setup_chrome_driver()

    if not driver:
        return

    checked_count = 0
    found_count = 0

    try:
        for item in urls_to_check:
            checked_count += 1

            print(
                f"\n{'=' * 40}\n"
                f"📦 Item "
                f"{checked_count}/{len(urls_to_check)}"
            )

            if check_single_item(
                driver,
                item,
                telegram_enabled,
                bot_api,
                chat_id,
                config
            ):
                found_count += 1

    finally:
        try:
            driver.quit()
        except Exception:
            pass

    elapsed = time.time() - start_time

    print("\n⚡ SUMMARY")
    print(f"✅ Checked: {checked_count}")
    print(f"🛍️ Found: {found_count}")
    print(f"⏱️ Total time: {elapsed:.1f} sec")


if __name__ == "__main__":
    main()
