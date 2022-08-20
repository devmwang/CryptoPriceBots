import asyncio
import time
import re
import subprocess
import discord
from discord import ui
from discord.ext import commands

import main


def parse_price(price_input, cur_price, cad_usd_conversion_ratio):
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
            amt /= cad_usd_conversion_ratio

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


class EmbedView(ui.View):
    def __init__(self, client):
        super().__init__()
        self.client = client


    @ui.button(label="Restart Bots", style=discord.ButtonStyle.red)
    async def restart_bots(self, interaction: discord.Interaction, button: discord.ui.Button):
        await msg.edit(view = None)
        await interaction.channel.send("Restarting all price bots.")
        try:
            pipe = subprocess.Popen("sudo service crypto-price-bots restart", shell=True,
                                    stdout=subprocess.PIPE, stderr=subprocess.PIPE)
            out, err = pipe.communicate()
            response = out.decode()
            error = err.decode()
            combined = response + error
            if combined == "":
                msg = await interaction.channel.send("Price bots restarted.")
                await asyncio.sleep(main.delete_cooldown)
                await msg.delete()
            else:
                await interaction.channel.send(f"```{combined}```")
        except discord.errors.HTTPException as _e:
            await interaction.channel.send(str(_e))


    @ui.button(label="Clear Alerts", style=discord.ButtonStyle.blurple)
    async def clear_alerts(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.channel.send(f"Cleared all alerts.")
        self.client.alert_handler.clear_all_alerts()


class CommandHandler(commands.Cog):
    def __init__(self, client):
        self.client = client

    
    @commands.Cog.listener()
    async def on_message(self, m):
        # On mention activities
        if m.content in [f"<@{self.client.user.id}>", f"<@!{self.client.user.id}>"]:           
            # Determine ticker through getting the nickname of the bot, usually in this format:
            # BTC - $30495.40
            embed_view = EmbedView(self.client)

            embed = discord.Embed(description=f"{self.client.assets[0]}: ${round(self.client.usd_price[0], 4)}", color=0x00ff00)

            embed.add_field(name="CAD:", value=f"${round(self.client.usd_price[0] * self.client.usd_cad_conversion, 3)}")
            embed.add_field(name="Price up:", value=parse_alert_val(self.client.alert_up[0]))
            embed.add_field(name="Price down:", value=parse_alert_val(self.client.alert_down[0]))

            if self.client.dual:
                dual_embed = discord.Embed(description=f"{self.client.assets[1]}: ${round(self.client.usd_price[1], 4)}", color=0x00ff00)

                dual_embed.add_field(name="CAD:", value=f"${round(self.client.usd_price[1] * self.client.usd_cad_conversion, 3)}")
                dual_embed.add_field(name="Price up:", value=parse_alert_val(self.client.alert_up[1]))
                dual_embed.add_field(name="Price down:", value=parse_alert_val(self.client.alert_down[1]))

            await m.delete()

            if self.client.dual:
                msg = await m.channel.send(embeds = [embed, dual_embed], view = EmbedView(self.client))
            else:
                msg = await m.channel.send(embed = embed, view = EmbedView(self.client))

            await embed_view.wait()
            embed_view.clear_items()
            await msg.edit(view = embed_view)

        # Set price alerts
        # * Intelligent command setter
        # * User only needs to mention the relevant price bot, it will then algorithmically determine the proper pair to assign it to
        elif m.content.startswith(f"<@{self.client.user.id}>") or m.content.startswith(f"<@!{self.client.user.id}>"):
            m_list = m.content.split()  # Should return list: [asset ticker, number]
            ticker = m_list[0]
            
            bot_member = m.guild.get_member(self.client.user.id)
  
            prim_curr_price = float(re.findall(r"\d+\.\d+", bot_member.nick)[0])
            prim_alert_price = parse_price(alert_string, prim_curr_price, self.client.cad_usd_conversion_ratio)

            if not self.client.dual:
                self.client.alert_handler.set_alert(0, prim_curr_price, prim_alert_price)

            else:
                sec_curr_price = float(re.findall(r"\d+\.\d+", bot_member.activities[0].name)[0])
                sec_alert_price = parse_price(alert_string, sec_curr_price, self.client.cad_usd_conversion_ratio)

                # If alert price not valid: Ignore since message could be generic
                # If alert price valid: Set alert
                alert_string = ""
                for i in range (1, len(m_list)):
                    alert_string += m_list[i]

                if (prim_alert_price is None) and (sec_alert_price is None):
                    return
                else:
                    # If override is specified, bypass guesser and set alert for specified asset directly
                    if "override" in m.content.lower():
                        if self.client.assets[0] in m.content.upper():
                            await m.reply(self.client.alert_handler.set_alert(0, prim_curr_price, prim_alert_price))
                        if self.client.assets[1] in m.content.upper():
                            await m.reply(self.client.alert_handler.set_alert(1, sec_curr_price, sec_alert_price))
                    else:
                        prim_delta = abs(prim_curr_price - prim_alert_price)
                        sec_delta = abs(sec_curr_price - sec_alert_price)

                        if abs(prim_delta - sec_delta)/prim_delta < 0.05 and abs(prim_delta - sec_delta)/sec_delta < 0.05:
                            await m.reply(f"Specified alert price is too close to the current price of both assets. Please try a different value, or use the targeted command using syntax ```{self.client.user.mention} alert_price override ticker```.")
                        elif prim_delta < sec_delta:
                            await m.reply(self.client.alert_handler.set_alert(0, prim_curr_price, prim_alert_price))
                        elif sec_delta < prim_delta:
                            await m.reply(self.client.alert_handler.set_alert(1, sec_curr_price, sec_alert_price))
    

    @commands.command(name="alerts")
    async def alerts(self, context):
        # If one of the alerts is not None, the bot replies with the alerts
        if (self.client.alert_up[0] is not None) or (self.client.alert_down[0] is not None) or (self.client.dual and (self.client.alert_up[1] is not None or self.client.alert_down[1] is not None)):
            embed = discord.Embed(title=f"Current Alerts", color=0x00ff00)
            embed.add_field(name="Asset:", value=f"{self.client.assets[0]}")
            embed.add_field(name="Price up:", value=parse_alert_val(self.client.alert_up[0]))
            embed.add_field(name="Price down:", value=parse_alert_val(self.client.alert_down[0]))

            if self.client.dual:
                embed.add_field(name="Asset:", value=f"{self.client.assets[1]}")
                embed.add_field(name="Price up:", value=parse_alert_val(self.client.alert_up[1]))
                embed.add_field(name="Price down:", value=parse_alert_val(self.client.alert_up[1]))

            await context.message.reply(embed=embed)
        await context.message.add_reaction("\U00002705")  # Add a reaction since bots without alerts don't reply


    @commands.command(name="uptime")
    async def uptime(self, context):
        await context.send(f"{self.client.name} price bot online since <t:{self.client.start_time}> (<t:{self.client.start_time}:R>)")


    @commands.command(name="last")
    async def last(self, context):
        if self.client.dual:
            await context.send(f"{self.client.assets[0]}/{self.client.assets[1]}: Last websocket message received on <t:{self.client.last_ws_update[0]}:D> at <t:{self.client.last_ws_update[0]}:t> (<t:{self.client.last_ws_update[0]}:R>)")
        else:
            await context.send(f"{self.client.assets[0]}: Last websocket message received on <t:{self.client.last_ws_update[0]}:D> at <t:{self.client.last_ws_update[0]}:t> (<t:{self.client.last_ws_update[0]}:R>)")


    @commands.command(name="requests")
    async def requests(self, context):
        await context.send(self.client.utils.multiline(2, 3, f"""Price Bot: {self.client.discord_api_gets} {parse_single_multi_val(self.client.discord_api_gets, "GET")} to Discord API since <t:{self.client.start_time}>  (<t:{self.client.start_time}:R>).""",
                                                        f"""{self.client.assets[0]}: {self.client.discord_api_posts[0]} {parse_single_multi_val(self.client.discord_api_posts[0], "POST")} to Discord API since <t:{self.client.start_time}> (<t:{self.client.start_time}:R>).""",
                                                        f"""{self.client.assets[1]}: {self.client.discord_api_posts[1]} {parse_single_multi_val(self.client.discord_api_posts[1], "POST")} to Discord API since <t:{self.client.start_time}> (<t:{self.client.start_time}:R>)."""))


    @commands.command(name="var")
    async def var(self, context):
        if self.client.dual:
            await context.send(self.client.utils.multiline(1, 2, f"{self.client.assets[0]} Variability: {self.client.variability_threshold[0] * 100}% (approx. ${round(self.client.usd_price[0] * self.client.variability_threshold[0], 4)})",
                                                           f"{self.client.assets[1]} Variability: {self.client.variability_threshold[1] * 100}% (approx. ${round(self.client.usd_price[1] * self.client.variability_threshold[1], 4)})"))


    @commands.command(name="ping")
    async def ping(self, context):
        before_ping = time.monotonic()
        message_ping = await context.send("Pong!")
        ping_time = (time.monotonic() - before_ping) * 1000

        await message_ping.edit(content=self.client.utils.multiline(3, 3, f"Pong!", f"REST API: `{int(ping_time)}ms`", f"WS API Heartbeat: `{int(self.client.latency * 1000)}ms`"))

        await asyncio.sleep(main.delete_cooldown)
        await message_ping.delete()


    @commands.command(name="force")
    async def force(self, context):
        pass


async def setup(client):
    await client.add_cog(CommandHandler(client))
