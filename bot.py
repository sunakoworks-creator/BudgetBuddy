import discord
from discord import app_commands
from discord.ext import commands
import database as db_handler 
import os
from datetime import datetime
import calendar
from dotenv import load_dotenv

# Load local environment variables for testing (if any)
load_dotenv()

# --- Configuration ---
# Render will provide these securely
TOKEN = os.environ.get('DISCORD_TOKEN') 
MY_GUILD = None 

class BudgetBot(commands.Bot):
    def __init__(self):
        super().__init__(command_prefix="!", intents=discord.Intents.default())
        self.db_pool = None

    async def setup_hook(self):
        self.db_pool = await db_handler.get_connection()
        if self.db_pool:
            await db_handler.initialize_db(self.db_pool)
            print("Database connected and initialized.")
        else:
            print("Failed to connect to the database. Bot might not function correctly.")
        if MY_GUILD:
            self.tree.copy_global_to(guild=MY_GUILD)
            await self.tree.sync(guild=MY_GUILD)
        else:
            await self.tree.sync()
        print("Synced commands globally.")

    async def on_ready(self):
        print(f'Logged in as {self.user} (ID: {self.user.id})')
        print('------')

bot = BudgetBot()

def format_currency(amount: float):
    return f"${amount:,.2f}"

@bot.tree.command(name="income", description="Log new income")
@app_commands.describe(category="e.g., Salary, Gift", amount="Amount earned", description="Details")
async def income(interaction: discord.Interaction, category: str, amount: float, description: str = None):
    try:
        await db_handler.add_transaction(bot.db_pool, interaction.user.id, "income", category, amount, description)
        embed = discord.Embed(title="✅ Income Logged", color=discord.Color.green(), timestamp=datetime.utcnow())
        embed.add_field(name="Category", value=category.title(), inline=True)
        embed.add_field(name="Amount", value=format_currency(amount), inline=True)
        if description: embed.add_field(name="Description", value=description, inline=False)
        await interaction.response.send_message(embed=embed)
    except Exception as e: await interaction.response.send_message(f"❌ Error: {e}", ephemeral=True)

@bot.tree.command(name="expense", description="Log a new expense")
@app_commands.describe(category="e.g., Food, Rent", amount="Amount spent", description="Details")
async def expense(interaction: discord.Interaction, category: str, amount: float, description: str = None):
    try:
        await db_handler.add_transaction(bot.db_pool, interaction.user.id, "expense", category, amount, description)
        embed = discord.Embed(title="💸 Expense Logged", color=discord.Color.red(), timestamp=datetime.utcnow())
        embed.add_field(name="Category", value=category.title(), inline=True)
        embed.add_field(name="Amount", value=format_currency(amount), inline=True)
        if description: embed.add_field(name="Description", value=description, inline=False)
        await interaction.response.send_message(embed=embed)
    except Exception as e: await interaction.response.send_message(f"❌ Error: {e}", ephemeral=True)

@bot.tree.command(name="balance", description="Check your current financial balance")
async def balance(interaction: discord.Interaction):
    await interaction.response.defer()
    inc_val, exp_val, bal_val = await db_handler.get_balance(bot.db_pool, interaction.user.id)
    embed = discord.Embed(title=f"Balance for {interaction.user.display_name}", timestamp=datetime.utcnow())
    if bal_val >= 0: embed.color = discord.Color.green()
    else: embed.color = discord.Color.red()
    embed.add_field(name="Total Income", value=format_currency(inc_val), inline=True)
    embed.add_field(name="Total Expenses", value=format_currency(exp_val), inline=True)
    embed.add_field(name="Current Balance", value=f"**{format_currency(bal_val)}**", inline=False)
    await interaction.followup.send(embed=embed)

@bot.tree.command(name="summary", description="View spending or income breakdown by category")
@app_commands.choices(type=[
    app_commands.Choice(name="Expenses", value="expense"),
    app_commands.Choice(name="Income", value="income")
])
async def summary(interaction: discord.Interaction, type: app_commands.Choice[str]):
    await interaction.response.defer()
    rows = await db_handler.get_category_summary(bot.db_pool, interaction.user.id, type.value)
    type_label = "Spending" if type.value == "expense" else "Earnings"
    embed = discord.Embed(title=f"{type_label} Summary by Category")
    if type.value == "expense": embed.color = discord.Color.red()
    else: embed.color = discord.Color.green()
    if not rows: embed.description = "No transactions recorded yet."
    else:
        summary_text, total_sum = "", 0
        for row in rows:
            amt_float = float(row['total'])
            summary_text += f"**{row['category'].title()}**: {format_currency(amt_float)}\n"
            total_sum += amt_float
        embed.description = summary_text
        embed.set_footer(text=f"Total {type_label}: {format_currency(total_sum)}")
    await interaction.followup.send(embed=embed)

@bot.tree.command(name="report", description="Get detailed monthly report")
async def report(interaction: discord.Interaction, month: int = None, year: int = None):
    await interaction.response.defer()
    now = datetime.now()
    r_month, r_year = month or now.month, year or now.year
    if r_month < 1 or r_month > 12: return await interaction.followup.send("❌ Invalid month. Use 1-12.")
    rows = await db_handler.get_monthly_report(bot.db_pool, interaction.user.id, r_month, r_year)
    month_name = calendar.month_name[r_month]
    embed = discord.Embed(title=f"Detailed Report: {month_name} {r_year}", color=discord.Color.blue())
    if not rows: embed.description = f"No transactions found."
    else:
        report_lines = [f"{'Date':<12} | {'Type':<7} | {'Category':<12} | {'Amount':>10}", "-" * 51]
        m_inc, m_exp = 0, 0
        for row in rows:
            amt = float(row['amount'])
            cat = row['category'][:11]
            fmt_date = row['timestamp'].strftime('%Y-%m-%d')
            report_lines.append(f"{fmt_date:<12} | {row['type'].title():<7} | {cat.title():<12} | {format_currency(amt):>10}")
            if row['type'] == 'income': m_inc += amt
            else: m_exp += amt
        embed.description = f"```\n" + "\n".join(report_lines) + "\n```"
        embed.add_field(name="Month Income", value=format_currency(m_inc), inline=True)
        embed.add_field(name="Month Expenses", value=format_currency(m_exp), inline=True)
        embed.add_field(name="Net", value=format_currency(m_inc - m_exp), inline=True)
    await interaction.followup.send(embed=embed)

bot.run(TOKEN)
