// Ecran de autentificare doar pentru demo: nu trimite și nu salvează nimic.
import { useState, type FormEvent } from "react";
import { AnimatePresence, motion } from "framer-motion";
import { Eye, EyeOff } from "lucide-react";
import { Button } from "../components/ui";

const DEMO_NOTE = "Demo only: accounts are not connected yet, so nothing was sent.";

export default function SignInTab() {
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [show, setShow] = useState(false);
  const [note, setNote] = useState<string | null>(null);

  const submit = (e: FormEvent) => {
    e.preventDefault();
    setPassword("");
    setNote(DEMO_NOTE);
  };

  return (
    <div className="grid gap-16 py-4 md:grid-cols-[minmax(0,1fr)_400px] md:items-start">
      <div className="max-w-md">
        <p className="text-xs font-medium uppercase tracking-[0.18em] text-accent">For brands and content owners</p>
        <h1 className="mt-3 font-serif text-4xl font-medium tracking-tight sm:text-5xl">Sign in</h1>
        <p className="mt-4 text-[15px] leading-relaxed text-ink-2">
          Manage your placements, follow your auctions and see how every market performs, all from one account.
        </p>
        <blockquote className="mt-12 border-l-2 border-ink pl-5 font-serif text-xl italic leading-relaxed text-ink-2">
          One scene. A different local brand in every country, placed in minutes instead of days.
        </blockquote>
      </div>

      <form onSubmit={submit} className="border border-rule bg-card p-8" noValidate>
        <label className="block text-xs text-muted">
          Email address
          <input
            type="email"
            autoComplete="off"
            value={email}
            onChange={(e) => setEmail(e.target.value)}
            placeholder="you@company.com"
            className="mt-1.5 block w-full border border-rule-strong bg-card px-3 py-2.5 text-sm text-ink outline-none focus:border-ink"
          />
        </label>

        <div className="mt-5 text-xs text-muted">
          <div className="flex items-baseline justify-between">
            <label htmlFor="signin-password">Password</label>
            <button
              type="button"
              onClick={() => setNote("Demo only: password reset is not available yet.")}
              className="text-xs text-ink underline decoration-rule-strong underline-offset-4 hover:decoration-ink"
            >
              Forgot password?
            </button>
          </div>
          <span className="mt-1.5 flex items-center border border-rule-strong bg-card focus-within:border-ink">
            <input
              id="signin-password"
              type={show ? "text" : "password"}
              autoComplete="off"
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              className="w-full bg-transparent px-3 py-2.5 text-sm text-ink outline-none"
            />
            <button
              type="button"
              onClick={() => setShow((s) => !s)}
              aria-label={show ? "Hide password" : "Show password"}
              className="px-3 text-muted hover:text-ink"
            >
              {show ? <EyeOff size={16} /> : <Eye size={16} />}
            </button>
          </span>
        </div>

        <label className="mt-5 flex items-center gap-2 text-sm text-ink-2">
          <input type="checkbox" className="size-4 accent-[var(--ink)]" />
          Keep me signed in
        </label>

        <Button type="submit" className="mt-6 w-full">
          Sign in
        </Button>

        <AnimatePresence mode="wait">
          {note && (
            <motion.p
              key={note}
              initial={{ opacity: 0, y: -4 }}
              animate={{ opacity: 1, y: 0 }}
              exit={{ opacity: 0 }}
              className="mt-4 text-sm text-muted"
            >
              {note}
            </motion.p>
          )}
        </AnimatePresence>

        <p className="mt-8 border-t border-rule pt-5 text-sm text-ink-2">
          New to Swapboard?{" "}
          <button
            type="button"
            onClick={() => setNote("Demo only: account requests are not available yet.")}
            className="text-ink underline decoration-rule-strong underline-offset-4 hover:decoration-ink"
          >
            Request access
          </button>
        </p>
      </form>
    </div>
  );
}
