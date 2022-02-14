import asyncio
import json
import subprocess
import time
import re
from turtle import clear

import discord
import requests
import main
from discord.ext import commands
from discord_slash.utils.manage_components import create_button, create_actionrow, wait_for_component
from discord_slash.model import ButtonStyle
from discord_slash import ComponentContext


def get_usd_cad_conversion():
    try:
        return float(json.loads(requests.get("https://api.coinbase.com/v2/exchange-rates", params={"currency": "USD"}).content)['data']['rates']['CAD'])
    except json.decoder.JSONDecodeError:
        return 1 / float(json.loads(requests.get('https://ftx.com/api/markets/CAD/USD').content)['result']['last'])


def parse_price(price_input, cur_price):
    price_input = price_input.lower()
    try:
        amt = float(re.findall(r"\d+\.?\d*", price_input)[0])
        if "k" in price_input:
            amt *= 1000
        if "+" in price_input:
            amt += cur_price
        if "-" in price_input:
            amt -= cur_price
        if "ca" in price_input:
            conversion_ratio = get_usd_cad_conversion()
            amt /= conversion_ratio

        return round(amt, 2)

    except IndexError or ValueError:
        return None

def parse_alert_val(alert_val):
    if alert_val is None:
        return "Not Set"
    else:
        return ("$" + str(alert_val))

def set_alert(self, rank, curr_price, alert_price):
    # Check if alert_price is bigger, equal to, or somaller than curr_price
    if alert_price > curr_price:
        price_movement = 'up'
    elif alert_price < curr_price:
        price_movement = 'down'
    else:
        price_movement = 'same'

    # Only set alert if price_movement exists
    if (price_movement != 'same'):
        # Open JSON file with persistent alert prices
        with open('price_alerts.json') as json_file:
            data = json.load(json_file)

            # Assign alert to proper JSON location
            if price_movement == 'up':
                data[self.client.pairs[rank].upper()]['up'] = alert_price
            elif price_movement == 'down':
                data[self.client.pairs[rank].upper()]['down'] = alert_price

            # Dump in-memory JSON to persistent JSON file
            with open('price_alerts.json', 'w') as outfile:
                    json.dump(data, outfile, indent=4)

    # Set client variable alert price
    if price_movement == 'up':
        self.client.prim_alert_up = alert_price
        return (f"Set alert for {self.client.pairs[rank].upper()} above ${alert_price}.")
    elif price_movement == 'down':
        self.client.prim_alert_down = alert_price
        return (f"Set alert for {self.client.pairs[rank].upper()} below ${alert_price}.")
    else:
        return ("BA DING")

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
    self.client.prim_alert_up = None
    self.client.prim_alert_down = None
    self.client.sec_alert_up = None
    self.client.sec_alert_down = None


