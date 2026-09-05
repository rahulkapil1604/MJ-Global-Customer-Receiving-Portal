# MJ Global Pvt Ltd Customer Receiving Portal - Render Setup

This package is ready for Render deployment.

## Render environment variables
- `PUBLIC_BASE_URL` = your final Render URL, e.g. `https://mj-global-receiving.onrender.com`
- `PORTAL_API_KEY` = a long secret key (Render can generate this from render.yaml)
- `SENDER_EMAIL` = Gmail / Google Workspace sender address
- `GMAIL_APP_PASSWORD` = Google App Password, not normal Gmail password
- `NOTIFY_TO` = email that receives customer receiving submissions
- `NOTIFY_CC` = optional CC
- `COMPANY_NAME` = MJ Global Pvt Ltd

## Deploy
1. Upload this folder to a GitHub repository.
2. In Render choose **New + > Blueprint** and connect the repository.
3. Render reads `render.yaml` and creates the web service.
4. After first deployment, copy the public URL.
5. Set `PUBLIC_BASE_URL` to that exact URL in Render Environment.
6. Redeploy once.
7. Open `<URL>/api/health` and confirm `ok: true`.

## Android settings
In the MJ Global Pvt Ltd Android app open **More > Gmail & Portal Settings**:
- Portal Base URL = Render public URL
- Portal API Key = same `PORTAL_API_KEY`
- Receiving Notification To = your receiving email
- Receiving Notification CC = optional

## Free Render note
Free services can sleep when idle and `/tmp` is not persistent. This package is suitable for testing. For production use, move SQLite/uploads to a persistent database/storage service or a paid persistent disk.
