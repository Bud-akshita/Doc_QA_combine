import React, { useState , useEffect } from "react";
import { Eye, EyeOff, Lock, Mail, LogIn, UserPlus } from "lucide-react";
import "./auth.css"; 
import DocumentManager from "./DocumentManager";
import { getBackendUrl } from "./utils/getBackendUrl";

const AuthComponent = () => {
  const [isLogin, setIsLogin] = useState(true);
  const [showPassword, setShowPassword] = useState(false);
  const [formData, setFormData] = useState({
    email: "",
    password: "",
  });
  const [loading, setLoading] = useState(false);
  const [message, setMessage] = useState({ text: "", type: "" });
  const [token, setToken] = useState(null);
  const [userData, setUserData] = useState(null);
  const [API_BASE_URL, setApiBaseUrl] = useState("");
  // ... other state

  // Fetch backend URL on mount
  useEffect(() => {
    const fetchUrl = async () => {
      try {
        const url = await getBackendUrl();
        setApiBaseUrl(url);
      } catch (error) {
        console.error("Failed to get backend URL:", error);
      }
    };
    fetchUrl();
  }, []);

  const handleInputChange = (e) => {
    setFormData({
      ...formData,
      [e.target.name]: e.target.value,
    });
    // Clear messages when user starts typing
    if (message.text) {
      setMessage({ text: "", type: "" });
    }
  };

  const handleRegister = async () => {
    setLoading(true);
    setMessage({ text: "", type: "" });

    try {
      const response = await fetch(`${API_BASE_URL}/auth/`, {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
        },
        body: JSON.stringify({
          email: formData.email,
          password: formData.password,
        }),
      });

      if (response.ok) {
        setMessage({
          text: "Registration successful! You can now login.",
          type: "success",
        });
        setFormData({ email: "", password: "" });
        setIsLogin(true);
      } else {
        const errorData = await response.json();
        setMessage({
          text: errorData.detail || "Registration failed",
          type: "error",
        });
      }
    } catch (error) {
      setMessage({ text: "Network error. Please try again.", type: "error" });
    } finally {
      setLoading(false);
    }
  };

  const handleLogin = async () => {
    setLoading(true);
    setMessage({ text: "", type: "" });

    try {
      const formDataToSend = new FormData();
      formDataToSend.append("username", formData.email);
      formDataToSend.append("password", formData.password);

      const response = await fetch(`${API_BASE_URL}/auth/login`, {
        method: "POST",
        body: formDataToSend,
      });

      if (response.ok) {
        const data = await response.json();
        setToken(data.access_token);
        setMessage({ text: "Login successful!", type: "success" });
        setFormData({ email: "", password: "" });

        // Fetch user data after successful login
        await fetchUserData(data.access_token);
      } else {
        const errorData = await response.json();
        setMessage({ text: errorData.detail || "Login failed", type: "error" });
      }
    } catch (error) {
      setMessage({ text: "Network error. Please try again.", type: "error" });
    } finally {
      setLoading(false);
    }
  };

  const fetchUserData = async (accessToken) => {
    try {
      const response = await fetch(`${API_BASE_URL}/`, {
        method: "GET",
        headers: {
          Authorization: `Bearer ${accessToken}`,
          "Content-Type": "application/json",
        },
      });

      if (response.ok) {
        const data = await response.json();
        setUserData(data.User);
      }
    } catch (error) {
      console.error("Failed to fetch user data:", error);
    }
  };

  const handleLogout = async () => {
    if (!token) return;

    try {
      await fetch(`${API_BASE_URL}/auth/logout`, {
        method: "POST",
        headers: {
          Authorization: `Bearer ${token}`,
          "Content-Type": "application/json",
        },
      });
    } catch (error) {
      console.error("Logout error:", error);
    } finally {
      setToken(null);
      setUserData(null);
      setMessage({ text: "Logged out successfully", type: "success" });
    }
  };

  const toggleMode = () => {
    setIsLogin(!isLogin);
    setFormData({ email: "", password: "" });
    setMessage({ text: "", type: "" });
  };

  // If user is logged in, show docs
  if (token && userData) {
    return (
      <DocumentManager
        token={token}
        userData={userData}
        onLogout={handleLogout}
      />
    );
  }

  return (
    <div className="auth-container">
      <div className="auth-card">
        <div className="auth-header">
          <div
            className={`auth-icon-container ${isLogin ? "login" : "register"}`}
          >
            {isLogin ? (
              <LogIn className="auth-icon" />
            ) : (
              <UserPlus className="auth-icon" />
            )}
          </div>
          <h2 className="auth-title">
            {isLogin ? "Welcome Back" : "Create Account"}
          </h2>
          <p className="auth-subtitle">
            {isLogin ? "Sign in to your account" : "Sign up for a new account"}
          </p>
        </div>

        {message.text && (
          <div className={`message ${message.type}`}>{message.text}</div>
        )}

        <div className="auth-form">
          <div className="input-group">
            <label htmlFor="email" className="input-label">
              Email Address
            </label>
            <div className="input-container">
              <Mail className="input-icon" />
              <input
                type="email"
                id="email"
                name="email"
                value={formData.email}
                onChange={handleInputChange}
                required
                className="input-field"
                placeholder="Enter your email"
              />
            </div>
          </div>

          <div className="input-group">
            <label htmlFor="password" className="input-label">
              Password
            </label>
            <div className="input-container">
              <Lock className="input-icon" />
              <input
                type={showPassword ? "text" : "password"}
                id="password"
                name="password"
                value={formData.password}
                onChange={handleInputChange}
                required
                className="input-field with-toggle"
                placeholder="Enter your password"
              />
              <button
                type="button"
                onClick={() => setShowPassword(!showPassword)}
                className="password-toggle"
              >
                {showPassword ? (
                  <EyeOff className="password-toggle-icon" />
                ) : (
                  <Eye className="password-toggle-icon" />
                )}
              </button>
            </div>
          </div>

          <button
            type="button"
            onClick={isLogin ? handleLogin : handleRegister}
            disabled={loading}
            className="auth-button primary"
          >
            {loading ? (
              <>
                <div className="loading-spinner"></div>
                {isLogin ? "Signing in..." : "Creating account..."}
              </>
            ) : (
              <>
                {isLogin ? (
                  <LogIn className="button-icon" />
                ) : (
                  <UserPlus className="button-icon" />
                )}
                {isLogin ? "Sign In" : "Create Account"}
              </>
            )}
          </button>
        </div>

        <div className="auth-toggle">
          <p className="auth-toggle-text">
            {isLogin ? "Don't have an account?" : "Already have an account?"}
          </p>
          <button onClick={toggleMode} className="auth-toggle-button">
            {isLogin ? "Create one here" : "Sign in instead"}
          </button>
        </div>
      </div>
    </div>
  );
};

export default AuthComponent;
