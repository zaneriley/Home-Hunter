## Home Hunter

Home Hunter is a Python-based tool that automates the process of searching for and monitoring new home listings on the popular Japanese real estate website, SUUMO. It leverages Selenium for web scraping, Discord for notifications, and offers these core features:

* **Targeted Search:** Efficiently search for homes on SUUMO based on your specific criteria.
* **Real-time Notifications:** Receive immediate Discord alerts when new listings match your search parameters.
* **Duplicate Filtering:** Avoid redundant notifications by tracking previously seen listings.

**Prerequisites**

* Python 3 ([https://www.python.org/](https://www.python.org/))
* Selenium WebDriver ([https://www.selenium.dev/documentation/webdriver/](https://www.selenium.dev/documentation/webdriver/))
* Chrome browser ([https://www.google.com/chrome/](https://www.google.com/chrome/))
* ChromeDriver ([https://chromedriver.chromium.org/](https://chromedriver.chromium.org/)) – Ensure compatibility with your Chrome version.
* Discord webhook ([https://support.discord.com/hc/en-us/articles/228383668-Intro-to-Webhooks](https://support.discord.com/hc/en-us/articles/228383668-Intro-to-Webhooks))

**Installation and Configuration**

1. **Clone the repository:**
   ```bash
   git clone [https://github.com/your-username/home-hunter.git](https://github.com/your-username/home-hunter.git)
   cd home-hunter
    ```
2. **Set up environment variables:**
   ```bash
    WEBDRIVER_PATH: The absolute path to your ChromeDriver executable.
    NOTIFICATION_URL: Your Discord webhook URL.
    TARGET_URL: The specific SUUMO URL for your desired search area.
    ```
3. **Run the docker container:**
   ```bash
   docker-compose up --build
   ```

Check your discord channel and you should see a notification like so (the bot will be whatever your webhook is set at)
![Discord embed example](https://github.com/zaneriley/home-hunter/example-image.png)

### How it Works

1. Home Hunter loads your target SUUMO search results page.
2. It extracts details of each available listing, including price, size, address, and access information.
3. New listings are compared against a list of previously seen URLs to prevent duplicate notifications.
4. If a new listing is discovered:
    - Home Hunter constructs a Discord message embed with the listing's details.
    - The formatted message is sent to your configured Discord webhook.

License

Home Hunter is licensed under the GNU General Public License v3.0. See the LICENSE file for details.
