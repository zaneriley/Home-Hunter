
from selenium import webdriver
from selenium.common.exceptions import NoSuchElementException, TimeoutException
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service as ChromeService
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.common.action_chains import ActionChains
from configparser import ConfigParser, SectionProxy
from typing import Dict, List, Optional, Union
from abc import ABC, abstractmethod

import logging
import os
import configparser
import requests
import json
import time
import traceback
import importlib


logger = logging.getLogger(__name__)
logger.setLevel(logging.DEBUG)  # Customize level as needed

enable_notifications: bool = os.getenv("ENABLE_NOTIFICATIONS", "false").lower() in ("true", "1", "t")
notification_url: Optional[str] = os.getenv("NOTIFICATION_URL")
webdriver_path: str = os.getenv("WEBDRIVER_PATH", "/usr/bin/chromedriver")

config = configparser.ConfigParser(interpolation=None)
config_path = 'websites.ini'
if config.read(config_path):
    logger.info(f"Configuration loaded from {config_path}")
else:
    logger.error(f"Failed to load configuration from {config_path}. Please check the file path and try again.")
    exit(1) 

# Set up logging
class IgnoreBrowserLogsFilter(logging.Filter):
    def filter(self, record):
        return 'Third-party cookie will be blocked' not in record.getMessage()

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
        chrome_options.add_argument('--log-level=off') # Suppress browser console logs
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

    def __init__(self, config: Union[SectionProxy, Dict[str, Union[str, bool, int]]]) -> None:
        """
        Initialize the hunter with a configuration section from configparser or a dictionary.
        """
        self.config = config
        self.seen_listings: List[str] = []
        self.new_listings: List[str] = [] # For notification summaries
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

    # Load and save seen listings to a file
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
        with open(filepath, 'w', encoding='utf-8') as file:
            file.write(html_content)
        logger.info(f"HTML content saved to {filepath}")

    @property
    def seen_listings_file(self):
        """
        Returns the file path for saving seen listings, incorporating the storage directory.
        """
        self.ensure_storage_directory_exists()
        return os.path.join(self.storage_directory, 'seen_listings.json')
    
    def load_seen_listings(self):
        """Load seen listings from a file."""
        try:
            with open(self.seen_listings_file, 'r') as file:
                self.seen_listings = json.load(file)
        except FileNotFoundError:
            self.seen_listings = []

    def save_seen_listings(self):
        """Save seen listings to a file."""
        with open(self.seen_listings_file, 'w') as file:
            json.dump(self.seen_listings, file)

    # Check if a listing has already been seen
    def has_listing_been_seen(self, listing_url):
        """Check if a listing has already been seen."""
        return listing_url in self.seen_listings

    def mark_listing_seen(self, listing_url):
        """Mark a listing as seen."""
        if listing_url not in self.seen_listings:
            self.seen_listings.append(listing_url)
            self.save_seen_listings()
            # Check if it's a new listing and add it to new_listings
            if listing_url not in self.new_listings:
                self.new_listings.append(listing_url)

    def track_new_listing(self, listing_details):
        """Track new listings if not already seen."""
        if not self.has_listing_been_seen(listing_details['url']):
            self.new_listings.append(listing_details)
            self.mark_listing_seen(listing_details['url'])
            logger.info("Tracking new listing: %s", listing_details['url'])

    @abstractmethod
    def format_listing_message(self, listing_details):
        """
        Generate a custom embed payload for a listing.
        
        :param listing_details: A dictionary containing details of the listing.
        :return: A dictionary representing the embed payload.
        """
        pass

    def announce_new_listings(self):
        """Announce new listings based on their count."""
        total_new_listings = len(self.new_listings)
        logger.info("Announcing new listings, count: %d", len(self.new_listings))

        if total_new_listings == 0:
            return  # No new listings to announce

        if total_new_listings < 3:
            # Send individual notifications with custom embeds for each listing
            for listing_details in self.new_listings:
                embed_payload = self.format_listing_message(listing_details)
                self.send_notification(embed_payload)
        else:
            # For three or more listings, prepare a summary notification
            # and include embeds for the first three listings
            content = f"Found {total_new_listings} new listings. Check them out here: [View Listings](YourListingsPageURL)"
            embeds = [self.format_listing_message(listing_details) for listing_details in self.new_listings[:3]]
            embed_payload = {"content": content, "embeds": embeds}
            logger.info(f"Sending notification: {embed_payload}")
            self.send_notification(embed_payload)

        self.new_listings = []

    def send_notification(self, embed_payload):
        """
        Send a notification about a new listing.
        """
        enable_notifications = self.config.get("enable_notifications", False)
        notification_url = self.config.get("notification_url", os.getenv("NOTIFICATION_URL"))

        if enable_notifications and notification_url:
            logger.info("Attempting to send notification. Payload: %s", embed_payload)
            try:
                response = requests.post(notification_url, json=embed_payload, timeout=10)
                response.raise_for_status()  # Raises an exception for 4XX/5XX errors
            except requests.exceptions.HTTPError as http_err:
                logger.error(f"HTTP error occurred: {http_err}; Response body: {response.text}")
            except requests.exceptions.ConnectionError as conn_err:
                logger.error(f"Connection error occurred: {conn_err}")
            except requests.exceptions.Timeout as timeout_err:
                logger.error(f"Timeout error occurred: {timeout_err}")
            except requests.exceptions.RequestException as req_err:
                logger.error(f"Request exception occurred: {req_err}")
            else:
                logger.info(f"Successfully sent notification to Discord; Status Code: {response.status_code}")
        else:
            pass

