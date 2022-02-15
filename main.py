import subprocess
import discord
import requests
import json
import re
import asyncio
import time
from discord.ext import tasks
from discord.ext.commands import Bot
from discord_slash import SlashCommand


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
        'LRC-PERP',
        'DOT-PERP',
    ],
    'OTMyNDQyMTE2NTY1NjU5NzY4.YeTCZA.Hg0jgaIPa8dVPpo1M_kKTQREB4I': [
        'RAY-PERP',
        'SRM-PERP',
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


def get_usd_cad_conversion():
    try:
        return float(json.loads(requests.get("https://api.coinbase.com/v2/exchange-rates", params={"currency": "USD"}).content)['data']['rates']['CAD'])
    except:
        return 1 / float(json.loads(requests.get('https://ftx.com/api/markets/CAD/USD').content)['result']['last'])

def clear_alert(self, rank, up_or_down):
    # Open JSON file with persistent alert prices
    with open('price_alerts.json') as json_file:
        data = json.load(json_file)

        if (up_or_down == 'up'):
            data[self.client.pairs[rank].upper()]['up'] = None
        elif (up_or_down == 'down'):
            data[self.client.pairs[rank].upper()]['down'] = None
    
        # Dump in-memory JSON to persistent JSON file
        with open('price_alerts.json', 'w') as outfile:
                json.dump(data, outfile, indent=4)

    # Clear client var alert prices
    if (rank == 0):
        if (up_or_down == 'up'):
            self.client.prim_alert_up = None
        elif (up_or_down == 'down'):
            self.client.prim_alert_down = None
    elif (rank == 1):
        if (up_or_down == 'up'):
            self.client.sec_alert_up = None
        elif (up_or_down == 'down'):
            self.client.sec_alert_down = None


class PriceBot:
    def __init__(self, bot_token, group):
        self.client = Bot(command_prefix='p!', intents=intents)
        self.slash = SlashCommand(self.client)
        self.client.load_extension('jishaku')
        self.client.load_extension('commandhandler')

        self.client.is_stale = False
        self.client.stale_end_trigger = None

        self.token = bot_token

        if (len(group) > 1):
            self.client.combined = True
        else:
            self.client.combined = False

        self.client.group = group
        self.client.pairs = []

        for trading_pair in self.client.group:
            self.client.pairs.append(re.sub('-PERP', '', trading_pair))

        # Load persistent alert prices into class variables
        with open('price_alerts.json') as json_file:
            data = json.load(json_file)

            self.client.prim_alert_up = data[self.client.pairs[0]]['up']
            self.client.prim_alert_down = data[self.client.pairs[0]]['down']
            self.client.sec_alert_up = data[self.client.pairs[1]]['up']
            self.client.sec_alert_down = data[self.client.pairs[1]]['down']


        self.on_ready = self.client.event(self.on_ready)

    def is_stale(self):
        if not self.client.is_stale:
            self.client.is_stale = True
            self.client.stale_end_trigger = time.monotonic() + 60
        elif self.client.is_stale:
            if int(time.monotonic) > int(self.client.stale_end_trigger):
                self.client.is_stale = False
                pipe = subprocess.Popen("sudo service crypto-price-bots restart", shell=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)


    @tasks.loop(seconds=loop_time*4)
    async def check_if_price_stale(self):
        guild = self.client.get_guild(696082479752413274)
        bot_member = guild.get_member(self.client.user.id)

        nick_price = float(re.findall(r"\d+\.\d+", bot_member.nick)[0])
        cur_price = get_price(self.client.group[0])
        variability_threshold = cur_price * 0.01
        # If lower threshold is larger than displayed price or higher threshold is smaller than displayed price, we have a slight problem
        if cur_price - variability_threshold > nick_price or cur_price + variability_threshold < nick_price:
            # Assume there might be volume spike and just mention it *could* be stale
            await self.client.change_presence(status=discord.Status.idle)
            self.is_stale()

        if cur_price - variability_threshold*2 > nick_price or cur_price + variability_threshold*2 < nick_price:
            # Now we have a larger problem
            await self.client.change_presence(status=discord.Status.dnd)
            self.is_stale()

        # Repeat checks if it is combined bot
        if self.client.combined == True:
            # Activity is not immediately set on launch, so check that bot has activity first
            if len(bot_member.activities) != 0:
                # Same as above code by vars changed to reflect secondary coin
                status_price = float(re.findall(r"\d+\.\d+", bot_member.activities[0].name)[0])
                cur_price = get_price(self.client.group[1])
                variability_threshold = cur_price * 0.01
                # If lower threshold is larger than displayed price or higher threshold is smaller than displayed price, we have a slight problem
                if cur_price - variability_threshold > status_price or cur_price + variability_threshold < status_price:
                    # Assume there might be volume spike and just mention it *could* be stale
                    await self.client.change_presence(status=discord.Status.idle)
                    self.is_stale()

                if cur_price - variability_threshold*2 > status_price or cur_price + variability_threshold*2 < status_price:
                    # Now we have a larger problem
                    await self.client.change_presence(status=discord.Status.dnd)
                    self.is_stale()

    @tasks.loop(seconds=loop_time)
    async def update_price(self):
        guild = self.client.get_guild(696082479752413274)

        usd_price_1 = get_price(self.client.group[0])  
        if self.client.combined == True:
            usd_price_2 = get_price(self.client.group[1])

        conversion_ratio = get_usd_cad_conversion()
        cad_price_1 = usd_price_1 * conversion_ratio

        # Check if any alerts triggered
        # Check primary asset
        if self.client.prim_alert_up:
            alert_channel = self.client.get_channel(696082479752413277)
            alert_role = guild.get_role(798457594661437450)
            if usd_price_1 > self.client.prim_alert_up:
                await alert_channel.send(f"\U0001f4c8 {alert_role.mention} {self.client.user.mention} is above {self.client.prim_alert_up}.")
                clear_alert(self, 0, 'up')
        if self.client.prim_alert_down:
            alert_channel = self.client.get_channel(696082479752413277)
            alert_role = guild.get_role(798457594661437450)
            if usd_price_1 < self.client.prim_alert_down:
                await alert_channel.send(f"\U0001f4c9 {alert_role.mention} {self.client.user.mention} is below {self.client.prim_alert_down}.")
                clear_alert(self, 0, 'down')

        # Check secondary asset
        if self.client.combined == True:
            if self.client.sec_alert_up:
                alert_channel = self.client.get_channel(696082479752413277)
                alert_role = guild.get_role(798457594661437450)
                if usd_price_2 > self.client.sec_alert_up:
                    await alert_channel.send(f"\U0001f4c8 {alert_role.mention} {self.client.user.mention} is above {self.client.sec_alert_up}.")
                    clear_alert(self, 1, 'up')
            if self.client.sec_alert_down:
                alert_channel = self.client.get_channel(696082479752413277)
                alert_role = guild.get_role(798457594661437450)
                if usd_price_2 < self.client.sec_alert_down:
                    await alert_channel.send(f"\U0001f4c9 {alert_role.mention} {self.client.user.mention} is below {self.client.sec_alert_down}.")
                    clear_alert(self, 1, 'down')

        # Format for bot users
        #
        # TICKER - $price.xx
        # Playing CA$price.xx
        #
        # or
        #
        # 1st Coin TICKER - $price.xx
        # 2nd Coin TICKER - $price.xx


        await guild.me.edit(nick=f"{self.client.pairs[0]} - ${round(usd_price_1, 4)}")

        if self.client.combined == True:
            await self.client.change_presence(activity=discord.Game(f"{self.client.pairs[1]} - ${round(usd_price_2, 4)}"))
        else:
            await self.client.change_presence(activity=discord.Game(f"CA${round(cad_price_1, 4)}"))

    async def on_ready(self):
        self.update_price.start()
        self.check_if_price_stale.start()
        if self.client.combined == True:
            print(f"{self.client.pairs[0]}/{self.client.pairs[1]} loaded")
        else:
            print(f"{self.client.pairs[0]} loaded")

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
