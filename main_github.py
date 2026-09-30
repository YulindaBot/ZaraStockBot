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
REEF_SEARCH_URL = "https://api.reefapi.com/zara/v1/search"

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


def normalize_reference(value):
    if value is None:
        return ""

    return re.sub(
        r"[^0-9]",
        "",
        str(value)
    )


def get_product_id_from_url(url):
    """
    Якщо URL вже містить:
    ?v1=545893127

    повертаємо цей product_id.
    """
    try:
        query = parse_qs(
            urlparse(url).query
        )

        values = query.get("v1", [])

        if values:
            return str(values[0])

    except Exception:
        pass

    return None


def get_zara_reference_from_url(url):
    """
    Приклади:

    p16102810.html -> 1610/281
    p16821710.html -> 1682/171
    p04575567.html -> 4575/567

    Остання цифра короткого Zara-коду
    не входить у display_reference.
    """

    try:
        path = urlparse(url).path

        match = re.search(
            r"-p(\d+)\.html",
            path,
            re.IGNORECASE
        )

        if not match:
            return None

        code = match.group(1)

        # Zara іноді має початковий 0
        if len(code) == 8 and code.startswith("0"):
            code = code[1:]

        # Наприклад:
        # 16102810 -> 1610/281
        if len(code) >= 7:
            article = code[:4]
            model = code[4:7]

            return f"{article}/{model}"

        return None

    except Exception as e:
        print(f"⚠️ Reference extraction error: {e}")
        return None


# ============================================================
# REEF API SEARCH
# ============================================================

def reef_search_product_id(url):
    """
    Якщо короткий URL Zara не містить ?v1=,
    шукаємо товар у Zara Polska за reference,
    наприклад 1610/281.

    Search повертає справжній product_id.
    """

    reference = get_zara_reference_from_url(url)

    if not reference:
        print(
            "❌ Could not extract Zara reference "
            "from URL"
        )
        return None

    print(
        f"🔎 Searching Zara Polska: {reference}"
    )

    try:
        response = requests.post(
            REEF_SEARCH_URL,
            headers={
                "x-api-key": REEF_KEY,
                "content-type": "application/json"
            },
            json={
                "query": reference,
                "market": "pl",
                "max_results": 40
            },
            timeout=30
        )

        print(
            "🌊 ReefAPI SEARCH HTTP: "
            f"{response.status_code}"
        )

        response.raise_for_status()

        payload = response.json()

    except requests.HTTPError as e:
        response = getattr(
            e,
            "response",
            None
        )

        print("❌ ReefAPI search HTTP error")

        if response is not None:
            try:
                print(response.text[:1500])
            except Exception:
                pass

        return None

    except Exception as e:
        print(
            f"❌ ReefAPI search request error: {e}"
        )
        return None

    if not payload.get("ok"):
        print(
            "❌ ReefAPI search returned error: "
            f"{payload.get('error')}"
        )
        return None

    data = payload.get("data") or {}

    results = data.get("results") or []

    print(
        f"🔎 Search rows received: {len(results)}"
    )

    wanted = normalize_reference(reference)

    # --------------------------------------------------------
    # 1. Шукаємо точний display_reference
    # --------------------------------------------------------

    for row in results:

        if not isinstance(row, dict):
            continue

        display_reference = normalize_reference(
            row.get("display_reference")
        )

        if display_reference == wanted:

            product_id = row.get("product_id")

            if product_id:

                print(
                    "✅ Exact Zara product found"
                )

                print(
                    f"🆔 product_id: {product_id}"
                )

                print(
                    "🏷️ display_reference: "
                    f"{row.get('display_reference')}"
                )

                return str(product_id)

    # --------------------------------------------------------
    # 2. Додаткова перевірка reference
    # --------------------------------------------------------

    for row in results:

        if not isinstance(row, dict):
            continue

        full_reference = normalize_reference(
            row.get("reference")
        )

        if wanted and wanted in full_reference:

            product_id = row.get("product_id")

            if product_id:

                print(
                    "✅ Zara product matched "
                    "by full reference"
                )

                print(
                    f"🆔 product_id: {product_id}"
                )

                return str(product_id)

    print(
        "❌ Exact Zara product not found "
        "in Polish search results"
    )

    return None


