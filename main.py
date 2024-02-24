import logging
from selenium import webdriver
from selenium.common.exceptions import NoSuchElementException, TimeoutException
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service as ChromeService
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.common.action_chains import ActionChains
import os
import shutil
import configparser
import requests
import json
from abc import ABC, abstractmethod


# Set up logging
logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)  # Customize level as needed

handler = logging.StreamHandler()
logger.addHandler(handler)

config = {
    "webdriver_path": "/usr/bin/chromedriver",
    "target_url": "https://suumo.jp/sp/tochi/tokyo/sc_113/map.html?kamax=8000&tmenmin=100&et=15&kjoken=2&sort=1&sjoken%5B0%5D=004&lt=0.6220203181688256&lg=2.4378622780639763&km=0",
    "listing_selector": "section#bukkenListAll .catchTitle",
    "title_selector": ".titleWrap",
    "dynamic_content_id": "bukkenListAll",  # element we are waiting to load before scraping
    "dynamic_content_timeout": 10,  # seconds
    "notification_url": "https://discord.com/api/webhooks/1210575135837392926/p7Qu1gQsvd-7JA0bA_ItY4A_xUFdaTGGyp9DxHbnhnRajNuRGboyCPwtN70Lm0tX68aI",
}

class WebDriverBase:
    def __init__(self, driver_path):
        self.driver_path = driver_path
        self.driver = self._init_driver()

    def _init_driver(self):
        chrome_options = Options()
        chrome_options.add_argument("--headless")
        chrome_options.add_argument("--no-sandbox")
        chrome_options.add_argument("--disable-dev-shm-usage")
        chrome_options.add_argument("--disable-gpu")
        chrome_options.add_argument("--window-size=1920x1080")
        chrome_options.set_capability('goog:loggingPrefs', {'browser': 'ALL'})  # Example capability setting

        service = ChromeService(executable_path=self.driver_path)
        driver = webdriver.Chrome(service=service, options=chrome_options) 

        return driver

    def close_driver(self):
        self.driver.quit()

class HomeHunter(WebDriverBase):
    def __init__(self, config):
        super().__init__(config["webdriver_path"])
        self.config = config
        self.seen_listings_file = "seen_listings.json"
        self.load_seen_listings()

    def load_seen_listings(self):
        try:
            with open(self.seen_listings_file, "r") as f:
                self.seen_listings = json.load(f)
        except FileNotFoundError:
            self.seen_listings = []  # Start with an empty list if no file exists

    def save_seen_listings(self):
        with open(self.seen_listings_file, "w") as f:
            json.dump(self.seen_listings, f)

    def is_listing_seen(self, listing_url):
        return listing_url in self.seen_listings

    def mark_listing_seen(self, listing_url):
        self.seen_listings.append(listing_url)
        self.save_seen_listings()

    def send_notification(self, embed_payload):
        try:
            response = requests.post(self.config["notification_url"], json=embed_payload)
            if 200 <= response.status_code < 300:
                logger.info("Successfully sent notification to Discord")
            else:
                logger.error(f"Failed to send notification to Discord. Status Code: {response.status_code}")
        except Exception as e:
            logger.error(f"Network or webhook error: {e}")

    def format_listing_message(self, listing_details):
        # Construct the Discord embed payload using listing_details
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

    def check_for_new_listings(self):
        self.driver.get(self.config["target_url"])
        logger.info("Opened target listings page")
        self.driver.save_screenshot('screenshot_initial_load.png')  # Screenshot initial page load
        page_source = self.driver.page_source
        with open('page_source_initial_load.html', 'w') as f:
            f.write(page_source)

        try:
            zoom_out_button = WebDriverWait(self.driver, self.config["dynamic_content_timeout"]).until(
                EC.element_to_be_clickable((By.XPATH, "//button[@aria-label='Zoom out']"))
            )
            zoom_out_button.click()
            logger.info("Clicked zoom out once.")
            self.driver.save_screenshot('screenshot_zoom_out_click1.png')  # Screenshot initial page load

            zoom_out_button.click()
            logger.info("Clicked zoom out twice.")
            self.driver.save_screenshot('screenshot_zoom_out_click2.png')  # Screenshot initial page load

        except TimeoutException:
            logger.error("Zoom out button not found or not clickable within timeout period.")

        try:
            # Wait for the button to be clickable
            WebDriverWait(self.driver, self.config["dynamic_content_timeout"]).until(
                EC.element_to_be_clickable((By.ID, "listViewButton"))
            )
            logger.info("List view button is clickable.")

            # Click the list view button
            list_view_button = self.driver.find_element(By.ID, "listViewButton")
            ActionChains(self.driver).click(list_view_button).perform()
            logger.info("Clicked on list view button.")
            # Wait for the listings to load by checking for at least one child in the <ul> container
            WebDriverWait(self.driver, self.config["dynamic_content_timeout"]).until(
                lambda d: len(d.find_elements(By.CSS_SELECTOR, "ul.listView.bukkenList.solid > li")) > 0
            )
            logger.info("Listings have successfully loaded.")
            self.driver.save_screenshot('screenshot_after_button_click.png')  # Screenshot after dynamic content loads
            with open('page_source_after_button_click.html', 'w') as f:
                f.write(self.driver.page_source)

            logger.info("Dynamic content loaded")

            # Find all listings
            listings = self.driver.find_elements(By.CSS_SELECTOR, "li")  # Adjusted to select the entire list item
            logger.info("Found %d listings", len(listings))
            seen_listings = []  # Pretend this is your database

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
                    
                    if not self.is_listing_seen(listing_details['url']):
                        embed_payload = self.format_listing_message(listing_details)
                        self.send_notification(embed_payload)
                        self.mark_listing_seen(listing_details['url'])
                    else:
                        logger.info(f"Listing already seen: {price}")
                except NoSuchElementException as e:
                    logger.error(f"Error extracting details for listing: {e}")
        except TimeoutException as e:
            logger.error(f"Timeout waiting for content: {e}")

        finally:
            # Log browser console outputs
            for entry in self.driver.get_log('browser'):
                logger.info(entry)
            self.close_driver()
            logger.info("Driver closed")

    def send_notification(self, embed_payload):
        try:
            response = requests.post(self.config["notification_url"], json=embed_payload, timeout=10)
            response.raise_for_status()  # Raises an exception for 4XX/5XX errors
        except requests.exceptions.HTTPError as http_err:
            # Log HTTP error and response body for more context
            logger.error(f"HTTP error occurred: {http_err}; Response body: {response.text}")
        except requests.exceptions.ConnectionError as conn_err:
            logger.error(f"Connection error occurred: {conn_err}")
        except requests.exceptions.Timeout as timeout_err:
            logger.error(f"Timeout error occurred: {timeout_err}")
        except requests.exceptions.RequestException as req_err:
            logger.error(f"Request exception occurred: {req_err}")
        else:
            # Success logging
            logger.info(f"Successfully sent notification to Discord; Status Code: {response.status_code}")


if __name__ == "__main__":
    logger.info("Starting home-hunter")
    hunter = HomeHunter(config)
    hunter.check_for_new_listings()
    logger.info("Home-hunter finished")
