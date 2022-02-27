import subprocess
import discord
import requests
import json
import re
import asyncio
import time
import websockets
from discord.ext import tasks
from discord.ext.commands import Bot
from discord_slash import SlashCommand

import alert_handler


groups = {
    # 'ODM5NjY2NjU4NjQ1OTAxMzIy.YJM-gw.JryOhVS2hdlX3gu5_htRgusDUFk': [
    #     'BTC-PERP',
    # ],
    # 'ODM5NjY3MDg4OTQ3ODA2Mjc4.YJM-6g._W4Z89u1-PE9F_jGs8nHeLPil8E': [
    #     'ETH-PERP',
    # ],
    # 'ODYwMDQxMDk4NTU4MDQ2MjA5.YN1dsA.nSk77b0x0s6gP4IsSwvVnPmRZks': [
    #     'SOL-PERP',
    # ],
    # 'ODYyODAyMjY3MTY5NzUxMDQ4.YOdpOg.eauZzdh8U51H3umSOTOWh2fe9BU': [
    #     'FTT-PERP',
    # ],
    # 'ODk1NzAyMTAyOTM5MTQ0Mjc0.YV8Zlg.Wj7CH-HrcJxxJXNDpDc_r6UTsVo': [
    #     'MATIC-PERP',
    # ],
    'OTE1Nzg0OTI4MTE1OTQ5NTY5.YagpLQ.swfkjBpwoSp9JpIknVD134xld_U': [
        'MATIC-PERP',
        'LRC-PERP',
    ],
    'OTM4ODQ1MjE5ODIxMDkyOTE3.YfwNvw.6HcRPj1_YbZBOd93AxSRaBVVCA0': [
        'LUNA-PERP',
        'DOT-PERP'
    ],
    'OTA4MjE3MDk2NTc0NDY4MTM2.YYyhFQ.eMtJCaZesp94kX_ZbBL1XZWrq6k': [
        'UNI-PERP',
        'AAVE-PERP',
    ],
    'ODk4MDEyMDE0OTg5OTM4NzQ4.YWeA3A.o3Lo7BC1vAwvL-lp1vAUr-xsdkA': [
        'LINK-PERP',
        'LTC-PERP',
    ],
}


intents = discord.Intents.default()
intents.members = True
delete_cooldown = 3
loop_time = 12
variability = 0.0015


def get_usd_cad_conversion():
    try:
        return float(json.loads(requests.get("https://api.coinbase.com/v2/exchange-rates", params={"currency": "USD"}).content)['data']['rates']['CAD'])
    except:
        return 1 / float(json.loads(requests.get('https://ftx.com/api/markets/CAD/USD').content)['result']['last'])


