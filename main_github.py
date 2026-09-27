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
        # записуємо зміни назад у репозиторій.
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

            # Якщо файл реально змінився
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
        if x.get("url") != item.get("url")
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
    """
    Zara Share links contain:
    ?v1=545893127

    ReefAPI uses this as the product/color ID.
    """
    try:
        query = parse_qs(urlparse(url).query)

        values = query.get("v1", [])

        if values:
            return str(values[0])

    except Exception:
        pass

    return None


# ============================================================
# REEF API
# ============================================================

def reef_product_detail(url):
    if not REEF_KEY:
        raise RuntimeError("REEF_KEY is missing")

    response = requests.post(
        REEF_API_URL,
        headers={
            "x-api-key": REEF_KEY,
            "content-type": "application/json"
        },
        json={
            "url": url,
            "market": "pl",
            "include_composition": False,
            "find_market": False
        },
        timeout=30
    )

    print(f"🌊 ReefAPI HTTP: {response.status_code}")

    response.raise_for_status()

    payload = response.json()

    if not payload.get("ok"):
        print(
            "❌ ReefAPI returned error: "
            f"{payload.get('error')}"
        )
        return None

    return payload.get("data")


# ============================================================
# ZARA DATA PARSING
# ============================================================

def find_matching_color(data, wanted_product_id):
    if not isinstance(data, dict):
        return None

    colors = data.get("colors")

    if isinstance(colors, list):

        # Спочатку шукаємо точний product/color ID з ?v1=
        for color in colors:

            if not isinstance(color, dict):
                continue

            color_product_id = color.get("product_id")

            if (
                wanted_product_id
                and color_product_id is not None
                and str(color_product_id) == str(wanted_product_id)
            ):
                return color

        # Якщо ReefAPI повернув тільки один колір —
        # можемо використати його.
        if len(colors) == 1 and isinstance(colors[0], dict):
            return colors[0]

    # Деякі відповіді ReefAPI можуть містити sizes
    # безпосередньо в основному об'єкті.
    if isinstance(data.get("sizes"), list):
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

    # Додатковий пошук усередині відповіді API.
    def walk(obj):

        if isinstance(obj, dict):

            obj_product_id = obj.get("product_id")

            if (
                product_id
                and obj_product_id is not None
                and str(obj_product_id) == str(product_id)
                and isinstance(obj.get("sizes"), list)
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

    return result if result is not None else []


# ============================================================
# STOCK CHECK
# ============================================================

def row_is_available(row):
    """
    ReefAPI normally provides in_stock=True/False.

    availability is kept as a fallback.
    """
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


def check_zara(url, wanted_sizes):
    print(f"🌐 {url}")

    product_id = get_product_id_from_url(url)

    print(
        "🆔 Zara product/color ID: "
        f"{product_id if product_id else 'not found'}"
    )

    try:
        data = reef_product_detail(url)

    except requests.HTTPError as e:

        response = getattr(e, "response", None)

        if response is not None:

            print(
                "❌ ReefAPI HTTP error: "
                f"{response.status_code}"
            )

            try:
                print(response.text[:1000])
            except Exception:
                pass

        return []

    except Exception as e:
        print(f"❌ ReefAPI request error: {e}")
        return []

    if not data:
        print("❌ ReefAPI returned no product data")
        return []

    size_rows = get_size_rows(
        data,
        product_id
    )

    print(
        f"📦 Size rows received: "
        f"{len(size_rows)}"
    )

    wanted_normalized = [
        normalize_size(size)
        for size in wanted_sizes
        if normalize_size(size)
    ]

    # ========================================================
    # ТОВАР БЕЗ РОЗМІРУ
    # Наприклад: сумка, аксесуар тощо.
    #
    # У config:
    # "sizes": []
    # ========================================================

    if not wanted_normalized:

        print(
            "👜 Product has no requested sizes — "
            "checking general availability"
        )

        if not size_rows:
            print("❌ No stock rows received")
            return []

        for row in size_rows:

            if not isinstance(row, dict):
                continue

            name = normalize_size(
                row.get("name")
            )

            availability = normalize_size(
                row.get("availability")
            )

            in_stock = row.get("in_stock")

            print(
                "👜 ITEM WITHOUT SIZE"
                f" | name={name or '-'}"
                f" | availability={availability or '-'}"
                f" | in_stock={in_stock}"
            )

            if row_is_available(row):

                print(
                    "✅ PRODUCT WITHOUT SIZE AVAILABLE"
                )

                return ["ONE SIZE"]

        print(
            "❌ PRODUCT WITHOUT SIZE UNAVAILABLE"
        )

        return []

    # ========================================================
    # ТОВАРИ З РОЗМІРАМИ
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

        in_stock = row.get("in_stock")

        found[name] = True

        print(
            f"📏 {name}"
            f" | availability={availability}"
            f" | in_stock={in_stock}"
        )

        if row_is_available(row):

            available_sizes.append(name)

            print(
                f"✅ {name} AVAILABLE"
            )

        else:

            print(
                f"❌ {name} unavailable"
            )

    # Якщо потрібного розміру немає у відповіді API.
    for size in wanted_normalized:

        if size not in found:

            print(
                f"⚠️ Requested size {size} "
                "not present in API response"
            )

    # Зберігаємо порядок із config
    # і прибираємо дублікати.
    ordered_available = []

    for size in wanted_normalized:

        if (
            size in available_sizes
            and size not in ordered_available
        ):
            ordered_available.append(size)

    print(
        "🟢 AVAILABLE REQUESTED SIZES: "
        + (
            ", ".join(ordered_available)
            if ordered_available
            else "NONE"
        )
    )

    return ordered_available


# ============================================================
# ITEM CHECK
# ============================================================

def check_item(item, config):
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
            f"⚠️ Unsupported store: "
            f"{store}"
        )

        return False

    if not url:

        print("⚠️ Missing URL")
        return False

    print(
        "\n" + "=" * 55
    )

    print(
        "📋 Checking ZARA "
        f"| sizes: {', '.join(sizes)}"
    )

    available = check_zara(
        url,
        sizes
    )

    if not available:

        print(
            "❌ No requested stock: "
            f"{', '.join(sizes)}"
        )

        return False

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
        f"📏 Розміри: <b>{sizes_text}</b>\n"
        "🏪 Магазин: <b>ZARA</b>\n"
        f"🔗 <a href='{url}'>Відкрити товар</a>\n"
        f"⏰ Час: <b>{warsaw_time}</b>"
    )

    # Спочатку надсилаємо Telegram.
    telegram_ok = send_telegram(
        message
    )

    # Видаляємо товар із config тільки після
    # успішного повідомлення Telegram.
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
            "Telegram notification failed"
        )

    return True


# ============================================================
# MAIN
# ============================================================

def main():
    start = time.time()

    print(
        "🌊 REEFAPI ZARA STOCK CHECKER"
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

    checked = 0
    found = 0

    for index, item in enumerate(
        items,
        start=1
    ):

        print(
            f"\n📦 ITEM "
            f"{index}/{len(items)}"
        )

        checked += 1

        try:

            if check_item(
                item,
                config
            ):
                found += 1

        except Exception as e:

            print(
                "❌ Unexpected item error: "
                f"{e}"
            )

    elapsed = time.time() - start

    print(
        "\n" + "=" * 55
    )

    print(
        "🌊 SUMMARY"
    )

    print(
        f"✅ Checked: {checked}"
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
