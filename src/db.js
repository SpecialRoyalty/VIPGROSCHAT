import pg from "pg";

const { Pool } = pg;

export const pool = new Pool({
  connectionString: process.env.DATABASE_URL,
  ssl: process.env.DATABASE_URL?.includes("railway") ? { rejectUnauthorized: false } : false
});

export async function initDb() {
  await pool.query(`
    CREATE TABLE IF NOT EXISTS users (
      id BIGSERIAL PRIMARY KEY,
      telegram_id BIGINT UNIQUE NOT NULL,
      username TEXT,
      first_name TEXT,
      last_name TEXT,
      free_interest BOOLEAN DEFAULT FALSE,
      premium_interest BOOLEAN DEFAULT FALSE,
      free_position INTEGER,
      premium_position INTEGER,
      created_at TIMESTAMP DEFAULT NOW(),
      updated_at TIMESTAMP DEFAULT NOW()
    );
  `);

  await pool.query(`
    CREATE TABLE IF NOT EXISTS logs (
      id BIGSERIAL PRIMARY KEY,
      telegram_id BIGINT,
      username TEXT,
      action TEXT NOT NULL,
      created_at TIMESTAMP DEFAULT NOW()
    );
  `);

  await pool.query(`
    CREATE TABLE IF NOT EXISTS settings (
      key TEXT PRIMARY KEY,
      value TEXT NOT NULL
    );
  `);

  await setDefaultSetting("auto_pub", "off");
  await setDefaultSetting("last_pub_message_id", "");
}

async function setDefaultSetting(key, value) {
  await pool.query(
    `INSERT INTO settings(key, value)
     VALUES($1, $2)
     ON CONFLICT(key) DO NOTHING`,
    [key, value]
  );
}

export async function getSetting(key) {
  const res = await pool.query("SELECT value FROM settings WHERE key=$1", [key]);
  return res.rows[0]?.value ?? null;
}

export async function setSetting(key, value) {
  await pool.query(
    `INSERT INTO settings(key, value)
     VALUES($1, $2)
     ON CONFLICT(key) DO UPDATE SET value=$2`,
    [key, value]
  );
}

export async function upsertUser(ctx) {
  const from = ctx.from;
  if (!from?.id) return;

  await pool.query(
    `
    INSERT INTO users(telegram_id, username, first_name, last_name)
    VALUES($1, $2, $3, $4)
    ON CONFLICT(telegram_id)
    DO UPDATE SET
      username=$2,
      first_name=$3,
      last_name=$4,
      updated_at=NOW()
    `,
    [
      from.id,
      from.username || null,
      from.first_name || null,
      from.last_name || null
    ]
  );
}

export async function markFree(ctx) {
  await upsertUser(ctx);

  const existing = await pool.query(
    "SELECT free_interest, free_position FROM users WHERE telegram_id=$1",
    [ctx.from.id]
  );

  if (existing.rows[0]?.free_interest) {
    return { already: true, position: existing.rows[0].free_position };
  }

  const count = await pool.query(
    "SELECT COUNT(*)::int AS count FROM users WHERE free_interest=TRUE"
  );

  const realPosition = count.rows[0].count + 1;
  const displayPosition = Math.max(69, 68 + realPosition);

  await pool.query(
    `
    UPDATE users
    SET free_interest=TRUE,
        free_position=$2,
        updated_at=NOW()
    WHERE telegram_id=$1
    `,
    [ctx.from.id, displayPosition]
  );

  await addLog(ctx, `VIP_GRATUIT_CLICK position=${displayPosition}`);

  return { already: false, position: displayPosition, realPosition };
}

export async function markPremium(ctx) {
  await upsertUser(ctx);

  const existing = await pool.query(
    "SELECT premium_interest, premium_position FROM users WHERE telegram_id=$1",
    [ctx.from.id]
  );

  if (existing.rows[0]?.premium_interest) {
    return { already: true, position: existing.rows[0].premium_position };
  }

  const count = await pool.query(
    "SELECT COUNT(*)::int AS count FROM users WHERE premium_interest=TRUE"
  );

  const position = count.rows[0].count + 1;

  await pool.query(
    `
    UPDATE users
    SET premium_interest=TRUE,
        premium_position=$2,
        updated_at=NOW()
    WHERE telegram_id=$1
    `,
    [ctx.from.id, position]
  );

  await addLog(ctx, `VIP_PREMIUM_CLICK position=${position}`);

  return { already: false, position };
}

export async function getStats() {
  const total = await pool.query("SELECT COUNT(*)::int AS count FROM users");
  const free = await pool.query("SELECT COUNT(*)::int AS count FROM users WHERE free_interest=TRUE");
  const premium = await pool.query("SELECT COUNT(*)::int AS count FROM users WHERE premium_interest=TRUE");
  const both = await pool.query("SELECT COUNT(*)::int AS count FROM users WHERE free_interest=TRUE AND premium_interest=TRUE");
  const autoPub = await getSetting("auto_pub");

  return {
    total: total.rows[0].count,
    free: free.rows[0].count,
    premium: premium.rows[0].count,
    both: both.rows[0].count,
    autoPub
  };
}

export async function getUsersBySegment(segment) {
  let query = "SELECT telegram_id FROM users";
  if (segment === "premium") query += " WHERE premium_interest=TRUE";
  if (segment === "free") query += " WHERE free_interest=TRUE";
  const res = await pool.query(query);
  return res.rows.map(r => r.telegram_id);
}

export async function addLog(ctx, action) {
  const from = ctx?.from || {};
  await pool.query(
    "INSERT INTO logs(telegram_id, username, action) VALUES($1, $2, $3)",
    [from.id || null, from.username || null, action]
  );
}

export async function getRecentLogs(limit = 10) {
  const res = await pool.query(
    "SELECT * FROM logs ORDER BY created_at DESC LIMIT $1",
    [limit]
  );
  return res.rows;
}
