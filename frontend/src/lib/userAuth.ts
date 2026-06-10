const TOKEN_KEY = "ot_user_token";
const USER_KEY = "ot_username";

export function getUserToken(): string {
  return window.localStorage.getItem(TOKEN_KEY) || "";
}

export function getUsername(): string {
  return window.localStorage.getItem(USER_KEY) || "";
}

export function setUserAuth(token: string, username: string): void {
  window.localStorage.setItem(TOKEN_KEY, token);
  window.localStorage.setItem(USER_KEY, username);
}

export function clearUserAuth(): void {
  window.localStorage.removeItem(TOKEN_KEY);
  window.localStorage.removeItem(USER_KEY);
}

export function isLoggedIn(): boolean {
  return !!getUserToken();
}

export function userAuthHeaders(): Record<string, string> {
  const token = getUserToken();
  return token ? { Authorization: `Bearer ${token}` } : {};
}
