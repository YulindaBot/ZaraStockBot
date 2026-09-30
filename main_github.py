import json
import os
import time
import subprocess
from datetime import datetime
from zoneinfo import ZoneInfo
from urllib.parse import urlparse, parse_qs

import requests


CONFIG_FILE = os.getenv("CONFIG_FILE", "config1.json")

REEF_API_URL = "https://api.reefapi.com/zara/v1/product_detail"
REEF_KEY = os.getenv("REEF_KEY")

BOT_API = os.getenv("BOT_API")
CHAT_ID = os.getenv("CHAT_ID")


# ============================================================
# CONFIG
# ============================================================

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
            json.dump(
                config,
                f,
                indent=2,
                ensure_ascii=False
            )

        # Якщо бот працює через GitHub Actions —
        # зберігаємо зміну config назад у репозиторій.
        try:
            subprocess.run(
                ["git", "config", "user.name", "github-actions[bot]"],
                check=False
            )

            subprocess.run(
                [
                    "git",
                    "config",
                    "user.email",
                    "41898282+github-actions[bot]@users.noreply.github.com"
                ],
                check=False
            )

            subprocess.run(
                ["git", "add", CONFIG_FILE],
                check=False
            )

            subprocess.run(
                [
                    "git",
                    "commit",
                    "-m",
                    f"Remove found Zara item from {CONFIG_FILE}"
                ],
                check=False
            )

            subprocess.run(
                ["git", "push"],
                check=False
            )

        except Exception as e:
            print(f"⚠️ Git save warning: {e}")

    except Exception as e:
        print(f"❌ Config save error: {e}")


# ============================================================
# TELEGRAM
# ============================================================

def send_telegram(text):
    try:
        if not BOT_API or not CHAT_ID:
            print("❌ BOT_API або CHAT_ID не задані")
            return False

        url = f"https://api.telegram.org/bot{BOT_API}/sendMessage"

        response = requests.post(
            url,
            data={
                "chat_id": CHAT_ID,
                "text": text,
                "parse_mode": "HTML",
                "disable_web_page_preview": False
            },
            timeout=20
        )

        print(
            f"📨 Telegram HTTP: "
            f"{response.status_code}"
        )

        return response.status_code == 200

    except Exception as e:
        print(f"❌ Telegram error: {e}")
        return False


# ============================================================
# PRODUCT ID FROM ZARA URL
# ============================================================

def get_product_id(url):
    try:
        parsed = urlparse(url)
        query = parse_qs(parsed.query)

        v1 = query.get("v1")

        if v1:
            return str(v1[0])

    except Exception as e:
        print(f"❌ URL parse error: {e}")

    return None


# ============================================================
# REEF API
# ============================================================

def get_product_detail(product_id):
    if not REEF_KEY:
        print("❌ REEF_KEY is missing")
        return None

    headers = {
        "x-api-key": REEF_KEY,
        "Content-Type": "application/json"
    }

    payload = {
        "product_id": str(product_id),
        "market": "pl",
        "include_composition": False,
        "find_market": False
    }

    for attempt in range(1, 4):

        try:
            print(
                f"📡 ReefAPI product_detail "
                f"attempt {attempt}/3"
            )

            response = requests.post(
                REEF_API_URL,
                headers=headers,
                json=payload,
                timeout=40
            )

            print(
                f"DETAIL HTTP: "
                f"{response.status_code}"
            )

            if response.status_code != 200:
                print(
                    response.text[:1000]
                )

                if attempt < 3:
                    time.sleep(2)

                continue

            result = response.json()

            if result.get("ok") is False:
                print(
                    f"❌ ReefAPI error: "
                    f"{result}"
                )
                return None

            data = result.get("data")

            if data:
                return data

            print(
                "❌ ReefAPI returned no data"
            )

        except Exception as e:
            print(
                f"❌ ReefAPI exception: {e}"
            )

        if attempt < 3:
            time.sleep(2)

    return None


# ============================================================
# STOCK HELPERS
# ============================================================

def normalize_status(value):
    return str(value or "").upper()


def status_is_available(value):
    status = normalize_status(value)

    return status in {
        "AVAILABLE",
        "IN_STOCK",
        "LOW_STOCK"
    }


def size_is_available(size):
    if size.get("in_stock") is True:
        return True

    if status_is_available(
        size.get("availability")
    ):
        return True

    return False


