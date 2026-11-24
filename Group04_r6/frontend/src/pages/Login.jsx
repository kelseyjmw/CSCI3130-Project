import { useState } from "react";
import {
  confirmTwoFactorSetup,
  login,
  startTwoFactorSetup,
  verifyLoginMfa,
} from "../api/auth";
import { Link, useNavigate } from "react-router-dom";
import { useAuth } from "../context/AuthContext";

function Login() {
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [code, setCode] = useState("");
  const [recoveryCode, setRecoveryCode] = useState(false);
  const [setup, setSetup] = useState(null);
  const [recoveryCodes, setRecoveryCodes] = useState([]);
  const [error, setError] = useState("");
  const [step, setStep] = useState("credentials");
  const [busy, setBusy] = useState(false);

  const navigate = useNavigate();
  const { refresh } = useAuth();

  async function finishLogin() {
    await refresh();
    navigate("/dashboard");
  }

  async function handleCredentialsSubmit(e) {
    e.preventDefault();
    setError("");
    if (!email.trim()) {
      setError("Email is required.");
      return;
    }
    if (!password) {
      setError("Password is required.");
      return;
    }

    setBusy(true);
    try {
      const data = await login(email.trim(), password);
      if (data.enrollment_required) {
        setSetup(await startTwoFactorSetup());
        setStep("enroll");
      } else if (data.mfa_required) {
        setStep("mfa");
      } else {
        await finishLogin();
      }
    } catch (err) {
      setError(err.message);
    } finally {
      setBusy(false);
    }
  }

  async function handleMfaSubmit(e) {
    e.preventDefault();
    setError("");
    if (!code.trim()) {
      setError("Enter a verification code.");
      return;
    }
    setBusy(true);
    try {
      await verifyLoginMfa(code.trim(), recoveryCode);
      await finishLogin();
    } catch (err) {
      setError(err.message);
    } finally {
      setBusy(false);
    }
  }

  async function handleEnrollmentSubmit(e) {
    e.preventDefault();
    setError("");
    if (!code.trim()) {
      setError("Enter the code from your authenticator app.");
      return;
    }
    setBusy(true);
    try {
      const data = await confirmTwoFactorSetup(code.trim());
      setRecoveryCodes(data.recovery_codes);
      setStep("recovery");
    } catch (err) {
      setError(err.message);
    } finally {
      setBusy(false);
    }
  }

  return (
    <div id="app-form">
      <h1>Login</h1>

      {step === "credentials" && (
        <form onSubmit={handleCredentialsSubmit}>
          <div className="form-section">
            <label htmlFor="login-email">Email</label>
            <input
              id="login-email"
              type="email"
              autoComplete="username"
              value={email}
              onChange={(e) => setEmail(e.target.value)}
              placeholder="example@email.com"
              required
            />
          </div>

          <div className="form-section">
            <label htmlFor="login-password">Password</label>
            <input
              id="login-password"
              type="password"
              autoComplete="current-password"
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              placeholder="Enter your password"
              required
            />
          </div>
          {error && <p role="alert" className="form-error">{error}</p>}
          <button type="submit" disabled={busy}>
            {busy ? "Signing in..." : "Log In"}
          </button>
          <p><Link to="/forgot-password">Forgot your password?</Link></p>
        </form>
      )}

      {step === "mfa" && (
        <form onSubmit={handleMfaSubmit}>
          <p>Enter a code from your authenticator app, or use an unused recovery code.</p>
          <label>
            <input
              type="checkbox"
              checked={recoveryCode}
              onChange={(e) => {
                setRecoveryCode(e.target.checked);
                setCode("");
              }}
            />
            Use a recovery code
          </label>
          <div className="form-section">
            <label htmlFor="mfa-code">{recoveryCode ? "Recovery code" : "Authenticator code"}</label>
            <input
              id="mfa-code"
              type="text"
              autoComplete="one-time-code"
              inputMode={recoveryCode ? "text" : "numeric"}
              value={code}
              onChange={(e) => setCode(e.target.value)}
              required
            />
          </div>
          {error && <p role="alert" className="form-error">{error}</p>}
          <button type="submit" disabled={busy}>
            {busy ? "Verifying..." : "Verify and Log In"}
          </button>
        </form>
      )}

      {step === "enroll" && setup && (
        <form onSubmit={handleEnrollmentSubmit}>
          <p>Administrators must set up an authenticator app before continuing.</p>
          <p>In your TOTP app, add this account using the setup key:</p>
          <p><strong>{setup.secret}</strong></p>
          <details>
            <summary>Manual setup details</summary>
            <p className="page-placeholder">{setup.otpauth_url}</p>
          </details>
          <div className="form-section">
            <label htmlFor="enrollment-code">Authenticator code</label>
            <input
              id="enrollment-code"
              type="text"
              inputMode="numeric"
              autoComplete="one-time-code"
              value={code}
              onChange={(e) => setCode(e.target.value)}
              required
            />
          </div>
          {error && <p role="alert" className="form-error">{error}</p>}
          <button type="submit" disabled={busy}>
            {busy ? "Verifying..." : "Enable Two-Factor Authentication"}
          </button>
        </form>
      )}

      {step === "recovery" && (
        <div>
          <h2>Save your recovery codes</h2>
          <p>These 10 codes are shown only once. Each code can be used once if your authenticator is unavailable.</p>
          <ul aria-label="Recovery codes">
            {recoveryCodes.map((recovery) => <li key={recovery}>{recovery}</li>)}
          </ul>
          <button type="button" onClick={finishLogin}>I saved these codes — continue</button>
        </div>
      )}
      {(step === "mfa" || step === "enroll") && (
        <button type="button" disabled={busy} onClick={() => {
          setStep("credentials");
          setCode("");
          setRecoveryCode(false);
          setSetup(null);
          setError("");
        }}>Back to login</button>
      )}
    </div>
  );
}

export default Login;
