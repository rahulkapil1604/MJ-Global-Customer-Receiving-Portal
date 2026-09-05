# MJ Global Pvt Ltd Customer Receiving Portal v2

Integrated with Android v1.3. Android creates unique no-login receiving links via `/api/receiving-links`. Customer uploads photo/PDF, submits, and the portal automatically mails the proof to the notification email stored with that link.

Setup: copy `config.example.json` to `config.json`, set Gmail sender/App Password, `public_base_url`, and a long random `api_key`. Use the same URL/API key in Android > More > Gmail & Portal Settings. For customers on the internet, use a public HTTPS URL.
