/**
 * BTF – Client API Frontend
 * Toutes les requêtes vers le backend FastAPI
 *
 * ⚙️  CONFIGURATION DÉPLOIEMENT :
 * - Développement local : API_BASE pointe vers http://localhost:8000/api/v1
 * - Production : changer BTF_API_URL ci-dessous avec votre URL Render
 *   ex: const BTF_API_URL = 'https://btf-api.onrender.com';
 */

// ── Changer cette URL avec votre backend Render en production ──
const BTF_API_URL = window.BTF_API_URL
  || (window.location.hostname === 'localhost' || window.location.hostname === '127.0.0.1'
      ? 'http://localhost:8000'
      : window.location.origin);

const API_BASE = BTF_API_URL + '/api/v1';

class BTFApi {

  // ─── AUTH ────────────────────────────────────────────────────────────────
  static async login(email, password) {
    const form = new FormData();
    form.append('username', email);
    form.append('password', password);
    return await BTFApi._req('POST', '/auth/login', form, false);
  }

  static async register(data) {
    return await BTFApi._req('POST', '/auth/register', data);
  }

  static async verifyTotp(userId, code) {
    return await BTFApi._req('POST', '/auth/totp/verify', { user_id: userId, totp_code: code });
  }

  static async setupTotp() {
    return await BTFApi._req('POST', '/auth/totp/setup');
  }

  static async enableTotp(code) {
    return await BTFApi._req('POST', `/auth/totp/enable?code=${code}`);
  }

  static async refreshToken() {
    const rt = localStorage.getItem('btf_refresh');
    if (!rt) return null;
    return await BTFApi._req('POST', '/auth/refresh', { refresh_token: rt }, false);
  }

  static async logout() {
    await BTFApi._req('POST', '/auth/logout');
    BTFApi.clearAuth();
  }

  // ─── TRADING ─────────────────────────────────────────────────────────────
  static async placeOrder(orderData) {
    return await BTFApi._req('POST', '/trading/order', orderData);
  }

  static async getOrders(statusFilter = null, limit = 50) {
    const q = new URLSearchParams({ limit });
    if (statusFilter) q.set('status_filter', statusFilter);
    return await BTFApi._req('GET', `/trading/orders?${q}`);
  }

  static async cancelOrder(orderId) {
    return await BTFApi._req('DELETE', `/trading/order/${orderId}`);
  }

  static async getPortfolio() {
    return await BTFApi._req('GET', '/trading/portfolio');
  }

  static async getPerformance() {
    return await BTFApi._req('GET', '/trading/performance');
  }

  static async toggleAutonomous(enabled, confirm = true) {
    return await BTFApi._req('POST', '/trading/autonomous/toggle', { enabled, confirm });
  }

  // ─── MARCHÉS ─────────────────────────────────────────────────────────────
  static async getMarketData(exchange, symbol, timeframe = '15m') {
    return await BTFApi._req('GET', `/markets/ohlcv?exchange=${exchange}&symbol=${encodeURIComponent(symbol)}&timeframe=${timeframe}`);
  }

  static async getSignals(limit = 20) {
    return await BTFApi._req('GET', `/markets/signals?limit=${limit}`);
  }

  static async getTickers() {
    return await BTFApi._req('GET', '/markets/tickers');
  }

  // ─── MARCHÉ PHYSIQUE ─────────────────────────────────────────────────────
  static async getPhysicalTrends(country = null, limit = 50) {
    const q = new URLSearchParams({ limit });
    if (country) q.set('country', country);
    return await BTFApi._req('GET', `/physical/trends?${q}`);
  }

  static async getPhysicalReport() {
    return await BTFApi._req('GET', '/physical/report');
  }

  // ─── PAIEMENTS ───────────────────────────────────────────────────────────
  static async getPaymentInfo() {
    return await BTFApi._req('GET', '/payments/info');
  }

  static async submitPayment(formData) {
    return await BTFApi._req('POST', '/payments/submit', formData, true, true);
  }

