import { useState, type FormEvent } from "react";
import { api } from "../api";
import { Wordmark } from "./Icons";

export default function AuthPage({ onAuthed }: { onAuthed: (token: string) => void }) {
  const [mode, setMode] = useState<"login" | "register">("login");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [showPassword, setShowPassword] = useState(false);

  const submit = async (e: FormEvent) => {
    e.preventDefault();
    setError(null);
    setBusy(true);
    try {
      if (mode === "register") await api.register(email, password);
      const { access_token } = await api.login(email, password);
      onAuthed(access_token);
    } catch (err) {
      setError(err instanceof Error ? err.message : "something went wrong");
    } finally {
      setBusy(false);
    }
  };

  const isLogin = mode === "login";
  const switchMode = () => {
    setMode(isLogin ? "register" : "login");
    setError(null);
  };

  return (
    <div className="auth">
      <div className="auth-col">
        <div className="auth-logo">
          <Wordmark size={34} />
        </div>
        <h1 className="auth-title">{isLogin ? "Sign in to Sage" : "Create your Sage account"}</h1>

        {error && (
          <div className="auth-flash" role="alert">
            {error}
          </div>
        )}

        <form className="auth-box" onSubmit={submit}>
          <label htmlFor="email">Email address</label>
          <input
            id="email"
            type="email"
            autoComplete="email"
            autoFocus
            value={email}
            onChange={(e) => setEmail(e.target.value)}
            required
          />

          <label htmlFor="password">Password</label>
          <div className="password-field">
            <input
              id="password"
              type={showPassword ? "text" : "password"}
              autoComplete={isLogin ? "current-password" : "new-password"}
              minLength={isLogin ? undefined : 8}
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              required
            />
            <button
              type="button"
              className="password-toggle"
              onClick={() => setShowPassword((v) => !v)}
              aria-label={showPassword ? "Hide password" : "Show password"}
            >
              {showPassword ? "Hide" : "Show"}
            </button>
          </div>
          {!isLogin && <p className="auth-note">Use at least 8 characters.</p>}

          <button type="submit" className="auth-submit" disabled={busy}>
            {busy ? (isLogin ? "Signing in…" : "Creating account…") : isLogin ? "Sign in" : "Create account"}
          </button>
        </form>

        <div className="auth-box auth-switch">
          {isLogin ? "New to Sage?" : "Already have an account?"}{" "}
          <button type="button" className="link" onClick={switchMode}>
            {isLogin ? "Create an account" : "Sign in"}
          </button>
        </div>

        <p className="auth-footer">S.A.G.E · Smart AI Gateway Engine</p>
      </div>
    </div>
  );
}
