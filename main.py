from selenium import webdriver
from selenium.common.exceptions import NoSuchElementException, TimeoutException, StaleElementReferenceException
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service as ChromeService
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait, Select
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.common.action_chains import ActionChains
from configparser import SectionProxy
from typing import Dict, Optional, Union
from abc import ABC, abstractmethod

import logging
import os
import configparser
import requests
import json
import time
import traceback

logger = logging.getLogger(__name__)

log_level = os.getenv("LOG_LEVEL", "DEBUG").upper()
logger.setLevel(log_level)

levels = {
    "DEBUG": logging.DEBUG,
    "INFO": logging.INFO,
    "WARNING": logging.WARNING,
    "ERROR": logging.ERROR,
    "CRITICAL": logging.CRITICAL,
}

enable_notifications: bool = os.getenv("ENABLE_NOTIFICATIONS", "false").lower() in (
    "true",
    "1",
    "t",
)
notification_url: Optional[str] = os.getenv("NOTIFICATION_URL")
webdriver_path: str = os.getenv("WEBDRIVER_PATH", "/usr/bin/chromedriver")
role_id = os.getenv("DISCORD_ROLE_ID")

config = configparser.ConfigParser(interpolation=None)
config_path = "websites.ini"
if config.read(config_path):
    logger.info(f"Configuration loaded from {config_path}")
else:
    logger.error(
        f"Failed to load configuration from {config_path}. Please check the file path and try again."
    )
    exit(1)


class IgnoreBrowserLogsFilter(logging.Filter):
    def filter(self, record):
        return "Third-party cookie will be blocked" not in record.getMessage()


handler = logging.StreamHandler()
logger.addHandler(handler)
logger.addFilter(IgnoreBrowserLogsFilter())


class WebDriverBase:
    def __init__(self):
        self.driver_path: str = webdriver_path
        self.driver = self._init_driver()

    def _init_driver(self):
        chrome_options = Options()
        chrome_options.add_argument("--headless")
        chrome_options.add_argument("--no-sandbox")
        chrome_options.add_argument("--disable-dev-shm-usage")
        chrome_options.add_argument("--disable-gpu")
        chrome_options.add_argument("--window-size=1920x1080")
        chrome_options.add_argument("--log-level=off")
        service = ChromeService(executable_path=self.driver_path)
        driver = webdriver.Chrome(service=service, options=chrome_options)

        return driver

    def close_driver(self):
        self.driver.quit()


