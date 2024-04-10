
<img src="https://github.com/zaneriley/home-hunter/blob/main/logo.png?raw=true" alt="Home Hunter logo" width="500">

## Home Hunter

Home Hunter is a Python-based tool that automates the process of searching for and monitoring new home listings on the popular Japanese real estate website, SUUMO. It leverages Selenium for web scraping and Discord for notifications.


**Installation and Configuration**

1. **Install Docker and Docker Compose:** Follow the official installation instructions for your operating system:
  * **Docker:** https://docs.docker.com/get-docker/
  * **Docker Compose:** https://docs.docker.com/compose/install/
  
  Docker is necessary because it allows us to run the application in a container, which is isolated from the host system and other containers. This means that the application will not interfere with other applications or the host system, and it will be easier to manage and update.

2. **Clone the repository:**
   ```bash
   git clone https://github.com/zaneriley/home-hunter.git
   cd home-hunter
    ```
    Now you need to configure what SUUMO listings you want to monitor, and where to send notifications on Discord.

3. **Add your SUUMO url in `websites.ini`**
    ```bash
    [SUUMO]
    target_url = https://suumo.jp/...
    ```
    Your URL needs to look like: 
    ```
    https://suumo.jp/jj/bukken/ichiran/JJ010FJ001/?ar=030&bknlistmodeflg=3&bs=030&initIdo=128505983&initKeido=502665119.5&pc=20&pj=1&po=0&ta=13&sc=13120
    ```
    **TIP:** You can customize your suumo search using the website's filters, and it will be reflected in the notifications. Really useful if you only want results near your work, a specific train line, etc.

4. **Set up other environment variables**. Open up `docker-compose.yml` and update the following variables:
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