# ============================================================
# REEF API PRODUCT DETAIL
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
        f"🌊 ReefAPI DETAIL HTTP: "
        f"{response.status_code}"
    )

    response.raise_for_status()

    payload = response.json()

    if not payload.get("ok"):
        print(
            "❌ ReefAPI detail returned error: "
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

    # --------------------------------------------------------
    # ReefAPI current response:
    # selected_color
    # --------------------------------------------------------

    selected_color = data.get(
        "selected_color"
    )

    if isinstance(selected_color, dict):

        selected_product_id = (
            selected_color.get("product_id")
        )

        if (
            not wanted_product_id
            or selected_product_id is None
            or str(selected_product_id)
            == str(wanted_product_id)
        ):
            return selected_color

    # --------------------------------------------------------
    # Інший можливий формат:
    # colors[]
    # --------------------------------------------------------

    colors = data.get("colors")

    if isinstance(colors, list):

        for color in colors:

            if not isinstance(color, dict):
                continue

            color_product_id = (
                color.get("product_id")
            )

            if (
                wanted_product_id
                and color_product_id is not None
                and str(color_product_id)
                == str(wanted_product_id)
            ):
                return color

        if (
            len(colors) == 1
            and isinstance(colors[0], dict)
        ):
            return colors[0]

    # --------------------------------------------------------
    # sizes можуть бути прямо в data
    # --------------------------------------------------------

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

    # --------------------------------------------------------
    # Рекурсивний fallback
    # --------------------------------------------------------

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
                    or not product_id
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

    return (
        result
        if result is not None
        else []
    )


# ============================================================
# STOCK CHECK
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

    return (
        availability
        in available_values
    )


def check_zara(url, wanted_sizes):
    print(f"🌐 {url}")

    # --------------------------------------------------------
    # Якщо є ?v1= — беремо product_id прямо з URL.
    # Інакше автоматично шукаємо його через ReefAPI Search.
    # --------------------------------------------------------

    product_id = get_product_id_from_url(
        url
    )

    if product_id:

        print(
            "🆔 Product ID from URL: "
            f"{product_id}"
        )

    else:

        print(
            "🆔 No v1 in URL"
        )

        product_id = (
            reef_search_product_id(url)
        )

        if not product_id:

            print(
                "❌ Could not resolve "
                "Zara product_id"
            )

            return []

    # --------------------------------------------------------
    # Product detail
    # --------------------------------------------------------

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

        if response is not None:

            print(
                "❌ ReefAPI DETAIL HTTP error: "
                f"{response.status_code}"
            )

            try:
                print(
                    response.text[:1500]
                )
            except Exception:
                pass

        return []

    except Exception as e:

        print(
            "❌ ReefAPI detail request error: "
            f"{e}"
        )

        return []

    if not data:

        print(
            "❌ ReefAPI returned "
            "no product data"
        )

        return []

    size_rows = get_size_rows(
        data,
        product_id
    )

    print(
        "📦 Size rows received: "
        f"{len(size_rows)}"
    )

    wanted_normalized = [
        normalize_size(size)
        for size in wanted_sizes
        if normalize_size(size)
    ]

    # ========================================================
    # СУМКА / ТОВАР БЕЗ РОЗМІРУ
    # ========================================================

    if not wanted_normalized:

        print(
            "👜 Product has no requested sizes — "
            "checking general availability"
        )

        if not size_rows:

            print(
                "❌ No stock rows received"
            )

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

            in_stock = row.get(
                "in_stock"
            )

            print(
                "👜 ITEM WITHOUT SIZE"
                f" | name={name or '-'}"
                f" | availability={availability or '-'}"
                f" | in_stock={in_stock}"
            )

            if row_is_available(row):

                print(
                    "✅ PRODUCT WITHOUT SIZE "
                    "AVAILABLE"
                )

                return ["ONE SIZE"]

        print(
            "❌ PRODUCT WITHOUT SIZE "
            "UNAVAILABLE"
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
                f"⚠️ Requested size {size} "
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
        "🟢 AVAILABLE REQUESTED SIZES: "
        + (
            ", ".join(
                ordered_available
            )
            if ordered_available
            else "NONE"
        )
    )

    return ordered_available


# ============================================================
# ITEM CHECK
# ============================================================

def check_item(item, config):
    if not isinstance(item, dict):

        print(
            "❌ Config item must be an object"
        )

        return False

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

        return False

    if not url:

        print(
            "⚠️ Missing URL"
        )

        return False

    print(
        "\n" + "=" * 55
    )

    print(
        "📋 Checking ZARA POLSKA "
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
        f"📏 Розмір: <b>{sizes_text}</b>\n"
        "🏪 Магазин: <b>ZARA POLSKA</b>\n"
        f"🔗 <a href='{url}'>Відкрити товар</a>\n"
        f"⏰ Час: <b>{warsaw_time}</b>"
    )

    telegram_ok = send_telegram(
        message
    )

    # Видаляємо товар тільки після
    # успішного Telegram повідомлення
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
