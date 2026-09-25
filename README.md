# FF Autolikes Shop Bot

This version uses **no Like API**. AutoLike orders are paid with coins, sent to the admin for approval, and the admin manually delivers the likes. At 4:00 AM IST the bot sends the admin a reminder containing active AutoLike UIDs.

## Setup

1. Install `requirements.txt`.
2. Copy `.env.example` to `.env`.
3. Set `TELEGRAM_TOKEN` and `OWNER_IDS`.
4. Run `python main.py`.
5. Open `/start` in Telegram.

## Important

- `database.json` is created automatically.
- Existing `database.json` data from the older bot is preserved where possible.
- Payment QR is easiest to set from **Admin Panel -> Settings -> UPI / Payment Details** by sending the Telegram `file_id` of the QR image.
- Set the How-to-Pay link from **Admin Panel -> Settings -> How to Pay Link**.
- Create redeem codes and Verify & Earn tasks from the Admin Panel.
