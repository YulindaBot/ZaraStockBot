import json
import os
import time
from datetime import datetime
from zoneinfo import ZoneInfo
from urllib.parse import urlparse, parse_qs

import requests


# ============================================================
# CONFIG
# ============================================================

CONFIG_FILE = os.getenv("CONFIG_FILE", "config1.json")

REEF_API_URL = "https://api.reefapi.com/zara/v1/product_detail"

REEF_KEY = os.getenv("REEF_KEY")
BOT_API = os.getenv("BOT_API")
CHAT_ID = os.getenv("CHAT_ID")

MARKET = "pl"

# Поки тестуємо:
# False = НЕ видаляти товар після знаходження
# Потім повернемо True
REMOVE_FOUND_ITEMS = False


# ============================================================
# HELPERS
# ============================================================

def now():
    return datetime.now(
        ZoneInfo("Europe/Warsaw")
    ).strftime("%Y-%m-%d %H:%M:%S")


def load_config():
    try:
        with open(CONFIG_FILE, "r", encoding="utf-8") as f:
            return json.load(f)

    except Exception as e:
        print(f"❌ CONFIG LOAD ERROR: {e}")
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

        print("💾 Config saved")

    except Exception as e:
        print(f"❌ CONFIG SAVE ERROR: {e}")


def send_telegram(message):
    if not BOT_API or not CHAT_ID:
        print("⚠️ Telegram secrets missing")
        return False

    try:
        url = f"https://api.telegram.org/bot{BOT_API}/sendMessage"

        response = requests.post(
            url,
            json={
                "chat_id": CHAT_ID,
                "text": message,
                "disable_web_page_preview": False
            },
            timeout=20
        )

        if response.status_code == 200:
            print("📨 Telegram sent")
            return True

        print(
            f"❌ Telegram error "
            f"{response.status_code}: "
            f"{response.text[:500]}"
        )

    except Exception as e:
        print(f"❌ Telegram exception: {e}")

    return False


# ============================================================
# ZARA PRODUCT ID
# ============================================================

def extract_product_id(url):
    """
    ReefAPI Zara product_detail використовує product_id,
    який у Zara URL знаходиться після ?v1=
    """

    try:
        parsed = urlparse(url)

        query = parse_qs(parsed.query)

        value = query.get("v1")

        if value and value[0]:
            product_id = str(value[0]).strip()

            if product_id.isdigit():
                return product_id

    except Exception:
        pass

    return None


# ============================================================
# REEF API
# ============================================================

def reef_product_detail(product_id):
    headers = {
        "x-api-key": REEF_KEY,
        "content-type": "application/json"
    }

    payload = {
        "product_id": str(product_id),
        "market": MARKET,

        # Нам не потрібен склад тканини/матеріалів.
        # Так запит буде швидший.
        "include_composition": False,

        # Перевіряємо тільки Польщу.
        "find_market": False
    }

    last_error = None

    for attempt in range(1, 4):

        print(
            f"📡 ReefAPI attempt "
            f"{attempt}/3..."
        )

        try:
            response = requests.post(
                REEF_API_URL,
                headers=headers,
                json=payload,
                timeout=45
            )

            print(
                f"📡 DETAIL HTTP: "
                f"{response.status_code}"
            )

            if response.status_code != 200:

                last_error = (
                    f"HTTP {response.status_code}: "
                    f"{response.text[:700]}"
                )

                print(
                    f"❌ ReefAPI HTTP ERROR: "
                    f"{last_error}"
                )

                if attempt < 3:
                    time.sleep(3)

                continue

            try:
                result = response.json()

            except Exception:
                last_error = (
                    "ReefAPI returned invalid JSON"
                )

                print(
                    f"❌ {last_error}"
                )

                if attempt < 3:
                    time.sleep(3)

                continue

            if result.get("ok") is False:

                error = result.get("error")

                last_error = str(error)

                print(
                    f"❌ ReefAPI ERROR: "
                    f"{last_error}"
                )

                return None, last_error

            data = result.get("data")

            if not data:
                last_error = (
                    "ReefAPI returned no data"
                )

                print(
                    f"❌ {last_error}"
                )

                return None, last_error

            return data, None

        except requests.Timeout:

            last_error = "ReefAPI timeout"

            print(
                f"⏱️ {last_error}"
            )

        except Exception as e:

            last_error = str(e)

            print(
                f"❌ ReefAPI exception: {e}"
            )

        if attempt < 3:
            time.sleep(3)

    return None, last_error


# ============================================================
# STOCK PARSING
# ============================================================

def get_product_name(data):
    return (
        data.get("name")
        or
        data.get("product_name")
        or
        "Zara product"
    )


def get_selected_color(data):
    color = data.get("selected_color")

    if isinstance(color, dict):
        return color

    # запасний варіант, якщо структура трохи інша
    color = data.get("color")

    if isinstance(color, dict):
        return color

    return {}


