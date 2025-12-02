
from flask import Flask, render_template, request, redirect
import sqlite3
import yfinance as yf
from datetime import datetime, date

app = Flask(__name__)

DB_NAME = "portfolio.db"

def init_db():
    conn = sqlite3.connect(DB_NAME)
    c = conn.cursor()
    c.execute("""
        CREATE TABLE IF NOT EXISTS stocks (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            symbol TEXT UNIQUE,
            quantity INTEGER,
            buy_price REAL,
            buy_date TEXT,
            notes TEXT
        )
    """)
    c.execute("""
        CREATE TABLE IF NOT EXISTS watchlist (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            symbol TEXT UNIQUE
        )
    """)
    c.execute("""
        CREATE TABLE IF NOT EXISTS alerts (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            symbol TEXT,
            target REAL
        )
    """)
    conn.commit()
    conn.close()

init_db()

TRENDING = ["TSLA", "AAPL", "GOOGL", "META", "NVDA", "MSFT", "AMZN", "NFLX"]

def get_live_price(symbol: str):
    try:
        data = yf.Ticker(symbol).history(period="1d")
        if data.empty:
            return None
        return float(data["Close"][0])
    except Exception:
        return None

def parse_date(d: str):
    try:
        return datetime.strptime(d, "%Y-%m-%d").date()
    except Exception:
        return None

@app.route("/", methods=["GET", "POST"])
def dashboard():
    # Handle add / update stock
    if request.method == "POST":
        symbol = request.form["symbol"].upper().strip()
        quantity = int(request.form["quantity"])
        buy_price = float(request.form["buy_price"])
        buy_date_str = request.form["buy_date"]
        notes = request.form.get("notes", "").strip()

        today = date.today()
        buy_date = parse_date(buy_date_str)
        if not buy_date or buy_date > today:
            buy_date = today
            buy_date_str = today.strftime("%Y-%m-%d")

        conn = sqlite3.connect(DB_NAME)
        c = conn.cursor()
        c.execute("SELECT quantity, buy_price, buy_date FROM stocks WHERE symbol=?", (symbol,))
        row = c.fetchone()

        if row:
            old_qty, old_bp, old_date_str = row
            new_qty = old_qty + quantity
            new_bp = (old_bp * old_qty + buy_price * quantity) / new_qty

            old_date = parse_date(old_date_str) or buy_date
            final_date = min(old_date, buy_date)

            c.execute("""
                UPDATE stocks
                SET quantity=?, buy_price=?, buy_date=?, notes=?
                WHERE symbol=?
            """, (new_qty, new_bp, final_date.strftime("%Y-%m-%d"), notes, symbol))
        else:
            c.execute("""
                INSERT INTO stocks(symbol, quantity, buy_price, buy_date, notes)
                VALUES (?, ?, ?, ?, ?)
            """, (symbol, quantity, buy_price, buy_date_str, notes))

        conn.commit()
        conn.close()
        return redirect("/")

    # ----- READ DATA -----
    conn = sqlite3.connect(DB_NAME)
    c = conn.cursor()

    c.execute("SELECT * FROM stocks")
    stock_rows = c.fetchall()

    c.execute("SELECT symbol FROM watchlist")
    watchlist_rows = c.fetchall()

    c.execute("SELECT symbol, target FROM alerts")
    alert_rows = c.fetchall()

    conn.close()

    # ----- PORTFOLIO CALCULATIONS -----
    portfolio = []
    total_invested = 0.0
    total_value = 0.0
    total_long_pl = 0.0
    total_short_pl = 0.0
    today = date.today()

    for _id, symbol, qty, bp, buy_date_str, notes in stock_rows:
        live_price = get_live_price(symbol)
        invalid = live_price is None
        live_val = live_price if live_price is not None else 0.0

        invested = qty * bp
        current = qty * live_val
        pl = current - invested

        total_invested += invested
        total_value += current

        holding_type = "N/A"
        d = parse_date(buy_date_str)
        if d:
            days_held = (today - d).days
            if days_held > 365:
                holding_type = "Long"
                total_long_pl += pl
            else:
                holding_type = "Short"
                total_short_pl += pl

        portfolio.append({
            "symbol": symbol,
            "qty": qty,
            "bp": round(bp, 2),
            "live": round(live_val, 2),
            "invest": round(invested, 2),
            "current": round(current, 2),
            "profit": round(pl, 2),
            "notes": notes or "",
            "buy_date": buy_date_str,
            "holding_type": holding_type,
            "invalid": invalid
        })

    total_profit = total_value - total_invested

    # ----- ALERTS -----
    alerts = []
    for sym, target in alert_rows:
        lp = get_live_price(sym)
        live_val = lp if lp is not None else 0.0
        alerts.append({
            "symbol": sym,
            "target": round(target, 2),
            "live": round(live_val, 2),
            "hit": lp is not None and live_val >= target
        })

    # ----- TRENDING -----
    trending = []
    for t in TRENDING:
        lp = get_live_price(t)
        trending.append({
            "symbol": t,
            "price": round(lp if lp is not None else 0.0, 2)
        })

    watchlist = [w[0] for w in watchlist_rows]

    return render_template(
        "index.html",
        portfolio=portfolio,
        total_invested=round(total_invested, 2),
        total_value=round(total_value, 2),
        total_profit=round(total_profit, 2),
        total_long_pl=round(total_long_pl, 2),
        total_short_pl=round(total_short_pl, 2),
        watchlist=watchlist,
        alerts=alerts,
        trending=trending
    )

@app.route("/add_watch", methods=["POST"])
def add_watch():
    symbol = request.form["symbol"].upper().strip()
    if not symbol:
        return redirect("/")
    conn = sqlite3.connect(DB_NAME)
    c = conn.cursor()
    try:
        c.execute("INSERT INTO watchlist(symbol) VALUES(?)", (symbol,))
        conn.commit()
    except sqlite3.IntegrityError:
        pass
    conn.close()
    return redirect("/")

@app.route("/add_alert", methods=["POST"])
def add_alert():
    symbol = request.form["symbol"].upper().strip()
    target = float(request.form["target"])
    conn = sqlite3.connect(DB_NAME)
    c = conn.cursor()
    c.execute("INSERT INTO alerts(symbol, target) VALUES(?, ?)", (symbol, target))
    conn.commit()
    conn.close()
    return redirect("/")

if __name__ == "__main__":
    app.run(debug=True)
