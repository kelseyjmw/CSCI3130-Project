import { useState } from "react";
import { login } from "../api/auth";
import { useNavigate } from "react-router-dom";
import { useAuth } from "../context/AuthContext";

function Login() {

  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState("");
  const [previousLogin, setPreviousLogin] = useState(undefined);

  const navigate = useNavigate();
  const { refresh } = useAuth();

  async function handleSubmit(e) {

    e.preventDefault();
    setError("");

    // Validate email
    if (!email.trim()) {
      setError("Email is required.");
      return;
    }

    const emailPattern = /^[^\s@]+@[^\s@]+\.[^\s@]+$/;

    if (!emailPattern.test(email.trim())) {
      setError("Please enter a valid email address.");
      return;
    }

    // Validate password
    if (!password) {
      setError("Password is required.");
      return;
    }

    try {

      const data = await login(email.trim(), password);
      setPreviousLogin(data.previous_login);
      console.log("Login successful");

      // Re-fetch /me/ so AuthContext knows about the new session
      // before we navigate to a route guarded by RequireAuth.
      await refresh();
      navigate("/dashboard");

    } catch (error) {
      setError(error.message);
    }
  }

  return (
    <div id="app-form">
      <h1>Login</h1>

      <form onSubmit={handleSubmit}>
        <div className="form-section">
          <label>Email</label>
          <input type="email" value={email || ''} onChange={(e) => setEmail(e.target.value)} placeholder="example@email.com"/>
        </div>

        <div className="form-section">
          <label>Password</label>
          <input type="password" value={password || ''} onChange={(e) => setPassword(e.target.value)} placeholder="Enter your password"/>
        </div>

        {error && (
          <span style={{ color: 'red', fontSize: '13px' }}>
            {error}
          </span>
        )}

        <button type="submit">
          Log In
        </button>
      </form>
    </div>
  );
}

export default Login;