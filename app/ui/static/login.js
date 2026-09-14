(() => {
  const form = document.querySelector("#login-form");
  const error = document.querySelector("#login-error");
  form.addEventListener("submit", async (event) => {
    event.preventDefault();
    error.textContent = "";
    const input = document.querySelector("#admin-key");
    try {
      const response = await fetch("/admin/session", { method: "POST", credentials: "same-origin", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ admin_api_key: input.value }) });
      input.value = "";
      if (!response.ok) throw new Error((await response.json()).detail || "Sign in failed");
      window.location.assign("/admin");
    } catch (err) { input.value = ""; error.textContent = err.message || "Sign in failed"; }
  });
})();

