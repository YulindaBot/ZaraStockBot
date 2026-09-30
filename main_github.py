import json
import os
import time
import subprocess
import re
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

            diff = subprocess.run(
                ["git", "diff", "--staged", "--quiet"],
                capture_output=True
            )

            if diff.returncode != 0:

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

                print(f"✅ {CONFIG_FILE} updated in GitHub")

        return True

    except Exception as e:
        print(f"⚠️ Config save/push error: {e}")
        return False


def remove_item_from_config(config, item):
    before = len(config.get("urls", []))

    config["urls"] = [
        x
        for x in config.get("urls", [])
        if (
            isinstance(x, dict)
            and x.get("url") != item.get("url")
        )
    ]

    if len(config["urls"]) < before:
        return save_config(config)

    return False


# ============================================================
# TELEGRAM
# ============================================================

def send_telegram(message):
    if not BOT_API or not CHAT_ID:
        print("⚠️ Telegram credentials missing")
        return False

    try:
        response = requests.post(
            f"https://api.telegram.org/bot{BOT_API}/sendMessage",
            data={
                "chat_id": CHAT_ID,
                "text": message,
                "parse_mode": "HTML",
                "disable_web_page_preview": False
            },
            timeout=10
        )

        response.raise_for_status()

        print("✅ Telegram message sent")
        return True

    except Exception as e:
        print(f"❌ Telegram error: {e}")
        return False


def send_error_telegram(url, reason):
    warsaw_time = datetime.now(
        ZoneInfo("Europe/Warsaw")
    ).strftime("%H:%M:%S")

    message = (
        "⚠️ <b>ПОМИЛКА ПЕРЕВІРКИ ZARA</b>\n\n"
        "Товар <b>НЕ БУВ перевірений</b>.\n"
        f"Причина: <b>{reason}</b>\n\n"
        f"🔗 <a href='{url}'>Відкрити товар</a>\n"
        f"⏰ Час: <b>{warsaw_time}</b>"
    )

    send_telegram(message)


# ============================================================
# HELPERS
# ============================================================

def normalize_size(value):
    if value is None:
        return ""

    return (
        str(value)
        .replace("\n", " ")
        .replace("\t", " ")
        .strip()
        .upper()
    )


def get_product_id_from_url(url):
    try:
        query = parse_qs(
            urlparse(url).query
        )

        values = query.get("v1", [])

        if values:
            return str(values[0])

    except Exception as e:
        print(
            f"⚠️ Could not read v1 from URL: {e}"
        )

    return None


# ============================================================
# REEF API
# ============================================================

def reef_product_detail(product_id):

    if not REEF_KEY:
        raise RuntimeError(
            "REEF_KEY is missing"
        )

    response = requests.post(
        REEF_API_URL,
        headers={
            "x-api-key": REEF_KEY,
            "content-type": "application/json"
        },
        json={
            "product_id": str(product_id),
            "market": "pl",
            "include_composition": False,
            "find_market": False
        },
        timeout=30
    )

    print(
        "🌊 ReefAPI DETAIL HTTP: "
        f"{response.status_code}"
    )

    response.raise_for_status()

    payload = response.json()

    if not payload.get("ok"):
        raise RuntimeError(
            f"ReefAPI error: {payload.get('error')}"
        )

    return payload.get("data")


# ============================================================
# ZARA DATA
# ============================================================

def find_matching_color(data, wanted_product_id):

    if not isinstance(data, dict):
        return None

    selected_color = data.get(
        "selected_color"
    )

    if isinstance(selected_color, dict):

        selected_product_id = (
            selected_color.get("product_id")
        )

        if (
            selected_product_id is None
            or str(selected_product_id)
            == str(wanted_product_id)
        ):
            return selected_color

    colors = data.get("colors")

    if isinstance(colors, list):

        for color in colors:

            if not isinstance(color, dict):
                continue

            color_product_id = (
                color.get("product_id")
            )

            if (
                color_product_id is not None
                and str(color_product_id)
                == str(wanted_product_id)
            ):
                return color

        if (
            len(colors) == 1
            and isinstance(colors[0], dict)
        ):
            return colors[0]

    if isinstance(
        data.get("sizes"),
        list
    ):
        return data

    return None


def get_size_rows(data, product_id):

    color = find_matching_color(
        data,
        product_id
    )

    if color:

        sizes = color.get("sizes")

        if isinstance(sizes, list):
            return sizes

    def walk(obj):

        if isinstance(obj, dict):

            if isinstance(
                obj.get("sizes"),
                list
            ):

                obj_product_id = (
                    obj.get("product_id")
                )

                if (
                    obj_product_id is None
                    or str(obj_product_id)
                    == str(product_id)
                ):
                    return obj["sizes"]

            for value in obj.values():

                result = walk(value)

                if result is not None:
                    return result

        elif isinstance(obj, list):

            for value in obj:

                result = walk(value)

                if result is not None:
                    return result

        return None

    result = walk(data)

    if result is None:
        return []

    return result


