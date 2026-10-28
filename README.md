# AZM Markets — Flask Sumsub + Ottu workflow training prototype

**SIMULATION ONLY.** This is not a payment gateway, real KYC verification, or a production application. Use only fabricated data and card artwork. No real card credentials, card photographs, PAN, CVV or customer identity documents.

## Run locally (Windows PowerShell)

```powershell
cd azm_flask_demo
py -m venv .venv
.venv\Scripts\Activate.ps1
pip install -r requirements.txt
$env:SECRET_KEY="replace-this-with-a-long-random-value"
$env:ADMIN_PASSWORD="UseYourOwnLongAdminPassword123!"
python app.py
```

Visit http://127.0.0.1:5000

Admin login: `admin@azm.local` / value of `ADMIN_PASSWORD`. If unset, the unsafe DEMO fallback is `ChangeMe123!`; change it before running. Admin is seeded only when the database is first created; changing the env var later will not reset the saved password. Delete `azm_demo.sqlite3` to restart the demo.

## Test journey
1. Register fictional client. A `demo_app_...` identifier simulates the Sumsub applicant linked to CRM.
2. Go to **Verify new card**, enter fabricated name, 6/8-digit dummy BIN, last four, expiry and a *dummy* card illustration. Do not upload a real payment card.
3. Log out; admin login. Review submitted image, approve or reject. This is a **human simulation**, not a Sumsub call or OCR check.
4. Log in as client. Choose approved card, create AED 100 deposit.
5. At the simulated Ottu checkout, enter fictional cardholder, BIN, last four and expiry only on the FIRST payment. For subsequent deposits, the stored card number is masked (•••• •••• •••• 3456) and a dummy CVV is required on the simulated hosted checkout. Never enter a real PAN or CVV.
6. Upon simulated success, a `mock_tok_...` identifier is stored. At the next deposit the customer sees **Previously used · Sumsub verified** and can use the saved token without re-entering the PAN, but must supply a dummy security code for the repeat payment. The code is cleared client-side before form submission and not stored by the backend.
7. Admin dashboard shows card action/check IDs, masked card and token, deposit status and simulated MT5 credit.

## Logical database models
- `users`: CRM client ID, name, email, password hash, role, mock `applicant_id`.
- `cards`: mock `action_id`/`check_id`, cardholder name, BIN and last 4 (test only), expiry, private demo-image pathname, admin review, mock token.
- `deposits`: client, card, amount, mock Ottu session, reference, status, mock MT5 credit status.

## Production implementation guide
- Replace registration's fake KYC state with real verified Sumsub applicant creation/KYC statuses.
- **Never upload real card evidence into this Flask app**. Instead, use the Sumsub SDK for card proof capture and authenticated applicant-action APIs and verified webhooks; retain only minimum masked metadata and external identifiers in CRM.
- Replace the mock Ottu checkout page with a backend call to Ottu's Checkout API, then redirect the user to returned `checkout_url`. Configure `customer_id`, amount, currency, webhook and return URL. Never collect PAN/CVV on the CRM domain.
- Receive Ottu payment webhooks, **verify provider signatures** following the currently applicable official documentation, deduplicate event IDs and reconcile amount, reference, currency, payment state and customer before setting paid.
- Obtain saved payment method tokens only from genuine Ottu/PSP tokenization mechanisms; encrypt token references and limit access. Validate whether tokens are PSP-specific and whether cross-gateway reuse is supported.
- **Do not use BIN + last four as unique-card matching**. You need secure proof that the Sumsub-checked card and Ottu token identify the *same card* before approving a reusable binding; this prototype assumes the binding solely for education.
- Implement role-based permissions, real identity verification, MFA, authorization, rate limits, audit trails, encrypted evidence storage where applicable, hardened secret management, backup and retention/deletion requirements before any real deployment.
- Never automatically credit MT5 from browser redirects. Use reconciled signed webhook/payment-status results and a compliant ownership decision. Use idempotent credit operations.
- This demo includes a basic CSRF token, hashed passwords, upload limits, image re-encoding, and admin-only image access. These are **not sufficient** for production security.

## Official references
- Ottu Checkout: https://docs.ottu.com/developers/payments/checkout-api/
- Ottu tokenization: https://docs.ottu.com/developers/cards-and-tokens/tokenization/
- Sumsub: https://docs.sumsub.com/docs/payment-method-check-advanced
- Sumsub applicant actions: https://docs.sumsub.com/docs/applicant-actions

## Where to find the explanatory notes in the app
- Open **http://127.0.0.1:5000/notes** or click **Implementation Notes** in the top navigation.
- This page gives the recommended build order, Sumsub evidence-handling caveats, token storage, retention, identifiers and vendor questions.
- The **Architecture** page (`/architecture`) contains the high-level flow diagram as text.
- The **Client Portal** is for simulated registration, card submission and deposits; the **Admin Portal** is for mock verification review.

## New workflow notes
This mock takes only dummy masked metadata on the Ottu-like page; a production hosted checkout collects real payment credentials only on the Ottu/PSP domain. Matching BIN, last four, name and expiry is not proof that two cards are identical. Implement a strong provider-supported binding before live use.


## v3 flow change (image-only Sumsub)
- Sumsub mock page asks **only** for a fabricated card image. Admin approves/rejects image evidence.
- For a client's **first** deposit there is no saved-card picker. A separate simulated Ottu checkout asks for fictional holder name, BIN, last four digits and expiry. Never supply actual card credentials here.
- A synthetic token is created only after simulated successful payment; no token is created by Sumsub approval or a declined payment.
- On **second** and later deposits an approved, previously paid saved-card option appears. The 16-digit card number is displayed as `•••• •••• •••• 3456` (example); the client must enter a fictional 3–4 digit CVV on the hosted demo screen. It is cleared before HTTP submission; the backend receives only a mock confirmation marker. Real CVV collection belongs entirely to the true PSP-hosted checkout, never the AZM backend.
- The mock is not an ownership verifier: neither image-only admin review nor KYC-name matching can prove the uploaded image and later payment instrument represent the same card. Real integration must bind a Sumsub verification result to a PSP-provided stable identifier.


## v6 — Add another card
In the client portal's **Make a deposit** section, choose **+ Use another card — Start new Sumsub verification** and enter the intended amount. The app redirects to `/cards/new` to upload a NEW dummy card image, creates a separate mock Sumsub action and marks it pending. The demo admin must approve the new evidence. The client can then select the newly approved card and continue to Ottu-style first-time card entry. Only after its first successful simulated payment is a new synthetic token created; thereafter this card appears in the previously used options. The existing previously used card stays available. No real Sumsub/Ottu calls occur.

**Deployment:** commit the updated `app.py`, `templates/client.html` and documentation to the same GitHub repository. Render connected to that branch will normally auto-deploy on new commits; otherwise use Render Dashboard → Manual Deploy → Deploy latest commit. Do not upload local DB files or card images.
