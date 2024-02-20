import os
import subprocess
from dotenv import load_dotenv
from multiprocessing import Process
import requests
import json
import re
import time
import websockets
import discord
from discord.ext import commands, tasks

import utils
import alert_handler


# Price Data Sources
sources = ["BinanceSpot", "BinanceFutures"]
source_endpoints = {
    # Array format: [REST Endpoint, WS Endpoint Beginning, WS Endpoint End (If applicable)]
    "BinanceSpot": {
        "REST": "https://api.binance.com/api/v3/ticker/price",
        "WS": "wss://stream.binance.com:9443/ws/",
        "WS_SUFFIX": "usdt@trade"
    },
    "BinanceFutures": {
        "REST": "https://fapi.binance.com/fapi/v1/ticker/price",
        "WS": "wss://fstream.binance.com/ws/",
        "WS_SUFFIX": "usdt@aggTrade"
    },
}

# Initialize Env Variables
load_dotenv()

# Initialize universal bot params
intents = discord.Intents.default()
intents.message_content = True

with open('cpb_store.json') as json_file:
    data = json.load(json_file)
    
    delete_cooldown = data["settings"]["system"]["delete-cooldown"]
    loop_time = data["settings"]["system"]["loop-time"]

    guild_id = data["settings"]["discord"]["guild-id"]
    alert_role_id = data["settings"]["discord"]["alert-role-id"]
    alert_channel_id = data["settings"]["discord"]["alert-channel-id"]
    bot_status_channel_id = data["settings"]["discord"]["bot-status-channel-id"]
    system_log_channel_id = data["settings"]["discord"]["system-log-channel-id"]


def initialize_with_rest(ticker):
    for source in sources:
        response = requests.get(source_endpoints[source]["REST"], params={"symbol": f"{ticker}USDT"})
        data = json.loads(response.content)

        if "price" in data:
            return [source, float(data['price'])]
    
    raise Exception(f"Could not initialize {ticker}")

def get_usd_cad_conversion():
    return float(
        json.loads(requests.get("https://api.coinbase.com/v2/exchange-rates", params={"currency": "USD"}).content)[
            'data']['rates']['CAD'])