# ============================================================
# AVAILABILITY
# ============================================================

def row_is_available(row):

    if not isinstance(row, dict):
        return False

    in_stock = row.get("in_stock")

    if in_stock is True:
        return True

    availability = normalize_size(
        row.get("availability")
    )

    available_values = {
        "AVAILABLE",
        "IN_STOCK",
        "IN STOCK",
        "LOW_ON_STOCK",
        "LOW ON STOCK",
        "LOW_STOCK"
    }

    return availability in available_values


# ============================================================
# CHECK ZARA
# ============================================================

def check_zara(url, wanted_sizes):

    print(f"🌐 {url}")

    product_id = get_product_id_from_url(
        url
    )

    if not product_id:

        print(
            "❌ ERROR: URL has no v1"
        )

        send_error_telegram(
            url,
            "в URL немає v1 / product_id"
        )

        return {
            "checked_ok": False,
            "available": []
        }

    print(
        "✅ v1 FOUND IN URL"
    )

    print(
        f"🆔 Product ID: {product_id}"
    )

    print(
        "🚀 Search skipped — "
        "checking this exact product"
    )

    try:

        data = reef_product_detail(
            product_id
        )

    except requests.HTTPError as e:

        response = getattr(
            e,
            "response",
            None
        )

        status = (
            response.status_code
            if response is not None
            else "unknown"
        )

        print(
            f"❌ ReefAPI HTTP error: {status}"
        )

        send_error_telegram(
            url,
            f"ReefAPI HTTP error {status}"
        )

        return {
            "checked_ok": False,
            "available": []
        }

    except Exception as e:

        print(
            f"❌ ReefAPI detail error: {e}"
        )

        send_error_telegram(
            url,
            f"ReefAPI error: {e}"
        )

        return {
            "checked_ok": False,
            "available": []
        }

    if not data:

        print(
            "❌ No product data received"
        )

        send_error_telegram(
            url,
            "API не повернув дані товару"
        )

        return {
            "checked_ok": False,
            "available": []
        }

    print(
        "✅ Exact product data received"
    )

    size_rows = get_size_rows(
        data,
        product_id
    )

    print(
        f"📦 Stock rows received: "
        f"{len(size_rows)}"
    )

    if not size_rows:

        print(
            "❌ No stock rows received"
        )

        send_error_telegram(
            url,
            "API не повернув stock rows"
        )

        return {
            "checked_ok": False,
            "available": []
        }

    wanted_normalized = [
        normalize_size(size)
        for size in wanted_sizes
        if normalize_size(size)
    ]

    # ========================================================
    # BAG / ONE SIZE
    # ========================================================

    if not wanted_normalized:

        print(
            "👜 PRODUCT WITHOUT SIZE"
        )

        for row in size_rows:

            if not isinstance(row, dict):
                continue

            name = normalize_size(
                row.get("name")
            )

            availability = normalize_size(
                row.get("availability")
            )

            in_stock = row.get(
                "in_stock"
            )

            print(
                "👜 STOCK"
                f" | name={name or '-'}"
                f" | availability={availability or '-'}"
                f" | in_stock={in_stock}"
            )

            if row_is_available(row):

                print(
                    "🎉 BAG IS AVAILABLE!"
                )

                return {
                    "checked_ok": True,
                    "available": ["ONE SIZE"]
                }

        print(
            "❌ BAG CURRENTLY UNAVAILABLE"
        )

        return {
            "checked_ok": True,
            "available": []
        }

    # ========================================================
    # CLOTHES / SIZES
    # ========================================================

    found = {}
    available_sizes = []

    for row in size_rows:

        if not isinstance(row, dict):
            continue

        name = normalize_size(
            row.get("name")
        )

        if not name:
            continue

        if name not in wanted_normalized:
            continue

        availability = normalize_size(
            row.get("availability")
        )

        in_stock = row.get(
            "in_stock"
        )

        found[name] = True

        print(
            f"📏 {name}"
            f" | availability={availability}"
            f" | in_stock={in_stock}"
        )

        if row_is_available(row):

            available_sizes.append(
                name
            )

            print(
                f"✅ {name} AVAILABLE"
            )

        else:

            print(
                f"❌ {name} unavailable"
            )

    for size in wanted_normalized:

        if size not in found:

            print(
                f"⚠️ Size {size} "
                "not present in API response"
            )

    ordered_available = []

    for size in wanted_normalized:

        if (
            size in available_sizes
            and size not in ordered_available
        ):

            ordered_available.append(
                size
            )

    print(
        "🟢 AVAILABLE: "
        + (
            ", ".join(
                ordered_available
            )
            if ordered_available
            else "NONE"
        )
    )

    return {
        "checked_ok": True,
        "available": ordered_available
    }