def get_sizes(data):
    """
    Основна структура ReefAPI:
    selected_color -> sizes
    """

    color = get_selected_color(data)

    sizes = color.get("sizes")

    if isinstance(sizes, list):
        return sizes

    # запасні варіанти
    sizes = data.get("sizes")

    if isinstance(sizes, list):
        return sizes

    return []


def size_name(size):
    return str(
        size.get("name")
        or
        size.get("size")
        or
        size.get("label")
        or
        size.get("description")
        or
        "?"
    )


def is_size_in_stock(size):
    value = size.get("in_stock")

    if value is True:
        return True

    availability = str(
        size.get("availability", "")
    ).lower()

    return availability in {
        "in_stock",
        "available",
        "availability",
        "low_stock"
    }


def get_available_sizes(data):
    sizes = get_sizes(data)

    available = []

    for size in sizes:

        if is_size_in_stock(size):
            available.append(
                size_name(size)
            )

    return available


def get_product_stock(data):
    """
    Перевіряємо загальний stock.
    """

    if data.get("in_stock") is True:
        return True

    availability = str(
        data.get("availability", "")
    ).lower()

    if availability in {
        "in_stock",
        "available",
        "low_stock"
    }:
        return True

    color = get_selected_color(data)

    if color.get("in_stock") is True:
        return True

    color_availability = str(
        color.get("availability", "")
    ).lower()

    if color_availability in {
        "in_stock",
        "available",
        "low_stock"
    }:
        return True

    available_sizes = get_available_sizes(data)

    if available_sizes:
        return True

    return False


# ============================================================
# DIAGNOSTIC OUTPUT
# ============================================================

def print_diagnostics(
    item,
    product_id,
    data
):
    url = item.get("url", "")

    name = get_product_name(data)

    availability = data.get(
        "availability"
    )

    in_stock = data.get(
        "in_stock"
    )

    color = get_selected_color(data)

    color_name = color.get(
        "name"
    )

    color_availability = color.get(
        "availability"
    )

    color_stock = color.get(
        "in_stock"
    )

    sizes = get_sizes(data)

    available_sizes = (
        get_available_sizes(data)
    )

    print("")
    print("=" * 70)
    print("🧪 ZARA PRODUCT DIAGNOSTICS")
    print("=" * 70)

    print(f"🕐 Time: {now()}")
    print(f"🌍 Market: PL")
    print(f"🔢 Product ID: {product_id}")
    print(f"👗 Name: {name}")

    if color_name:
        print(
            f"🎨 Color: {color_name}"
        )

    print(
        f"📦 Product availability: "
        f"{availability}"
    )

    print(
        f"📦 Product in_stock: "
        f"{in_stock}"
    )

    if color:
        print(
            f"🎨 Color availability: "
            f"{color_availability}"
        )

        print(
            f"🎨 Color in_stock: "
            f"{color_stock}"
        )

    print(
        f"📏 Sizes returned: "
        f"{len(sizes)}"
    )

    if sizes:

        print("")
        print("📋 ALL SIZES:")

        for size in sizes:

            name_size = size_name(size)

            stock = size.get(
                "in_stock"
            )

            av = size.get(
                "availability"
            )

            sku = (
                size.get("sku")
                or
                size.get("sku_id")
                or
                size.get("id")
                or
                "-"
            )

            print(
                f"   ↳ {name_size}"
                f" | in_stock={stock}"
                f" | availability={av}"
                f" | sku={sku}"
            )

    print("")

    if available_sizes:

        print(
            "🚨 AVAILABLE SIZES: "
            + ", ".join(
                available_sizes
            )
        )

    elif get_product_stock(data):

        print(
            "🚨 PRODUCT IS IN STOCK"
        )

    else:

        print(
            "✅ PRODUCT CHECKED CORRECTLY "
            "— CURRENTLY NOT IN STOCK"
        )

    print(f"🔗 {url}")

    print("=" * 70)
    print("")


# ============================================================
# CHECK ONE PRODUCT
# ============================================================

