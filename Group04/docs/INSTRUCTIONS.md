# Project instructions

Run the commands below in PowerShell from the repository root.

## 1. Requirements

Install Python and Node.js (including npm).

## 2. Environment and email

Create the local configuration file once:

```powershell
Copy-Item backend\config\.env.example backend\config\.env
```

If `.env` already exists, edit it instead of copying over it. Fill in:

```ini
EMAIL_ADDRESS=your-project-account@gmail.com
EMAIL_HOST_PASSWORD=your-gmail-app-password
SECRET_KEY=your-long-random-secret-key
```

Use the project Gmail credentials supplied by the team, or your own Gmail address and app password. SMTP already uses port 587 with TLS in `backend/config/settings.py`; `EMAIL_PORT` in the template is not read by the code.

To generate a secret key:

```powershell
python -c "import secrets; print(secrets.token_urlsafe(50))"
```

Keep `.env` local; Git already ignores it. Restart the backend after changing it.

Without Gmail credentials, set `use_email = False` in `backend/config/settings.py`. Verification and password-reset links will appear in the backend terminal. Keep `SECRET_KEY` configured and restore `use_email = True` before committing.

## 3. Start the complete project

```powershell
.\start-project.bat
```

The script creates the Python environment if needed, installs dependencies, applies migrations, seeds the catalog, and starts three windows: backend, listing maintenance, and frontend.

- Frontend: http://127.0.0.1:5173
- Backend: http://127.0.0.1:8000

Close all three service windows to stop the project. Register through the frontend and open the verification link from your email or backend terminal before signing in.

## 4. Create an administrator

After starting the project once, run:

```powershell
$env:ADMIN_EMAIL = "admin@example.com"
$env:ADMIN_PASSWORD = "ChooseAStrongPassword123!"
.\backend\venv\Scripts\python.exe .\backend\manage.py create_admin
Remove-Item Env:ADMIN_EMAIL, Env:ADMIN_PASSWORD
```

Sign in through the frontend with these credentials. The account is already email-verified. If the email already exists, the command resets its password and grants administrator access.

To approve a seller, open **Admin panel → Review Applications**. Use a separate account from the applicant; users cannot approve their own applications.

## 5. Run tests

Backend suite:

```powershell
.\backend\venv\Scripts\python.exe .\backend\manage.py test tests
```

To run one category, replace `tests` with `tests.accounts`, `tests.security`, or `tests.catalog`.

The default in-memory SQLite test database skips six concurrency tests. Those require a file-based test database.

Check the frontend build:

```powershell
npm.cmd --prefix frontend run build
```

## 6. Listing policies

- Suspended sellers cannot publish or sell. Existing listings are hidden until reactivation; public profiles remain visible and suspension reasons stay private.
- Ended listings remain publicly visible indefinitely through their detail pages, but cannot be purchased and do not appear in the active catalog.
