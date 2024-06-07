from selenium import webdriver
from fake_useragent import UserAgent
import sys
import random as rnd
import logging
from typing import Optional
from dotenv import load_dotenv
from time import sleep
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.common.exceptions import (
    NoSuchElementException,
    TimeoutException,
    WebDriverException,
)
from selenium.webdriver.remote.webelement import WebElement
from selenium.webdriver.common.keys import Keys
from functools import reduce
from os import getenv
from webdriver_manager.firefox import GeckoDriverManager
from selenium.webdriver.firefox.service import Service as FirefoxService

load_dotenv()

X_LOGIN_URL = "https://twitter.com/i/flow/login"
LOGGER = logging.getLogger(__name__)
USERNAME = getenv("X_USERNAME", "")
PASSWORD = getenv("X_PASSWORD", "")

SCORES = {
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
    def __init__(self):
        if not USERNAME or not PASSWORD:
            LOGGER.error("X_USERNAME or X_PASSWORD is not provided")
            sys.exit(1)

        self.username = USERNAME
        self.password = PASSWORD
        self.driver = self._init_driver()

    def _init_driver(self) -> Optional[webdriver.Firefox]:
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
                LOGGER.warn("Downloading web driver...")
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

    def _input_credentials(self) -> None:
        max_attempts = 5
        attempts = 0

        # username
        while attempts < max_attempts:
            try:
                username_field = self.driver.find_element(
                    "xpath", "//input[@autocomplete='username']"
                )
                self._simulate_typing(username_field, self.username)
                username_field.send_keys(Keys.RETURN)
                sleep(1)
                break
            except NoSuchElementException:
                attempts += 1

                if attempts == max_attempts:
                    LOGGER.error("Max attempts reached")
                    self.driver.quit()
                    sys.exit(1)

                LOGGER.warn("Username field not found, retrying...")
                sleep(2)

        sleep(2)
        attempts = 0

        # password
        while attempts < max_attempts:
            try:
                password_field = self.driver.find_element(
                    "xpath", "//input[@autocomplete='current-password']"
                )

                self._simulate_typing(password_field, self.password)
                sleep(0.3)
                password_field.send_keys(Keys.RETURN)
                sleep(3)
                break
            except NoSuchElementException:
                attempts += 1

                if attempts == max_attempts:
                    LOGGER.error("Max attempts reached")
                    self.driver.quit()
                    sys.exit(1)

                LOGGER.warn("Password field not found, retrying...")
                sleep(2)

        try:
            cookies = self.driver.get_cookies()
            logged = False

            for cookie in cookies:
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
                EC.visibility_of_all_elements_located(
                    (
                        By.XPATH,
                        "//div[@aria-label='Timeline: Followers you know']/div//span[contains(text(), '@')]",
                    )
                )
            )
            return elements
        except TimeoutException as e:
            LOGGER.error(f"Error waiting for followers list")
            return None

    def _get_score(self, elememts: list[WebElement]) -> float:
        followers = [el.text.replace("@", "").lower() for el in elememts]
        return float(
            reduce(
                lambda acc, follower: acc + SCORES.get(follower, 0.0), followers, 0.0
            )
        )

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