class SUUMOHunter(AbstractHunter, WebDriverBase):
    def __init__(self):
        super().__init__(config['SUUMO'])
        WebDriverBase.__init__(self)

    def check_for_new_listings(self):
        logger.debug(f"Accessing URL: {self.config['target_url']}")
        self.driver.get(self.config["target_url"])
        self.save_screenshot('screenshot_initial_load.png')
        page_source = self.driver.page_source
        self.save_html_content(page_source, 'page_source_initial_load.html')

        try:
            zoom_out_button = WebDriverWait(self.driver, self.config["dynamic_content_timeout"]).until(
                EC.element_to_be_clickable((By.XPATH, "//button[@aria-label='Zoom out']"))
            )
            zoom_out_button.click()
            logger.info("Clicked zoom out once.")
            self.save_screenshot('screenshot_zoom_out_click1.png')

        except TimeoutException:
            logger.error("Zoom out button not found or not clickable within timeout period.")

        try:
            WebDriverWait(self.driver, self.config["dynamic_content_timeout"]).until(
                EC.element_to_be_clickable((By.ID, "listViewButton"))
            )
            logger.info("List view button is clickable.")

   
            list_view_button = self.driver.find_element(By.ID, "listViewButton")
            ActionChains(self.driver).click(list_view_button).perform()
            logger.info("Clicked on list view button.")

            WebDriverWait(self.driver, self.config["dynamic_content_timeout"]).until(
                lambda d: len(d.find_elements(By.CSS_SELECTOR, "ul.listView.bukkenList.solid > li")) > 0
            )
            logger.info("Listings have successfully loaded.")
            self.save_screenshot('screenshot_after_button_click.png')  
            self.save_html_content(self.driver.page_source, 'page_source_after_button_click.html')

            logger.info("Dynamic content loaded")

            # Find all listings
            listings = self.driver.find_elements(By.CSS_SELECTOR, "li")  
            logger.info("Found %d listings", len(listings))

            for listing in listings:
                logger.info("Processing listing %s", listing.text)
                try:
                    price = listing.find_element(By.CSS_SELECTOR, ".price").text
                    size = listing.find_element(By.CSS_SELECTOR, ".exclusive").text
                    address = listing.find_element(By.CSS_SELECTOR, ".address").text
                    access = listing.find_element(By.CSS_SELECTOR, ".ensen").text
                    url = listing.find_element(By.CSS_SELECTOR, ".innerInfo a").get_attribute('href')
                    image_url = listing.find_element(By.CSS_SELECTOR, ".imgWrap img").get_attribute('src')

                    listing_details = {
                        "price": price,
                        "size": size,
                        "address": address,
                        "access": access,
                        "url": url,
                        "image_url": image_url
                    }
                    
                    if not self.has_listing_been_seen(listing_details['url']):
                        embed_payload = self.format_listing_message(listing_details)
                        self.mark_listing_seen(listing_details['url'])
                        self.track_new_listing(listing_details)
                        

                    else:
                        logger.info(f"Listing already seen: {price}")
                except NoSuchElementException as e:
                    logger.error(f"Error extracting details for listing: {e}")
            self.announce_new_listings()
        except TimeoutException as e:
            logger.error(f"Timeout waiting for content: {e}")
        
        


        finally:
            for entry in self.driver.get_log('browser'):
                logger.info(entry)
            self.close_driver()
            logger.info("Driver closed")
    
    def has_listing_been_seen(self, listing_url):
        # Check if a listing has already been seen
        return listing_url in self.seen_listings
    
    def mark_listing_seen(self, listing_url):
        # Mark a listing as seen
        if listing_url not in self.seen_listings:
            self.seen_listings.append(listing_url)
            self.save_seen_listings()

    def format_listing_message(self, listing_details):
        embed_payload = {
            "content": None,
            "embeds": [
                {
                    "title": listing_details["price"],
                    "description": listing_details["size"],
                    "url": listing_details["url"],
                    "color": 4937567,
                    "fields": [
                        {"name": "Address", "value": listing_details["address"], "inline": True},
                        {"name": "Access", "value": listing_details["access"], "inline": True}
                    ],
                    "author": {
                        "name": "SUUMO",
                        "url": listing_details["url"],
                        "icon_url": "https://cdn3.emoji.gg/emojis/9666-link.png"
                    },
                    "image": {"url": listing_details["image_url"]}
                }
            ]
        }
        return embed_payload
 
