from selenium import webdriver
from selenium.common.exceptions import (
    NoSuchElementException,
    StaleElementReferenceException,
)
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service as ChromeService
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from configparser import SectionProxy
from typing import Dict, Union
from abc import ABC, abstractmethod

import logging
import os
import configparser
import re
import requests
import json
import time
import signal
import sys


def setup_logging():
    log_level = os.getenv("LOG_LEVEL", "DEBUG").upper()
    numeric_level = getattr(logging, log_level, None)
    if not isinstance(numeric_level, int):
        raise ValueError(f"Invalid log level: {log_level}")
    logging.basicConfig(level=numeric_level, format="%(message)s")

    return logging.getLogger(__name__)


# This is just to clear out irrelevant logs from thewebsites themselves
class IgnoreBrowserLogsFilter(logging.Filter):
    def filter(self, record):
        unwanted_phrases = [
            "Third-party cookie will be blocked",
            "Google Maps JavaScript API has been loaded",
            "google.maps.event.addDomListener() is deprecated",
            "An iframe which has both allow-scripts and allow-same-origin",
            "A parser-blocking, cross site",
        ]
        return not any(phrase in record.getMessage() for phrase in unwanted_phrases)


logger = setup_logging()
logger.addFilter(IgnoreBrowserLogsFilter())  # Add the filter


def load_config(config_path: str = "websites.ini") -> configparser.ConfigParser:
    config = configparser.ConfigParser(interpolation=None)
    if not config.read(config_path):
        raise FileNotFoundError(
            f"Failed to load configuration from {config_path}. Please check the file path and try again."
        )
    return config


class AppConfig:
    def __init__(self):
        self.enable_notifications = os.getenv(
            "ENABLE_NOTIFICATIONS", "false"
        ).lower() in ("true", "1", "t")
        self.notification_url = os.getenv("NOTIFICATION_URL")
        self.webdriver_path = os.getenv("WEBDRIVER_PATH", "/usr/bin/chromedriver")
        self.role_id = os.getenv("DISCORD_ROLE_ID")
        self.config = load_config()


