from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import TimeoutException, NoSuchElementException
import time
import os


# =========================
# ZARA
# =========================
def check_stock_zara(driver, sizes_to_check):
    try:
        wait = WebDriverWait(driver, 4)

        # Cookies - перевіряємо без довгого очікування
        try:
            cookie_buttons = driver.find_elements(By.ID, "onetrust-accept-btn-handler")
            if cookie_buttons and cookie_buttons[0].is_displayed():
                driver.execute_script("arguments[0].click();", cookie_buttons[0])
                print("Cookie alert closed.")
        except Exception:
            pass

        # Кнопка "Add to cart"
        try:
            add_to_cart_button = wait.until(
                EC.presence_of_element_located(
                    (By.CSS_SELECTOR, "button[data-qa-action='add-to-cart']")
                )
            )

            overlays = driver.find_elements(By.CLASS_NAME, "zds-backdrop")
            if overlays:
                try:
                    driver.execute_script("arguments[0].remove();", overlays[0])
                except Exception:
                    pass

            driver.execute_script("arguments[0].click();", add_to_cart_button)

        except TimeoutException:
            print("Add to cart button not found.")
            return None

        # Список розмірів
        try:
            wait.until(
                EC.presence_of_element_located(
                    (By.CLASS_NAME, "size-selector-sizes-size")
                )
            )
        except TimeoutException:
            print("Size selector not found.")
            return None

        size_elements = driver.find_elements(
            By.CLASS_NAME,
            "size-selector-sizes-size"
        )

        found_requested_size = False

        for li in size_elements:
            try:
                size_label = li.find_element(
                    By.CSS_SELECTOR,
                    "div[data-qa-qualifier='size-selector-sizes-size-label']"
                ).text.strip()

                if size_label not in sizes_to_check:
                    continue

                found_requested_size = True

                button = li.find_element(
                    By.CLASS_NAME,
                    "size-selector-sizes-size__button"
                )

                data_qa = button.get_attribute("data-qa-action") or ""

                if data_qa in ["size-in-stock", "size-low-on-stock"]:
                    print(f"✅ {size_label} is in stock.")
                    return size_label

                print(f"❌ {size_label} is out of stock.")

            except Exception as e:
                print(f"Error processing size element: {e}")
                continue

        if not found_requested_size:
            print(f"Sizes {', '.join(sizes_to_check)} not found.")

        return None

    except Exception as e:
        print(f"Zara check error: {e}")
        return None


# =========================
# ROSSMANN
# =========================
def rossmannStockCheck(driver):
    wait = WebDriverWait(driver, 20)

    try:
        wait.until(
            EC.presence_of_element_located(
                (By.CLASS_NAME, "product-add-form")
            )
        )
    except Exception:
        print("Rossmann product not available.")
        return False

    try:
        button = driver.find_element(
            By.XPATH,
            "//button[@type='submit' and contains(., 'Sepete Ekle')]"
        )

        if button:
            print("Rossmann product in stock.")
            driver.execute_script("arguments[0].click();", button)
            return True

    except Exception:
        print("Rossmann product out of stock.")

    return False


# =========================
# BERSHKA
# =========================
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
                    (By.CSS_SELECTOR, "ul[data-qa-anchor='productDetailSize']")
                )
            )
        except TimeoutException:
            print("Bershka size list not found.")
            return None

        size_buttons = driver.find_elements(
            By.CSS_SELECTOR,
            "button[data-qa-anchor='sizeListItem']"
        )

        found_requested_size = False

        for button in size_buttons:
            try:
                size_label_elem = button.find_element(
                    By.CSS_SELECTOR,
                    "span.text__label"
                )

                size_label = size_label_elem.text.strip()

                if size_label not in sizes_to_check:
                    continue

                found_requested_size = True

                class_attr = button.get_attribute("class") or ""

                if "is-disabled" in class_attr:
                    print(f"❌ {size_label} is out of stock.")
                    continue

                print(f"✅ {size_label} is in stock.")
                return size_label

            except Exception as e:
                print(f"Error processing Bershka size: {e}")
                continue

        if not found_requested_size:
            print(f"Sizes {', '.join(sizes_to_check)} not found.")

        return None

    except Exception as e:
        print(f"Bershka check error: {e}")
        return None


