# Gmail Integration Setup

AURIX can check, search, and send emails through the Gmail API using OAuth2.

## Step 1: Enable the Gmail API

1. Go to [Google Cloud Console](https://console.cloud.google.com/)
2. Select your project (or create one -- yours is `aurix-493110`)
3. Navigate to **APIs & Services > Library**
4. Search for "Gmail API" and click **Enable**

## Step 2: Create OAuth2 Credentials

1. Go to **APIs & Services > Credentials**
2. Click **+ CREATE CREDENTIALS > OAuth client ID**
3. Application type: **Desktop app**
4. Name: `AURIX`
5. Click **Create**, then **Download JSON**
6. Save the file as `config/gmail_credentials.json` in the AURIX project root

If you already have a `config/gmail_credentials.json` file, skip this step.

## Step 3: Configure the OAuth Consent Screen

1. Go to **APIs & Services > OAuth consent screen**
2. User type: **External** (or Internal if using Google Workspace)
3. Fill in:
   - App name: `AURIX`
   - User support email: your email
   - Developer contact: your email
4. Under **Scopes**, add:
   - `https://www.googleapis.com/auth/gmail.readonly`
   - `https://www.googleapis.com/auth/gmail.send`
5. Under **Test users**, add your own Gmail address
6. Click **Save**

## Step 4: First Authorization

Run AURIX and say one of:
- "Hey Jarvis, check my email"
- "Hey Jarvis, read my recent emails"

On the first run, a browser window will open asking you to sign in with your
Google account and authorize AURIX. After you approve:

- A token is saved at `config/gmail_token.json`
- Subsequent runs use the cached token (no browser needed)
- The token auto-refreshes; you should only need to re-authorize if you
  revoke access or change scopes

## Step 5: Install Dependencies

```
pip install google-auth google-auth-oauthlib google-api-python-client
```

Or just run `pip install -r requirements.txt`.

## File Locations

```
config/
  gmail_credentials.json   <-- OAuth client secret (from Google Cloud Console)
  gmail_token.json         <-- Auto-generated after first authorization
```

## Voice Commands

| Command | What it does |
|---|---|
| "check my email" | Shows unread count |
| "read my recent emails" | Reads last 5 email subjects + senders |
| "send an email to john@example.com about meeting" | Composes and sends |
| "search emails for invoice" | Searches by keyword |

## Troubleshooting

**"Gmail credentials not found"**
- Make sure `config/gmail_credentials.json` exists and is valid JSON
- Re-download from Google Cloud Console if needed

**"Token has been expired or revoked"**
- Delete `config/gmail_token.json` and re-run to trigger the OAuth flow again

**"Access blocked: This app's request is invalid"**
- Make sure your email is listed under **Test users** in the OAuth consent screen
- Make sure the Gmail API is enabled for your project

**"Insufficient Permission"**
- Delete `config/gmail_token.json` to re-authorize with the correct scopes
