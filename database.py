import asyncpg
import os
import datetime
import calendar

# Load database URL from environment variable
DATABASE_URL = os.environ.get('DATABASE_URL')

async def get_connection():
    """Returns an asynchronous connection pool to the PostgreSQL database."""
    try:
        # --- CRITICAL PERMANENTLY FREE UPDATE ---
        # Free Supabase/Cloud PostgreSQL tiers often pause connections or 
        # use transaction pooling. A short max_pool_size is required
        # to ensure it stays active and never times out during inactivity.
        return await asyncpg.create_pool(
            DATABASE_URL, 
            ssl="require",
            min_size=1,
            max_size=3, # Keep this very low!
            command_timeout=60
        )
    except Exception as e:
        print(f"Error connecting to database: {e}")
        return None

async def initialize_db(pool):
    """Creates the necessary tables if they do not exist (PostgreSQL syntax)."""
    async with pool.acquire() as conn:
        async with conn.transaction():
            await conn.execute("""
                CREATE TABLE IF NOT EXISTS transactions (
                    id SERIAL PRIMARY KEY,
                    user_id BIGINT NOT NULL,
                    type TEXT NOT NULL CHECK(type IN ('income', 'expense')),
                    category TEXT NOT NULL,
                    amount NUMERIC(12, 2) NOT NULL,
                    description TEXT,
                    timestamp TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP
                )
            """)
            await conn.execute("CREATE INDEX IF NOT EXISTS idx_user_time ON transactions (user_id, timestamp)")
    print("Database initialized.")

async def add_transaction(pool, user_id: int, trans_type: str, category: str, amount: float, description: str = None):
    if amount <= 0: raise ValueError("Amount must be positive.")
    async with pool.acquire() as conn:
        await conn.execute("""
            INSERT INTO transactions (user_id, type, category, amount, description)
            VALUES ($1, $2, $3, $4, $5)
        """, user_id, trans_type.lower(), category.lower(), amount, description)

async def get_balance(pool, user_id: int):
    async with pool.acquire() as conn:
        row = await conn.fetchrow("""
            SELECT 
                SUM(CASE WHEN type = 'income' THEN amount ELSE 0 END) as total_income,
                SUM(CASE WHEN type = 'expense' THEN amount ELSE 0 END) as total_expense
            FROM transactions
            WHERE user_id = $1
        """, user_id)
    income = float(row['total_income'] or 0.0)
    expense = float(row['total_expense'] or 0.0)
    balance = income - expense
    return income, expense, balance

async def get_category_summary(pool, user_id: int, trans_type: str):
    async with pool.acquire() as conn:
        rows = await conn.fetch("""
            SELECT category, SUM(amount) as total
            FROM transactions
            WHERE user_id = $1 AND type = $2
            GROUP BY category
            ORDER BY total DESC
        """, user_id, trans_type.lower())
    return rows

async def get_monthly_report(pool, user_id: int, month: int, year: int):
    async with pool.acquire() as conn:
        start_date = datetime.date(year, month, 1)
        if month == 12: end_date = datetime.date(year + 1, 1, 1)
        else: end_date = datetime.date(year, month + 1, 1)
        rows = await conn.fetch("""
            SELECT type, category, amount, description, timestamp
            FROM transactions
            WHERE user_id = $1 AND timestamp >= $2 AND timestamp < $3
            ORDER BY timestamp ASC
        """, user_id, start_date, end_date)
    return rows
