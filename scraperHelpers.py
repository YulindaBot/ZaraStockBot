from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import TimeoutException
import os


def check_stock_zara(driver, sizes_to_check):
    try:
        wait = WebDriverWait(driver, 4)

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

        try:
            add_to_cart_button = wait.until(
                EC.presence_of_element_located(
                    (
                        By.CSS_SELECTOR,
                        "button[data-qa-action='add-to-cart']"
                    )
                )
            )
        except TimeoutException:
            print("Add to cart button not found.")
            return []

        try:
            overlays = driver.find_elements(
                By.CLASS_NAME,
                "zds-backdrop"
            )
            if overlays:
                driver.execute_script(
                    "arguments[0].remove();",
                    overlays[0]
                )
        except Exception:
            pass

        try:
            driver.execute_script(
                "arguments[0].click();",
                add_to_cart_button
            )
        except Exception:
            return []

        try:
            wait.until(
                EC.presence_of_element_located(
                    (
                        By.CLASS_NAME,
                        "size-selector-sizes-size"
                    )
                )
            )
        except TimeoutException:
            print("Size selector not found.")
            return []

        size_elements = driver.find_elements(
            By.CLASS_NAME,
            "size-selector-sizes-size"
        )

        available_sizes = []
        requested_sizes_found = []

        for li in size_elements:
            try:
                size_label = li.find_element(
                    By.CSS_SELECTOR,
                    "div[data-qa-qualifier='size-selector-sizes-size-label']"
                ).text.strip()

                if size_label not in sizes_to_check:
                    continue

                requested_sizes_found.append(size_label)

                button = li.find_element(
                    By.CLASS_NAME,
                    "size-selector-sizes-size__button"
                )

                data_qa = (
                    button.get_attribute("data-qa-action") or ""
                )

                if data_qa in [
                    "size-in-stock",
                    "size-low-on-stock"
                ]:
                    print(f"✅ {size_label} is in stock.")
                    available_sizes.append(size_label)
                else:
                    print(f"❌ {size_label} is out of stock.")

            except Exception as e:
                print(f"Error processing size: {e}")
                continue

        missing_sizes = [
            size for size in sizes_to_check
            if size not in requested_sizes_found
        ]

        for size in missing_sizes:
            print(f"⚠️ {size} not found in selector.")

        return available_sizes

    except Exception as e:
        print(f"Zara check error: {e}")
        return []


def check_stock_bershka(driver, sizes_to_check):
    try:
        wait = WebDriverWait(driver, 5)

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

        try:
            wait.until(
                EC.presence_of_element_located(
                    (
                        By.CSS_SELECTOR,
                        "ul[data-qa-anchor='productDetailSize']"
                    )
                )
            )
        except TimeoutException:
            return []

        size_buttons = driver.find_elements(
            By.CSS_SELECTOR,
            "button[data-qa-anchor='sizeListItem']"
        )

        available_sizes = []

        for button in size_buttons:
            try:
                size_label = button.find_element(
                    By.CSS_SELECTOR,
                    "span.text__label"
                ).text.strip()

                if size_label not in sizes_to_check:
                    continue

                class_attr = (
                    button.get_attribute("class") or ""
                )

                if "is-disabled" in class_attr:
                    print(f"❌ {size_label} is out of stock.")
                else:
                    print(f"✅ {size_label} is in stock.")
                    available_sizes.append(size_label)

            except Exception:
                continue

        return available_sizes

    except Exception as e:
        print(f"Bershka check error: {e}")
        return []


def check_stock_stradivarius(driver, sizes_to_check):
    try:
        wait = WebDriverWait(driver, 5)

        add_to_cart_selectors = [
            "button[data-qa-action='add-to-cart']",
            ".product-detail-actions__add-to-cart",
            ".add-to-cart-button",
            ".product-actions__add-to-cart",
            "button[class*='add-to-cart']"
        ]

        add_to_cart_button = None

        for selector in add_to_cart_selectors:
            elements = driver.find_elements(
                By.CSS_SELECTOR,
                selector
            )
            if elements:
                add_to_cart_button = elements[0]
                break

        if not add_to_cart_button:
            return []

        driver.execute_script(
            "arguments[0].click();",
            add_to_cart_button
        )

        try:
            wait.until(
                lambda d: len(
                    d.find_elements(
                        By.CSS_SELECTOR,
                        ".size-selector-sizes-size, "
                        ".product-size-selector__item, "
                        ".size-list__item, "
                        "[data-qa*='size'], "
                        ".sizes__item"
                    )
                ) > 0
            )
        except TimeoutException:
            return []

        size_selectors = [
            ".size-selector-sizes-size",
            ".product-size-selector__item",
            ".size-list__item",
            "[data-qa*='size']",
            ".sizes__item"
        ]

        size_elements = []

        for selector in size_selectors:
            elements = driver.find_elements(
                By.CSS_SELECTOR,
                selector
            )
            if elements:
                size_elements = elements
                break

        available_sizes = []

        for element in size_elements:
            try:
                size_label = element.text.strip()

                if size_label not in sizes_to_check:
                    continue

                classes = (
                    element.get_attribute("class") or ""
                ).lower()

                unavailable = any(
                    marker in classes
                    for marker in [
                        "disabled",
                        "unavailable",
                        "out-of-stock",
                        "sold-out"
                    ]
                )

                if unavailable:
                    print(f"❌ {size_label} is out of stock.")
                else:
                    print(f"✅ {size_label} is in stock.")
                    available_sizes.append(size_label)

            except Exception:
                continue

        return available_sizes

    except Exception as e:
        print(f"Stradivarius check error: {e}")
        return []


def rossmannStockCheck(driver):
    return False


def watsonsChecker(driver):
    return False
