const TOKEN_KEY = "ot_user_token";
const USER_KEY = "ot_username";
const ADMIN_KEY = "ot_is_admin";

export function getUserToken(): string {
  return window.localStorage.getItem(TOKEN_KEY) || "";
}

export function getUsername(): string {
  return window.localStorage.getItem(USER_KEY) || "";
}

export function isAdmin(): boolean {
  return window.localStorage.getItem(ADMIN_KEY) === "1";
}

export function setUserAuth(token: string, username: string, admin = false): void {
  window.localStorage.setItem(TOKEN_KEY, token);
  window.localStorage.setItem(USER_KEY, username);
  if (admin) {
    window.localStorage.setItem(ADMIN_KEY, "1");
  } else {
    window.localStorage.removeItem(ADMIN_KEY);
  }
}

export function clearUserAuth(): void {
  window.localStorage.removeItem(TOKEN_KEY);
  window.localStorage.removeItem(USER_KEY);
  window.localStorage.removeItem(ADMIN_KEY);
}

export function isLoggedIn(): boolean {
  return !!getUserToken();
}

export function userAuthHeaders(): Record<string, string> {
  const token = getUserToken();
  return token ? { Authorization: `Bearer ${token}` } : {};
}