class CommandHandler(commands.Cog):
    def __init__(self, client):
        self.client = client

    @commands.Cog.listener()
    async def on_message(self, m):
        # On mention activities
        if m.content in [f"<@{self.client.user.id}>", f"<@!{self.client.user.id}>"]:
            # Buttons
            buttons = [create_button(style=ButtonStyle.green, label="Restart all"),
                       create_button(style=ButtonStyle.blue, label="View alerts"),
                       create_button(style=ButtonStyle.red, label="Clear alerts")]
            action_row = create_actionrow(*buttons)

            # Determine ticker through getting the nickname of the bot, usually in this format:
            # BTC - $30495.40
            name = m.guild.get_member(self.client.user.id).nick.split()
            msg = await m.reply(f"{main.get_price(f'{name[0]}-PERP')} USD", components=[action_row])
            try:
                while True:
                    button_ctx: ComponentContext = await wait_for_component(self.client, components=action_row, timeout=10)
                    if button_ctx.component['label'] == "Restart all":
                        await msg.edit(components=None)
                        await button_ctx.send("Restarting all price bots.")
                        try:
                            pipe = subprocess.Popen("sudo service crypto-price-bots restart", shell=True,
                                                    stdout=subprocess.PIPE, stderr=subprocess.PIPE)
                            out, err = pipe.communicate()
                            response = out.decode()
                            error = err.decode()
                            combined = response + error
                            if combined == "":
                                msg = await button_ctx.send("Price bots restarted.")
                                await asyncio.sleep(main.delete_cooldown)
                                await msg.delete()
                            else:
                                await button_ctx.send(f"```{combined}```")
                        except discord.errors.HTTPException as _e:
                            await button_ctx.send(str(_e))
                    if button_ctx.component['label'] == "View alerts":
                        embed = discord.Embed(title=f"Current Alerts", color=0x00ff00)

                        embed.add_field(name="Asset:", value=f"{self.client.pairs[0]}")
                        embed.add_field(name="Price up:", value=parse_alert_val(self.client.prim_alert_up))
                        embed.add_field(name="Price down:", value=parse_alert_val(self.client.prim_alert_down))

                        if self.client.combined == True:
                            embed.add_field(name="Asset:", value=f"{self.client.pairs[1]}")
                            embed.add_field(name="Price up:", value=parse_alert_val(self.client.sec_alert_up))
                            embed.add_field(name="Price down:", value=parse_alert_val(self.client.sec_alert_down))

                        await button_ctx.send(embed=embed)

                    if button_ctx.component['label'] == "Clear alerts":
                        await button_ctx.send(f"Cleared all alerts.")
                        clear_alert(self, 0, 'up')
                        clear_alert(self, 0, 'down')
                        clear_alert(self, 1, 'up')
                        clear_alert(self, 1, 'down')

            except asyncio.TimeoutError:
                await msg.edit(components=None)

        # Set price alerts
        # Updated price alert setter code to be compatible with combined bots
        elif m.content.upper().startswith(self.client.pairs[0]) or m.content.upper().startswith(self.client.pairs[1]):
            mlist = m.content.split()  # Should return list: [asset ticker, number]
            ticker = mlist[0]
            index = self.client.pairs.index(ticker.upper())
            
            # If primary asset: Retrieve the current display price from bot's nickname
            # If secondary asset: Retrive the current display price from bot's activity
            if index == 0:
                curr_price = float(re.findall(r"\d+\.\d+", m.guild.get_member(self.client.user.id).nick)[0])
            elif index == 1:
                curr_price = float(re.findall(r"\d+\.\d+", m.guild.get_member(self.client.user.id).activities[0].name)[0])
            else:
                raise ReferenceError("Index of ticker not 0 or 1")
            
            # If alert price not valid: Ignore since message could be generic
            # If alert price valid: Set alert
            alertstring = ""
            for i in range (1, len(mlist)):
                alertstring += mlist[i]

            alert_price = parse_price(alertstring, curr_price)
            if alert_price is None:
                return
            else:
                await m.reply(set_alert(self, index, curr_price, alert_price))

                # if index == 0:
                #     if alertprice > curr_price:
                #         self.client.prim_alert_up = alertprice
                #         await m.reply(f"Set alert for {self.client.pairs[index]} above ${alertprice}.")
                #     elif alertprice < curr_price:
                #         self.client.prim_alert_down = alertprice
                #         await m.reply(f"Set alert for {self.client.pairs[index]} below ${alertprice}.")
                #     else:
                #         await m.reply("BA DING")

                # elif index == 1:
                #     if alertprice > curr_price:
                #         self.client.sec_alert_up = alertprice
                #         await m.reply(f"Set alert for {self.client.pairs[index]} above ${alertprice}.")
                #     elif alertprice < curr_price:
                #         self.client.sec_alert_down = alertprice
                #         await m.reply(f"Set alert for {self.client.pairs[index]} below ${alertprice}.")
                #     else:
                #         await m.reply("BA DING")

    @commands.command(name="alerts")
    async def alerts(self, context):
        # If one of the alerts is not None, the bot replies with the alerts
        if self.client.prim_alert_up is not None or self.client.prim_alert_down is not None or self.client.sec_alert_up is not None or self.client.sec_alert_down is not None:
            embed = discord.Embed(title=f"Current Alerts", color=0x00ff00)
            embed.add_field(name="Asset:", value=f"{self.client.pairs[0]}")
            embed.add_field(name="Price up:", value=parse_alert_val(self.client.prim_alert_up))
            embed.add_field(name="Price down:", value=parse_alert_val(self.client.prim_alert_down))

            if self.client.combined == True:
                embed.add_field(name="Asset:", value=f"{self.client.pairs[1]}")
                embed.add_field(name="Price up:", value=parse_alert_val(self.client.sec_alert_up))
                embed.add_field(name="Price down:", value=parse_alert_val(self.client.sec_alert_down))

            await context.message.reply(embed=embed)
        await context.message.add_reaction("\U00002705")  # Add a reaction since bots without alerts don't reply

    @commands.command(name="ping")
    async def ping(self, context):
        beforeping = time.monotonic()
        messageping = await context.send("Pong!")
        pingtime = (time.monotonic() - beforeping) * 1000
        await messageping.edit(content=f"""Pong!
REST API: `{int(pingtime)}ms`
WS API Heartbeat: `{int(self.client.latency * 1000)}ms`""")

    @commands.command(name='h')
    async def h(self, context):
        if context.author.voice is None:
            await context.add_reaction("\U0000274c")
        else:
            await context.message.add_reaction("\U00002705")
            voice_client: discord.VoiceClient = discord.utils.get(self.client.voice_clients, guild=context.guild)
            if voice_client is None:
                await context.author.voice.channel.connect()
                voice_client: discord.VoiceClient = discord.utils.get(self.client.voice_clients, guild=context.guild)
            audio = discord.FFmpegPCMAudio('heeheeheehaa.mp3')
            voice_client.play(audio)
            try:
                react = await self.client.wait_for('reaction', timeout=10)
                if str(react.emoji) == '✅':
                    raise asyncio.TimeoutError
            except asyncio.TimeoutError:
                await voice_client.disconnect()


def setup(client):
    client.add_cog(CommandHandler(client))
