
<img src="https://github.com/zaneriley/home-hunter/blob/main/logo.png?raw=true" alt="Home Hunter logo" width="500">

## Home Hunter

Home Hunter is a Python-based tool that automates the process of searching for and monitoring new home listings on the popular Japanese real estate website, SUUMO. It leverages Selenium for web scraping and Discord for notifications.

**Prerequisites**

* Python 3 ([https://www.python.org/](https://www.python.org/))
* Selenium WebDriver ([https://www.selenium.dev/documentation/webdriver/](https://www.selenium.dev/documentation/webdriver/))
* Chrome browser ([https://www.google.com/chrome/](https://www.google.com/chrome/))
* ChromeDriver ([https://chromedriver.chromium.org/](https://chromedriver.chromium.org/)) – Ensure compatibility with your Chrome version.
* Discord webhook ([https://support.discord.com/hc/en-us/articles/228383668-Intro-to-Webhooks](https://support.discord.com/hc/en-us/articles/228383668-Intro-to-Webhooks))

**Installation and Configuration**

1. **Install Docker and Docker Compose:** Follow the official installation instructions for your operating system:
  * **Docker:** https://docs.docker.com/get-docker/
  * **Docker Compose:** https://docs.docker.com/compose/install/

2. **Clone the repository:**
   ```bash
   git clone [https://github.com/your-username/home-hunter.git](https://github.com/your-username/home-hunter.git)
   cd home-hunter
    ```
    Configure Environment Variables:
3. **Add your SUUMO url in `websites.ini`**
    ```bash
    [SUUMO]
    target_url = https://suumo.jp/
    ```
4. **Set up environment variables**
   ```bash
    WEBDRIVER_PATH: The absolute path to your ChromeDriver executable.
    NOTIFICATION_URL: Your Discord webhook URL.
    DISCORD_ROLE_ID=Your Discord role ID for notifications
    ```
5. **Run the docker container:**
   ```bash
   docker-compose up --build
   ```

Check your discord channel and you should see a notification like so (the bot will be whatever your webhook is set at)

<img src="https://github.com/zaneriley/home-hunter/blob/main/example-image.png?raw=true" alt="Discord embed example" width="300">


### How it Works

1. Home Hunter loads your target SUUMO search results page.
2. It extracts details of each available listing, including price, size, address, and access information.
3. New listings are compared against a list of previously seen URLs to prevent duplicate notifications.
4. If a new listing is discovered:
    - Home Hunter constructs a Discord message embed with the listing's details.
    - The formatted message is sent to your configured Discord webhook.

License

Home Hunter is licensed under the GNU General Public License v3.0. See the LICENSE file for details.