class AbstractHunter(ABC):
    """
    Abstract base class for website hunters.
    Defines the template methods and properties each hunter must implement.
    """

    def __init__(
        self, config: Union[SectionProxy, Dict[str, Union[str, bool, int]]]
    ) -> None:
        """
        Initialize the hunter with a configuration section from configparser or a dictionary.
        """
        self.config = config
        self.listings = {
            "seen_listings": {},
            "new_listings": [],
        }
        self.load_seen_listings()

    def restart_driver(self):
        """Close and restart the WebDriver."""
        self.close_driver()
        self.driver = self._init_driver()

    @abstractmethod
    def check_for_new_listings(self):
        """
        Check the website for new listings.
        This method needs to be implemented by each subclass.
        """
        pass

    @property
    def storage_directory(self):
        """
        Returns a directory name derived from the class name for saving files.
        This eliminates the need for subclasses to override this unless a custom name is desired.
        """
        class_name = self.__class__.__name__.lower()
        directory_name = f"{class_name}"
        parent_directory = "results"
        full_directory_path = os.path.join(parent_directory, directory_name)
        return full_directory_path

    def ensure_storage_directory_exists(self):
        """Ensure the storage directory exists."""
        os.makedirs(self.storage_directory, exist_ok=True)
        if not os.access(self.storage_directory, os.W_OK):
            raise PermissionError(
                f"Directory {self.storage_directory} is not writable."
            )

    def save_screenshot(self, filename):
        """
        Saves a screenshot with the given filename into the hunter's specific storage directory.
        """
        self.ensure_storage_directory_exists()
        filepath = os.path.join(self.storage_directory, filename)
        self.driver.save_screenshot(filepath)
        logger.info(f"Screenshot saved to {filepath}")

    def save_html_content(self, html_content, filename):
        """
        Saves HTML content to a file within the hunter's specific storage directory.
        """
        self.ensure_storage_directory_exists()
        filepath = os.path.join(self.storage_directory, filename)
        with open(filepath, "w", encoding="utf-8") as file:
            file.write(html_content)
        logger.info(f"HTML content saved to {filepath}")

    @property
    def seen_listings_file(self):
        """
        Returns the file path for saving seen listings, incorporating the storage directory.
        """
        self.ensure_storage_directory_exists()
        return os.path.join(self.storage_directory, "seen_listings.json")

    def load_seen_listings(self):
        self.ensure_storage_directory_exists()

        try:
            with open(self.seen_listings_file, "r") as file:
                self.seen_listings = json.load(file)
            logger.info("Loaded seen listings from file.")
        except FileNotFoundError:
            self.seen_listings = {}
            logger.info("Seen listings file not found. Starting with an empty set.")
        except json.JSONDecodeError:
            self.seen_listings = {}
            logger.error(
                "Error decoding the seen listings file. Starting with an empty set."
            )

    def save_seen_listings(self):
        try:
            # Load existing seen listings from file
            existing_seen_listings = {}
            try:
                with open(self.seen_listings_file, "r") as file:
                    existing_seen_listings = json.load(file)
            except FileNotFoundError:
                logger.info("Seen listings file not found. Creating a new one.")
            except json.JSONDecodeError:
                logger.error(
                    "Error decoding the seen listings file. Starting with an empty set."
                )

            # Update existing seen listings with new ones
            updated_seen_listings = {
                **existing_seen_listings,
                **self.listings["seen_listings"],
            }

            if updated_seen_listings:
                first_url, first_listing_details = next(
                    iter(updated_seen_listings.items())
                )
                pretty_first_listing = json.dumps(
                    {first_url: first_listing_details}, indent=4
                )
                logger.debug(f"First seen listing to be saved: {pretty_first_listing}")
            else:
                logger.debug("No listings to save.")

            # Save updated seen listings back to file
            pretty_listings = json.dumps(updated_seen_listings, indent=4)
            with open(self.seen_listings_file, "w") as file:
                file.write(pretty_listings)

            logger.info("Saved seen listings to file: %s", self.seen_listings_file)
        except IOError as e:
            logger.error(f"IOError when trying to save seen listings: {e}")
        except Exception as e:
            logger.error(f"Unexpected error when saving seen listings: {e}")

    def process_listings(self, scraped_listings):
        """Process a batch of scraped listings."""
        if not scraped_listings:
            print("No listings to process.", flush=True)
            logger.info("No listings to process.")
            return

        logger.info("\n===== Processing Scraped Listings =====\n")

        new_listings_count = 0
        seen_listings_count = 0

        for listing in scraped_listings:
            logger.info(f"Evaluating listing: {listing['url']}")
            if listing["url"] not in self.seen_listings:
                new_listings_count += 1
                self.listings["new_listings"].append(listing)
                self.listings["seen_listings"][listing["url"]] = listing
                logger.info(
                    json.dumps(
                        {
                            "action": "New listing found",
                            "url": listing["url"],
                            "details": listing,
                        },
                        indent=4,
                    )
                )
            else:
                seen_listings_count += 1
                logger.info(
                    json.dumps(
                        {"action": "Already seen, skipping", "url": listing["url"]},
                        indent=4,
                    )
                )

        logger.info("\n===== Summary =====")
        logger.info(f"New listings found: {new_listings_count}")
        logger.info(f"Listings already seen: {seen_listings_count}")
        if new_listings_count == 0:
            logger.info("No new listings found, skipping notification.")

        if self.listings["new_listings"]:
            self.announce_new_listings()

        self.save_seen_listings()
        self.load_seen_listings()

        self.listings["new_listings"] = []

    def format_listing_message(self, listing_details):
        try:
            embed_payload = {
                "title": listing_details.get("price"),
                "description": listing_details.get("size"),
                "url": listing_details.get("url"),
                "color": 4937567,
                "fields": [
                    {
                        "name": "Address",
                        "value": listing_details.get("address"),
                        "inline": True,
                    },
                    {
                        "name": "Access",
                        "value": listing_details.get("access"),
                        "inline": True,
                    },
                ],
                "author": {
                    "name": "SUUMO",
                    "url": listing_details.get("url"),
                    "icon_url": "https://cdn3.emoji.gg/emojis/9666-link.png",
                },
                "image": {"url": listing_details.get("image_url")},
            }

            return embed_payload
        except KeyError as e:
            logger.error("Missing key in listing details: %s", e)
            return None

    def announce_new_listings(self):
        """Announce new listings based on their count."""
        new_listings_count = len(self.listings["new_listings"])

        if new_listings_count == 0:
            return

        if new_listings_count < 3:
            for listing in self.listings["new_listings"]:
                logger.info("Preparing message for %s", listing["url"])
                embed_payload = self.format_listing_message(listing)
                self.send_notification({"content": "", "embeds": [embed_payload]})
        else:
            logger.info(
                "Preparing summary for %d listings", len(self.listings["new_listings"])
            )
            self.send_summary_notification(self.listings["new_listings"])

        self.listings["new_listings"] = []

    def send_notification(self, embed_payload):
        """Send a notification with the given payload."""
        if enable_notifications and notification_url:
            try:
                logger.info(
                    f"Payload to send notification:\n{json.dumps(embed_payload, indent=4)}"
                )
                response = requests.post(notification_url, json=embed_payload)
                response.raise_for_status()  # Raise an exception if a non-200 status code is returned
                logger.info("Notification sent successfully.")
            except requests.exceptions.HTTPError as e:
                logger.error("Failed to send notification: %s", e)
            except requests.exceptions.ConnectionError as e:
                logger.error("Failed to send notification: %s", e)
            except requests.exceptions.Timeout as e:
                logger.error("Failed to send notification: %s", e)
            except requests.exceptions.RequestException as e:
                logger.error("Failed to send notification: %s", e)

        else:
            logger.info(
                "Notifications are disabled, or notification URL is not provided, skipping notification."
            )
            logger.info("Would have sent notification: %s", embed_payload)
            logger.info(
                "⚠️  Edit the environment variables to enable notifications.  ⚠️ "
            )

    def send_summary_notification(self, listings):
        """Send a summary notification for multiple listings."""

        target_url = self.config["target_url"]
        content = f"Found {len(listings)} new listings. View on [SUUMO]({target_url})"
        if role_id:
            content = f"<@&{role_id}> " + content
        embeds = [self.format_listing_message(listing) for listing in listings[:3]]
        self.send_notification({"content": content, "embeds": embeds})


