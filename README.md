# CryptoPriceBots

CryptoPriceBots is a system that instantiates multiple Discord bots to relay the price of a cryptocurrency to the bot's guild nickname.

### Usage

1. Clone the repository
2. Install the dependencies in requirements.txt
3. Create a Discord bot and invite it to your server, take note of the bot's token
4. Rename `cpb_store.json.example` to `cpb_store.json`
5. In `cpb_store.json`, replace the existing tickers with your desired tickers
6. (Optional) In `cpb_store.json`, set a variability threshold for your desired tickers.
   This is the minimum percent change in price that will trigger a price update on the bot's nickname
7. Rename `.env_template` to `.env` and set the Discord bot tokens for your tickers
8. In main.py, change variables ending with `_id` to your IDs for your guild and channel
9. Run main.py
