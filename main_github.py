import json
import time
import subprocess
import os
import requests

from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.chrome.options import Options
from selenium.common.exceptions import TimeoutException, WebDriverException
from webdriver_manager.chrome import ChromeDriverManager

from scraperHelpers import (
    check_stock_zara,
    check_stock_bershka,
    check_stock_stradivarius
)


# Bot 1 uses config1.json by default.
# Bot 2 sets CONFIG_FILE=config2.json before importing this file.
CONFIG_FILE = os.getenv("CONFIG_FILE", "config1.json")


def load_config():
    try:
        with open(CONFIG_FILE, "r") as config_file:
            return json.load(config_file)

    except FileNotFoundError:
        print(f"❌ {CONFIG_FILE} file not found!")
        return None

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
            try:
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
                    commit_msg = (
                        f"🗑️ Auto-remove found item "
                        f"- {time.strftime('%H:%M:%S')}"
                    )

                    subprocess.run(
                        ["git", "commit", "-m", commit_msg],
                        check=True,
                        capture_output=True
                    )

                    subprocess.run(
                        ["git", "push"],
                        check=True,
                        capture_output=True
                    )

                    print(
                        f"✅ {CONFIG_FILE} changes pushed to GitHub"
                    )

                else:
                    print("⚠️ No config changes to commit")

                return True

            except subprocess.CalledProcessError as e:
                print(f"⚠️ Git operation failed: {e}")
                return True

        print(f"✅ {CONFIG_FILE} saved locally")
        return True

    except Exception as e:
        print(f"❌ Config save failed: {e}")
        return False


def remove_item_from_config(config, item_to_remove):
    try:
        original_count = len(config.get("urls", []))

        config["urls"] = [
            item
            for item in config.get("urls", [])
            if item["url"] != item_to_remove["url"]
        ]

        removed = original_count - len(config["urls"])

        if removed > 0:
            print(
                f"🗑️ Removed {removed} item from {CONFIG_FILE}"
            )
            return save_config(config)

        return False

    except Exception as e:
        print(f"❌ Remove item error: {e}")
        return False


def setup_telegram():
    bot_api = os.getenv("BOT_API")
    chat_id = os.getenv("CHAT_ID")

    if not bot_api or not chat_id:
        print(
            "⚠️ BOT_API or CHAT_ID missing. "
            "Telegram disabled."
        )
        return False, None, None

    return True, bot_api, chat_id


def send_telegram_message(message, bot_api, chat_id):
    if not bot_api or not chat_id:
        return False

    url = (
        f"https://api.telegram.org/"
        f"bot{bot_api}/sendMessage"
    )

    payload = {
        "chat_id": chat_id,
        "text": message,
        "parse_mode": "HTML"
    }

    try:
        response = requests.post(
            url,
            data=payload,
            timeout=8
        )

        response.raise_for_status()

        print("✅ Telegram message sent.")
        return True

    except requests.exceptions.RequestException as e:
        print(f"❌ Telegram error: {e}")
        return False


