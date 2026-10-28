# Deploy the AZM Markets educational Flask demo on GitHub + Render

**FAKE DATA ONLY.** This has no live Sumsub, Ottu, or MT5 integration. Do not enter real card data or upload real identity/card photos. Do not use for production.

## 1. Upload to GitHub (no Git required)
1. Create a **Private** GitHub repository named `azm-sumsub-ottu-demo`. Don't initialize with a README.
2. Extract this ZIP locally. In the new GitHub repo choose **uploading an existing file**, drag the **contents** of the extracted folder (app.py, requirements.txt, render.yaml, templates/, static/ etc.) into the browser, then Commit changes. The repository root must contain app.py and requirements.txt. GitHub web uploads can be tricky with folders; if necessary use GitHub Desktop as below.
3. Alternative: GitHub Desktop > File > Add local repository (or create repository from the extracted folder) > Publish repository > Keep this code private.

## 2. Configure Render
1. Log in at https://dashboard.render.com/ and choose **New > Web Service**. Connect the GitHub repository, allowing access to the private repository.
2. Language: Python 3; root directory: blank (because app.py is at repository root).
3. Build command: `pip install -r requirements.txt`
4. Start command: `gunicorn --bind 0.0.0.0:$PORT --workers 1 app:app`
5. Instance type: Free, for temporary demonstration only.
6. Add environment variables before deploying: `SECRET_KEY` = long random string, `ADMIN_PASSWORD` = strong unique password, `ADMIN_EMAIL` = your admin login email, `HTTPS_ONLY` = `1`. You may also use the included render.yaml Blueprint; `ADMIN_PASSWORD` is prompted as a secret with `sync: false`.
7. Deploy. Browse to the shown https://...onrender.com URL.

## 3. Test
Register a fictional client, upload synthetic card art, log in as admin, approve the card, then complete a first simulated Ottu checkout. On the second deposit confirm the masked saved card + dummy CVV step.

## 4. Caveat: free hosting data loss
The app uses SQLite and local image uploads. Render Free web service filesystem is ephemeral: all registered accounts, approved cards and uploads can disappear upon deployment, restart or spin-down. For persistent test data, a paid Render service with a disk can use `AZM_DATA_DIR=/var/data` and a disk mounted at `/var/data` (subject to cost and security review). For a real system, use a supported managed database and direct-to-Sumsub secure capture, not local storage.

## 5. Troubleshooting
- `ModuleNotFoundError: gunicorn`: make sure requirements.txt contains gunicorn and deploy rebuilt.
- `ModuleNotFoundError: app`: Root directory must be blank when app.py is at the repo root.
- Login loops: set a fixed SECRET_KEY, redeploy.
- Admin password: the admin user is created during initial database initialization. Changing ADMIN_PASSWORD later won't change the previously persisted admin user.
- Repeated loss of demo accounts: expected on Render Free.


## v6 — Add another card
In the client portal's **Make a deposit** section, choose **+ Use another card — Start new Sumsub verification** and enter the intended amount. The app redirects to `/cards/new` to upload a NEW dummy card image, creates a separate mock Sumsub action and marks it pending. The demo admin must approve the new evidence. The client can then select the newly approved card and continue to Ottu-style first-time card entry. Only after its first successful simulated payment is a new synthetic token created; thereafter this card appears in the previously used options. The existing previously used card stays available. No real Sumsub/Ottu calls occur.

**Deployment:** commit the updated `app.py`, `templates/client.html` and documentation to the same GitHub repository. Render connected to that branch will normally auto-deploy on new commits; otherwise use Render Dashboard → Manual Deploy → Deploy latest commit. Do not upload local DB files or card images.
