// Conturile site-ului, salvate în baza de date a browserului (IndexedDB): rămân după reîncărcare și după
// închiderea browserului, merg și cu demo/index.html deschis de pe disc, fără server.
// Parola nu se salvează: doar o amprentă PBKDF2 cu sare (Web Crypto), din care nu poate fi recuperată.

export interface Account {
  email: string;
  name: string;
  created: number;
}

interface StoredAccount extends Account {
  salt: string;
  hash: string;
}

const DB_NAME = "prodefenders";
const STORE = "accounts";
const SESSION_KEY = "pd_session";
const SESSION_DAYS = 7;
const EMAIL_RE = /^[^@\s]+@[^@\s]+\.[^@\s]+$/;

/** Creat la prima deschidere, ca la prezentare să existe mereu un cont cu care să intri. */
export const DEMO_ACCOUNT = { email: "demo@swapboard.app", name: "Demo Brand", password: "demo1234" };

function open(): Promise<IDBDatabase> {
  return new Promise((resolve, reject) => {
    const req = indexedDB.open(DB_NAME, 1);
    req.onupgradeneeded = () => req.result.createObjectStore(STORE, { keyPath: "email" });
    req.onsuccess = () => resolve(req.result);
    req.onerror = () => reject(new Error("This browser blocked its local database (private window?)"));
  });
}

async function tx<T>(mode: IDBTransactionMode, run: (s: IDBObjectStore) => IDBRequest<T>): Promise<T> {
  const db = await open();
  return new Promise((resolve, reject) => {
    const req = run(db.transaction(STORE, mode).objectStore(STORE));
    req.onsuccess = () => resolve(req.result);
    req.onerror = () => reject(req.error);
  });
}

const toHex = (buf: ArrayBuffer) => [...new Uint8Array(buf)].map((b) => b.toString(16).padStart(2, "0")).join("");
const fromHex = (hex: string) => new Uint8Array(hex.match(/../g)!.map((h) => parseInt(h, 16)));

async function hashPassword(password: string, salt: Uint8Array<ArrayBuffer>): Promise<string> {
  if (!crypto?.subtle) throw new Error("This browser can't hash passwords here; open the page in Chrome or Edge");
  const key = await crypto.subtle.importKey("raw", new TextEncoder().encode(password), "PBKDF2", false, ["deriveBits"]);
  const bits = await crypto.subtle.deriveBits({ name: "PBKDF2", salt, iterations: 150_000, hash: "SHA-256" }, key, 256);
  return toHex(bits);
}

const publicPart = ({ email, name, created }: StoredAccount): Account => ({ email, name, created });

async function store(email: string, name: string, password: string): Promise<Account> {
  const salt = crypto.getRandomValues(new Uint8Array(16));
  const account: StoredAccount = { email, name, created: Date.now(), salt: toHex(salt.buffer), hash: await hashPassword(password, salt) };
  await tx("readwrite", (s) => s.add(account));
  return publicPart(account);
}

let seeded: Promise<void> | undefined;
/** Contul demo, creat o singură dată pe fiecare browser. */
function ensureDemo(): Promise<void> {
  seeded ??= tx<StoredAccount | undefined>("readonly", (s) => s.get(DEMO_ACCOUNT.email)).then(async (found) => {
    if (!found) await store(DEMO_ACCOUNT.email, DEMO_ACCOUNT.name, DEMO_ACCOUNT.password);
  });
  return seeded;
}

/** Toate conturile, fără parole (pentru lista din pagina de cont). */
export async function listAccounts(): Promise<Account[]> {
  await ensureDemo();
  const all = await tx<StoredAccount[]>("readonly", (s) => s.getAll());
  return all.map(publicPart).sort((a, b) => a.created - b.created);
}

export async function register(name: string, email: string, password: string): Promise<Account> {
  await ensureDemo();
  const clean = email.trim().toLowerCase();
  if (!name.trim()) throw new Error("Enter your name or company");
  if (!EMAIL_RE.test(clean)) throw new Error("Enter a valid email address");
  if (password.length < 8) throw new Error("The password needs at least 8 characters");
  if (await tx("readonly", (s) => s.get(clean))) throw new Error("An account with this email already exists");
  const account = await store(clean, name.trim(), password);
  startSession(clean);
  return account;
}

export async function signIn(email: string, password: string): Promise<Account> {
  await ensureDemo();
  const found = await tx<StoredAccount | undefined>("readonly", (s) => s.get(email.trim().toLowerCase()));
  // același mesaj pentru email necunoscut și parolă greșită: nu dezvăluim ce conturi există
  if (!found || (await hashPassword(password, fromHex(found.salt))) !== found.hash) throw new Error("Wrong email or password");
  startSession(found.email);
  return publicPart(found);
}

function startSession(email: string) {
  try {
    localStorage.setItem(SESSION_KEY, JSON.stringify({ email, expires: Date.now() + SESSION_DAYS * 86_400_000 }));
  } catch {
    /* fără stocare (fereastră privată): rămâi logat doar până la reîncărcare */
  }
}

/** Contul logat acum, dacă sesiunea n-a expirat. */
export async function currentAccount(): Promise<Account | null> {
  let session: { email?: string; expires?: number } | null = null;
  try {
    session = JSON.parse(localStorage.getItem(SESSION_KEY) ?? "null");
  } catch {
    return null;
  }
  if (!session?.email || !session.expires || session.expires < Date.now()) return null;
  await ensureDemo();
  const found = await tx<StoredAccount | undefined>("readonly", (s) => s.get(session.email!));
  return found ? publicPart(found) : null;
}

export function signOut() {
  try {
    localStorage.removeItem(SESSION_KEY);
  } catch {
    /* nimic de șters */
  }
}
