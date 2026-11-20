## How to Download & Configure Your Own MySQL Database

### Step 1: Clone the Repository & Install Dependencies
```bash
git clone https://github.com
cd PingGuard-Wi-Fi-Fault-Congestion-Diagnostics-Logger
pip install flask mysql-connector-python python-dotenv matplotlib
```

### Step 2: Set Your MySQL Host, User & Password
1. Ensure **MySQL Server** is installed and running on your machine.
2. In the project root folder, find the `.env.example` file, make a copy of it, and rename the copy to **`.env`**.
3. Open **`.env`** in any text editor and enter your own MySQL credentials:
   ```env
   DB_HOST=localhost
   DB_PORT=3306
   DB_USER=root
   DB_PASSWORD=enter_your_own_mysql_password
   DB_NAME=my_python_app
   ```
   *(You do not need to manually create the database or tables—PingGuard automatically creates `DB_NAME` and the `pingguard_logs` table on startup).*

### Step 3: Run PingGuard
```bash
python wifi_logger.py
```
* Use the **Interval** dropdown to adjust polling speed.
* Click **Open Info Tab** to inspect logged sessions by date in your browser.
* Click **Stop & Save DB** (or type `end` in the terminal) to shut down cleanly.
