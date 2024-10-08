import logging
import random as rnd
import sys
from functools import reduce
from os import getenv
from time import sleep
from typing import Dict, Optional

from dotenv import load_dotenv
from fake_useragent import UserAgent  # type: ignore
from selenium import webdriver
from selenium.common.exceptions import NoSuchElementException, TimeoutException, WebDriverException
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.firefox.service import Service as FirefoxService
from selenium.webdriver.remote.webelement import WebElement
from selenium.webdriver.support import expected_conditions as ec
from selenium.webdriver.support.ui import WebDriverWait
from webdriver_manager.firefox import GeckoDriverManager

load_dotenv()

X_LOGIN_URL: str = "https://twitter.com/i/flow/login"
LOGGER: logging.Logger = logging.getLogger(__name__)
USERNAME: str = getenv("X_USERNAME", "")
PASSWORD: str = getenv("X_PASSWORD", "")
PHONE: str = getenv("X_PHONE", "")

SCORES: Dict[str, float] = {
    "wallstreetbets": 1,
    "kookcapitalllc": 0.5,
    "hgeabc": 0.5,
    "beaniemaxi": 1,
    "soljakey": 0.5,
    "issathecooker": 0.25,
    "mrsolana69": 0.5,
    "crashiusclay69": 1,
    "pauly0x": 1.5,
    "scooterxbt": 1,
    "0xwinged": 0.5,
    "yennii56": 0.5,
    "obijai": 0.5,
    "resolventsol": 1.25,
    "notthreadguy": 1,
    "frankdegods": 0.25,
    "yogurt_eth": 1,
    "orangie": 0.5,
    "seniornft": 0.5,
    "w0lf0fcrypt0": 0.25,
    "metaversejoji": 1,
    "yelotree": 1,
    "nate_rivers": 1,
    "a1lon9": 0.5,
    "blknoiz06": 1,
    "rehabonsolana": 4.5,
}


