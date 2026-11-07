// Conturi reale, salvate în baza de date a browserului (src/data/accounts.ts): creare cont, autentificare, delogare.
import { useEffect, useState, type FormEvent, type ReactNode } from "react";
import { AnimatePresence, motion } from "framer-motion";
import { Database, Eye, EyeOff } from "lucide-react";
import { useAuth } from "../auth";
import { DEMO_ACCOUNT, listAccounts, register, signIn, type Account } from "../data/accounts";
import { Button } from "../components/ui";

type Mode = "signin" | "register";

const date = (ms: number) => new Date(ms).toLocaleDateString("en-GB", { day: "numeric", month: "short", year: "numeric" });

export default function SignInTab() {
  const { account } = useAuth();
  const [accounts, setAccounts] = useState<Account[]>([]);
  const refresh = () => listAccounts().then(setAccounts, () => setAccounts([]));
  useEffect(() => {
    refresh();
  }, [account]);

  return (
    <div className="grid gap-16 py-4 md:grid-cols-[minmax(0,1fr)_420px] md:items-start">
      <div className="max-w-md">
        <p className="text-xs font-medium uppercase tracking-[0.18em] text-accent">For brands and content owners</p>
        <h1 className="mt-3 font-serif text-4xl font-medium tracking-tight sm:text-5xl">{account ? "Your account" : "Sign in"}</h1>
        <p className="mt-4 text-[15px] leading-relaxed text-ink-2">
          Manage your placements, follow your auctions and see how every market performs, all from one account.
        </p>
        <blockquote className="mt-12 border-l-2 border-ink pl-5 font-serif text-xl italic leading-relaxed text-ink-2">
          One scene. A different local brand in every country, placed in minutes instead of days.
        </blockquote>
        <DatabaseNote count={accounts.length} />
      </div>

      <AnimatePresence mode="wait">
        {account === undefined ? null : account ? (
          <motion.div key="account" initial={{ opacity: 0, y: 6 }} animate={{ opacity: 1, y: 0 }} exit={{ opacity: 0 }} transition={{ duration: 0.2 }}>
            <AccountPanel account={account} accounts={accounts} />
          </motion.div>
        ) : (
          <motion.div key="forms" initial={{ opacity: 0, y: 6 }} animate={{ opacity: 1, y: 0 }} exit={{ opacity: 0 }} transition={{ duration: 0.2 }}>
            <Forms />
          </motion.div>
        )}
      </AnimatePresence>
    </div>
  );
}

function DatabaseNote({ count }: { count: number }) {
  return (
    <div className="mt-12 flex gap-3 border-t border-rule pt-5 text-sm text-ink-2">
      <Database size={18} className="mt-0.5 shrink-0 text-muted" />
      <p>
        <b className="tabular-nums">{count}</b> account{count === 1 ? "" : "s"} saved in this browser's database (IndexedDB). They stay after
        a reload or a restart. Passwords are never stored, only a salted PBKDF2 hash.
      </p>
    </div>
  );
}