class PriceBot:
    def __init__(self, bot_token, group):
        self.client = Bot(command_prefix='p!', intents=intents)
        self.slash = SlashCommand(self.client)
        self.client.load_extension('jishaku')
        self.client.load_extension('command_handler')
        
        self.token = bot_token

        self.client.paused = False

        self.client.last_ws_update = [None, None]
        self.client.discord_api_gets = 0
        self.client.discord_api_posts = [0, 0]
        self.client.start_time = int(time.time())

        self.client.usd_price = [None, None]

        self.client.is_stale = False
        self.client.stale_end_trigger = None

        self.client.group = group
        self.client.pairs = []

        for trading_pair in self.client.group:
            self.client.pairs.append(re.sub('-PERP', '', trading_pair))

        # Init persistent alert prices into class variables
        self.client.alert_up = self.client.alert_down = [None, None]

        with open('price_alerts.json') as json_file:
            data = json.load(json_file)

            self.client.alert_up[0] = data[self.client.pairs[0]]['up']
            self.client.alert_down[0] = data[self.client.pairs[0]]['down']
            self.client.alert_up[1] = data[self.client.pairs[1]]['up']
            self.client.alert_down[1] = data[self.client.pairs[1]]['down']

        self.on_ready = self.client.event(self.on_ready)

    async def main_loop(self):
        alert_channel = self.client.get_channel(696082479752413277)
        alert_role = self.client.guild.get_role(798457594661437450)

        # async with websockets.connect("wss://ftx.com/ws", ping_interval=15) as websocket:
        async for websocket in websockets.connect("wss://ftx.com/ws", ping_interval=15):
            try:
                await websocket.send(f'{{"op": "subscribe", "channel": "trades", "market": "{self.client.group[0]}"}}')
                await websocket.send(f'{{"op": "subscribe", "channel": "trades", "market": "{self.client.group[1]}"}}')

                while True:
                    data = json.loads(await websocket.recv())

                    if data['type'] == "update":
                        if data['market'] == self.client.group[0]:
                            group_index = 0
                        elif data['market'] == self.client.group[1]:
                            group_index = 1

                        self.client.last_ws_update[group_index] = int(time.time())

                        self.client.usd_price[group_index] = float(data['data'][0]['price'])

                        # Check Alerts (Since every iteration loop only gets new data for one asset, we only need to check alert on one asset)
                        if self.client.alert_up[group_index]:
                            if self.client.usd_price[group_index] > self.client.alert_up[group_index]:
                                await alert_channel.send(f"\U0001f4c8 {alert_role.mention} {self.client.user.mention} is above {self.client.alert_up[group_index]}.")
                                alert_handler.clear_alert(self, [group_index], 'up')
                        if self.client.alert_down[group_index]:
                            if self.client.usd_price[group_index] < self.client.alert_down[group_index]:
                                await alert_channel.send(f"\U0001f4c9 {alert_role.mention} {self.client.user.mention} is below {self.client.alert_down[group_index]}.")
                                alert_handler.clear_alert(self, [group_index], 'down')

                        # Get currently displayed prices from Discord API
                        bot_display_price = [None, None]

                        bot_member = self.client.guild.get_member(self.client.user.id)

                        # Add 1 to API GET counter
                        self.client.discord_api_gets += 1

                        bot_display_price[0] = float(re.findall(r"\d+\.\d+", bot_member.nick)[0])

                        # Bot activity will be None during cold start, try to parse existing activity, otherwise manually set display price to near $0 to force update
                        if bot_member.activity is not None:
                            try:
                                bot_display_price[1] = float(re.findall(r"\d+\.\d+", bot_member.activity.name)[0])
                            except IndexError:
                                bot_display_price[1] = float(10**-10)
                        else:
                            bot_display_price[1] = float(10**-10)

                        # Calculate delta factor between actual price and displayed price
                        delta_factor = abs(1-(self.client.usd_price[group_index] / bot_display_price[group_index]))

                        if delta_factor > variability:
                            await self.update_display(group_index)
                            self.client.discord_api_posts[group_index] += 1

                    elif data['type'] == "subscribed" or data['type'] == "unsubscribed":
                        pass
                    elif data['type'] == "info" and data['code'] == 20001:
                        raise websockets.ConnectionClosed
                    else:
                        await alert_channel.send(f"could not parse `{data}`")
                        print(data)
            except websockets.exceptions.ConnectionClosedError:
                continue
            except websockets.ConnectionClosed:
                continue

    @tasks.loop(minutes=30)
    async def update_cad_usd_conversion(self):
        if self.client.paused:
            return

        self.client.cad_usd_conversion_ratio = get_usd_cad_conversion()

    @tasks.loop(seconds=10)
    async def check_last_ws_msg(self):
        if self.client.paused:
            return

        disconnected = [False, False]

        if self.client.last_ws_update[0] is not None and (self.client.last_ws_update[0] + 30) < int(time.time()):
            disconnected[0] = True
        if self.client.last_ws_update[1] is not None and (self.client.last_ws_update[1] + 30) < int(time.time()):
            disconnected[1] = True
        
        if disconnected[0] == True and disconnected[1] == True:
            await self.client.change_presence(activity=discord.Game(f"[!] Both WS Disconnected."), status=discord.Status.dnd)
        elif disconnected[0] == True:
            await self.client.change_presence(activity=discord.Game(f"[!] Primary WS Disconnected."), status=discord.Status.dnd)
        elif disconnected[1] == True:
            await self.client.change_presence(activity=discord.Game(f"[!] Secondary WS Disconnected."), status=discord.Status.dnd)

    async def update_display(self, group_index):
        if self.client.paused:
            return

        # Format for bot users
        #
        # TICKER - $price.xx
        # Playing CA$price.xx
        #
        # or
        #
        # 1st Coin TICKER - $price.xx
        # 2nd Coin TICKER - $price.xx

        if (group_index == 0):
            await self.client.guild.me.edit(nick=f"{self.client.pairs[0]} - ${round(self.client.usd_price[0], 4)}")
        elif (group_index == 1):
            await self.client.change_presence(activity=discord.Game(f"{self.client.pairs[1]} - ${round(self.client.usd_price[1], 4)}"))

    async def on_ready(self):
        self.client.guild = self.client.get_guild(696082479752413274)

        self.update_cad_usd_conversion.start()
        self.check_last_ws_msg.start()

        print(f"{self.client.pairs[0]}/{self.client.pairs[1]} loaded.")

        await self.main_loop()

    def start(self):
        return self.client.start(self.token)


def get_price(trading_pair):
    response = requests.get(f"https://ftx.com/api/markets/{trading_pair}")
    data = json.loads(response.content)
    return float(data['result']['last'])


loop = asyncio.get_event_loop()

for group in groups:
    bot_token = group
    client = PriceBot(bot_token, groups[bot_token])
    loop.create_task(client.start())


loop.run_forever()
