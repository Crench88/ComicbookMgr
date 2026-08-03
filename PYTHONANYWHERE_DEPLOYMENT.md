# Deploy ComicbookMgr on PythonAnywhere (beginner guide)

This guide assumes you have never used PythonAnywhere before.
Follow the steps **in order**. Your live site will be:

`https://YOUR_USERNAME.pythonanywhere.com`

Replace `YOUR_USERNAME` everywhere with your real PythonAnywhere username.

---

## Before you start (important)

1. **Use the deploy branch** (already prepared in GitHub):
   - Branch name: `deploy/pythonanywhere`
2. **Account type**
   - **Free** account: the site can run, but **ComicVine / eBay / many external APIs will not work** (outbound internet is restricted).
   - **Paid “Beginner” (~$5/mo)**: full internet access — recommended if you want search, enrich, and pricing.
3. **Disk space**
   - Covers and CBZ/CBR files use disk. Start without uploading a huge digital library.
4. You will need:
   - A [PythonAnywhere](https://www.pythonanywhere.com/) account
   - Your GitHub repo access
   - About 30–45 minutes

---

## Part A — What we already prepared in this branch

You do **not** need to invent these files; they are in the repo:

| File | Purpose |
|------|---------|
| `pythonanywhere_wsgi.py` | Ready-to-paste WSGI starter for PythonAnywhere |
| `env.pythonanywhere.example` | Template for your secret `.env` |
| `scripts/pythonanywhere_bootstrap.py` | Creates folders, runs DB migrations, creates admin user |

---

## Part B — Create the web app on PythonAnywhere

1. Log in at [pythonanywhere.com](https://www.pythonanywhere.com/).
2. Open the **Web** tab.
3. Click **Add a new web app**.
4. Click **Next**.
5. Choose **Manual configuration** (not “Flask” wizard — we paste our own WSGI code).
6. Choose **Python 3.12** (or the newest 3.x they offer that is ≥ 3.10).
7. Click **Next** until the web app is created.
8. Leave the page open — you will come back to it.

Your default site URL is shown at the top of the Web tab.

---

## Part C — Clone the code (Bash console)

1. Open the **Consoles** tab.
2. Click **Bash** to open a new console.
3. Run these commands **one block at a time** (replace `YOUR_USERNAME` and the GitHub URL if needed):

```bash
cd ~
git clone -b deploy/pythonanywhere https://github.com/Crench88/ComicbookMgr.git
cd ComicbookMgr
```

If the repo is private, PythonAnywhere will ask you to authenticate (GitHub username + a [personal access token](https://github.com/settings/tokens) as the password).

4. Create a virtual environment and install packages:

```bash
python3.12 -m venv venv
source venv/bin/activate
pip install --upgrade pip
pip install -r requirements.txt
```

**If `pip install` fails** on a heavy package (`opencv`, `rapidocr`, `pyzbar`):

- Retry once.
- Or install the rest and skip that package for now; core collection CRUD still works without barcode OCR / panel tools.

5. Keep this console open for Part E.

---

## Part D — Create your secret `.env` file

1. Still in the Bash console (venv activated, inside `ComicbookMgr`):

```bash
cp env.pythonanywhere.example .env
python generate_secret_key.py
```

2. Copy the **Hex Secret Key** line that looks like `SECRET_KEY=abcd1234...`

3. Edit `.env`:

```bash
nano .env
```

4. In nano:
   - Replace **every** `YOUR_USERNAME` with your PythonAnywhere username.
   - Paste your real `SECRET_KEY=...` value.
   - Optionally paste `COMICVINE_API_KEY` / eBay keys (paid PA plan).
   - Save: `Ctrl+O`, Enter, then exit: `Ctrl+X`.

Example database line after editing:

```env
DATABASE_URL=sqlite:////home/jane/ComicbookMgr/instance/comicbook.db
```

(Note: **four** slashes after `sqlite:` for an absolute path.)

---

## Part E — Create the database and admin user

Still in Bash, from `~/ComicbookMgr` with venv on:

```bash
source venv/bin/activate
cd ~/ComicbookMgr
python scripts/pythonanywhere_bootstrap.py \
  --username admin \
  --email 'you@example.com' \
  --password 'ChooseAStrongPassword123!'
```

Change the email and password to yours.

You should see messages about migrations and “Created admin user”.

---

## Part F — Point the Web tab at this project

1. Open the **Web** tab again.
2. Find **Virtualenv** section.
   - Enter: `/home/YOUR_USERNAME/ComicbookMgr/venv`
   - Tab out of the field so it saves (green check / no error).
3. Find **Code** → **WSGI configuration file** and click the link (opens an editor).
4. **Delete all the sample code** in that file.
5. Paste this (replace `YOUR_USERNAME` twice):

```python
import os
import sys

PROJECT_HOME = '/home/YOUR_USERNAME/ComicbookMgr'
os.environ['COMICBOOKMGR_HOME'] = PROJECT_HOME

if PROJECT_HOME not in sys.path:
    sys.path.insert(0, PROJECT_HOME)

os.chdir(PROJECT_HOME)

from dotenv import load_dotenv
load_dotenv(os.path.join(PROJECT_HOME, '.env'))

from werkzeug.middleware.proxy_fix import ProxyFix
from app import create_app

application = create_app()
application.wsgi_app = ProxyFix(application.wsgi_app, x_for=1, x_proto=1, x_host=1)
```

6. Click **Save**.
7. Back on the **Web** tab, set **Static files**:

| URL | Directory |
|-----|-----------|
| `/static/` | `/home/YOUR_USERNAME/ComicbookMgr/app/static/` |

Click the checkmark / green button to save the mapping.

8. Scroll to the top of the **Web** tab and click the big green **Reload** button.

---

## Part G — Open your site

1. Visit `https://YOUR_USERNAME.pythonanywhere.com`
2. Log in with the admin username/password from Part E.
3. If you see an error page:
   - Web tab → **Error log** (link near the top)
   - Read the newest lines at the bottom
   - Common fixes are in “Troubleshooting” below

---

## Part H — (Optional) Upload your existing comics database

To bring over your local collection **metadata** (not necessarily every CBZ file):

1. On your PC, locate: `instance/comicbook.db`
2. On PythonAnywhere, open the **Files** tab.
3. Go to `/home/YOUR_USERNAME/ComicbookMgr/instance/`
4. Upload `comicbook.db` (overwrite if a fresh empty one exists).
5. Also upload cover files into `instance/covers/` if you use filesystem covers.
6. In Bash:

```bash
cd ~/ComicbookMgr
source venv/bin/activate
flask db upgrade
```

(`FLASK_APP` tip if needed: `export FLASK_APP=pythonanywhere_wsgi:application`)

7. Web tab → **Reload**.

**Note:** Large CBZ libraries often do not fit on a free account. Metadata + cover images first is enough to try the site.

---

## Updating the site later

In Bash:

```bash
cd ~/ComicbookMgr
source venv/bin/activate
git pull origin deploy/pythonanywhere
pip install -r requirements.txt
python -c "from flask_migrate import upgrade; from app import create_app; app=create_app();\
import os; \
exec('with app.app_context(): upgrade()')"
```

Or simply:

```bash
export FLASK_APP=pythonanywhere_wsgi:application
flask db upgrade
```


Then **Web** → **Reload**.

---

## Troubleshooting

| Problem | What to do |
|---------|------------|
| `SECRET_KEY must be configured` | `.env` missing or not loaded; fix Part D and WSGI `load_dotenv` path |
| `ModuleNotFoundError` | Virtualenv path wrong on Web tab, or `pip install -r requirements.txt` not run |
| Site loads but CSS missing | Static files mapping wrong (Part F) |
| ComicVine / eBay fails on free plan | Expected — upgrade to paid Beginner for open internet |
| `Permission denied` / cannot write DB | Check `instance/` exists and `DATABASE_URL` path is correct |
| Import error in WSGI | Confirm `PROJECT_HOME` path matches the real clone folder name |

Error logs: **Web** tab → **Error log**.

---

## Success checklist

- [ ] `https://YOUR_USERNAME.pythonanywhere.com` opens
- [ ] You can log in as admin
- [ ] Static CSS/JS loads
- [ ] You can add or view a comic
- [ ] (Paid plan) ComicVine search works if API key is set

---

## Need help?

- PythonAnywhere help: https://help.pythonanywhere.com/
- In this chat: paste the **bottom 30 lines** of your Error log and we can fix it together.