class SUUMOHunter(AbstractHunter, WebDriverBase):
    def __init__(self):
        super().__init__(config["SUUMO"])
        WebDriverBase.__init__(self)

    def check_for_new_listings(self):
        logger.debug(f"Accessing URL: {self.config['target_url']}")
        self.driver.get(self.config["target_url"])
        self.save_screenshot("screenshot_initial_load.png")
        page_source = self.driver.page_source
        self.save_html_content(page_source, "page_source_initial_load.html")

        # Zoom out of the map to get more results
        try:
            zoom_out_button = WebDriverWait(
                self.driver, self.config["dynamic_content_timeout"]
            ).until(
                EC.element_to_be_clickable(
                    (By.XPATH, "//button[@aria-label='Zoom out']")
                )
            )
            zoom_out_button.click()
            logger.info("Clicked zoom out once.")
            self.save_screenshot("screenshot_zoom_out_click1.png")

        except TimeoutException:
            logger.error(
                "Zoom out button not found or not clickable within timeout period."
            )

        # Switch the list view, rather than map view
        try:
            WebDriverWait(self.driver, self.config["dynamic_content_timeout"]).until(
                EC.element_to_be_clickable((By.ID, "listViewButton"))
            )
            logger.info("List view button is clickable.")

            list_view_button = self.driver.find_element(By.ID, "listViewButton")
            ActionChains(self.driver).click(list_view_button).perform()
            logger.info("Clicked on list view button.")

            WebDriverWait(self.driver, self.config["dynamic_content_timeout"]).until(
                lambda d: len(
                    d.find_elements(By.CSS_SELECTOR, "ul.listView.bukkenList > li")
                )
                > 0
            )
            logger.info("Listings have successfully loaded.")
            self.save_screenshot("screenshot_after_button_click.png")
            self.save_html_content(
                self.driver.page_source, "page_source_after_button_click.html"
            )

            logger.info("Dynamic content loaded")

            # Wait for the dropdown menu to be clickable and select "New arrival order"
            try:
                WebDriverWait(
                    self.driver, self.config["dynamic_content_timeout"]
                ).until(EC.element_to_be_clickable((By.ID, "listSort")))
                select = Select(self.driver.find_element(By.ID, "listSort"))
                select.select_by_value("11")  # Selecting "New arrival order"
                logger.info("Sorting listings by newest")

                self.save_screenshot("screenshot_after_selecting_new_arrival_order.png")

            except TimeoutException:
                logger.error(
                    "Dropdown menu not found or not interactable within timeout period."
                )

            all_listings = []

            listings = self.driver.find_elements(
                By.CSS_SELECTOR, "ul.listView.bukkenList > li"
            )

            for listing in listings:
                try:
                    price = listing.find_element(By.CSS_SELECTOR, ".price").text
                    size = listing.find_element(By.CSS_SELECTOR, ".exclusive").text
                    address = listing.find_element(By.CSS_SELECTOR, ".address").text
                    access = listing.find_element(By.CSS_SELECTOR, ".ensen").text
                    url = listing.find_element(
                        By.CSS_SELECTOR, ".innerInfo a"
                    ).get_attribute("href")
                    image_url = listing.find_element(
                        By.CSS_SELECTOR, ".imgWrap img"
                    ).get_attribute("src")

                    listing_details = {
                        "price": price,
                        "size": size,
                        "address": address,
                        "access": access,
                        "url": url,
                        "image_url": image_url,
                    }

                    all_listings.append(listing_details)

                except NoSuchElementException as e:
                    logger.error(f"Error extracting details for listing: {e}")

            # Open the URL from each listing
            # Find the table[summary="hyo"]
            # Look for the text "建ぺい率･容積率" and get the second th+td pair
            # Find second number
            # Do original land size * second number / 100
            # If this above number is larger than 140, it is a good listing
            

            self.process_listings(all_listings)

            self.announce_new_listings()

        except StaleElementReferenceException as e:
            logger.error(f"StaleElementReferenceException: {e}")
            self.restart_driver()
            self.check_for_new_listings()

        finally:
            for entry in self.driver.get_log("browser"):
                logger.info(entry)
            self.close_driver()
            logger.info("Driver closed")