def get_all_sizes(data):
    sizes = []

    # ReefAPI може повертати кольори
    colors = data.get("colors")

    if isinstance(colors, list):
        for color in colors:
            color_sizes = color.get("sizes")

            if isinstance(color_sizes, list):
                sizes.extend(color_sizes)

    # Або selected_color
    selected_color = data.get("selected_color")

    if isinstance(selected_color, dict):
        color_sizes = selected_color.get("sizes")

        if isinstance(color_sizes, list):
            sizes.extend(color_sizes)

    # Або sizes напряму
    direct_sizes = data.get("sizes")

    if isinstance(direct_sizes, list):
        sizes.extend(direct_sizes)

    return sizes


def get_available_sizes(data):
    available = []

    for size in get_all_sizes(data):

        if not size_is_available(size):
            continue

        size_name = (
            size.get("name")
            or size.get("size")
            or size.get("label")
            or size.get("description")
        )

        if size_name:
            size_name = str(size_name)

            if size_name not in available:
                available.append(size_name)

    return available


def product_is_available(data):
    if data.get("in_stock") is True:
        return True

    if status_is_available(
        data.get("availability")
    ):
        return True

    selected_color = data.get(
        "selected_color"
    )

    if isinstance(selected_color, dict):

        if selected_color.get(
            "in_stock"
        ) is True:
            return True

        if status_is_available(
            selected_color.get(
                "availability"
            )
        ):
            return True

    available_sizes = (
        get_available_sizes(data)
    )

    if available_sizes:
        return True

    return False


# ============================================================
# CHECK PRODUCT
# ============================================================

def check_product(item):
    url = item.get("url", "")
    wanted_sizes = item.get(
        "sizes",
        []
    )

    print("")
    print("=" * 60)
    print(f"🔍 Checking:")
    print(url)

    product_id = get_product_id(url)

    if not product_id:
        print(
            "❌ Не знайдено v1= у URL"
        )
        return False, []

    print(
        f"🆔 Product ID: "
        f"{product_id}"
    )

    data = get_product_detail(
        product_id
    )

    if not data:
        return False, []

    available_sizes = (
        get_available_sizes(data)
    )

    print(
        f"📦 availability: "
        f"{data.get('availability')}"
    )

    print(
        f"📦 in_stock: "
        f"{data.get('in_stock')}"
    )

    print(
        f"📏 Available sizes: "
        f"{available_sizes}"
    )

    # ========================================================
    # СУМКИ / ТОВАР БЕЗ РОЗМІРУ
    # ========================================================

    if not wanted_sizes:

        if product_is_available(data):
            print("🎉 FOUND")
            return True, available_sizes

        print("❌ Not available")
        return False, []

    # ========================================================
    # ОДЯГ З РОЗМІРАМИ
    # ========================================================

    wanted = {
        str(x).strip().upper()
        for x in wanted_sizes
    }

    matching_sizes = []

    for size in available_sizes:

        if str(size).strip().upper() in wanted:
            matching_sizes.append(size)

    if matching_sizes:
        print(
            f"🎉 FOUND sizes: "
            f"{matching_sizes}"
        )

        return True, matching_sizes

    print(
        "❌ Потрібного розміру немає"
    )

    return False, []


# ============================================================
# MAIN
# ============================================================

def main():
    print("")
    print("=" * 60)
    print("⚡ ZARA STOCK CHECKER")
    print(
        f"📄 CONFIG_FILE: "
        f"{CONFIG_FILE}"
    )
    print(
        f"🕐 "
        f"{datetime.now(ZoneInfo('Europe/Warsaw'))}"
    )
    print("=" * 60)

    config = load_config()

    if not config:
        return

    items = config.get(
        "urls",
        []
    )

    if not items:
        print("ℹ️ Немає товарів")
        return

    remaining_items = []

    for item in items:

        found, sizes = check_product(
            item
        )

        if found:

            url = item.get(
                "url",
                ""
            )

            person = item.get(
                "person",
                "Yulia"
            )

            message = (
                "🚨 <b>ZARA Є В НАЯВНОСТІ!</b>\n\n"
                f"👤 {person}\n"
            )

            if sizes:
                message += (
                    "📏 Розміри: "
                    + ", ".join(sizes)
                    + "\n"
                )

            message += (
                f"\n🔗 {url}"
            )

            sent = send_telegram(
                message
            )

            if sent:
                print(
                    "✅ Telegram sent — "
                    "removing item"
                )

                # Не додаємо назад =
                # товар видаляється з config

            else:
                print(
                    "⚠️ Telegram failed — "
                    "keeping item"
                )

                remaining_items.append(
                    item
                )

        else:
            remaining_items.append(
                item
            )

    if len(remaining_items) != len(items):

        config["urls"] = (
            remaining_items
        )

        save_config(
            config
        )

        print(
            "💾 Config updated"
        )

    print("")
    print("✅ Check finished")


if __name__ == "__main__":
    main()
