
import os
import requests
import pandas as pd
import re
import json
from io import StringIO
from pathlib import Path
from datetime import datetime, date, timedelta
from dotenv import load_dotenv

# =========================================================
# 1. CONFIGURATION
# =========================================================

URL = "https://www.investorgain.com/report/ipo-gmp-live/331/"

# Alert when GMP percentage is ABOVE this value
THRESHOLD = 20

# TELEGRAM SETTINGS: loaded from a private .env file
PROJECT_DIR = Path(__file__).resolve().parent
load_dotenv(PROJECT_DIR / ".env")

BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")

HEADERS = {
    "User-Agent": "Mozilla/5.0"
}

# Stores sent alerts to prevent duplicate notifications
STATE_FILE = PROJECT_DIR / "ipo_alert_state.json"


# =========================================================
# 2. SEND TELEGRAM MESSAGE
# =========================================================

def send_telegram(message):

    if (
        not BOT_TOKEN
        or not CHAT_ID
        or BOT_TOKEN == "PASTE_YOUR_BOT_TOKEN_HERE"
        or CHAT_ID == "PASTE_YOUR_CHAT_ID_HERE"
    ):
        print("ERROR: Telegram token or Chat ID is missing.")
        return False

    telegram_url = (
        f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"
    )

    try:
        response = requests.post(
            telegram_url,
            data={
                "chat_id": CHAT_ID,
                "text": message
            },
            timeout=20
        )

        response.raise_for_status()
        result = response.json()

        if result.get("ok"):
            print("Telegram notification sent successfully.")
            return True

        print("Telegram API error:", result)
        return False

    except requests.RequestException as error:
        print("Telegram notification failed:", error)
        return False


# =========================================================
# 3. DUPLICATE ALERT PREVENTION
# =========================================================

def load_alert_state():

    try:
        with open(STATE_FILE, "r", encoding="utf-8") as file:
            return json.load(file)

    except (FileNotFoundError, json.JSONDecodeError):
        return {}


def save_alert_state(state):

    with open(STATE_FILE, "w", encoding="utf-8") as file:
        json.dump(state, file, indent=4)


# =========================================================
# 4. DATE HANDLING
# =========================================================

def parse_date(value, reference_date):

    text = str(value).strip()

    if not text or text.lower() in ("nan", "none", "-"):
        return None

    patterns = [
        r"\b\d{1,2}[-/][A-Za-z]{3,9}[-/]\d{4}\b",
        r"\b\d{4}-\d{1,2}-\d{1,2}\b",
        r"\b\d{1,2}[-/][A-Za-z]{3,9}\b",
        r"\b\d{1,2}/\d{1,2}/\d{4}\b",
        r"\b\d{1,2}/\d{1,2}\b",
    ]

    date_text = None

    for pattern in patterns:
        match = re.search(pattern, text)

        if match:
            date_text = match.group(0)
            break

    if date_text is None:
        return None

    formats = [
        "%d-%b-%Y",
        "%d-%B-%Y",
        "%d/%b/%Y",
        "%d/%B/%Y",
        "%Y-%m-%d",
        "%d/%m/%Y",
        "%d-%b",
        "%d-%B",
        "%d/%b",
        "%d/%B",
        "%d/%m",
    ]

    for fmt in formats:
        try:

            if "%Y" in fmt:
                return datetime.strptime(date_text, fmt).date()

            parsed = datetime.strptime(
                date_text + "-" + str(reference_date.year),
                fmt + "-%Y"
            ).date()

            # Handle dates around the end of a calendar year.
            if parsed < reference_date - timedelta(days=180):
                parsed = parsed.replace(
                    year=reference_date.year + 1
                )

            elif parsed > reference_date + timedelta(days=180):
                parsed = parsed.replace(
                    year=reference_date.year - 1
                )

            return parsed

        except ValueError:
            continue

    return None


# =========================================================
# 5. COLUMN HANDLING
# =========================================================