  static async getPaymentHistory() {
    return await BTFApi._req('GET', '/payments/history');
  }

  static async getSubscriptionStatus() {
    return await BTFApi._req('GET', '/payments/subscription-status');
  }

  // ─── RISK ────────────────────────────────────────────────────────────────
  static async getRiskProfile() {
    return await BTFApi._req('GET', '/risk/profile');
  }

  static async updateRiskProfile(data) {
    return await BTFApi._req('PUT', '/risk/profile', data);
  }

  // ─── USERS ───────────────────────────────────────────────────────────────
  static async getMe() {
    return await BTFApi._req('GET', '/users/me');
  }

  static async updateProfile(data) {
    return await BTFApi._req('PUT', '/users/me', data);
  }

  static async addApiKey(keyData) {
    return await BTFApi._req('POST', '/users/api-keys', keyData);
  }

  static async getApiKeys() {
    return await BTFApi._req('GET', '/users/api-keys');
  }

  static async deleteApiKey(keyId) {
    return await BTFApi._req('DELETE', `/users/api-keys/${keyId}`);
  }

  static async getAlerts(limit = 30) {
    return await BTFApi._req('GET', `/users/alerts?limit=${limit}`);
  }

  // ─── HTTP HELPER ─────────────────────────────────────────────────────────
  static async _req(method, path, body = null, auth = true, isFormData = false) {
    const headers = {};
    if (auth) {
      const token = localStorage.getItem('btf_token');
      if (token) headers['Authorization'] = `Bearer ${token}`;
    }
    if (body && !isFormData && !(body instanceof FormData)) {
      headers['Content-Type'] = 'application/json';
    }

    const opts = { method, headers };
    if (body) {
      if (body instanceof FormData) {
        opts.body = body;
      } else {
        opts.body = JSON.stringify(body);
      }
    }

    try {
      const resp = await fetch(API_BASE + path, opts);
      if (resp.status === 401) {
        // Tentative de refresh
        const refreshed = await BTFApi.refreshToken();
        if (refreshed?.access_token) {
          BTFApi.saveToken(refreshed.access_token);
          return await BTFApi._req(method, path, body, auth, isFormData);
        }
        BTFApi.clearAuth();
        if (!window.location.pathname.includes('login')) {
          window.location.href = '/pages/login.html';
        }
        return null;
      }
      const data = await resp.json().catch(() => ({}));
      if (!resp.ok) throw { status: resp.status, detail: data.detail || 'Erreur serveur' };
      return data;
    } catch (err) {
      if (err.detail) throw err;
      throw { status: 0, detail: 'Connexion impossible au serveur BTF.' };
    }
  }

  // ─── AUTH HELPERS ─────────────────────────────────────────────────────────
  static saveTokens(access, refresh) {
    localStorage.setItem('btf_token',   access);
    localStorage.setItem('btf_refresh', refresh);
  }
  static saveToken(access) {
    localStorage.setItem('btf_token', access);
  }
  static clearAuth() {
    localStorage.removeItem('btf_token');
    localStorage.removeItem('btf_refresh');
    localStorage.removeItem('btf_user');
  }
  static isLoggedIn() {
    return !!localStorage.getItem('btf_token');
  }
  static getUser() {
    try { return JSON.parse(localStorage.getItem('btf_user') || 'null'); } catch { return null; }
  }
  static saveUser(user) {
    localStorage.setItem('btf_user', JSON.stringify(user));
  }
}

// ─── WEBSOCKET MANAGER ────────────────────────────────────────────────────────
class BTFWebSocket {
  constructor() {
    this.priceWs = null;
    this.alertWs = null;
    this.priceHandlers = [];
    this.alertHandlers = [];
  }