if __name__ == "__main__":
    blue_bold = "\x1b[34;1m"
    reset = "\033[0m"
    yellow = "\033[93m"
    green = "\033[92m"
    red = "\033[91m"
    ascii_logo = (
        blue_bold
        + """
ooooo   ooooo                                   ooooo   ooooo                         .                      
`888'   `888'                                   `888'   `888'                       .o8                     
 888     888  .ooooo. ooo. .oo.  .oo.   .ooooo.  888     888 oooo  oooo ooo. .oo. .o888oo  .ooooo.  oooo d8b
 888ooooo888 d88' `88b`888P"Y88bP"Y88b d88' `88b 888ooooo888 `888  `888 `888P"Y88b  888   d88' `88b `888""8P
 888     888 888   888 888   888   888 888ooo888 888     888  888   888  888   888  888   888ooo888  888
 888     888 888   888 888   888   888 888    .o 888     888  888   888  888   888  888 . 888    .o  888
o888o   o888o`Y8bod8P o888o o888o o888o`Y8bod8P'o888o   o888o `V88V"V8P'o888o o888o "888" `Y8bod8P' d888b                                                                                                                                                                                                                                                                                      
    """
        + reset
    )
    print(ascii_logo, flush=True)
    logger.info("Starting home-hunter")

    enable_notifications = os.getenv("ENABLE_NOTIFICATIONS", "false").lower() in (
        "true",
        "1",
        "t",
    )
    notification_url = os.getenv("NOTIFICATION_URL")
    if not enable_notifications or not notification_url:
        alert_message = f"""{yellow}
            ⚠️  Attention: Notifications are disabled or notification URL is not provided. ⚠️
                                   Notifications will NOT be sent.                        
                        {reset}"""
        print(alert_message, flush=True)


    hunter = SUUMOHunter()

    while True:
        try:
            hunter.restart_driver()
            hunter.check_for_new_listings()
            hunter.close_driver()
            sleep_time = int(os.getenv("WAIT_SECONDS_BETWEEN_CHECKS", "60"))
            logger.info(f"Waiting for {sleep_time} seconds before the next check...")
            time.sleep(sleep_time)

        except Exception as e:
            logger.error(f"❗ Error processing SUUMOHunter: {e}", exc_info=True)
            hunter.close_driver()
            sleep_time = int(os.getenv("WAIT_SECONDS_BETWEEN_CHECKS", "60"))
            logger.info(f"Restarting after error. Waiting for {sleep_time} seconds before the next check...")
            time.sleep(sleep_time)
            # No need to restart the driver here, it will be restarted at the beginning of the next loop iteration

        except KeyboardInterrupt:
            logger.warning("🛑 Home-hunter terminated by user.")
            hunter.close_driver()
            break  # Exit the loop gracefully
