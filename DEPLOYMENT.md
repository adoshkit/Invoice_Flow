# Deploy InvoiceFlow

This project is a Streamlit application. The repository can remain private, and Streamlit Community Cloud can deploy from a private repository after you authorize access.

## 1. Put the project in your home directory

Extract the ZIP. The resulting folder should be:

```text
~/Invoice_Flow/
    app.py
    db.py
    pipeline.py
    requirements.txt
    packages.txt
    colours.txt
    samples/
    ...
```

If the extracted folder is named `invoiceflow`, rename it:

```bash
mv ~/invoiceflow ~/Invoice_Flow
cd ~/Invoice_Flow
```

If it is already named `Invoice_Flow`, just run `cd ~/Invoice_Flow`.

## 2. Test locally

```bash
cd ~/Invoice_Flow
python3 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
pip install -r requirements.txt
streamlit run app.py
```

Open the local URL printed by Streamlit, usually `http://localhost:8501`. The demo login is `admin` / `admin`.

Optional Gemini extraction:

```bash
pip install -r requirements-gemini.txt
```

Put the API key in a local `.env` file, not in Python source or Git:

```bash
cp .env.example .env
nano .env
```

Set `GEMINI_API_KEY` in `.env` if you use Gemini. The `.gitignore` excludes `.env`.

## 3. Create and push the private GitHub repository

Create an **empty private repository** named `Invoice_Flow` under the GitHub account `adoshkit`. Do not initialize it with a README, license, or `.gitignore`, because the project already contains those files.

Then run:

```bash
cd ~/Invoice_Flow
git init
git branch -M main
git add .
git status
```

Check the staged files. Confirm that `.env`, `.streamlit/secrets.toml`, database files, and personal credentials are not listed. Then:

```bash
git commit -m "Initial InvoiceFlow application"
git remote add origin https://github.com/adoshkit/Invoice_Flow.git
git push -u origin main
```

If Git asks you to authenticate, use GitHub's browser sign-in or a GitHub Personal Access Token; do not put a token in the remote URL or save it in the repository.

## 4. Deploy from the private repository

1. Open [Streamlit Community Cloud](https://share.streamlit.io/) and sign in with GitHub.
2. If prompted, authorize Streamlit to access private repositories. You can review this under Streamlit's linked-account settings.
3. Select **Create app**.
4. Choose repository `adoshkit/Invoice_Flow`, branch `main`, and main file path `app.py`.
5. Deploy. The app will receive a `streamlit.app` URL.

A private GitHub repository does not automatically mean the deployed app is private on every hosting platform. Streamlit Community Cloud currently inherits repository permissions: an app deployed from a private repository is private by default. Use the app's **Sharing** settings to control viewers and invite specific people. Check the current sharing controls before sending the link.

## 5. Configure hosted secrets

In Streamlit Community Cloud, open the app's **Settings → Secrets** and add:

```toml
INVOICEFLOW_ADMIN_USER = "admin"
INVOICEFLOW_ADMIN_PASSWORD = "admin"
```

These values are accepted as requested for the demo. They are not GitHub repository secrets and must not be committed to Git. For any app exposed beyond trusted viewers, replace the password with a unique strong password. The app's admin account can change invoice decisions and review history.

If using Gemini, add this to the same Secrets area:

```toml
GEMINI_API_KEY = "your-real-api-key"
```

Do not paste a real API key into source files, README files, screenshots, or Git commits.

## 6. Push later changes

```bash
cd ~/Invoice_Flow
git add .
git commit -m "Describe your change"
git push
```

Streamlit Community Cloud detects the push and redeploys the app.

## Data persistence limitation

The app stores run history in a local SQLite database. A hosted app's local filesystem should not be treated as durable storage; data may be lost when the app is rebuilt or its container is replaced. This deployment is suitable for a demo, not production financial records. A production deployment needs a persistent database, backups, and stronger authentication and authorization.

## Official guides

- [Deploy an app](https://docs.streamlit.io/deploy/streamlit-community-cloud/deploy-your-app/deploy)
- [Connect GitHub and authorize private repositories](https://docs.streamlit.io/deploy/streamlit-community-cloud/get-started/connect-your-github-account)
- [Share public and private apps](https://docs.streamlit.io/deploy/streamlit-community-cloud/share-your-app)
- [Manage app settings and secrets](https://docs.streamlit.io/deploy/streamlit-community-cloud/manage-your-app/app-settings)
