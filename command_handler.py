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

import alert_handler


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

def parse_single_multi_val(num, string):
    if (num == 1):
        return string
    else:
        return string + 's'


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
                        embed.add_field(name="Price up:", value=parse_alert_val(self.client.alert_up[0]))
                        embed.add_field(name="Price down:", value=parse_alert_val(self.client.alert_down[0]))

                        embed.add_field(name="Asset:", value=f"{self.client.pairs[1]}")
                        embed.add_field(name="Price up:", value=parse_alert_val(self.client.alert_up[1]))
                        embed.add_field(name="Price down:", value=parse_alert_val(self.client.alert_down[1]))

                        await button_ctx.send(embed=embed)

                    if button_ctx.component['label'] == "Clear alerts":
                        await button_ctx.send(f"Cleared all alerts.")
                        alert_handler.clear_all_alerts(self)

            except asyncio.TimeoutError:
                await msg.edit(components=None)

        # Set price alerts
        # * Intelligent command setter
        # * User only needs to mention the relevant price bot, it will then algorithmically determine the proper pair to assign it to
        elif m.content.startswith(f"<@{self.client.user.id}>") or m.content.startswith(f"<@!{self.client.user.id}>"):
            m_list = m.content.split()  # Should return list: [asset ticker, number]
            ticker = m_list[0]
            
            bot_member = m.guild.get_member(self.client.user.id)

            prim_curr_price = float(re.findall(r"\d+\.\d+", bot_member.nick)[0])
            sec_curr_price = float(re.findall(r"\d+\.\d+", bot_member.activities[0].name)[0])

            # If alert price not valid: Ignore since message could be generic
            # If alert price valid: Set alert
            alertstring = ""
            for i in range (1, len(m_list)):
                alertstring += m_list[i]

            prim_alert_price = parse_price(alertstring, prim_curr_price)
            sec_alert_price = parse_price(alertstring, sec_curr_price)

            if (prim_alert_price is None) and (sec_alert_price is None):
                return
            else:
                # If override is specified, bypass guesser and set alert for specified asset directly
                if "override" in m.content:
                    if self.client.pairs[0] in m.content.upper():
                        await m.reply(alert_handler.set_alert(self, 0, prim_curr_price, prim_alert_price))
                    if self.client.pairs[1] in m.content.upper():
                        await m.reply(alert_handler.set_alert(self, 1, sec_curr_price, sec_alert_price))
                else:
                    prim_delta = abs(prim_curr_price - prim_alert_price)
                    sec_delta = abs(sec_curr_price - sec_alert_price)

                    if prim_delta < sec_delta:
                        await m.reply(alert_handler.set_alert(self, 0, prim_curr_price, prim_alert_price))
                    elif sec_delta < prim_delta:
                        await m.reply(alert_handler.set_alert(self, 1, sec_curr_price, sec_alert_price))
                    else:
                        await m.reply('Specified alert price is too close to the current price of both assets. Please try a different value, or use the targeted command using syntax ```ticker alert_price```.')
    
    @commands.command(name="alerts")
    async def alerts(self, context):
        print(self.client.pairs[0])

        # If one of the alerts is not None, the bot replies with the alerts
        if self.client.alert_up[0] is not None or self.client.alert_down[0] is not None or self.client.alert_up[1] is not None or self.client.alert_down[1] is not None:
            embed = discord.Embed(title=f"Current Alerts", color=0x00ff00)
            embed.add_field(name="Asset:", value=f"{self.client.pairs[0]}")
            embed.add_field(name="Price up:", value=parse_alert_val(self.client.alert_up[0]))
            embed.add_field(name="Price down:", value=parse_alert_val(self.client.alert_down[0]))

            embed.add_field(name="Asset:", value=f"{self.client.pairs[1]}")
            embed.add_field(name="Price up:", value=parse_alert_val(self.client.alert_up[1]))
            embed.add_field(name="Price down:", value=parse_alert_val(self.client.alert_up[1]))

            await context.message.reply(embed=embed)
        await context.message.add_reaction("\U00002705")  # Add a reaction since bots without alerts don't reply

    @commands.command(name="uptime")
    async def uptime(self, context):
        await context.send(f"{self.client.pairs[0]}/{self.client.pairs[1]} price bot online since <t:{self.client.start_time}> (<t:{self.client.start_time}:R>)")

    @commands.command(name="last")
    async def last(self, context):
        await context.send(f"""{self.client.pairs[0]}: Last websocket message received on <t:{self.client.last_ws_update[0]}:D> at <t:{self.client.last_ws_update[0]}:t> (<t:{self.client.last_ws_update[0]}:R>)
{self.client.pairs[1]}: Last websocket message received on <t:{self.client.last_ws_update[1]}:D> at <t:{self.client.last_ws_update[1]}:t> (<t:{self.client.last_ws_update[1]}:R>)""")

    @commands.command(name="requests")
    async def requests(self, context):
        await context.send(f"""Price Bot: {self.client.discord_api_gets} {parse_single_multi_val(self.client.discord_api_gets, "GET")} to Discord API since <t:{self.client.start_time}>  (<t:{self.client.last_ws_update[1]}:R>).
{self.client.pairs[0]}: {self.client.discord_api_posts[0]} {parse_single_multi_val(self.client.discord_api_posts[0], "POST")} to Discord API since <t:{self.client.start_time}> (<t:{self.client.last_ws_update[1]}:R>).
{self.client.pairs[1]}: {self.client.discord_api_posts[1]} {parse_single_multi_val(self.client.discord_api_posts[1], "POST")} to Discord API since <t:{self.client.start_time}> (<t:{self.client.last_ws_update[1]}:R>).""")

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

    @commands.command(name="force")
    async def force(self, context):
        pass


def setup(client):
    client.add_cog(CommandHandler(client))
