from ctypes import sizeof
import discord
import requests
import json
import re
import asyncio
from discord.ext import tasks
from discord.ext.commands import Bot
from discord_slash import SlashCommand


groups = {
    'ODM5NjY2NjU4NjQ1OTAxMzIy.YJM-gw.JryOhVS2hdlX3gu5_htRgusDUFk': [
        'BTC-PERP',
    ],
    'ODM5NjY3MDg4OTQ3ODA2Mjc4.YJM-6g._W4Z89u1-PE9F_jGs8nHeLPil8E': [
        'ETH-PERP',
    ],
    'ODYwMDQxMDk4NTU4MDQ2MjA5.YN1dsA.nSk77b0x0s6gP4IsSwvVnPmRZks': [
        'SOL-PERP',
    ],
    'ODYyODAyMjY3MTY5NzUxMDQ4.YOdpOg.eauZzdh8U51H3umSOTOWh2fe9BU': [
        'FTT-PERP',
    ],
    'OTA4MjE3MDk2NTc0NDY4MTM2.YYyhFQ.eMtJCaZesp94kX_ZbBL1XZWrq6k': [
        'UNI-PERP',
        'AAVE-PERP',
    ],
    'ODk4MDEyMDE0OTg5OTM4NzQ4.YWeA3A.o3Lo7BC1vAwvL-lp1vAUr-xsdkA': [
        'LINK-PERP',
        'LTC-PERP',
    ],
    'ODk1NzAyMTAyOTM5MTQ0Mjc0.YV8Zlg.Wj7CH-HrcJxxJXNDpDc_r6UTsVo': [
        'MATIC-PERP',
    ],
    'OTE1Nzg0OTI4MTE1OTQ5NTY5.YagpLQ.swfkjBpwoSp9JpIknVD134xld_U': [
        'LRC-PERP',
    ],
    'OTMyNDQyMTE2NTY1NjU5NzY4.YeTCZA.Hg0jgaIPa8dVPpo1M_kKTQREB4I': [
        'RAY-PERP',
        'SRM-PERP',
    ],
}


intents = discord.Intents.default()
intents.members = True
delete_cooldown = 3
loop_time = 12


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
        # self.client.load_extension('commandhandler')

        # Init for Price Alerts functionality
        self.client.alert_up = None
        self.client.alert_down = None

        self.token = bot_token

        if (len(group) > 1):
            self.combined = True
        else:
            self.combined = False

        self.group = group
        self.pairs = []

        for trading_pair in self.group:
            self.pairs.append(re.sub('-PERP', '', trading_pair))

        self.on_ready = self.client.event(self.on_ready)

    # @tasks.loop(seconds=loop_time*4)
    # async def check_if_price_stale(self):
    #     guild = self.client.get_guild(696082479752413274)
    #     nick_price = float(re.findall(r"\d+\.\d+", guild.get_member(self.client.user.id).nick)[0])
    #     cur_price = get_price(self.pair)
    #     variability_threshold = cur_price * 0.01
    #     # If lower threshold is larger than displayed price or higher threshold is smaller than displayed price, we have a slight problem
    #     if cur_price - variability_threshold > nick_price or cur_price + variability_threshold < nick_price:
    #         # Assume there might be volume spike and just mention it *could* be stale
    #         await self.client.change_presence(activity=discord.Game(f"[!] Prices may be stale."), status=discord.Status.idle)

    #     if cur_price - variability_threshold*2 > nick_price or cur_price + variability_threshold*2 < nick_price:
    #         # Now we have a larger problem
    #         await self.client.change_presence(activity=discord.Game(f"[!!] Prices are stale."), status=discord.Status.dnd)

    @tasks.loop(seconds=loop_time)
    async def update_price(self):
        guild = self.client.get_guild(696082479752413274)

        usd_price_1 = get_price(self.group[0])  
        if self.combined == True:
            usd_price_2 = get_price(self.group[1])

        conversion_ratio = get_usd_cad_conversion()
        cad_price = usd_price_1 * conversion_ratio

        # Check if any alerts triggered
        # TODO: Rewrite alert logic to check price for both tokens (if applicable)
        if self.client.alert_up:
            alert_channel = self.client.get_channel(696082479752413277)
            alert_role = guild.get_role(798457594661437450)
            if usd_price_1 > self.client.alert_up:
                await alert_channel.send(f"\U0001f4c8 {alert_role.mention} {self.client.user.mention} is above {self.client.alert_up}.")
                self.client.alert_up = None
        if self.client.alert_down:
            alert_channel = self.client.get_channel(696082479752413277)
            alert_role = guild.get_role(798457594661437450)
            if usd_price_1 < self.client.alert_down:
                await alert_channel.send(f"\U0001f4c9 {alert_role.mention} {self.client.user.mention} is below {self.client.alert_down}.")
                self.client.alert_down = None

        # Format for bot users
        #
        # TICKER - $price.xx
        # Playing CA$price.xx
        #
        # or
        #
        # 1st Coin TICKER - $price.xx
        # 2nd Coin TICKER - $price.xx


        await guild.me.edit(nick=f"{self.pairs[0]} - ${round(usd_price_1, 4)}")

        if self.combined == True:
            await self.client.change_presence(activity=discord.Game(f"{self.pairs[1]} - ${round(usd_price_2, 4)}"))
        else:
            await self.client.change_presence(activity=discord.Game(f"CA${round(cad_price, 4)}"))

    async def on_ready(self):
        self.update_price.start()
        # self.check_if_price_stale.start()
        if self.combined == True:
            print(f"{self.pairs[0]}/{self.pairs[1]} loaded")
        else:
            print(f"{self.pairs[0]} loaded")

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
