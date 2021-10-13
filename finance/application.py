import os

from cs50 import SQL
from flask import Flask, flash, redirect, render_template, request, session
from flask_session import Session
from tempfile import mkdtemp
from werkzeug.exceptions import default_exceptions, HTTPException, InternalServerError
from werkzeug.security import check_password_hash, generate_password_hash
from datetime import datetime

from helpers import apology, login_required, lookup, usd

# Configure application
app = Flask(__name__)

# Ensure templates are auto-reloaded
app.config["TEMPLATES_AUTO_RELOAD"] = True


# Ensure responses aren't cached
@app.after_request
def after_request(response):
    response.headers["Cache-Control"] = "no-cache, no-store, must-revalidate"
    response.headers["Expires"] = 0
    response.headers["Pragma"] = "no-cache"
    return response


# Custom filter
app.jinja_env.filters["usd"] = usd

# Configure session to use filesystem (instead of signed cookies)
app.config["SESSION_FILE_DIR"] = mkdtemp()
app.config["SESSION_PERMANENT"] = False
app.config["SESSION_TYPE"] = "filesystem"
Session(app)

# Configure CS50 Library to use SQLite database
db = SQL("sqlite:///finance.db")

# Make sure API key is set
if not os.environ.get("API_KEY"):
    raise RuntimeError("API_KEY not set")


@app.route("/")
@login_required
def index():
    """Show portfolio of stocks"""
    # user account summary
    rows = db.execute("SELECT * FROM users WHERE id = ?", session["user_id"])

    name = rows[0]["username"]
    balance = rows[0]["cash"]

    # users share info
    stocks = db.execute(
        "SELECT stock_name, SUM(quantity)FROM purchases WHERE purchase_id = ? GROUP BY stock_name ORDER BY date DESC;", session["user_id"])

    grand_total = balance

    profile = []

    for stock in stocks:
        if stock["SUM(quantity)"] == 0:
            continue
        details = {}
        price = lookup(stock["stock_name"])["price"]
        total = stock["SUM(quantity)"] * price
        grand_total += total
        details["stock"] = stock["stock_name"]
        details["quantity"] = stock["SUM(quantity)"]
        details["current_price"] = price
        details["total"] = total
        profile.append(details)





    return render_template("index.html", name=name, balance=balance, profile=profile, grand_total=grand_total )


@app.route("/buy", methods=["GET", "POST"])
@login_required
def buy():
    """Buy shares of stock"""

    # if made POST request
    if request.method == "POST":

        # get the inputs
        symbol = request.form.get("symbol")
        share_i = request.form.get("shares")



        # use lookup function to get details of the stock
        row = lookup(symbol)

        # if symnol not found or field left emty validate
        if not symbol or not row:
            return apology("Stock does not exist/invalid and/or symbol field empty", 400)
        else:
            if share_i.isalpha() or not share_i.isdigit() or int(share_i) < 1:
                return apology("Invalid number of stocks \n MUST BE AN INTEGER", 400)
            else:


                # check the balance and prompt if low
                balance = db.execute("SELECT cash FROM users WHERE id = ?", session["user_id"])
                cash = balance[0]["cash"]
                price = float(share_i) * row["price"]

                if cash < price:
                    return apology(f"No sufficient balance to execute the purchase, current balance = ${cash} ", 400)

                db.execute("INSERT INTO purchases (purchase_id, stock_name, price, quantity, total_price, date, type) VALUES (?, ?, ?, ?, ?, ?, ?)",
                           session["user_id"], row["symbol"], row["price"], share_i , price, datetime.now().strftime("%Y-%m-%d %H:%M:%S"), "Buy")

                cash = cash - price

                db.execute("UPDATE users SET cash = ? WHERE id = ?", cash, session["user_id"])
                
                flash("Buy Successful!")
                return redirect("/")
    else:
        return render_template("buy.html")


@app.route("/history")
@login_required
def history():
    """Show history of transactions"""

    transactions = db.execute(
        "SELECT stock_name, price, quantity, total_price, type, date FROM purchases WHERE purchase_id = ? ORDER BY date DESC", session["user_id"])

    return render_template("history.html", transactions=transactions)