if __name__ == "__main__":
    # ANSI color codes
    blue_bold = '\x1b[34;1m'
    reset = '\033[0m'
    yellow = '\033[93m'
    green = '\033[92m'
    red = '\033[91m'
    ascii_logo = blue_bold + """
ooooo   ooooo                                       ooooo   ooooo                             .                      
`888'   `888'                                       `888'   `888'                           .o8                      
 888     888   .ooooo.  ooo. .oo.  .oo.    .ooooo.   888     888  oooo  oooo  ooo. .oo.   .o888oo  .ooooo.  oooo d8b 
 888ooooo888  d88' `88b `888P"Y88bP"Y88b  d88' `88b  888ooooo888  `888  `888  `888P"Y88b    888   d88' `88b `888""8P 
 888     888  888   888  888   888   888  888ooo888  888     888   888   888   888   888    888   888ooo888  888     
 888     888  888   888  888   888   888  888    .o  888     888   888   888   888   888    888 . 888    .o  888     
o888o   o888o `Y8bod8P' o888o o888o o888o `Y8bod8P' o888o   o888o  `V88V"V8P' o888o o888o   "888" `Y8bod8P' d888b                                                                                                                                                                                                                                                                                      
    """ + reset
    print(ascii_logo, flush=True)
    logger.info("Starting home-hunter")

    # Check if notifications are enabled and if the notification URL is provided
    enable_notifications = os.getenv("ENABLE_NOTIFICATIONS", "false").lower() in ("true", "1", "t")
    notification_url = os.getenv("NOTIFICATION_URL")
    if not enable_notifications or not notification_url:
        # Notification disabled message
        alert_message = f"""{yellow}
            ⚠️  Attention: Notifications are disabled or notification URL is not provided. ⚠️
            ⚠️                      Notifications will NOT be sent.                        ⚠️
                        {reset}"""
        print(alert_message, flush=True)
    
    hunter = SUUMOHunter()

    try:
        while True:
            hunter.restart_driver() 
            hunter.check_for_new_listings()
            logger.info("Waiting for 5 minutes before the next check...")
            time.sleep(300)  

    except Exception as e:
        error_message = f"{red}❗ Error processing SUUMOHunter: {e}{reset}"
        print(error_message, flush=True)
        traceback.print_exc()
    except KeyboardInterrupt:
        user_termination_message = f"{yellow}🛑 Home-hunter terminated by user.{reset}"
        print(user_termination_message, flush=True)
    finally:
        hunter.close_driver()
        completion_message = f"{green}✅ Home-hunter finished.{reset}"
        print(completion_message, flush=True)