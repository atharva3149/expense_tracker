import { useEffect, useState } from "react";

const API_BASE = (import.meta.env.VITE_API_URL || "").replace(/\/$/, "");
const CURRENCY = import.meta.env.VITE_CURRENCY || "USD";
const TOKEN_KEY = "spend-tracker-access-token";
const USER_KEY = "spend-tracker-user";

function localDate() {
  const now = new Date();
  const offset = now.getTimezoneOffset();
  return new Date(now.getTime() - offset * 60 * 1000).toISOString().slice(0, 10);
}

function currentMonth() {
  return localDate().slice(0, 7);
}

function money(value) {
  return new Intl.NumberFormat(undefined, {
    style: "currency",
    currency: CURRENCY,
    maximumFractionDigits: 2,
  }).format(Number(value || 0));
}

function errorText(body, status) {
  if (body?.detail) {
    if (Array.isArray(body.detail)) {
      return body.detail.map((item) => item.msg).join("; ");
    }
    return body.detail;
  }
  return `Request failed (${status})`;
}

async function request(path, options = {}, token = "") {
  const headers = { ...(options.headers || {}) };
  if (options.body && !headers["Content-Type"]) {
    headers["Content-Type"] = "application/json";
  }
  if (token) headers.Authorization = `Bearer ${token}`;

  const response = await fetch(`${API_BASE}${path}`, { ...options, headers });
  const body = await response.json().catch(() => null);
  if (!response.ok) throw new Error(errorText(body, response.status));
  return body;
}

function validatePassword(value) {
  if (!value) return "Password is required";
  if (value.length < 8) return "Password must be at least 8 characters";
  const letterCount = (value.match(/[A-Za-z]/g) || []).length;
  if (letterCount < 6) return "Password must contain at least 6 alphabetic characters";
  if (!/\d/.test(value)) return "Password must contain at least one number";
  if (!/[^A-Za-z0-9]/.test(value)) return "Password must contain at least one special character";
  return "";
}

function AuthScreen({ onAuthenticated }) {
  const [mode, setMode] = useState("login");
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [message, setMessage] = useState("");
  const [busy, setBusy] = useState(false);
  const [passwordError, setPasswordError] = useState("");

  async function submit(event) {
    event.preventDefault();
    const nextPasswordError = mode === "register" ? validatePassword(password) : "";
    setPasswordError(nextPasswordError);
    if (nextPasswordError) {
      setMessage(nextPasswordError);
      return;
    }
    setBusy(true);
    setMessage("");
    try {
      const data = await request(`/auth/${mode}`, {
        method: "POST",
        body: JSON.stringify({ username, password }),
      });
      localStorage.setItem(TOKEN_KEY, data.access_token);
      localStorage.setItem(USER_KEY, JSON.stringify(data.user));
      onAuthenticated(data);
    } catch (error) {
      setMessage(error.message);
    } finally {
      setBusy(false);
    }
  }

  return (
    <main className="auth-page">
      <section className="auth-card">
        <p className="eyebrow">Personal finance, without the noise</p>
        <h1>Keep your spending visible.</h1>
        <p className="lede">
          Log an expense in seconds, then see where this month is heading.
        </p>
        <div className="auth-tabs" role="tablist" aria-label="Authentication mode">
          <button
            className={mode === "login" ? "active" : ""}
            onClick={() => setMode("login")}
            type="button"
          >
            Sign in
          </button>
          <button
            className={mode === "register" ? "active" : ""}
            onClick={() => setMode("register")}
            type="button"
          >
            Create account
          </button>
        </div>
        <form className="stack-form" onSubmit={submit}>
          <label>
            Username
            <input
              autoComplete="username"
              minLength="3"
              maxLength="50"
              onChange={(event) => setUsername(event.target.value)}
              placeholder="alex"
              required
              value={username}
            />
          </label>
          <label>
            Password
            <input
              autoComplete={mode === "login" ? "current-password" : "new-password"}
              minLength="8"
              maxLength="128"
              onChange={(event) => {
                const nextValue = event.target.value;
                setPassword(nextValue);
                if (mode === "register") {
                  setPasswordError(validatePassword(nextValue));
                  if (!validatePassword(nextValue)) setMessage("");
                }
              }}
              placeholder="Abcdefg1!"
              required
              type="password"
              value={password}
            />
          </label>
          {passwordError && mode === "register" && (
            <p className="form-message error">{passwordError}</p>
          )}
          {message && <p className="form-message error">{message}</p>}
          <button className="primary-button" disabled={busy} type="submit">
            {busy ? "Working..." : mode === "login" ? "Open tracker" : "Create account"}
          </button>
        </form>
      </section>
    </main>
  );
}