@app.route("/login", methods=["GET", "POST"])
def login():
    """Log user in"""

    # Forget any user_id
    session.clear()

    # User reached route via POST (as by submitting a form via POST)
    if request.method == "POST":

        # Ensure username was submitted
        if not request.form.get("username"):
            return apology("must provide username", 403)

        # Ensure password was submitted
        elif not request.form.get("password"):
            return apology("must provide password", 403)

        # Query database for username
        rows = db.execute("SELECT * FROM users WHERE username = ?", request.form.get("username"))

        # Ensure username exists and password is correct
        if len(rows) != 1 or not check_password_hash(rows[0]["hash"], request.form.get("password")):
            return apology("invalid username and/or password", 403)

        # Remember which user has logged in
        session["user_id"] = rows[0]["id"]

        # Redirect user to home page
        flash("Successfully logged in!")
        return redirect("/")

    # User reached route via GET (as by clicking a link or via redirect)
    else:
        return render_template("login.html")


@app.route("/logout")
def logout():
    """Log user out"""

    # Forget any user_id
    session.clear()

    # Redirect user to login form
    flash("Successfully logged out!")
    return redirect("/")


@app.route("/quote", methods=["GET", "POST"])
@login_required
def quote():
    """Get stock quote."""
    if request.method == "POST":


        if not request.form.get("symbol"):
            return apology("MISSING SYMBOL")

        row = lookup(request.form.get("symbol"))
        print(row)

        if row == None:
            return apology("INVALID SYMBOl")

        name = row["name"]
        print(name)
        symbol = row["symbol"]
        price = row["price"]
        
        flash("Result found!")
        return render_template("quoted.html", name=name, symbol=symbol, price=price)
    else:
        return render_template("quote.html")


@app.route("/register", methods=["GET", "POST"])
def register():
    """Register user"""
    if request.method == "POST":

        # get the name match from the db if exists
        rows = db.execute("SELECT * FROM users WHERE username = ?", request.form.get("username"))

        # get the input data
        username = request.form.get("username")
        password = request.form.get("password")
        confirmation = request.form.get("confirmation")

        # check the validation for username as password
        if not username or (len(rows) == 1 and username == rows[0]["username"]):
            return apology("Username already exist or field empty")

        if not password or password != confirmation:
            return apology("Password do not match or field empty")

        # register the user
        db.execute("INSERT INTO users (username, hash) VALUES (?, ?)", username, generate_password_hash(password))
        
        flash("Successfully registered!")
        return render_template("login.html")

    else:
        return render_template("register.html")


@app.route("/sell", methods=["GET", "POST"])
@login_required
def sell():
    """Sell shares of stock"""
    symbols = {}
    # users share info
    stocks = db.execute(
        "SELECT stock_name, SUM(quantity)FROM purchases WHERE purchase_id = ? GROUP BY stock_name ORDER BY date DESC;", session["user_id"])

    for stock in stocks:
        symbols[stock["stock_name"]] = stock["SUM(quantity)"]

    if request.method == "POST":
        name = request.form.get("symbol")
        requested = request.form.get("shares")


        if not name:
            return apology("No stocks selected", 400)

        if int(requested) > symbols[name]:
            return apology(f"Quantity Exceeded: You have: \n {symbols[name]} shares of {name} availabe to sell", 400)

        current_price = lookup(name)["price"]

        total_cost = float(requested) * current_price

        db.execute("INSERT INTO purchases (purchase_id, stock_name, price, quantity, total_price, date, type) VALUES (?, ?, ?, - ?, ?, ?, ?)",
                   session["user_id"], name, current_price, int(requested), total_cost, datetime.now().strftime("%Y-%m-%d %H:%M:%S"), "Sell")

        db.execute("UPDATE users SET cash = cash + :cash WHERE id = :id ", cash = round(total_cost, 2), id = session["user_id"])

        flash("Successfully sold!")
        return redirect("/")
    else:
        if not symbols:
            return apology("You don't own any stock", 400)

        return render_template("sell.html", symbols=symbols)


def errorhandler(e):
    """Handle error"""
    if not isinstance(e, HTTPException):
        e = InternalServerError()
    return apology(e.name, e.code)


# Listen for errors
for code in default_exceptions:
    app.errorhandler(code)(errorhandler)
