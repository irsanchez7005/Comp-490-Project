# GamePlan

**Play more. Together.**

GamePlan is a web app for finding golf courses, booking tee times, and connecting with other golfers. It is our team project for COMP 490 and is built with Django and PostgreSQL.

> **Status:** in development. Accounts, course browsing, and tee time booking work. Lessons and the community side are still being built (see [Roadmap](#roadmap)).

---

## Features

### Accounts
- Sign up with a username and email. New accounts are activated by a 6-digit code sent by email.
- Log in with your email and password.
- Reset a forgotten password with an emailed code.
- Codes expire after 10 minutes. After 3 wrong guesses, entering codes is locked for 1 minute, and the page shows a countdown.
- Account settings: change your username, email, or password (you confirm your current password first), or delete your account.
- Profile page with avatar, cover image, bio, city, ZIP code, skill level, and handicap.

### Courses and booking
- Browse all courses, or use the search bar to find a course by name or city.
- Each course page has a calendar for picking a date and tee time, and shows how many spots are open.
- Book 1–4 players on a tee time. Checkout shows the subtotal, 9.5% tax, and total.
- **Simulated payment:** card details are checked for format only. No real payment is processed, and only the last 4 digits are stored.
- Booking confirmation with a receipt, plus a **My Bookings** page where you can cancel a booking.
- If two people try to book the last spot at the same time, only one booking goes through.

### Admin
- The Django admin manages courses, tee times, bookings, and users.
- The **"Generate 15-min tee times for next 7 days"** action creates a week of tee times for the selected courses.

---

## Tech stack

| Layer    | Tools |
|----------|-------|
| Backend  | Python 3.12, Django 6.1 |
| Database | PostgreSQL (hosted on [Neon](https://neon.tech)), accessed with psycopg 3 |
| Frontend | Django templates, plain CSS and JavaScript |
| Other    | Pillow (image uploads), python-decouple (reads settings from `.env`) |

---

## Project structure

```
Comp-490-Project/
├── requirements.txt
└── gameplan/                  # Django project root (run manage.py from here)
    ├── manage.py
    ├── gameplan/              # settings.py, urls.py
    ├── accounts/              # users, profiles, signup/login, verification codes
    ├── facility/              # courses, tee times, booking, checkout, receipts
    ├── courses/               # courses listing template
    ├── community/             # posts, comments, saved posts (models only so far)
    ├── reservation/           # reservations and payments (models only so far)
    ├── static/                # css/, js/, images/
    └── media/                 # uploaded avatars and cover images (not committed)
```

---

## Getting started

### 1. Clone and install

```bash
git clone https://github.com/irsanchez7005/Comp-490-Project.git
cd Comp-490-Project

python -m venv venv
# Windows
venv\Scripts\activate
# macOS / Linux
source venv/bin/activate

pip install -r requirements.txt
```

### 2. Create a `.env` file

Create `gameplan/.env` (next to `manage.py`). It is listed in `.gitignore`, so it is never committed.

```env
SECRET_KEY=your-django-secret-key
DEBUG=True
DB_PASSWORD=ask-a-team-member
```

- **`SECRET_KEY`**: generate one with
  `python -c "from django.core.management.utils import get_random_secret_key; print(get_random_secret_key())"`
- **`DEBUG`**: keep this `True` for local development. With `DEBUG=False`, the site rejects every request until `ALLOWED_HOSTS` is set.
- **`DB_PASSWORD`**: the password for the team's Neon database. Ask a team member for it, and never commit it.

### 3. Set up the database

```bash
cd gameplan
python manage.py migrate
python manage.py createsuperuser
```

> ⚠️ **The whole team shares one database.** Running `migrate` changes it for everyone. Before you run it, commit your migration files and pull everyone else's.
>
> Don't run `loaddata demo_facilities` on the shared database. The fixture uses fixed IDs and would overwrite the course and tee times that already have those IDs.

### 4. Run the server

```bash
python manage.py runserver
```

Open <http://127.0.0.1:8000/>. The admin is at <http://127.0.0.1:8000/admin/>.

To get tee times to book: in the admin, open **Facilities**, select one or more courses, and run **"Generate 15-min tee times for next 7 days"**.

### Emails in development

Emails are printed to the terminal running `runserver` instead of being sent (`EMAIL_BACKEND` is the console backend). When you sign up or reset a password, copy the 6-digit code from the terminal.

---

## Main pages

| URL | Page |
|-----|------|
| `/` | Home |
| `/courses/` | All courses |
| `/search/?q=` | Course search results as JSON (used by the search bar) |
| `/facilities/<id>/` | Course page with calendar and tee times |
| `/checkout/` | Checkout for a selected tee time |
| `/bookings/` | My Bookings |
| `/register/`, `/login/`, `/logout/` | Sign up, log in, log out |
| `/password-reset/` | Forgot password |
| `/profile/`, `/profile/edit/` | View and edit your profile |
| `/my-gameplan/` | Dashboard |
| `/settings/` | Account settings |
| `/admin/` | Django admin |

---

## Roadmap

- [ ] Lessons: browse instructors and book lessons
- [ ] Community: posts, comments, and saved posts (models exist; pages not built yet)
- [ ] Messages and notifications
- [ ] Reviews and ratings
- [ ] Automated tests
- [ ] Send real emails instead of printing them to the terminal
- [ ] AI agent chatbot 

---

## Team

| Name | 
|------|
| Isaac Sanchez | |
| Kelvin Jinn (Htet Oo Lwin)| |
| Matthew Messiha | |
| Sumchhay Cheap | |
| Pablo Panduro Torres | |

---

*COMP 490 · 2026*