  connectPrices(token) {
    const wsBase = location.origin.replace('http', 'ws');
    this.priceWs = new WebSocket(`${wsBase}/ws/prices?token=${token}`);
    this.priceWs.onmessage = (e) => {
      const msg = JSON.parse(e.data);
      if (msg.type === 'prices') {
        this.priceHandlers.forEach(h => h(msg.data));
      }
    };
    this.priceWs.onclose = () => setTimeout(() => this.connectPrices(token), 3000);
    this.priceWs.onerror = () => this.priceWs.close();
  }

  onPrice(handler) { this.priceHandlers.push(handler); }
  onAlert(handler) { this.alertHandlers.push(handler); }

  disconnect() {
    this.priceWs?.close();
    this.alertWs?.close();
  }
}

// ─── UI HELPERS ───────────────────────────────────────────────────────────────
class UI {
  static toast(message, type = 'info', duration = 4000) {
    const container = document.getElementById('toasts') || UI._createToastContainer();
    const el = document.createElement('div');
    el.className = `toast toast-${type} slide-up`;
    el.innerHTML = `
      <span class="toast-icon">${{info:'ℹ️',success:'✅',error:'❌',warning:'⚠️'}[type]||'ℹ️'}</span>
      <span class="toast-msg">${message}</span>
    `;
    container.appendChild(el);
    setTimeout(() => { el.style.opacity='0'; setTimeout(()=>el.remove(),300); }, duration);
  }

  static _createToastContainer() {
    const c = document.createElement('div');
    c.id = 'toasts';
    c.className = 'toast-container';
    document.body.appendChild(c);
    return c;
  }

  static loading(btn, state) {
    if (state) {
      btn.dataset.original = btn.innerHTML;
      btn.innerHTML = '<div class="spinner"></div> Chargement...';
      btn.disabled = true;
    } else {
      btn.innerHTML = btn.dataset.original || btn.innerHTML;
      btn.disabled = false;
    }
  }

  static formatPrice(n, decimals = 2) {
    if (n === null || n === undefined) return '–';
    return new Intl.NumberFormat('fr-FR', {
      minimumFractionDigits: decimals,
      maximumFractionDigits: decimals,
    }).format(n);
  }

  static formatFCFA(n) {
    return new Intl.NumberFormat('fr-FR').format(Math.round(n)) + ' F CFA';
  }

  static pnlClass(v) { return v > 0 ? 'text-green' : v < 0 ? 'text-red' : 'text-dim'; }
  static pnlSign(v)  { return v > 0 ? '+' : ''; }

  static timeAgo(isoDate) {
    const d = new Date(isoDate), now = new Date();
    const s = Math.round((now - d) / 1000);
    if (s < 60)    return `il y a ${s}s`;
    if (s < 3600)  return `il y a ${Math.round(s/60)}min`;
    if (s < 86400) return `il y a ${Math.round(s/3600)}h`;
    return `il y a ${Math.round(s/86400)}j`;
  }

  static requireAuth() {
    if (!BTFApi.isLoggedIn()) {
      window.location.href = '/frontend/pages/login.html';
      return false;
    }
    return true;
  }
}

// ─── GLOBAL TOAST CSS ─────────────────────────────────────────────────────────
const toastStyle = document.createElement('style');
toastStyle.textContent = `
  .toast-container { position:fixed; bottom:1.5rem; right:1.5rem; z-index:9999; display:flex; flex-direction:column; gap:.5rem; }
  .toast {
    display:flex; align-items:center; gap:.65rem;
    background:var(--card); border:1px solid var(--border2);
    border-radius:12px; padding:.75rem 1rem;
    min-width:260px; max-width:360px;
    box-shadow:0 8px 32px rgba(0,0,0,.5);
    font-size:.82rem;
  }
  .toast-success { border-color:rgba(16,185,129,.3); }
  .toast-error   { border-color:rgba(244,63,94,.3); }
  .toast-warning { border-color:rgba(245,158,11,.3); }
  .toast-icon { font-size:1rem; flex-shrink:0; }
  .toast-msg  { color:var(--text); }
`;
document.head.appendChild(toastStyle);
