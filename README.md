# IPO GMP Alert System

A Python automation project that checks InvestorGain IPO Grey Market Premium (GMP) data and sends Telegram alerts for IPOs that are open for subscription and have a GMP percentage above a configurable threshold.

## Features

- Retrieves IPO data from InvestorGain.
- Handles several common date formats.
- Uses the displayed GMP percentage when available and can calculate it from GMP amount and issue price when necessary.
- Sends Telegram alerts.
- Stores local alert history to avoid sending the same IPO alert more than once per day.
- Runs once and exits, so it can be scheduled with Windows Task Scheduler.

## Requirements

- Python 3.10 or newer recommended
- Internet access
- A Telegram bot and your Telegram chat ID

## Install on Windows

1. Install Python from the official Python website and ensure Python is available in Command Prompt.
2. Download or clone this repository and open Command Prompt in the project folder.
3. Create a virtual environment:

```bat
python -m venv venv
```

4. Install dependencies:

```bat
venv\Scripts\python.exe -m pip install -r requirements.txt
```

5. Create your private credentials file:

```bat
copy .env.example .env
```

6. Open `.env` in a text editor and replace the sample values with your own Telegram bot token and chat ID. Do not share or upload `.env`.

7. Run the program:

```bat
venv\Scripts\python.exe ipo_alert.py
```

## Configuration

Change `THRESHOLD` near the top of `ipo_alert.py` to adjust the GMP percentage threshold. The current default is 20, and the code alerts only when the percentage is strictly greater than that value.

The program stores alert history in `ipo_alert_state.json` in the project directory. That file is local runtime data and is excluded from Git.

## Scheduling on Windows

Use Windows Task Scheduler to run `venv\Scripts\python.exe` with the argument `"C:\path\to\ipo_alert.py"`. Set the task's **Start in** field to the project folder. The computer needs internet access when the task runs.

## Data and limitations

The program depends on InvestorGain's publicly accessible page and table structure. If the website changes, the parser may need updating. IPO GMP is unofficial market information and is not a reliable guarantee of listing performance.

## Security

Credentials are loaded from `.env` using `python-dotenv`. The `.env` file is excluded by `.gitignore`; only `.env.example`, containing placeholders, should be published. Never commit real bot tokens or chat IDs. If a token has ever been exposed publicly, revoke it through Telegram's BotFather.

## Disclaimer

For educational and informational purposes only. This project is not investment advice and does not guarantee IPO listing gains.
