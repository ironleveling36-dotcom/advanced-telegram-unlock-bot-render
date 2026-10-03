# Advanced Telegram Unlock Bot

Render-ready Telegram webhook bot with colorful inline buttons, per-link referral counts, admin-granted full unlock, UTR payment submission and admin approval.

## Render variables
BOT_TOKEN, ADMIN_IDS, WEBHOOK_URL, PAYMENT_QR_URL, PAYMENT_TEXT.

## Admin commands
/addlink TITLE | URL | REFCOUNT
/removelink ID
/setref LINK_ID COUNT
/grant USER_ID [LINK_ID|ALL]
/admin

Admin-granted users are fully unlocked without referral requirements.

This version does not collect Gmail passwords, OTPs, bank credentials, cookies, or hidden arbitrary user input.
