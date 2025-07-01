from flask import Flask, render_template, request, redirect, url_for, flash
import pandas as pd
from datetime import datetime
import pyodbc
from dotenv import load_dotenv
import os
import math



app = Flask(__name__)
app.secret_key = 'supersecret'  # for flash messages

load_dotenv()
password = os.getenv("SQL_PASSWORD")

server = 'quiz6server.database.windows.net'
database = 'quiz6db' 
username = 'quiz6us'
driver = '{ODBC Driver 18 for SQL Server}'

def get_connection():
    return pyodbc.connect(
        f'DRIVER={driver};'
        f'SERVER={server};'
        f'DATABASE={database};'
        f'UID={username};'
        f'PWD={password};'
        f'Encrypt=yes;'
        f'TrustServerCertificate=no;'
        f'Connection Timeout=30;'
    )

@app.route('/')
def index():
    print("Rendering index.html")  # Make sure this prints in your terminal
    return render_template('index.html')
    #return "<h1>Test page</h1>"

@app.route('/query', methods=['GET', 'POST'])
def query():
    if request.method == 'POST':
        # Get up to 5 grocery items from form
        items = [
            request.form.get(f'item{i}', '').strip()
            for i in range(1, 6)
        ]
        items = [item for item in items if item]  # remove empty inputs

        conn = get_connection()
        cursor = conn.cursor()

        inserted = []
        for item in items:
            try:
                cursor.execute("""
                    MERGE GroceryInventory AS target
                    USING (SELECT ? AS item) AS source
                    ON target.item = source.item
                    WHEN MATCHED THEN 
                        UPDATE SET quantity = target.quantity + 1
                    WHEN NOT MATCHED THEN 
                        INSERT (item, quantity) VALUES (source.item, 1);
                """, item)
                inserted.append(item)
                # Log the addition
                cursor.execute("INSERT INTO InventoryLog (action, item) VALUES (?, ?)", "Added to Inventory", item)
            except Exception as e:
                print(f"Failed to insert '{item}': {e}")
                flash(f"Item '{item}' could not be added (maybe duplicate?)")

        conn.commit()

        # Fetch all items in the inventory
        df = df = pd.read_sql("SELECT * FROM GroceryInventory", conn)

        cursor.close()
        conn.close()

        html_table = df.to_html(classes='table table-striped', index=False).replace('\n', '')
        flash(f"Inserted: {', '.join(inserted)}")
        return render_template('results.html', tables=[html_table], titles=df.columns.values)

    return render_template('query.html')


@app.route('/query2', methods=['GET'])
def query2():
    try:
        conn = get_connection()
        df = df = pd.read_sql("SELECT * FROM GroceryInventory", conn)
        conn.close()

        html_table = df.to_html(classes='table table-striped', index=False).replace('\n', '')
        return render_template('results.html', tables=[html_table], titles=df.columns.values)

    except Exception as e:
        flash(f"Error fetching grocery items: {e}")
        return redirect(url_for('index'))

@app.route('/shopping/<shopper>', methods=['GET', 'POST'])
def shopping(shopper):
    conn = get_connection()
    cursor = conn.cursor()

    # Handle item purchase
    if request.method == 'POST':
        action = request.form.get('action')
        item = request.form.get('item')

        if action == 'buy':
            cursor.execute("SELECT quantity FROM GroceryInventory WHERE item = ?", item)
            row = cursor.fetchone()
            if row and row[0] > 0:
                cursor.execute("UPDATE GroceryInventory SET quantity = quantity - 1 WHERE item = ?", item)
                cursor.execute("""
                    MERGE ShopperCart AS target
                    USING (SELECT ? AS shopper_name, ? AS item) AS source
                    ON target.shopper_name = source.shopper_name AND target.item = source.item
                    WHEN MATCHED THEN UPDATE SET quantity = target.quantity + 1
                    WHEN NOT MATCHED THEN INSERT (shopper_name, item, quantity) VALUES (?, ?, 1);
                """, shopper, item, shopper, item)
                flash(f"{item} added to your cart.")
                cursor.execute("INSERT INTO InventoryLog (action, item, shopper) VALUES (?, ?, ?)", "Sold", item, shopper)
            else:
                flash(f"{item} is out of stock.")
        
        elif action == 'return':
            # Check shopper has item
            cursor.execute("SELECT quantity FROM ShopperCart WHERE shopper_name=? AND item=?", shopper, item)
            row = cursor.fetchone()
            if row and row[0] > 0:
                cursor.execute("UPDATE ShopperCart SET quantity = quantity - 1 WHERE shopper_name=? AND item=?", shopper, item)
                cursor.execute("DELETE FROM ShopperCart WHERE quantity=0")
                cursor.execute("UPDATE GroceryInventory SET quantity = quantity + 1 WHERE item = ?", item)
                flash(f"{item} returned to store.")
                cursor.execute("INSERT INTO InventoryLog (action, item, shopper) VALUES (?, ?, ?)", "Returned", item, shopper)
            else:
                flash("You don't have that item to return.")

        conn.commit()

    # Show available items
    inv_df = pd.read_sql("SELECT * FROM GroceryInventory", conn)
    cart_df = pd.read_sql("SELECT item, quantity FROM ShopperCart WHERE shopper_name = ?", conn, params=[shopper])
    cursor.close()
    conn.close()

    inv_html = inv_df.to_html(classes="table table-bordered", index=False)
    cart_html = cart_df.to_html(classes="table table-bordered", index=False)

    return render_template("shopping.html", shopper=shopper, inventory_table=inv_html, cart_table=cart_html)

@app.route('/shop', methods=['GET', 'POST'])
def shop():
    if request.method == 'POST':
        shopper = request.form.get('shopper', '').strip()
        if not shopper:
            flash("Please enter a valid name.")
            return redirect(url_for('shop'))

        return redirect(url_for('shopping', shopper=shopper))
    return render_template('shop.html')


@app.route('/log')
def view_log():
    try:
        conn = get_connection()
        df = pd.read_sql("SELECT * FROM InventoryLog ORDER BY timestamp DESC", conn)
        conn.close()

        html_table = df.to_html(classes="table table-bordered", index=False)
        return render_template("results.html", tables=[html_table], titles=df.columns.values)
    except Exception as e:
        flash(f"Error fetching log: {e}")
        return redirect(url_for('index'))

    
if __name__ == '__main__':
    os.makedirs(os.path.join('static', 'uploads'), exist_ok=True)
    app.run(debug=True)