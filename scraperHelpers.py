from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import TimeoutException


def check_stock_zara(driver, sizes_to_check):
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

        # Zara can use different selectors for the add button
        selectors = [
            "button[data-qa-action='add-to-cart']",
            "button[data-qa-action*='add']",
            "button[class*='add-to-cart']",
            "[data-qa-action='add-to-cart']"
        ]

        add_button = None

        for selector in selectors:
            try:
                elements = WebDriverWait(driver, 3).until(
                    lambda d: d.find_elements(By.CSS_SELECTOR, selector)
                )

                for element in elements:
                    if element.is_displayed():
                        add_button = element
                        break

                if add_button:
                    break

            except Exception:
                continue

        if not add_button:
            print("❌ Zara add button not found.")
            return []

        # Remove overlay if present
        try:
            overlays = driver.find_elements(
                By.CLASS_NAME,
                "zds-backdrop"
            )
            for overlay in overlays:
                driver.execute_script(
                    "arguments[0].remove();",
                    overlay
                )
        except Exception:
            pass

        try:
            driver.execute_script(
                "arguments[0].click();",
                add_button
            )
        except Exception as e:
            print(f"❌ Could not click Zara add button: {e}")
            return []

        # Wait for size elements
        try:
            wait.until(
                lambda d: len(
                    d.find_elements(
                        By.CLASS_NAME,
                        "size-selector-sizes-size"
                    )
                ) > 0
            )
        except TimeoutException:
            print("❌ Zara size selector not found.")
            return []

        size_elements = driver.find_elements(
            By.CLASS_NAME,
            "size-selector-sizes-size"
        )

        available_sizes = []

        for wanted_size in sizes_to_check:
            found_size = False

            for li in size_elements:
                try:
                    label = li.find_element(
                        By.CSS_SELECTOR,
                        "div[data-qa-qualifier='size-selector-sizes-size-label']"
                    ).text.strip()

                    if label != wanted_size:
                        continue

                    found_size = True

                    button = li.find_element(
                        By.CLASS_NAME,
                        "size-selector-sizes-size__button"
                    )

                    action = (
                        button.get_attribute("data-qa-action")
                        or ""
                    )

                    if action in [
                        "size-in-stock",
                        "size-low-on-stock"
                    ]:
                        print(f"✅ {wanted_size} is in stock.")
                        available_sizes.append(wanted_size)
                    else:
                        print(f"❌ {wanted_size} is out of stock.")

                    break

                except Exception:
                    continue

            if not found_size:
                print(f"⚠️ {wanted_size} not found in size list.")

        return available_sizes

    except Exception as e:
        print(f"❌ Zara check error: {e}")
        return []


def check_stock_bershka(driver, sizes_to_check):
    return []


def check_stock_stradivarius(driver, sizes_to_check):
    return []


def rossmannStockCheck(driver):
    return False


def watsonsChecker(driver):
    return False
