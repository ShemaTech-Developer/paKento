# 📔 paKento — Cafeteria Debt Ledger

Replaces the paper "debt book": students who buy without money are recorded digitally.
When they pay, the amount is **subtracted** and the debt is marked **PAID**.
Red marks = owes. Green = paid. Nothing can be lost, wet or forged.

## Screens
| Tab | What it does |
|-----|--------------|
| 🏠 Today | Stats + today's ledger with red 🔴 / paid ✅ marks |
| 🔴 Debtors | All students who owe (red badges), search by name/class |
| 📅 Timetable | Month calendar — days turn **red** when unpaid debts exist, **green** when clear. Tap a date to see that day's debts |
| 📝 Record | Write a debt (name, class, amount, item) |
| ⚙️ Settings | **Admin: change password** |

## 🎒 Student Mode (no login needed)
On the entry screen: *"I'm a student — record / check my debt"*
- Student types their **name + class + amount** → debt is recorded
- Student checks their own debt anytime and sees paid/unpaid status

## ➖ Pay / Subtract
Open a debtor → tap an open debt → enter amount (quick chips: 100/200/500/1000 or full) →
- Partial payment → remaining is shown
- Full payment → debt becomes **PAID ✅**
- Paying more than the debt is refused

## Login
Default admin: **admin** / **kento123** — change it in ⚙️ Settings.

## How to run

### First time
```bash
cd ~/Desktop/paKento
python3 -m venv venv
./venv/bin/python -m pip install flask
```

### Every time
```bash
cd ~/Desktop/paKento
./venv/bin/python backend/app.py
```
Server at **http://localhost:5000** — or open `frontend/index.html` with **Live Server** + your **Mobile Preview** extension (it auto-connects to port 5000).

## Data
- SQLite file `pakento.db` — survives restarts, never lost
- Every debt/payment stores date, time and who recorded it (`admin` or `self:<name>` for student entries)
- Debts are never deleted — only paid off, so the record stays honest

## Database — SQLite (default) or MySQL

The app now has a database layer (`backend/database.py`). SQLite works automatically (data in `pakento.db`). To store everything in **MySQL** instead:

1. Create the database + user (run in your terminal, enter your MySQL/sudo password):
```bash
sudo mysql -e "CREATE DATABASE IF NOT EXISTS pakento CHARACTER SET utf8mb4; CREATE USER IF NOT EXISTS 'pakento'@'localhost' IDENTIFIED BY 'pakento123'; GRANT ALL ON pakento.* TO 'pakento'@'localhost'; FLUSH PRIVILEGES;"
```
2. Start the app with MySQL:
```bash
cd ~/Desktop/paKento
PAKENTO_DB=mysql PAKENTO_MYSQL_USER=pakento PAKENTO_MYSQL_PASSWORD=pakento123 ./venv/bin/python backend/app.py
```
Tables are created automatically. All data (students, credit, payments, history) is stored in MySQL.

## Project layout
```
paKento/
├── backend/app.py        # Flask API
├── backend/database.py   # SQLite/MySQL database layer
├── frontend/           # Mobile-first UI
├── venv/               # Python environment
├── requirements.txt
├── README.md
└── pakento.db          # SQLite data (default engine)
```