# =========================
# WATSONS
# =========================
def watsonsChecker(driver):
    wait = WebDriverWait(driver, 20)

    try:
        elements = wait.until(
            EC.presence_of_all_elements_located(
                (By.CLASS_NAME, "product-grid-manager__view-mount")
            )
        )

        text = " ".join(
            element.text.strip()
            for element in elements
        )

        return "0 ürün" not in text

    except Exception:
        return False


# =========================
# STRADIVARIUS
# =========================
def check_stock_stradivarius(driver, sizes_to_check):
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

        add_to_cart_selectors = [
            "button[data-qa-action='add-to-cart']",
            ".product-detail-actions__add-to-cart",
            ".add-to-cart-button",
            ".product-actions__add-to-cart",
            "button[class*='add-to-cart']"
        ]

        add_to_cart_button = None

        for selector in add_to_cart_selectors:
            try:
                elements = driver.find_elements(
                    By.CSS_SELECTOR,
                    selector
                )

                if elements:
                    add_to_cart_button = elements[0]
                    break

            except Exception:
                continue

        if not add_to_cart_button:
            print("Stradivarius add to cart button not found.")
            return None

        try:
            driver.execute_script(
                "arguments[0].click();",
                add_to_cart_button
            )
        except Exception:
            return None

        try:
            WebDriverWait(driver, 3).until(
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
            print("No Stradivarius sizes found.")
            return None

        size_selectors = [
            ".size-selector-sizes-size",
            ".product-size-selector__item",
            ".size-list__item",
            "[data-qa*='size']",
            ".sizes__item"
        ]

        size_elements = []

        for selector in size_selectors:
            elements = driver.find_elements(By.CSS_SELECTOR, selector)

            if elements:
                size_elements = elements
                break

        found_requested_size = False

        for element in size_elements:
            try:
                size_label = None

                size_text_selectors = [
                    "div[data-qa-qualifier='size-selector-sizes-size-label']",
                    ".size-label",
                    ".text__label",
                    "span"
                ]

                for text_selector in size_text_selectors:
                    try:
                        label_element = element.find_element(
                            By.CSS_SELECTOR,
                            text_selector
                        )

                        size_label = label_element.text.strip()

                        if size_label:
                            break

                    except Exception:
                        continue

                if not size_label:
                    size_label = element.text.strip()

                if size_label not in sizes_to_check:
                    continue

                found_requested_size = True

                button = None

                for button_selector in [
                    ".size-selector-sizes-size__button",
                    "button",
                    "[role='button']"
                ]:
                    try:
                        button = element.find_element(
                            By.CSS_SELECTOR,
                            button_selector
                        )
                        break
                    except Exception:
                        continue

                if button is None:
                    button = element

                element_classes = (
                    element.get_attribute("class") or ""
                ).lower()

                button_classes = (
                    button.get_attribute("class") or ""
                ).lower()

                unavailable_indicators = [
                    "disabled",
                    "unavailable",
                    "out-of-stock",
                    "sold-out"
                ]

                if any(
                    indicator in element_classes
                    or indicator in button_classes
                    for indicator in unavailable_indicators
                ):
                    print(f"❌ {size_label} is out of stock.")
                    continue

                data_qa = (
                    button.get_attribute("data-qa-action") or ""
                ).lower()

                if (
                    "disabled" not in data_qa
                    and "unavailable" not in data_qa
                ):
                    print(f"✅ {size_label} is in stock.")
                    return size_label

            except Exception as e:
                print(f"Error processing Stradivarius size: {e}")
                continue

        if not found_requested_size:
            print(f"Sizes {', '.join(sizes_to_check)} not found.")

        return None

    except Exception as e:
        print(f"Stradivarius check error: {e}")
        return None
