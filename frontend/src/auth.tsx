import { createContext, useCallback, useContext, useEffect, useState, type ReactNode } from "react";
import { currentAccount, signOut as endSession, type Account } from "./data/accounts";

interface AuthState {
  /** contul logat; null = nimeni, undefined = încă se citește din baza de date */
  account: Account | null | undefined;
  setAccount: (a: Account | null) => void;
  signOut: () => void;
}

const AuthContext = createContext<AuthState | null>(null);

export function AuthProvider({ children }: { children: ReactNode }) {
  const [account, setAccount] = useState<Account | null | undefined>(undefined);

  useEffect(() => {
    currentAccount().then(setAccount, () => setAccount(null));
  }, []);

  const signOut = useCallback(() => {
    endSession();
    setAccount(null);
  }, []);

  return <AuthContext.Provider value={{ account, setAccount, signOut }}>{children}</AuthContext.Provider>;
}

export function useAuth(): AuthState {
  const ctx = useContext(AuthContext);
  if (!ctx) throw new Error("useAuth must be used inside <AuthProvider>");
  return ctx;
}