function StatCard({ label, value, detail, tone = "" }) {
  return (
    <article className={`stat-card ${tone}`}>
      <span className="stat-label">{label}</span>
      <strong>{value}</strong>
      {detail && <span className="stat-detail">{detail}</span>}
    </article>
  );
}

function App() {
  const [token, setToken] = useState(() => localStorage.getItem(TOKEN_KEY) || "");
  const [user, setUser] = useState(() => {
    try {
      return JSON.parse(localStorage.getItem(USER_KEY) || "null");
    } catch {
      return null;
    }
  });
  const [summary, setSummary] = useState(null);
  const [expenses, setExpenses] = useState([]);
  const [month, setMonth] = useState(currentMonth);
  const [filters, setFilters] = useState({ category: "", start_date: "", end_date: "" });
  const [form, setForm] = useState({
    amount: "",
    category: "",
    date: localDate(),
    note: "",
  });
  const [status, setStatus] = useState({ type: "", text: "" });
  const [loading, setLoading] = useState(false);

  function signOut() {
    localStorage.removeItem(TOKEN_KEY);
    localStorage.removeItem(USER_KEY);
    setToken("");
    setUser(null);
    setSummary(null);
    setExpenses([]);
  }

  function handleAuthenticated(data) {
    setToken(data.access_token);
    setUser(data.user);
  }

  async function loadDashboard(clearStatus = true) {
    if (!token) return;
    setLoading(true);
    if (clearStatus) setStatus({ type: "", text: "" });
    try {
      const params = new URLSearchParams();
      if (month) params.set("month", month);
      const expenseParams = new URLSearchParams();
      Object.entries(filters).forEach(([key, value]) => {
        if (value) expenseParams.set(key, value);
      });
      const [summaryData, expenseData] = await Promise.all([
        request(`/summary?${params}`, {}, token),
        request(`/expenses?${expenseParams}`, {}, token),
      ]);
      setSummary(summaryData);
      setExpenses(expenseData.expenses || []);
    } catch (error) {
      if (/token|bearer|401|expired/i.test(error.message)) signOut();
      setStatus({ type: "error", text: error.message });
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    if (token) loadDashboard();
  }, [token, month]);

  async function addExpense(event) {
    event.preventDefault();
    setStatus({ type: "", text: "" });
    try {
      const payload = {
        amount: Number(form.amount),
        category: form.category,
        note: form.note,
        date: form.date || undefined,
      };
      await request("/expenses", { method: "POST", body: JSON.stringify(payload) }, token);
      setForm({ amount: "", category: "", date: localDate(), note: "" });
      setStatus({ type: "success", text: "Expense added to your tracker." });
      await loadDashboard(false);
    } catch (error) {
      setStatus({ type: "error", text: error.message });
    }
  }

  if (!token) return <AuthScreen onAuthenticated={handleAuthenticated} />;

  const mom = summary?.month_over_month;
  const change = mom?.change_pct;
  const changeLabel = change === null || change === undefined
    ? "No previous month"
    : `${change > 0 ? "+" : ""}${change}%`;

  return (
    <div className="app-shell">
      <header className="topbar">
        <div className="topbar-inner">
          <div className="brand-lockup">
            <div className="brand-mark small">ST</div>
            <div>
              <p className="eyebrow">Spend Tracker</p>
              <span className="topbar-subtitle">A clearer view of your money</span>
            </div>
          </div>
          <div className="account-area">
            <span className="user-chip">{user?.username || "Account"}</span>
            <button className="ghost-button" onClick={signOut} type="button">Sign out</button>
          </div>
        </div>
      </header>

      <main className="dashboard">
        <section className="dashboard-heading">
          <div>
            <p className="eyebrow">Your overview</p>
            <h1>Make every expense count.</h1>
            <p className="lede">A quiet dashboard for the habits you want to understand.</p>
          </div>
          <label className="month-picker">
            <span>Viewing month</span>
            <input onChange={(event) => setMonth(event.target.value)} type="month" value={month} />
          </label>
        </section>

        {status.text && <div className={`banner ${status.type}`}>{status.text}</div>}

        <section className="stats-grid" aria-label="Spending summary">
          <StatCard label="All-time spend" value={money(summary?.total_spend)} detail={`${summary?.total_expenses || 0} expenses logged`} />
          <StatCard label={`${month} spend`} value={money(mom?.current_total)} detail="Selected month" />
          <StatCard
            label="Month over month"
            value={changeLabel}
            detail={mom?.previous_month ? `Compared with ${mom.previous_month}` : "Add a prior month to compare"}
            tone={change > 0 ? "warm" : change < 0 ? "cool" : ""}
          />
        </section>

        <div className="content-grid">
          <section className="card add-card">
            <div className="card-heading">
              <div>
                <p className="eyebrow">New entry</p>
                <h2>Log an expense</h2>
              </div>
              <span className="card-icon">+</span>
            </div>
            <form className="stack-form" onSubmit={addExpense}>
              <div className="form-row">
                <label>
                  Amount
                  <input min="0.01" onChange={(event) => setForm({ ...form, amount: event.target.value })} placeholder="0.00" required step="0.01" type="number" value={form.amount} />
                </label>
                <label>
                  Category
                  <input maxLength="50" onChange={(event) => setForm({ ...form, category: event.target.value })} placeholder="Groceries" required type="text" value={form.category} />
                </label>
              </div>
              <div className="form-row">
                <label>
                  Date
                  <input onChange={(event) => setForm({ ...form, date: event.target.value })} required type="date" value={form.date} />
                </label>
                <label>
                  Note <span className="optional">Optional</span>
                  <input maxLength="500" onChange={(event) => setForm({ ...form, note: event.target.value })} placeholder="What was it for?" type="text" value={form.note} />
                </label>
              </div>
              <button className="primary-button" disabled={loading} type="submit">{loading ? "Saving..." : "Add expense"}</button>
            </form>
          </section>

          <section className="card insight-card">
            <div className="card-heading">
              <div>
                <p className="eyebrow">Signal</p>
                <h2>What changed?</h2>
              </div>
              <span className="signal-dot" />
            </div>
            <p className="insight-copy">{mom?.insight || "Your first month-over-month insight will appear here."}</p>
            <div className="category-list">
              {(summary?.spend_by_category || []).slice(0, 5).map((item) => (
                <div className={`category-row ${item.flagged ? "flagged" : ""}`} key={item.category}>
                  <div>
                    <strong>{item.category}</strong>
                    {item.flagged && <span className="flag">Up &gt;20%</span>}
                  </div>
                  <div className="category-amount">
                    <strong>{money(item.amount)}</strong>
                    <span>{item.change_pct == null ? "New" : `${item.change_pct > 0 ? "+" : ""}${item.change_pct}%`}</span>
                  </div>
                </div>
              ))}
              {!summary?.spend_by_category?.length && <p className="empty-state">No spending in this month yet.</p>}
            </div>
          </section>
        </div>

        <section className="card history-card">
          <div className="card-heading history-heading">
            <div>
              <p className="eyebrow">Transaction history</p>
              <h2>Recent expenses</h2>
            </div>
            <button className="ghost-button" disabled={loading} onClick={loadDashboard} type="button">Refresh</button>
          </div>
          <div className="filters">
            <input onChange={(event) => setFilters({ ...filters, category: event.target.value })} placeholder="Filter category" type="search" value={filters.category} />
            <input aria-label="Filter from date" onChange={(event) => setFilters({ ...filters, start_date: event.target.value })} type="date" value={filters.start_date} />
            <input aria-label="Filter to date" onChange={(event) => setFilters({ ...filters, end_date: event.target.value })} type="date" value={filters.end_date} />
            <button className="secondary-button" onClick={loadDashboard} type="button">Apply filters</button>
          </div>
          <div className="table-wrap">
            <table>
              <thead><tr><th>Date</th><th>Category</th><th>Note</th><th className="amount-column">Amount</th></tr></thead>
              <tbody>
                {expenses.map((expense) => (
                  <tr key={expense.id}>
                    <td>{expense.date}</td>
                    <td><span className="category-pill">{expense.category}</span></td>
                    <td className="note-cell">{expense.note || "-"}</td>
                    <td className="amount-column">{money(expense.amount)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
            {!expenses.length && <p className="empty-state">No expenses match these filters.</p>}
          </div>
        </section>
      </main>
    </div>
  );
}

export default App;