class WebDriverBase:
    def __init__(self, app_config: AppConfig):
        self.app_config = app_config
        self.driver_path = app_config.webdriver_path
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
                with open(self.seen_listings_file, "r", encoding="utf-8") as file:
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
                    {first_url: first_listing_details}, indent=4, ensure_ascii=False
                )
                logger.debug(f"First seen listing to be saved: {pretty_first_listing}")
            else:
                logger.debug("No listings to save.")

            # Save updated seen listings back to file
            pretty_listings = json.dumps(
                updated_seen_listings, indent=4, ensure_ascii=False
            )
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
            description = f"""
            **Size:** {listing_details.get('size')}\n**Price per tsubo:** {listing_details.get('price_per_tsubo')}\n**Building coverage ratio:** {listing_details.get('building_coverage_ratio')}\n**Floor area ratio:** {listing_details.get('floor_area_ratio')}\n**Features:** {listing_details.get('features')} 
            """

            embed_payload = {
                "title": listing_details.get("price"),
                "description": description,
                "url": listing_details.get("url"),
                "color": 4937567,
                "fields": [
                    {
                        "name": "Access",
                        "value": listing_details.get("transportation", "Not Available"),
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
        if self.app_config.enable_notifications and self.app_config.notification_url:
            try:
                logger.info(
                    f"Payload to send notification:\n{json.dumps(embed_payload, indent=4)}"
                )
                response = requests.post(
                    self.app_config.notification_url, json=embed_payload
                )
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
        if self.app_config.role_id:
            content = f"<@&{self.app_config.role_id}> " + content
        embeds = [self.format_listing_message(listing) for listing in listings[:3]]
        self.send_notification({"content": content, "embeds": embeds})


class SUUMOHunter(AbstractHunter, WebDriverBase):
    def __init__(self, app_config: AppConfig):
        suumo_config = app_config.config["SUUMO"]
        AbstractHunter.__init__(self, config=suumo_config)
        WebDriverBase.__init__(self, app_config=app_config)

    def check_for_new_listings(self):
        logger.debug(f"Accessing URL: {self.config['target_url']}")
        self.driver.get(self.config["target_url"])
        self.save_screenshot("screenshot_initial_load.png")
        page_source = self.driver.page_source
        self.save_html_content(page_source, "page_source_initial_load.html")

        logger.info("Waiting for listings to load...")
        element_present = EC.presence_of_element_located(
            (By.CSS_SELECTOR, "#right_sliderList2")
        )
        WebDriverWait(self.driver, self.config["dynamic_content_timeout"]).until(
            element_present
        )

        try:
            all_listings = []
            listings = self.driver.find_elements(
                By.CSS_SELECTOR,
                "#right_sliderList2  li[id^='jsiRightSliderListChild_']",
            )
            logger.info(f"Found {len(listings)} listings", extra={"listings": listings})
            for listing in listings:
                try:
                    property_name = listing.find_element(By.CSS_SELECTOR, "p a").text
                    property_features_elements = listing.find_elements(
                        By.CSS_SELECTOR, "ul.cf li"
                    )
                    property_features = "\n".join(
                        element.text for element in property_features_elements
                    )

                    # Price and per_tsubo price
                    price_elements = listing.find_elements(
                        By.XPATH,
                        ".//div[@class='fr w105 bw']/p[contains(text(), '円')]",
                    )

                    price = "Not found"
                    price_per_tsubo = "Not found"

                    for elem in price_elements:
                        text = elem.text
                        # Check for total price
                        if "万円" in text and price == "Not found":
                            price = text
                        # Check for price per tsubo
                        elif "坪単価" in text:
                            match = re.search(r"\d+(\.\d+)?万円", text)
                            if match:
                                price_per_tsubo = match.group()

                    # Get the size of the property
                    try:
                        size_element = listing.find_element(
                            By.CSS_SELECTOR, "div.fr p:nth-of-type(2)"
                        ).text
                        # Remove the prefix and replace m² or ㎡ with sqm
                        size = (
                            size_element.replace("土地／", "")
                            .replace("m<sup>2</sup>", "sqm")
                            .replace("㎡", "sqm")
                        )

                        size = re.sub(r"<[^>]+>", "", size)

                    except NoSuchElementException:
                        size = "Not Available"

                    # Building and floor coverage ratios
                    try:
                        # Find the element containing both ratios
                        ratios_element = listing.find_element(
                            By.XPATH,
                            ".//div[@class='fr w105 bw']/p[contains(text(), '建ぺい率・容積率')]",
                        )
                        ratios_text = ratios_element.text

                        # Extracting the ratios using split
                        _, ratios_combined = ratios_text.split("／")
                        (
                            building_coverage_ratio_value,
                            floor_area_ratio_value,
                        ) = ratios_combined.split("　")

                        # Formatting the ratios
                        building_coverage_ratio = f"{building_coverage_ratio_value}"
                        floor_area_ratio = f"{floor_area_ratio_value}"

                    except NoSuchElementException:
                        building_coverage_ratio = "Not Available"
                        floor_area_ratio = "Not Available"
                    except (
                        ValueError
                    ):  # In case the text format is unexpected and split fails
                        building_coverage_ratio = "Not Available"
                        floor_area_ratio = "Not Available"

                    transportation = listing.find_element(
                        By.CSS_SELECTOR, "p.mt5:nth-of-type(2)"
                    ).text

                    # Get high res image
                    try:
                        image_url = listing.find_element(
                            By.CSS_SELECTOR, ".fl.w90 img"
                        ).get_attribute("src")

                        # Use regex to replace &w=NNN&h=NNN with &w=1000&h=1000
                        modified_image_url = re.sub(
                            r"&w=\d+&h=\d+", "&w=500&h=500", image_url
                        )

                        # Use the modified_image_url as needed
                        image_url = modified_image_url

                    except NoSuchElementException:
                        logger.error("Image element not found.")
                        image_url = None
                    except Exception as e:
                        logger.error(f"Unexpected error when processing image URL: {e}")
                        image_url = None

                    property_url = listing.find_element(
                        By.CSS_SELECTOR, "p a"
                    ).get_attribute("href")

                    listing_details = {
                        "price": price,
                        "name": property_name,
                        "size": size,
                        "price_per_tsubo": price_per_tsubo,
                        "building_coverage_ratio": building_coverage_ratio,
                        "floor_area_ratio": floor_area_ratio,
                        "features": property_features,
                        "transportation": transportation,
                        "url": property_url,
                        "image_url": image_url,
                        "html_list_item": listing.get_attribute("outerHTML"),
                    }

                    all_listings.append(listing_details)

                except NoSuchElementException as e:
                    logger.error(f"Error extracting details for listing: {e}")

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


def signal_handler(sig, frame):
    logger.info("Signal received: shutting down...")
    sys.exit(0)


signal.signal(signal.SIGINT, signal_handler)
signal.signal(signal.SIGTERM, signal_handler)


def print_ascii_logo():
    blue_bold = "\x1b[34;1m"
    reset = "\033[0m"
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


def check_notification_settings(app_config: AppConfig):
    yellow = "\033[93m"
    reset = "\033[0m"
    if not app_config.enable_notifications or not app_config.notification_url:
        alert_message = f"""{yellow}
⚠️  Attention: Notifications are disabled or notification URL is not provided. ⚠️
                               Notifications will NOT be sent.                        
                {reset}"""
        print(alert_message, flush=True)


def main():
    logger = setup_logging()
    app_config = AppConfig()
    print_ascii_logo()
    logger.info("Starting home-hunter")
    check_notification_settings(app_config)

    hunter = SUUMOHunter(app_config=app_config)

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
            logger.info(
                f"Restarting after error. Waiting for {sleep_time} seconds before the next check..."
            )
            time.sleep(sleep_time)
        except KeyboardInterrupt:
            logger.warning("🛑 Home-hunter terminated by user.")
            hunter.close_driver()
            break


if __name__ == "__main__":
    main()