def CryptoPriceBot(bot_token, asset):
    # * Initialization
    client = commands.Bot(command_prefix="p!", intents=intents)

    # * Initialize Utils
    client.utils = utils.Utils(client)

    # * Initialize Alert Handler
    client.alert_handler = alert_handler.AlertHandler(client)

    # * Initialize Client Variables
    client.source = None
    client.last_ws_update = None
    client.discord_api_gets = 0
    client.discord_api_posts = 0
    client.start_time = int(time.time())

    client.dc_threshold_time = None
    client.status_message = None
    client.disconnected = False

    client.asset = asset
    client.name = client.asset

    # * Set Price Alerts
    client.alert_up = None
    client.alert_down = None

    with open('cpb_store.json') as json_file:
        data = json.load(json_file)

        try: client.alert_up = data["price-alerts"][client.asset]['up']
        except KeyError: client.alert_up = None

        try: client.alert_down = data["price-alerts"][client.asset]['down']
        except KeyError: client.alert_up = None

    # * Set Variability Threshold
    client.variability_threshold = None

    with open('cpb_store.json') as json_file:
        data = json.load(json_file)

        try: client.variability_threshold = data["variability-threshold"][client.asset]
        except KeyError: client.variability_threshold = 0.001

    # * Main Bot Loop
    async def main_loop():
        alert_channel = client.get_channel(alert_channel_id)
        alert_role = client.guild.get_role(alert_role_id)

        async for websocket in websockets.connect(f'{source_endpoints[client.source]["WS"]}{client.asset.lower()}{source_endpoints[client.source]["WS_SUFFIX"]}'):
            try:
                while True:
                    data = json.loads(await websocket.recv())

                    if parse_ws_response(data):
                        # Check Alerts (Since every iteration loop only gets new data for one asset, we only need to check alert on one asset)
                        if client.alert_up:
                            if client.usd_price > client.alert_up:
                                await alert_channel.send(f"\U0001f4c8 {alert_role.mention} {client.asset} is above {client.alert_up}.")
                                client.alert_handler.clear_alert('up')
                        if client.alert_down:
                            if client.usd_price < client.alert_down:
                                await alert_channel.send(f"\U0001f4c9 {alert_role.mention} {client.asset} is below {client.alert_down}.")
                                client.alert_handler.clear_alert('down')

                        # Get currently displayed prices from Discord API
                        bot_member = client.guild.get_member(client.user.id)

                        # Add 1 to API GET counter
                        client.discord_api_gets += 1

                        # Bot nickname can be formatted incorrectly for regex, try to parse, otherwise manually set display price to near $0 to force update
                        try:
                            bot_display_price = float(re.findall(r"\d+\.\d+", bot_member.nick)[0])
                        except Exception:
                            bot_display_price = float(10**-10)

                        # Calculate delta factor between actual price and displayed price
                        delta_factor = abs(1-(client.usd_price / bot_display_price))

                        if delta_factor > client.variability_threshold:
                            await update_display()
                            client.discord_api_posts += 1
                    else:
                        await alert_channel.send(f"could not parse `{data}`")
                        print(data)
            except Exception:
                continue

    # * Task Loops
    @tasks.loop(hours=1)
    async def update_cad_usd_conversion():
        client.usd_cad_conversion = get_usd_cad_conversion()

    @tasks.loop(seconds=5)
    async def check_last_ws_msg():
        if client.last_ws_update is not None and (client.last_ws_update + 60) < int(time.time()):
            client.disconnected = True
        else:
            client.disconnected = False

        # Prolonged DC Self-Restart Logic
        # If either websocket is disconnected, run checker logic
        if client.disconnected:
            # Set bot status and rich presence
            await client.status_message.edit(content=f"{client.asset} WS Status: :red_circle:")

            await client.change_presence(activity=discord.Game(client.utils.get_activity_label()), status=discord.Status.dnd)

            # If there is already a trigger time set, check if current time is over threshold time
            if client.dc_threshold_time != None:
                curr_time = int(time.time())

                # If current time over threshold time, trigger restart
                if curr_time > client.dc_threshold_time:
                    await client.get_channel(system_log_channel_id).send(f"[PRICE BOT HEALTH SYS] Price bot service restart triggered at <t:{curr_time}:T> (<t:{curr_time}:R>)")

                    subprocess.Popen("sudo systemctl restart crypto-price-bots", shell=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)

            # If there is no trigger time set, set a trigger time 120 seconds later
            else:
                client.dc_threshold_time = (int(time.time()) + 120)

        # If no websockets are disconnected, cancel threshold if it exists
        else:
            # Cancel current threshold time
            client.dc_threshold_time = None

            # Reset bot status and rich presence in Discord
            await client.status_message.edit(content=f"{client.asset} WS Status: :green_circle:")

            await client.change_presence(activity=discord.Game(client.utils.get_activity_label()), status=discord.Status.online)

    # * Update Displayed Price
    async def update_display():
        # Format for price bots
        #
        # Primary Asset TICKER - $price.xx (USD)
        # Primary Asset TICKER - $price.xx (CAD)

        await client.guild.me.edit(nick=f"{client.asset} - ${round(client.usd_price, 4)}")

        # Set status based on current disconnected status
        if client.disconnected:
            await client.change_presence(activity=discord.Game(client.utils.get_activity_label()), status=discord.Status.dnd)
        else:
            await client.change_presence(activity=discord.Game(client.utils.get_activity_label()), status=discord.Status.online)

    # * Parse WS Response
    def parse_ws_response(data):
        if client.source == "BinanceSpot" and data['e'] == "trade":
            client.last_ws_update = int(time.time())
            client.usd_price = float(data['p'])

            return True
        
        if client.source == "BinanceFutures" and data['e'] == "aggTrade":
            client.last_ws_update = int(time.time())
            client.usd_price = float(data['p'])

            return True
        
        else:
            return False

    # * On Ready
    @client.event
    async def on_ready():
        # Initialize price data source and initial price data with rest
        price_source, rest_usd_price = initialize_with_rest(client.asset)

        client.source = price_source
        client.usd_price = rest_usd_price

        # Load extensions
        await client.load_extension('command_handler')

        # Get Discord Server
        client.guild = client.get_guild(guild_id)

        print(f"{client.name} loaded.")

        # Bot Status System
        bot_status_channel = client.get_channel(bot_status_channel_id)

        # Clear Status Channel of Previous Statuses
        messages = []

        async for message in bot_status_channel.history():
            if message.author == client.user:
                messages.append(message)

        await bot_status_channel.delete_messages(messages)

        # Create Bot Status Message
        client.status_message = await bot_status_channel.send(f"{client.asset} WS Status: :green_circle:")

        # Start Background Tasks
        update_cad_usd_conversion.start()
        check_last_ws_msg.start()

        await update_display()

        # Run main loop
        await main_loop()

    # * Run Bot
    client.run(bot_token)


def main():
    processes = []

    bots = []

    with open('cpb_store.json') as json_file:
        data = json.load(json_file)
        bots = data["tickers"]

    for bot_ticker in bots:
        bot_token = os.getenv(f"{bot_ticker}_TOKEN")

        new_process = Process(target=CryptoPriceBot, args=(bot_token, bot_ticker))
        new_process.start()
        processes.append(new_process)

    for process in processes:
        process.join()


if __name__ == '__main__':
    main()