def normalize_column(value):

    return re.sub(r"[^a-z0-9]", "", str(value).lower())


def find_column(columns, keywords):

    normalized = {
        column: normalize_column(column)
        for column in columns
    }

    # First try exact matches.
    for keyword in keywords:

        target = normalize_column(keyword)

        for column, name in normalized.items():

            if name == target:
                return column

    # Then try headings that begin with the keyword.
    for keyword in keywords:

        target = normalize_column(keyword)

        for column, name in normalized.items():

            if name.startswith(target):
                return column

    return None


# =========================================================
# 6. GMP PERCENTAGE CALCULATION
# =========================================================

def extract_gmp(value, issue_price=None):

    text = str(value).strip()

    if not text or text.lower() in ("nan", "none", "-"):
        return None, None, text

    amount_match = re.search(
        r"[-+]?\s*₹?\s*([\d,]+(?:\.\d+)?)",
        text
    )

    percent_match = re.search(
        r"\(\s*([-+]?\d+(?:\.\d+)?)\s*%\s*\)",
        text
    )

    gmp_amount = None
    gmp_percent = None

    if amount_match:

        try:
            gmp_amount = float(
                amount_match.group(1).replace(",", "")
            )

        except ValueError:
            pass

    # Prefer the percentage displayed by the website.
    if percent_match:

        try:
            gmp_percent = float(percent_match.group(1))

        except ValueError:
            pass

    # If the website does not display a percentage,
    # calculate it from GMP amount and issue price.
    if gmp_percent is None and gmp_amount is not None:

        try:
            price = float(
                str(issue_price)
                .replace(",", "")
                .replace("₹", "")
                .strip()
            )

            if price > 0:
                gmp_percent = (gmp_amount / price) * 100

        except (ValueError, TypeError):
            pass

    return gmp_amount, gmp_percent, text


# =========================================================
# 7. DOWNLOAD AND FILTER IPO DATA
# =========================================================

def check_ipos():

    print("Downloading IPO data...")

    response = requests.get(
        URL,
        headers=HEADERS,
        timeout=30
    )

    response.raise_for_status()

    tables = pd.read_html(StringIO(response.text))

    if not tables:
        raise ValueError("No tables found on the IPO webpage.")

    df = None
    columns_found = None

    # Identify the table containing the IPO information.
    for table in tables:

        if isinstance(table.columns, pd.MultiIndex):

            table.columns = [
                " ".join(
                    str(part)
                    for part in column
                    if "Unnamed" not in str(part)
                ).strip()
                for column in table.columns
            ]

        else:

            table.columns = [
                str(column).strip()
                for column in table.columns
            ]

        columns = table.columns

        name_col = find_column(
            columns,
            ["Name", "IPO Name", "Company"]
        )

        gmp_col = find_column(
            columns,
            ["GMP", "Grey Market Premium"]
        )

        open_col = find_column(
            columns,
            ["Open", "Open Date"]
        )

        close_col = find_column(
            columns,
            ["Close", "Close Date"]
        )

        price_col = find_column(
            columns,
            ["Price (₹)", "Issue Price", "Price"]
        )

        if all([name_col, gmp_col, open_col, close_col]):

            df = table

            columns_found = (
                name_col,
                gmp_col,
                open_col,
                close_col,
                price_col
            )

            break

    if df is None:

        raise ValueError(
            "Could not identify the required IPO columns. "
            "The website layout may have changed."
        )

    (
        name_col,
        gmp_col,
        open_col,
        close_col,
        price_col
    ) = columns_found

    print("IPO table found successfully.")
    print("Columns:", list(df.columns))

    today = date.today()

    alerts = []
    skipped_dates = []

    for _, row in df.iterrows():

        name = str(row[name_col]).strip()

        # Skip the repeated header row if present in the data.
        if name.lower() in ("name", "ipo name", "company"):
            continue

        if not name or name.lower() == "nan":
            continue

        open_raw = row[open_col]
        close_raw = row[close_col]

        open_date = parse_date(open_raw, today)
        close_date = parse_date(close_raw, today)

        if open_date is None or close_date is None:

            skipped_dates.append(
                f"{name}: Open={open_raw}, Close={close_raw}"
            )

            continue

        # Include only IPOs open for subscription today.
        if not (open_date <= today <= close_date):
            continue

        issue_price = (
            row[price_col]
            if price_col is not None
            else None
        )

        gmp_amount, gmp_percent, gmp_text = extract_gmp(
            row[gmp_col],
            issue_price
        )

        if gmp_percent is None:
            continue

        # Strictly greater than the configured threshold.
        if gmp_percent > THRESHOLD:

            alerts.append({
                "name": name,
                "gmp": gmp_amount,
                "gmp_text": gmp_text,
                "percent": gmp_percent,
                "price": issue_price,
                "open": open_date,
                "close": close_date
            })

    return alerts, skipped_dates