class Scrapper:
    def __init__(self) -> None:
        """Initialize Scrapper."""
        if not USERNAME or not PASSWORD:
            LOGGER.error("X_USERNAME or X_PASSWORD is not provided")
            sys.exit(1)

        self.username = USERNAME
        self.password = PASSWORD
        self.phone = PHONE
        self.driver = self._init_driver()

    def _init_driver(self) -> webdriver.Firefox:
        LOGGER.info("Initializing driver...")
        ua = UserAgent()

        browser_opts = webdriver.FirefoxOptions()
        browser_opts.add_argument("--no-sandbox")
        browser_opts.add_argument("--disable-dev-shm-usage")
        browser_opts.add_argument("--ignore-certificate-errors")
        browser_opts.add_argument("--disable-gpu")
        browser_opts.add_argument("--log-level=3")
        browser_opts.add_argument("--disable-notifications")
        browser_opts.add_argument("--disable-popup-blocking")
        browser_opts.add_argument("--user-agent={}".format(ua.firefox))
        browser_opts.add_argument("--headless")

        try:
            driver = webdriver.Firefox(options=browser_opts)
            self.wait = WebDriverWait(driver, 10)
            LOGGER.info("Driver initialized successfully")
            return driver
        except WebDriverException:
            try:
                LOGGER.warning("Downloading web driver...")
                firefoxdriver_path = GeckoDriverManager().install()
                firefox_service = FirefoxService(executable_path=firefoxdriver_path)
                driver = webdriver.Firefox(
                    service=firefox_service,
                    options=browser_opts,
                )

                LOGGER.info("Driver initialized successfully")
                return driver
            except Exception as e:
                LOGGER.error(f"Error initializing web driver: {e}")
                sys.exit(1)

    def login(self) -> None:
        LOGGER.info("Logging in...")
        self.driver.get(X_LOGIN_URL)
        sleep(3)
        self._input_credentials()

    def _input_unusual_activity(self) -> None:
        max_attempts = 5
        attempts = 0

        while attempts < max_attempts:
            try:
                unusual_activity = self.driver.find_element("xpath", "//input[@data-testid='ocfEnterTextTextInput']")
                LOGGER.info("Unusual activity field found, entering phone number...")
                self._simulate_typing(unusual_activity, self.phone)
                unusual_activity.send_keys(Keys.RETURN)
                sleep(1)
                break
            except NoSuchElementException:
                attempts += 1

                if attempts == max_attempts:
                    LOGGER.error("Max attempts reached for unusual activity field")
                    break

                LOGGER.warning("Unusual activity field not found, retrying...")
                sleep(2)

    def _input_username(self) -> None:
        max_attempts = 5
        attempts = 0

        while attempts < max_attempts:
            try:
                username_field = self.driver.find_element("xpath", "//input[@autocomplete='username']")
                LOGGER.info("Username field found, entering username...")
                self._simulate_typing(username_field, self.username)
                sleep(0.3)
                username_field.send_keys(Keys.RETURN)
                break
            except NoSuchElementException:
                attempts += 1

                if attempts == max_attempts:
                    LOGGER.error("Max attempts reached")
                    self.driver.quit()
                    sys.exit(1)

                LOGGER.warning("Username field not found, retrying...")
                sleep(2)

    def _input_password(self) -> None:
        max_attempts = 5
        attempts = 0

        while attempts < max_attempts:
            try:
                password_field = self.driver.find_element("xpath", "//input[@autocomplete='current-password']")
                LOGGER.info("Password field found, entering password...")
                self._simulate_typing(password_field, self.password)
                sleep(0.3)
                password_field.send_keys(Keys.RETURN)
                break
            except NoSuchElementException:
                attempts += 1

                if attempts == max_attempts:
                    LOGGER.error("Max attempts reached")
                    self.driver.quit()
                    sys.exit(1)

                LOGGER.warning("Password field not found, retrying...")
                sleep(2)

    def _input_credentials(self) -> None:
        # username
        self._input_username()
        sleep(3)
        self._input_unusual_activity()
        sleep(2)
        # password
        self._input_password()
        sleep(3)

        try:
            cookies = self.driver.get_cookies()
            logged = False

            for cookie in cookies:
                LOGGER.info(f"Cookie found: {cookie['name']}")  # debug
                if cookie["name"] == "auth_token":
                    logged = True
                    break
            if not logged:
                raise Exception("Authentication Cookie not found")
        except Exception as e:
            LOGGER.error(f"Failed to login: {e}")
            self.driver.quit()
            sys.exit(1)

        self.logged_in = True
        LOGGER.info("Logged in successfully")

    def calc_score(self, username: str) -> float:
        elements = self._get_followers(username)
        if not elements:
            return 0.0
        return self._get_score(elements)

    def _get_followers(self, username: str) -> Optional[list[WebElement]]:
        if not self.logged_in:
            LOGGER.error("Not logged in")
            return None

        self.driver.get(f"https://x.com/{username}/followers_you_follow")
        try:
            elements = self.wait.until(
                ec.visibility_of_all_elements_located(
                    (
                        By.XPATH,
                        "//div[@aria-label='Timeline: Followers you know']/div//span[contains(text(), '@')]",
                    )
                )
            )
            return elements
        except TimeoutException:
            LOGGER.error("Error waiting for followers list")
            return None

    def _get_score(self, elememts: list[WebElement]) -> float:
        followers = [el.text.replace("@", "").lower() for el in elememts]
        return float(reduce(lambda acc, follower: acc + SCORES.get(follower, 0.0), followers, 0.0))

    def _simulate_typing(
        self,
        element: WebElement,
        text: str,
        min_delay: float = 0.1,
        max_delay: float = 0.3,
    ) -> None:
        for char in text:
            element.send_keys(char)
            sleep(rnd.uniform(min_delay, max_delay))


if __name__ == "__main__":
    test1 = "Nate_Rivers"
    test2 = "WallStreetBets"

    logging.basicConfig(
        level=logging.INFO,
        stream=sys.stdout,
    )
    scrapper = Scrapper()
    scrapper.login()
    print(scrapper.calc_score(test1))
    sleep(2)
    print(scrapper.calc_score(test2))
