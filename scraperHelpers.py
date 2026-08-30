from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.common.exceptions import TimeoutException


def check_stock_zara(driver, sizes_to_check):
    """
    Перевіряє всі задані розміри Zara БЕЗ натискання Add to cart.
    Повертає список усіх доступних розмірів.
    """

    try:
        wait = WebDriverWait(driver, 8)

        # Cookies
        try:
            cookie_buttons = driver.find_elements(
                By.ID,
                "onetrust-accept-btn-handler"
            )

            if cookie_buttons and cookie_buttons[0].is_displayed():
                driver.execute_script(
                    "arguments[0].click();",
                    cookie_buttons[0]
                )
        except Exception:
            pass

        # Чекаємо, поки Zara завантажить елементи розмірів у DOM.
        # Вони можуть бути навіть прихованими на сторінці.
        try:
            wait.until(
                lambda d: len(
                    d.find_elements(
                        By.CSS_SELECTOR,
                        "[data-qa-action='size-in-stock'], "
                        "[data-qa-action='size-low-on-stock'], "
                        "[data-qa-action='size-out-of-stock'], "
                        ".size-selector-sizes-size"
                    )
                ) > 0
            )
        except TimeoutException:
            print("❌ Zara size data not found in DOM.")
            return []

        available_sizes = []

        print("🔎 Looking for Zara sizes directly in DOM...")

        # Беремо всі елементи, які Zara позначає як розміри
        size_items = driver.find_elements(
            By.CSS_SELECTOR,
            ".size-selector-sizes-size"
        )

        print(f"📦 Size elements found: {len(size_items)}")

        for wanted_size in sizes_to_check:
            found_requested_size = False

            for item in size_items:
                try:
                    # Пробуємо кілька способів отримати назву розміру
                    label = ""

                    label_selectors = [
                        "div[data-qa-qualifier='size-selector-sizes-size-label']",
                        "[data-qa-qualifier='size-selector-sizes-size-label']",
                        ".size-selector-sizes-size__label",
                        "span"
                    ]

                    for selector in label_selectors:
                        try:
                            elements = item.find_elements(
                                By.CSS_SELECTOR,
                                selector
                            )

                            for element in elements:
                                text = element.text.strip()

                                if text:
                                    label = text
                                    break

                            if label:
                                break

                        except Exception:
                            continue

                    # Якщо окремий label не знайшли
                    if not label:
                        label = item.text.strip().split("\n")[0]

                    if label != wanted_size:
                        continue

                    found_requested_size = True

                    # Шукаємо кнопку/елемент стану цього розміру
                    buttons = item.find_elements(
                        By.CSS_SELECTOR,
                        "[data-qa-action]"
                    )

                    action = ""

                    for button in buttons:
                        current_action = (
                            button.get_attribute("data-qa-action")
                            or ""
                        )

                        if current_action:
                            action = current_action
                            break

                    print(
                        f"📏 {wanted_size} → action: "
                        f"{action if action else 'unknown'}"
                    )

                    if action in [
                        "size-in-stock",
                        "size-low-on-stock"
                    ]:
                        print(
                            f"✅ {wanted_size} is in stock."
                        )

                        available_sizes.append(
                            wanted_size
                        )

                    elif action == "size-out-of-stock":
                        print(
                            f"❌ {wanted_size} is out of stock."
                        )

                    else:
                        # Додаткова перевірка атрибутів
                        item_class = (
                            item.get_attribute("class")
                            or ""
                        ).lower()

                        aria_disabled = (
                            item.get_attribute("aria-disabled")
                            or ""
                        ).lower()

                        disabled_words = [
                            "disabled",
                            "unavailable",
                            "out-of-stock",
                            "sold-out"
                        ]

                        if (
                            aria_disabled == "true"
                            or any(
                                word in item_class
                                for word in disabled_words
                            )
                        ):
                            print(
                                f"❌ {wanted_size} appears unavailable."
                            )
                        else:
                            # Не вважаємо товар доступним,
                            # якщо Zara не дала чіткий сигнал.
                            print(
                                f"⚠️ {wanted_size}: "
                                f"availability unclear."
                            )

                    break

                except Exception as e:
                    print(
                        f"⚠️ Error checking "
                        f"{wanted_size}: {e}"
                    )
                    continue

            if not found_requested_size:
                print(
                    f"⚠️ {wanted_size} not found "
                    f"in Zara size list."
                )

        print(
            "🟢 AVAILABLE REQUESTED SIZES: "
            + (
                ", ".join(available_sizes)
                if available_sizes
                else "NONE"
            )
        )

        return available_sizes

    except Exception as e:
        print(f"❌ Zara checker error: {e}")
        return []


def check_stock_bershka(driver, sizes_to_check):
    return []


def check_stock_stradivarius(driver, sizes_to_check):
    return []


def rossmannStockCheck(driver):
    return False


def watsonsChecker(driver):
    return False