# =========================================================
# 8. RUN ONE CHECK AND SEND ALERTS
# =========================================================

def run_check():

    print("\n" + "=" * 60)

    print(
        "IPO GMP CHECK:",
        datetime.now().strftime("%d-%m-%Y %H:%M:%S")
    )

    print("=" * 60)

    try:

        alerts, skipped_dates = check_ipos()

        today_string = date.today().isoformat()

        state = load_alert_state()

        # Retain today's history only.
        state = {
            key: value
            for key, value in state.items()
            if key.startswith(today_string + "|")
        }

        if not alerts:

            print(
                f"No open IPO with GMP above {THRESHOLD}% found."
            )

        else:

            print(
                f"\n{len(alerts)} OPEN IPO(S) "
                f"WITH GMP ABOVE {THRESHOLD}%:"
            )

        for ipo in alerts:

            print("\n" + "-" * 45)
            print("ALERT:", ipo["name"])
            print("GMP:", ipo["gmp_text"])
            print("GMP percentage:", f'{ipo["percent"]:.2f}%')
            print("Issue price:", ipo["price"])

            print(
                "Subscription dates:",
                f'{ipo["open"]} to {ipo["close"]}'
            )

            # Send each IPO alert only once per day.
            alert_key = f'{today_string}|{ipo["name"]}'

            if alert_key in state:

                print("Telegram alert already sent today.")
                continue

            message = (
                "🚨 IPO GMP ALERT\n\n"
                f'📌 IPO: {ipo["name"]}\n'
                f'💰 GMP: {ipo["gmp_text"]}\n'
                f'📈 GMP Percentage: {ipo["percent"]:.2f}%\n'
                f'🏷️ Issue Price: ₹{ipo["price"]}\n'
                f'📅 Subscription: {ipo["open"]} to {ipo["close"]}\n\n'
                "⚠️ GMP is unofficial and does not guarantee "
                "listing gains."
            )

            if send_telegram(message):

                state[alert_key] = datetime.now().isoformat()
                save_alert_state(state)

        if skipped_dates:

            print(
                "\nWARNING: These IPO dates could not "
                "be interpreted:"
            )

            for item in skipped_dates:
                print(" -", item)

    except Exception as error:

        print("\nIPO CHECK FAILED:", error)

        # Report a failure to Telegram, if possible.
        send_telegram(
            "⚠️ IPO GMP checker failed.\n\n"
            f"Error: {str(error)[:500]}"
        )


# =========================================================
# 9. RUN ONCE AND EXIT
# =========================================================

if __name__ == "__main__":

    print("\nIPO GMP ALERT CHECK STARTED.")
    print("GMP threshold:", THRESHOLD, "%")
    if not BOT_TOKEN or not CHAT_ID:
        raise SystemExit(
            "Telegram credentials are missing. Create a .env file "
            "using .env.example as a guide."
        )

    print("Telegram credentials loaded.")
    print("Checking IPOs now...\n")

    run_check()

    print("\nIPO check finished. Program exiting.")