# ============================================================
# CHECK ITEM
# ============================================================

def check_item(item, config):

    if not isinstance(item, dict):

        print(
            "❌ Config item must be an object"
        )

        return {
            "checked_ok": False,
            "found": False
        }

    store = item.get(
        "store",
        ""
    ).lower()

    url = item.get("url")

    sizes = item.get(
        "sizes",
        []
    )

    person = item.get(
        "person",
        "Yulia"
    )

    if store != "zara":

        print(
            f"⚠️ Unsupported store: {store}"
        )

        return {
            "checked_ok": False,
            "found": False
        }

    if not url:

        print(
            "⚠️ Missing URL"
        )

        return {
            "checked_ok": False,
            "found": False
        }

    print(
        "\n" + "=" * 55
    )

    print(
        "📋 Checking ZARA POLSKA"
    )

    print(
        f"📏 Requested sizes: "
        f"{', '.join(sizes) if sizes else 'ONE SIZE'}"
    )

    result = check_zara(
        url,
        sizes
    )

    if not result["checked_ok"]:

        print(
            "⚠️ ITEM CHECK FAILED"
        )

        return {
            "checked_ok": False,
            "found": False
        }

    available = result["available"]

    if not available:

        print(
            "❌ No requested stock"
        )

        return {
            "checked_ok": True,
            "found": False
        }

    sizes_text = ", ".join(
        available
    )

    print(
        f"🎉 FOUND: {sizes_text}"
    )

    warsaw_time = datetime.now(
        ZoneInfo("Europe/Warsaw")
    ).strftime("%H:%M:%S")

    message = (
        "🛍️ <b>ТОВАР З'ЯВИВСЯ!</b>\n\n"
        f"👤 <b>{person}</b>\n"
        f"📏 Розмір: <b>{sizes_text}</b>\n"
        "🏪 Магазин: <b>ZARA POLSKA</b>\n"
        f"🔗 <a href='{url}'>Відкрити товар</a>\n"
        f"⏰ Час: <b>{warsaw_time}</b>"
    )

    telegram_ok = send_telegram(
        message
    )

    if telegram_ok:

        removed = remove_item_from_config(
            config,
            item
        )

        if removed:

            print(
                "🗑️ Product removed "
                "from tracking config"
            )

        else:

            print(
                "⚠️ Product found, but "
                "config removal failed"
            )

    else:

        print(
            "⚠️ Product NOT removed because "
            "Telegram failed"
        )

    return {
        "checked_ok": True,
        "found": True
    }


# ============================================================
# MAIN
# ============================================================

def main():

    start = time.time()

    print(
        "🌊 REEFAPI ZARA POLAND STOCK CHECKER"
    )

    print(
        f"📄 Config: {CONFIG_FILE}"
    )

    if not REEF_KEY:

        print(
            "❌ REEF_KEY secret is missing"
        )

        return

    config = load_config()

    if not config:
        return

    items = list(
        config.get(
            "urls",
            []
        )
    )

    if not items:

        print(
            "🎯 No items in config"
        )

        return

    checked_ok = 0
    errors = 0
    found = 0

    for index, item in enumerate(
        items,
        start=1
    ):

        print(
            f"\n📦 ITEM "
            f"{index}/{len(items)}"
        )

        try:

            result = check_item(
                item,
                config
            )

            if result["checked_ok"]:
                checked_ok += 1
            else:
                errors += 1

            if result["found"]:
                found += 1

        except Exception as e:

            errors += 1

            print(
                "❌ Unexpected item error: "
                f"{e}"
            )

            url = ""

            if isinstance(item, dict):
                url = item.get("url", "")

            if url:
                send_error_telegram(
                    url,
                    f"Unexpected error: {e}"
                )

    elapsed = time.time() - start

    print(
        "\n" + "=" * 55
    )

    print(
        "🌊 SUMMARY"
    )

    print(
        f"✅ Successfully checked: {checked_ok}"
    )

    print(
        f"⚠️ Errors: {errors}"
    )

    print(
        f"🛍️ Found: {found}"
    )

    print(
        f"⏱️ Total time: "
        f"{elapsed:.1f} sec"
    )


if __name__ == "__main__":
    main()
