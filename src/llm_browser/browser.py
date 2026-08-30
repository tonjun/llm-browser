"""SeleniumBase CDP Mode helpers."""

from seleniumbase import sb_cdp


def open_url(url: str, headless: bool = False) -> None:
    """Open a URL using SeleniumBase's standalone CDP Mode.

    Unlike ``SB(uc=True)``, this skips the Selenium WebDriver layer
    entirely and talks to Chrome directly over the DevTools Protocol,
    which is lighter weight and doesn't need a pytest-style context.
    """
    driver = sb_cdp.Chrome(url, headless=headless)
    try:
        driver.sleep(2)
        print(driver.get_title())
    finally:
        driver.quit()
