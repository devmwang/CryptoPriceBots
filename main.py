import os
from dotenv import load_dotenv
from multiprocessing import Process
import subprocess
import discord
import requests
import json
import re
import asyncio
import time
import websockets
from discord.ext import commands, tasks

import alert_handler


# Initialize Env Variables
load_dotenv()

# Get Bot Tokens from Env Vars
MATIC_TOKEN = os.getenv('MATIC_TOKEN')

bots = {
    MATIC_TOKEN: [
        'MATIC',
    ],
}


intents = discord.Intents.default()
intents.message_content = True
delete_cooldown = 3
loop_time = 12


def get_rest_price(ticker):
    response = requests.get(f"https://ftx.com/api/markets/{ticker}-PERP")
    data = json.loads(response.content)
    return float(data['result']['last'])

def get_usd_cad_conversion():
    try:
        return float(json.loads(requests.get("https://api.coinbase.com/v2/exchange-rates", params={"currency": "USD"}).content)['data']['rates']['CAD'])
    except:
        return 1 / float(json.loads(requests.get('https://ftx.com/api/markets/CAD/USD').content)['result']['last'])

def CryptoPriceBot(bot_token, assets):
    # * Initialization
    client = discord.Client(intents=intents,
                            status=discord.Status.idle,
                            activity=discord.Game(name="Initializing..."))

    client.dual = True if len(assets) == 2 else False

    client.last_ws_update = [None, None]
    client.discord_api_gets = 0
    client.discord_api_posts = 0
    client.start_time = int(time.time())

    client.dc_threshold_time = None
    client.status_message = None

    client.assets = assets

    client.usd_price = [get_rest_price(client.assets[0]), get_rest_price(client.assets[1])] if client.dual else [get_rest_price(client.assets[0])]

    # * Set Price Alerts
    client.alert_up = [None, None]
    client.alert_down = [None, None]

    with open('price_alerts.json') as json_file:
        data = json.load(json_file)

        client.alert_up[0] = data[client.assets[0]]['up']
        client.alert_down[0] = data[client.assets[0]]['down']

        if client.dual:
            client.alert_up[1] = data[client.assets[1]]['up']
            client.alert_down[1] = data[client.assets[1]]['down']

    # * Set Variability Threshold
    client.variability_threshold = [None, None]

    with open('settings.json') as json_file:
        data = json.load(json_file)

        client.variability_threshold[0] = data["variability-threshold"][client.assets[0]]

        if client.dual:
            client.variability_threshold[1] = data["variability-threshold"][client.assets[1]]

    # * Main Bot Loop
    async def main_loop():
        alert_channel = client.get_channel(696082479752413277)
        alert_role = client.guild.get_role(798457594661437450)

        # async with websockets.connect("wss://ftx.com/ws", ping_interval=15) as websocket:
        async for websocket in websockets.connect("wss://ftx.com/ws", ping_interval=15):
            try:
                await websocket.send(f'{{"op": "subscribe", "channel": "trades", "market": "{client.assets[0]}-PERP"}}')

                if client.dual:
                    await websocket.send(f'{{"op": "subscribe", "channel": "trades", "market": "{client.assets[1]}-PERP"}}')

                while True:
                    data = json.loads(await websocket.recv())

                    if data['type'] == "update":
                        if data['market'] == f"{client.assets[0]}-PERP":
                            group_index = 0

                        elif client.dual and data['market'] == f"{client.assets[1]}-PERP":
                            group_index = 1

                        client.last_ws_update[group_index] = int(time.time())

                        client.usd_price[group_index] = float(data['data'][0]['price'])

                        # Check Alerts (Since every iteration loop only gets new data for one asset, we only need to check alert on one asset)
                        if client.alert_up[group_index]:
                            if client.usd_price[group_index] > client.alert_up[group_index]:
                                await alert_channel.send(f"\U0001f4c8 {alert_role.mention} {client.assets[group_index]} is above {client.alert_up[group_index]}.")
                                alert_handler.clear_alert(client, group_index, 'up')
                        if client.alert_down[group_index]:
                            if client.usd_price[group_index] < client.alert_down[group_index]:
                                await alert_channel.send(f"\U0001f4c9 {alert_role.mention} {client.assets[group_index]} is below {client.alert_down[group_index]}.")
                                alert_handler.clear_alert(client, group_index, 'down')

                        # Get currently displayed prices from Discord API
                        bot_display_price = [None, None]

                        bot_member = client.guild.get_member(client.user.id)

                        # Add 1 to API GET counter
                        client.discord_api_gets += 1

                        if group_index == 0:
                            # Bot nickname can be formatted incorrectly for regex, try to parse, otherwise manually set display price to near $0 to force update
                            try:
                                bot_display_price[0] = float(re.findall(r"\d+\.\d+", bot_member.nick)[0])
                            except Exception:
                                bot_display_price[0] = float(10**-10)

                        elif group_index == 1:
                            # Bot activity will be None during cold start, try to parse existing activity, otherwise manually set display price to near $0 to force update
                            if bot_member.activity is not None:
                                try:
                                    bot_display_price[1] = float(re.findall(r"\d+\.\d+", bot_member.activity.name)[0])
                                except IndexError:
                                    bot_display_price[1] = float(10**-10)
                            else:
                                bot_display_price[1] = float(10**-10)

                        # Calculate delta factor between actual price and displayed price
                        delta_factor = abs(1-(client.usd_price[group_index] / bot_display_price[group_index]))

                        if delta_factor > client.variability_threshold[group_index]:
                            await update_display(group_index)
                            client.discord_api_posts[group_index] += 1

                    elif data['type'] == "subscribed" or data['type'] == "unsubscribed":
                        pass
                    elif data['type'] == "info" and data['code'] == 20001:
                        raise websockets.ConnectionClosed
                    else:
                        await alert_channel.send(f"could not parse `{data}`")
                        print(data)
            except Exception:
                continue

    # * Task Loops
    @tasks.loop(hours=1)
    async def update_cad_usd_conversion():
        client.usd_cad_conversion = get_usd_cad_conversion()

    # * Update Displayed Price
    async def update_display(group_index):
        # Format for dual asset price bots
        #
        # Primary Asset TICKER - $price.xx (USD)
        # Primary Asset TICKER - $price.xx (CAD)
        #
        # Format for dual asset price bots
        #
        # Primary Asset TICKER - $price.xx (USD)
        # Secondary Asset TICKER - $price.xx (USD)

        if (group_index == 0):
            await client.guild.me.edit(nick=f"{client.pairs[0]} - ${round(client.usd_price[0], 4)}")
        elif (group_index == 1):
            if client.dual:
                # Set status based on current disconnected status
                if client.disconnected[0] == True or client.disconnected[1] == True:
                    await client.change_presence(activity=discord.Game(f"{client.pairs[1]} - ${round(client.usd_price[1], 4)}"), status=discord.Status.dnd)
                else:
                    await client.change_presence(activity=discord.Game(f"{client.pairs[1]} - ${round(client.usd_price[1], 4)}"), status=discord.Status.online)
            else:
                # Set status based on current disconnected status
                if client.disconnected[0] == True or client.disconnected[1] == True:
                    await client.change_presence(activity=discord.Game(f"CA${round((client.usd_price[0] * client.usd_cad_conversion), 4)}"), status=discord.Status.dnd)
                else:
                    await client.change_presence(activity=discord.Game(f"CA${round((client.usd_price[0] * client.usd_cad_conversion), 4)}"), status=discord.Status.online)

    # * On Ready
    @client.event
    async def on_ready():
        client.guild = client.get_guild(696082479752413274)

        update_cad_usd_conversion.start()
        # check_last_ws_msg.start()

        console_message = (f"{client.assets[0]}/{client.assets[1]} loaded.") if client.dual else (f"{client.assets[0]} loaded.")

        print(console_message)

        # Bot Status System
        bot_status_channel = client.get_channel(951549833368461372)

        # Clear Status Channel of Previous Statuses
        messages = []

        async for message in bot_status_channel.history():
            if message.author == client.user:
                messages.append(message)

        await bot_status_channel.delete_messages(messages)

        # Create Bot Status Message
        if client.dual:
            client.status_msg = await bot_status_channel.send(f"""{client.assets[0]} WS Status: :green_circle:
{client.assets[1]} WS Status: :green_circle:""")
        else:
            client.status_msg = await bot_status_channel.send(f"{client.assets[0]} WS Status: :green_circle:")

        await main_loop()
    
    # * Run Bot
    client.run(bot_token)


def main():
    processes = []

    for bot_token in bots:
        new_process = Process(target = CryptoPriceBot, args = (bot_token, bots[bot_token],))
        new_process.start()
        processes.append(new_process)

    for process in processes:
        process.join()


if __name__ == '__main__':
    main()
