document.getElementById("loginForm").addEventListener("submit", async event => {
  event.preventDefault();
  const errorBanner = document.getElementById("errorBanner");
  errorBanner.style.display = "none";

  const username = document.getElementById("username").value.trim();
  const password = document.getElementById("password").value;
  const role = document.body.dataset.portalRole;

  try {
    const response = await fetch("/api/auth/login", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ username, password })
    });
    const data = await response.json();
    if (!response.ok) throw new Error(data.detail || "Authentication failed.");

    const allowedRoles = role === "ADMIN"
      ? ["ADMIN"]
      : role === "ELECTRICIAN"
        ? ["ELECTRICIAN", "ADMIN"]
        : ["MANAGEMENT", "ADMIN"];
    if (!allowedRoles.includes(data.role)) {
      const message = role === "ADMIN"
        ? "This portal is restricted to Administrator accounts."
        : role === "ELECTRICIAN"
          ? "This portal is restricted to Electrician accounts. Use Management login."
          : "This portal is restricted to Management & Admin accounts. Use Electrician login.";
      throw new Error(message);
    }

    localStorage.setItem("dss_token", data.access_token);
    localStorage.setItem("dss_user", JSON.stringify(data));
    window.location.href = data.role === "ADMIN"
      ? "/admin"
      : data.role === "ELECTRICIAN"
        ? "/electrician"
        : "/management";
  } catch (error) {
    errorBanner.textContent = error.message;
    errorBanner.style.display = "block";
  }
});