function Forms() {
  const { setAccount } = useAuth();
  const [mode, setMode] = useState<Mode>("signin");
  const [name, setName] = useState("");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [show, setShow] = useState(false);
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState<{ error: boolean; text: string } | null>(null);

  const switchTo = (m: Mode) => {
    setMode(m);
    setMessage(null);
    setPassword("");
  };

  const submit = async (e: FormEvent) => {
    e.preventDefault();
    setBusy(true);
    setMessage(null);
    try {
      setAccount(mode === "signin" ? await signIn(email, password) : await register(name, email, password));
    } catch (err) {
      setMessage({ error: true, text: (err as Error).message });
      setPassword("");
    } finally {
      setBusy(false);
    }
  };

  return (
    <form onSubmit={submit} className="border border-rule bg-card p-8" noValidate>
      <p className="font-serif text-2xl">{mode === "signin" ? "Welcome back" : "Create your account"}</p>

      {mode === "register" && (
        <Field label="Name or company">
          <input value={name} onChange={(e) => setName(e.target.value)} autoComplete="organization" className={INPUT} />
        </Field>
      )}

      <Field label="Email address">
        <input type="email" value={email} onChange={(e) => setEmail(e.target.value)} placeholder="you@company.com" autoComplete="email" className={INPUT} />
      </Field>

      <div className="mt-5 text-xs text-muted">
        <div className="flex items-baseline justify-between">
          <label htmlFor="signin-password">Password{mode === "register" ? " (at least 8 characters)" : ""}</label>
          {mode === "signin" && (
            <button
              type="button"
              onClick={() => setMessage({ error: false, text: "Password reset is not available in the prototype. Use the demo account below." })}
              className="text-xs text-ink underline decoration-rule-strong underline-offset-4 hover:decoration-ink"
            >
              Forgot password?
            </button>
          )}
        </div>
        <span className="mt-1.5 flex items-center border border-rule-strong bg-card focus-within:border-ink">
          <input
            id="signin-password"
            type={show ? "text" : "password"}
            value={password}
            onChange={(e) => setPassword(e.target.value)}
            autoComplete={mode === "signin" ? "current-password" : "new-password"}
            className="w-full bg-transparent px-3 py-2.5 text-sm text-ink outline-none"
          />
          <button type="button" onClick={() => setShow((s) => !s)} aria-label={show ? "Hide password" : "Show password"} className="px-3 text-muted hover:text-ink">
            {show ? <EyeOff size={16} /> : <Eye size={16} />}
          </button>
        </span>
      </div>

      <Button type="submit" className="mt-6 w-full" disabled={busy}>
        {busy ? "One moment…" : mode === "signin" ? "Sign in" : "Create account"}
      </Button>

      <AnimatePresence mode="wait">
        {message && (
          <motion.p
            key={message.text}
            initial={{ opacity: 0, y: -4 }}
            animate={{ opacity: 1, y: 0 }}
            exit={{ opacity: 0 }}
            role={message.error ? "alert" : "status"}
            className={`mt-4 text-sm ${message.error ? "text-accent" : "text-muted"}`}
          >
            {message.text}
          </motion.p>
        )}
      </AnimatePresence>

      {mode === "signin" && (
        <div className="mt-6 bg-paper px-4 py-3 text-sm text-ink-2">
          Demo account: <span className="font-mono text-xs">{DEMO_ACCOUNT.email}</span> / <span className="font-mono text-xs">{DEMO_ACCOUNT.password}</span>
          <button
            type="button"
            onClick={() => {
              setEmail(DEMO_ACCOUNT.email);
              setPassword(DEMO_ACCOUNT.password);
              setMessage(null);
            }}
            className="ml-2 underline decoration-rule-strong underline-offset-4 hover:decoration-ink"
          >
            Fill in
          </button>
        </div>
      )}

      <p className="mt-6 border-t border-rule pt-5 text-sm text-ink-2">
        {mode === "signin" ? "New to SwapBoard? " : "Already have an account? "}
        <button
          type="button"
          onClick={() => switchTo(mode === "signin" ? "register" : "signin")}
          className="text-ink underline decoration-rule-strong underline-offset-4 hover:decoration-ink"
        >
          {mode === "signin" ? "Create an account" : "Sign in"}
        </button>
      </p>
    </form>
  );
}

const INPUT = "mt-1.5 block w-full border border-rule-strong bg-card px-3 py-2.5 text-sm text-ink outline-none focus:border-ink";

function Field({ label, children }: { label: string; children: ReactNode }) {
  return (
    <label className="mt-5 block text-xs text-muted">
      {label}
      {children}
    </label>
  );
}

function AccountPanel({ account, accounts }: { account: Account; accounts: Account[] }) {
  const { signOut } = useAuth();
  const initials = account.name
    .split(/\s+/)
    .map((w) => w[0])
    .join("")
    .slice(0, 2)
    .toUpperCase();

  return (
    <div className="border border-rule bg-card p-8">
      <div className="flex items-center gap-4">
        <span className="grid size-12 shrink-0 place-items-center rounded-full bg-ink font-serif text-lg text-paper">{initials}</span>
        <div className="min-w-0">
          <p className="text-xs uppercase tracking-[0.14em] text-muted">Signed in as</p>
          <p className="truncate font-serif text-2xl">{account.name}</p>
        </div>
      </div>
      <dl className="mt-6 grid grid-cols-2 gap-4 border-t border-rule pt-5 text-sm">
        <div className="col-span-2">
          <dt className="text-xs text-muted">Email</dt>
          <dd className="truncate">{account.email}</dd>
        </div>
        <div>
          <dt className="text-xs text-muted">Member since</dt>
          <dd>{date(account.created)}</dd>
        </div>
        <div>
          <dt className="text-xs text-muted">Session</dt>
          <dd>7 days on this browser</dd>
        </div>
      </dl>
      <Button variant="secondary" className="mt-6 w-full" onClick={signOut}>
        Sign out
      </Button>

      <p className="mt-8 text-xs uppercase tracking-[0.14em] text-muted">Accounts in the database · {accounts.length}</p>
      <ul className="mt-2 max-h-56 overflow-y-auto">
        {accounts.map((a) => (
          <li key={a.email} className={`flex items-baseline justify-between gap-3 border-b border-rule py-2 text-sm ${a.email === account.email ? "font-medium" : ""}`}>
            <span className="min-w-0 truncate">
              {a.name} <span className="text-xs text-muted">{a.email}</span>
            </span>
            <span className="shrink-0 text-xs text-muted">{date(a.created)}</span>
          </li>
        ))}
      </ul>
    </div>
  );
}