def check_product(item):
    url = item.get("url", "").strip()

    wanted_sizes = item.get(
        "sizes",
        []
    )

    print("")
    print("━" * 70)
    print("👜 CHECKING PRODUCT")
    print(f"🔗 {url}")
    print("━" * 70)

    if not url:

        return {
            "ok": False,
            "error": "Missing URL"
        }

    product_id = extract_product_id(url)

    if not product_id:

        error = (
            "URL does not contain ?v1=. "
            "ReefAPI cannot reliably identify "
            "the Zara product."
        )

        print(
            f"❌ {error}"
        )

        return {
            "ok": False,
            "error": error
        }

    print(
        f"🔢 Product ID: {product_id}"
    )

    print(
        f"🌍 Market: {MARKET.upper()}"
    )

    data, error = reef_product_detail(
        product_id
    )

    if error:

        return {
            "ok": False,
            "error": error,
            "product_id": product_id
        }

    print(
        "✅ ReefAPI responded correctly"
    )

    print_diagnostics(
        item,
        product_id,
        data
    )

    available_sizes = (
        get_available_sizes(data)
    )

    product_in_stock = (
        get_product_stock(data)
    )

    # Якщо в config не вказані розміри,
    # достатньо будь-якої наявності.
    if not wanted_sizes:

        found = product_in_stock

        matching_sizes = (
            available_sizes
        )

    else:

        wanted_normalized = {
            str(x).strip().lower()
            for x in wanted_sizes
        }

        matching_sizes = [
            size
            for size in available_sizes
            if str(size).strip().lower()
            in wanted_normalized
        ]

        found = bool(
            matching_sizes
        )

    return {
        "ok": True,
        "found": found,
        "data": data,
        "product_id": product_id,
        "available_sizes": available_sizes,
        "matching_sizes": matching_sizes
    }


# ============================================================
# TELEGRAM FOUND MESSAGE
# ============================================================

def send_found_message(
    item,
    result
):
    data = result["data"]

    name = get_product_name(data)

    url = item.get(
        "url",
        ""
    )

    sizes = result.get(
        "matching_sizes"
    ) or result.get(
        "available_sizes"
    )

    availability = data.get(
        "availability"
    )

    lines = [
        "🚨 ZARA — DOSTĘPNE! 🚨",
        "",
        f"👜 {name}",
        "",
        "🇵🇱 Polska",
    ]

    if sizes:

        lines.append(
            "📏 Rozmiary: "
            + ", ".join(sizes)
        )

    lines.extend([
        f"📦 Status: {availability}",
        "",
        url
    ])

    return send_telegram(
        "\n".join(lines)
    )


# ============================================================
# MAIN
# ============================================================

def main():
    print("")
    print("=" * 70)
    print("⚡ ZARA STOCK CHECKER")
    print(f"📄 CONFIG: {CONFIG_FILE}")
    print(f"🌍 MARKET: {MARKET.upper()}")
    print(f"🕐 START: {now()}")
    print("=" * 70)

    if not REEF_KEY:
        print(
            "❌ REEF_KEY secret missing"
        )
        return

    config = load_config()

    if not config:
        print(
            "❌ Config unavailable"
        )
        return

    items = config.get(
        "urls",
        []
    )

    print(
        f"📦 Products to check: "
        f"{len(items)}"
    )

    if not items:
        print(
            "ℹ️ Nothing to check"
        )
        return

    checked_ok = 0
    errors = 0
    found_count = 0

    remaining_items = []

    for index, item in enumerate(
        items,
        start=1
    ):

        print("")
        print(
            f"🔎 PRODUCT "
            f"{index}/{len(items)}"
        )

        result = check_product(
            item
        )

        if not result.get("ok"):

            errors += 1

            error_text = result.get(
                "error",
                "Unknown error"
            )

            print(
                f"❌ CHECK FAILED: "
                f"{error_text}"
            )

            # Не видаляємо товар при помилці
            remaining_items.append(
                item
            )

            continue

        checked_ok += 1

        if result.get("found"):

            found_count += 1

            print("")
            print(
                "🚨🚨🚨 PRODUCT FOUND "
                "IN STOCK 🚨🚨🚨"
            )

            telegram_ok = (
                send_found_message(
                    item,
                    result
                )
            )

            # Під час тестування НЕ видаляємо.
            if (
                REMOVE_FOUND_ITEMS
                and telegram_ok
            ):
                print(
                    "🗑️ Product will be "
                    "removed from config"
                )

            else:
                remaining_items.append(
                    item
                )

                if not REMOVE_FOUND_ITEMS:
                    print(
                        "🧪 TEST MODE: "
                        "product remains "
                        "in config"
                    )

        else:

            print(
                "👀 Not available yet — "
                "keep watching"
            )

            remaining_items.append(
                item
            )

    # ========================================================
    # SAVE
    # ========================================================

    if REMOVE_FOUND_ITEMS:

        config["urls"] = (
            remaining_items
        )

        save_config(
            config
        )

    # ========================================================
    # SUMMARY
    # ========================================================

    print("")
    print("=" * 70)
    print("📊 CHECK SUMMARY")
    print("=" * 70)

    print(
        f"✅ Checked OK: {checked_ok}"
    )

    print(
        f"🚨 Found: {found_count}"
    )

    print(
        f"❌ Errors: {errors}"
    )

    print(
        f"📦 Total: {len(items)}"
    )

    print(
        f"🕐 Finished: {now()}"
    )

    if not REMOVE_FOUND_ITEMS:
        print(
            "🧪 TEST MODE ON — "
            "nothing removed from config"
        )

    print("=" * 70)
    print("")


if __name__ == "__main__":
    main()