def setup_chrome_driver():
    chrome_options = Options()

    # Load DOM faster without waiting for every resource.
    chrome_options.page_load_strategy = "eager"

    chrome_options.add_argument("--headless=new")
    chrome_options.add_argument("--no-sandbox")
    chrome_options.add_argument("--disable-dev-shm-usage")
    chrome_options.add_argument("--disable-gpu")
    chrome_options.add_argument("--disable-extensions")
    chrome_options.add_argument("--disable-plugins")
    chrome_options.add_argument("--disable-images")
    chrome_options.add_argument("--disable-fonts")
    chrome_options.add_argument("--disable-notifications")
    chrome_options.add_argument("--disable-background-networking")
    chrome_options.add_argument("--disable-background-timer-throttling")
    chrome_options.add_argument("--disable-renderer-backgrounding")
    chrome_options.add_argument(
        "--disable-backgrounding-occluded-windows"
    )
    chrome_options.add_argument("--disable-sync")
    chrome_options.add_argument("--disable-translate")
    chrome_options.add_argument("--hide-scrollbars")
    chrome_options.add_argument("--mute-audio")
    chrome_options.add_argument("--no-first-run")
    chrome_options.add_argument("--window-size=1280,720")

    chrome_options.add_argument(
        "--user-agent=Mozilla/5.0 "
        "(X11; Linux x86_64) "
        "AppleWebKit/537.36 "
        "(KHTML, like Gecko) "
        "Chrome/120.0.0.0 Safari/537.36"
    )

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

        # Shorter timeout.
        driver.set_page_load_timeout(10)

        # Important:
        # no 5-second implicit wait on every lookup.
        driver.implicitly_wait(0)

        return driver

    except Exception as e:
        print(f"❌ Chrome setup failed: {e}")
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

    if not url or not store:
        print("⚠️ Invalid item configuration")
        return False

    print(
        f"\n📋 Checking {store.upper()} "
        f"| sizes: {', '.join(sizes_to_check)}"
    )

    try:
        try:
            driver.get(url)

        except TimeoutException:
            # Even if full page load times out,
            # DOM may already contain what we need.
            print("⚡ Page load timeout - checking DOM anyway.")

        size_in_stock = None

        if store == "zara":
            size_in_stock = check_stock_zara(
                driver,
                sizes_to_check
            )

        elif store == "bershka":
            size_in_stock = check_stock_bershka(
                driver,
                sizes_to_check
            )

        elif store == "stradivarius":
            size_in_stock = check_stock_stradivarius(
                driver,
                sizes_to_check
            )

        else:
            print(f"❌ Unsupported store: {store}")
            return False

        if not size_in_stock:
            print(
                f"❌ No stock: "
                f"{', '.join(sizes_to_check)}"
            )
            return False

        print(
            f"🎉 STOCK FOUND: "
            f"{size_in_stock} - {store.upper()}"
        )

        removed = remove_item_from_config(
            config,
            item
        )

        if removed:
            auto_remove_msg = (
                "🗑️ Товар автоматично видалено "
                "зі списку відстеження"
            )
        else:
            auto_remove_msg = (
                "⚠️ Перевір список відстеження вручну"
            )

        message = (
            f"🛍️ <b>ТОВАР З'ЯВИВСЯ!</b>\n\n"
            f"👤 <b>{person}</b>\n"
            f"📏 Розмір: <b>{size_in_stock}</b>\n"
            f"🏪 Магазин: <b>{store.upper()}</b>\n"
            f"🔗 <a href='{url}'>Відкрити товар</a>\n\n"
            f"{auto_remove_msg}"
        )

        if telegram_enabled:
            send_telegram_message(
                message,
                bot_api,
                chat_id
            )

        return True

    except WebDriverException as e:
        print(f"🌐 WebDriver error: {e}")
        return False

    except Exception as e:
        print(f"❌ Item error: {e}")
        return False


def main():
    start_time = time.time()

    print("⚡ FAST Zara Stock Checker")
    print(f"📄 Config: {CONFIG_FILE}")
    print(f"🚀 Start: {time.strftime('%H:%M:%S')}")

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

    found_stock = False
    checked_count = 0

    try:
        for item in urls_to_check:
            checked_count += 1

            print(
                f"\n{'=' * 40}\n"
                f"📦 Item "
                f"{checked_count}/{len(urls_to_check)}"
            )

            result = check_single_item(
                driver,
                item,
                telegram_enabled,
                bot_api,
                chat_id,
                config
            )

            if result:
                found_stock = True

            # NO 1-2 second sleep between products.

    except Exception as e:
        print(f"❌ Main loop error: {e}")

    finally:
        try:
            driver.quit()
        except Exception:
            pass

    elapsed = time.time() - start_time
    remaining_items = len(
        config.get("urls", [])
    )

    print("\n⚡ SUMMARY")
    print(f"✅ Checked: {checked_count}")
    print(
        f"🛍️ Found: "
        f"{'YES' if found_stock else 'NO'}"
    )
    print(f"📋 Remaining: {remaining_items}")
    print(f"⏱️ Total time: {elapsed:.1f} sec")


if __name__ == "__main__":
    main()
