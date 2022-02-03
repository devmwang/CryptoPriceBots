import asyncio
import json
import subprocess
import time
import re

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
                        embed.add_field(name="Price up:", value=(None if self.client.prim_alert_up is None else ("$" + str(self.client.prim_alert_up))) or "Not Set")
                        embed.add_field(name="Price down:", value=(None if self.client.prim_alert_down is None else ("$" + str(self.client.prim_alert_down))) or "Not Set")

                        if self.client.combined == True:
                            embed.add_field(name="Asset:", value=f"{self.client.pairs[1]}")
                            embed.add_field(name="Price up:", value=(None if self.client.sec_alert_up is None else ("$" + str(self.client.sec_alert_up))) or "Not Set")
                            embed.add_field(name="Price down:", value=(None if self.client.sec_alert_down is None else ("$" + str(self.client.sec_alert_down))) or "Not Set")

                        await button_ctx.send(embed=embed)

                    if button_ctx.component['label'] == "Clear alerts":
                        await button_ctx.send(f"Cleared all alerts.")
                        self.client.prim_alert_up = None
                        self.client.prim_alert_down = None
                        self.client.sec_alert_up = None
                        self.client.sec_alert_down = None
            except asyncio.TimeoutError:
                await msg.edit(components=None)

        # Set price alerts
        # Updated price alert setter code to be compatible with combined bots
        elif m.content.upper().startswith(self.client.pairs[0] or self.client.pairs[1]):
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
            
            # If alert price not valid: Tell user
            # If alert price valid: Set alert
            alertstring = ""
            for i in range (1, len(mlist)):
                alertstring += mlist[i]

            alertprice = parse_price(alertstring, curr_price)
            if alertprice is None:
                msg = await m.reply(f"Could not parse a price from `{alertstring}`.")
                await asyncio.sleep(main.delete_cooldown)
                await m.delete()
                await msg.delete()
            
            if index == 0:
                if alertprice > curr_price:
                    self.client.prim_alert_up = alertprice
                    await m.reply(f"Set alert for {self.client.pairs[index]} above ${alertprice}.")
                elif alertprice < curr_price:
                    self.client.prim_alert_down = alertprice
                    await m.reply(f"Set alert for {self.client.pairs[index]} below ${alertprice}.")
                else:
                    await m.reply("BA DING")

            elif index == 1:
                if alertprice > curr_price:
                    self.client.sec_alert_up = alertprice
                    await m.reply(f"Set alert for {self.client.pairs[index]} above ${alertprice}.")
                elif alertprice < curr_price:
                    self.client.sec_alert_down = alertprice
                    await m.reply(f"Set alert for {self.client.pairs[index]} below ${alertprice}.")
                else:
                    await m.reply("BA DING")

    @commands.command(name="alerts")
    async def alerts(self, context):
        # If one of the alerts is not None, the bot replies with the alerts
        if self.client.prim_alert_up is not None or self.client.prim_alert_down is not None or self.client.sec_alert_up is not None or self.client.sec_alert_down is not None:
            embed = discord.Embed(title=f"Current Alerts", color=0x00ff00)
            embed.add_field(name="Asset:", value=f"{self.client.pairs[0]}")
            embed.add_field(name="Price up:", value=(None if self.client.prim_alert_up is None else ("$" + str(self.client.prim_alert_up))) or "Not Set")
            embed.add_field(name="Price down:", value=(None if self.client.prim_alert_down is None else ("$" + str(self.client.prim_alert_down))) or "Not Set")

            if self.client.combined == True:
                embed.add_field(name="Asset:", value=f"{self.client.pairs[1]}")
                embed.add_field(name="Price up:", value=(None if self.client.sec_alert_up is None else ("$" + str(self.client.sec_alert_up))) or "Not Set")
                embed.add_field(name="Price down:", value=(None if self.client.sec_alert_down is None else ("$" + str(self.client.sec_alert_down))) or "Not Set")

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
