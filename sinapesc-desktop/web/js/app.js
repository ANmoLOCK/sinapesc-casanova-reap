/* Sinapesc REAP — UI web compacta (pywebview) */

(function () {
  "use strict";

  const TABS = [
    { id: "socies", label: "Sócios", screen: "admin" },
    { id: "pendencias", label: "Pendências", screen: "pendencias" },
    { id: "relatorio", label: "Relatório", screen: "relatorio" },
    { id: "backup", label: "Backup", screen: "backup" },
    { id: "auditoria", label: "Auditoria", screen: "auditoria" },
    { id: "atalhos", label: "Config.Atalhos", screen: "atalhos" },
    { id: "lista", label: "Lista pública", screen: "lista" },
  ];

  const MAR_OUT = ["mar", "abr", "mai", "jun", "jul", "ago", "set", "out"];

  const state = {
    bootstrap: null,
    screen: "home",
    navHistory: [],
    loggedIn: false,
    adminUser: "",
    pessoas: [],
    expanded: new Set(),
    search: "",
    pendencias: null,
    auditoria: [],
    connLabel: "",
    sortMode: (typeof localStorage !== "undefined" && localStorage.getItem("sinapesc_sort")) || "recent",
    loteBackdrop: null,
    afterLogin: "",
    defesoItens: [],
    defesoFicha: null,
    defesoSearch: "",
    defesoLocalidade: "",
    defesoSomenteConfirmadas: false,
    defesoSomenteParcelas: false,
    defesoLocalidades: [],
    adminLocalidade: "",
    adminLocalidades: [],
    relLocalidade: "",
    consultaRgpItens: [],
    consultaRgpKpis: null,
    consultaRgpSearch: "",
    consultaRgpFiltro: "",
    consultaRgpSelectedId: "",
    consultaRgpEditMode: false,
    consultaRgpPendingConsulta: false,
    consultaRgpPage: 1,
    consultaRgpPageSize: 20,
    consultaRgpImportAuto: false,
    consultaRgpGovbr: false,
    consultaRgpLoaded: false,
    consultaRgpLoading: false,
  };

  const $ = (sel) => document.querySelector(sel);
  const content = $("#content");
  const tabBar = $("#tab-bar");
  const tabInner = $("#tab-inner");
  const headerActions = $("#header-actions");
  const headerEmail = $("#header-email");
  const modalRoot = $("#modal-root");

  window.AppEvents = {
    _handlers: {},
    on(event, fn) {
      (this._handlers[event] = this._handlers[event] || []).push(fn);
    },
    dispatch(event, payload) {
      (this._handlers[event] || []).forEach((fn) => {
        try { fn(payload); } catch (e) { console.error(e); }
      });
    },
  };

  function api(method, ...args) {
    if (!window.pywebview || !window.pywebview.api) {
      return Promise.reject(new Error("API Python indisponível"));
    }
    return window.pywebview.api[method](...args);
  }

  function toast(msg, ms = 3200) {
    const el = document.createElement("div");
    el.className = "toast";
    el.textContent = msg;
    $("#toast-root").appendChild(el);
    setTimeout(() => el.remove(), ms);
  }

  function setStatus(msg) {
    $("#status-text").textContent = msg || "Pronto.";
  }

  function setFooter() {
    $("#footer-user").textContent = state.loggedIn ? state.adminUser : "";
    const sep = document.querySelector(".footer-conn-sep");
    if (sep) sep.style.display = state.connLabel ? "" : "none";
    $("#footer-conn").textContent = state.connLabel;
  }

  function setPage(html) {
    content.innerHTML = `<div class="page">${html}</div>`;
  }

  function esc(s) {
    return String(s ?? "")
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;")
      .replace(/"/g, "&quot;");
  }

  function formatCpf(value) {
    const d = String(value || "").replace(/\D/g, "").slice(0, 11);
    const p1 = d.slice(0, 3);
    const p2 = d.slice(3, 6);
    const p3 = d.slice(6, 9);
    const p4 = d.slice(9, 11);
    let out = p1;
    if (p2) out += `.${p2}`;
    if (p3) out += `.${p3}`;
    if (p4) out += `-${p4}`;
    return out;
  }

  function formatNome(value) {
    return String(value || "")
      .trim()
      .split(/\s+/)
      .filter(Boolean)
      .map((word) => word.split("-").map((part) => {
        if (!part) return part;
        return part.charAt(0).toLocaleUpperCase("pt-BR") + part.slice(1).toLocaleLowerCase("pt-BR");
      }).join("-"))
      .join(" ");
  }

  function bindNomeMask(input) {
    if (!input) return;
    const paint = () => { input.value = formatNome(input.value); };
    input.addEventListener("blur", paint);
    input.addEventListener("change", paint);
  }

  function bindCpfMask(input) {
    if (!input) return;
    const paint = () => { input.value = formatCpf(input.value); };
    input.addEventListener("input", paint);
    paint();
  }

  function createModal(html, className = "") {
    const backdrop = document.createElement("div");
    backdrop.className = "modal-backdrop";
    backdrop.innerHTML = `<div class="modal ${className}">${html}</div>`;
    function close(result) {
      backdrop.remove();
      if (backdrop._onClose) backdrop._onClose(result);
    }
    backdrop.addEventListener("click", (e) => {
      if (e.target === backdrop) close(false);
    });
    backdrop.querySelectorAll("[data-modal-close]").forEach((btn) => {
      btn.addEventListener("click", () => close(btn.dataset.modalClose === "ok"));
    });
    backdrop._close = close;
    modalRoot.appendChild(backdrop);
    return backdrop;
  }

  function confirmModal(title, text) {
    return new Promise((resolve) => {
      const backdrop = createModal(`
        <div class="modal-head">${esc(title)}</div>
        <div class="modal-body"><p style="margin:0;white-space:pre-wrap">${esc(text)}</p></div>
        <div class="modal-foot">
          <button type="button" class="btn btn-outline-dark" data-modal-close="">Cancelar</button>
          <button type="button" class="btn btn-primary" data-modal-close="ok">Confirmar</button>
        </div>
      `);
      backdrop._onClose = resolve;
    });
  }

  function mesesKeys() {
    return state.bootstrap?.meses || ["jan","fev","mar","abr","mai","jun","jul","ago","set","out","nov","dez"];
  }

  function monthChecksHtml(className, selected) {
    const sel = new Set(selected || []);
    return mesesKeys().map((m) => `
      <div class="month-check">
        <label><input type="checkbox" class="${className}" value="${m}" ${sel.has(m) ? "checked" : ""} /> ${m.toUpperCase()}</label>
      </div>
    `).join("");
  }

  function applyPreset(root, className, meses) {
    root.querySelectorAll(`.${className}`).forEach((cb) => {
      cb.checked = meses.includes(cb.value);
    });
  }

  function presetButtons(className) {
    return `
      <div class="preset-row" data-preset-for="${className}">
        <button type="button" class="btn btn-ghost btn-sm" data-preset-set="marout">Mar → Out</button>
        <button type="button" class="btn btn-ghost btn-sm" data-preset-set="ano">Ano inteiro</button>
        <button type="button" class="btn btn-ghost btn-sm" data-preset-set="limpar">Limpar</button>
      </div>`;
  }

  function bindPresets(root, className) {
    root.querySelectorAll(`[data-preset-for="${className}"] [data-preset-set]`).forEach((btn) => {
      btn.addEventListener("click", () => {
        const kind = btn.dataset.presetSet;
        const all = mesesKeys();
        if (kind === "marout") applyPreset(root, className, MAR_OUT);
        else if (kind === "ano") applyPreset(root, className, all);
        else applyPreset(root, className, []);
      });
    });
  }

  function selectedMonths(root, className) {
    return [...root.querySelectorAll(`.${className}:checked`)].map((c) => c.value);
  }

  function isSecretariaScreen(screen) {
    return !["home", "login", "settings", "defeso", "defeso_ficha", "consulta_rgp"].includes(screen || "");
  }

  function navigate(screen, { push = true, tab = null } = {}) {
    const leavingSecretaria =
      state.loggedIn && isSecretariaScreen(state.screen) && !isSecretariaScreen(screen);
    if (push && state.screen && state.screen !== screen) {
      state.navHistory.push(state.screen);
    }
    state.screen = screen;
    renderTabs(tab);
    renderHeader();
    renderScreen();
    // Ao sair da secretaria, puxa a planilha fresca do Google (contador e REAP).
    if (leavingSecretaria) loadPessoas();
  }

  function goBack() {
    const prev = state.navHistory.pop();
    navigate(prev || (state.loggedIn ? "admin" : "home"), { push: false });
  }

  function tabForScreen(screen) {
    const map = {
      admin: "socies",
      pendencias: "pendencias",
      relatorio: "relatorio",
      backup: "backup",
      auditoria: "auditoria",
      atalhos: "atalhos",
      lista: "lista",
    };
    return map[screen] || null;
  }

  function renderTabs(activeTab) {
    const secretaria = state.loggedIn && isSecretariaScreen(state.screen);
    tabBar.hidden = !secretaria;
    if (!secretaria) return;

    const tabId = activeTab || tabForScreen(state.screen) || "socies";
    tabInner.innerHTML = TABS.map((t) => `
      <div class="tab-cell ${t.id === tabId ? "active" : ""}" data-tab="${t.id}">
        <div class="tab-label">${esc(t.label)}</div>
        <div class="tab-underline"></div>
      </div>
    `).join("");

    tabInner.querySelectorAll(".tab-cell").forEach((cell) => {
      cell.addEventListener("click", () => {
        const tab = TABS.find((x) => x.id === cell.dataset.tab);
        if (tab) navigate(tab.screen, { tab: tab.id });
      });
    });
  }

  function renderHeader() {
    headerEmail.textContent = state.loggedIn ? state.adminUser : "";
    headerActions.innerHTML = "";

    const mkBtn = (label, cls, fn) => {
      const b = document.createElement("button");
      b.type = "button";
      b.className = `btn btn-sm ${cls}`;
      b.textContent = label;
      b.addEventListener("click", fn);
      return b;
    };

    if (state.screen === "home") {
      headerActions.appendChild(mkBtn("⚙ Configurações", "btn-outline", () => navigate("settings")));
      return;
    }

    if (state.screen === "defeso" || state.screen === "defeso_ficha") {
      headerActions.appendChild(mkBtn("← Voltar", "btn-outline", () => {
        if (state.screen === "defeso_ficha") navigate("defeso", { push: false });
        else navigate("home", { push: false });
      }));
      if (state.loggedIn) {
        headerActions.appendChild(mkBtn("Sair", "btn-outline", doLogout));
      }
      headerActions.appendChild(mkBtn("⚙ Configurações", "btn-outline", () => navigate("settings")));
      return;
    }

    if (state.screen === "consulta_rgp") {
      headerActions.appendChild(mkBtn("← Voltar", "btn-outline", () => navigate("home", { push: false })));
      if (state.loggedIn) {
        headerActions.appendChild(mkBtn("Sair", "btn-outline", doLogout));
      }
      headerActions.appendChild(mkBtn("⚙ Configurações", "btn-outline", () => navigate("settings")));
      return;
    }

    if (state.loggedIn) {
      if (state.navHistory.length) {
        headerActions.appendChild(mkBtn("← Voltar", "btn-outline", goBack));
      }
      if (state.screen === "admin") {
        headerActions.appendChild(mkBtn("Sinc. Planilhas", "btn-outline", () => {
          api("sync_planilhas_municipio");
        }));
      }
      headerActions.appendChild(mkBtn("Lista pública", "btn-outline", () => navigate("lista", { tab: "lista" })));
      headerActions.appendChild(mkBtn("⚙ Configurações", "btn-outline", () => navigate("settings")));
      headerActions.appendChild(mkBtn("Sair", "btn-outline", doLogout));
      return;
    }

    headerActions.appendChild(mkBtn("← Voltar", "btn-outline", goBack));
    headerActions.appendChild(mkBtn("⚙ Configurações", "btn-outline", () => navigate("settings")));
  }

  async function doLogout() {
    await api("logout");
    state.loggedIn = false;
    state.adminUser = "";
    state.navHistory = [];
    state.expanded.clear();
    state.connLabel = "";
    setFooter();
    loadPessoas();
    navigate("home", { push: false });
  }

  function renderScreen() {
    const fns = {
      home: renderHome,
      login: renderLogin,
      settings: renderSettings,
      admin: renderAdmin,
      pendencias: renderPendencias,
      relatorio: renderRelatorio,
      backup: renderBackup,
      auditoria: renderAuditoria,
      atalhos: renderAtalhos,
      lista: renderLista,
      defeso: renderDefesoLista,
      defeso_ficha: renderDefesoFicha,
      consulta_rgp: renderConsultaRgp,
    };
    (fns[state.screen] || renderHome)();
  }

  function goDefeso() {
    if (state.loggedIn) {
      navigate("defeso");
      return;
    }
    state.afterLogin = "defeso";
    navigate("login");
  }

  function goConsultaRgp() {
    if (state.loggedIn) {
      state.consultaRgpLoaded = false;
      navigate("consulta_rgp");
      loadConsultaRgp(true);
      return;
    }
    state.afterLogin = "consulta_rgp";
    navigate("login");
  }

  function renderHome() {
    setPage(`
      <div class="hero">
        <div class="hero-title">${esc(state.bootstrap?.org_short || "Sinapesc")}</div>
        <div class="hero-sub">${esc(state.bootstrap?.org_full || "")}</div>
        <div class="hero-tag">Controle REAP · Defeso Fácil · Consulta RGP · consulta online</div>
      </div>
      <div class="home-cards">
        <div class="home-card">
          <h3>Secretaria</h3>
          <p>Cadastre sócios, marque REAPs e importe lotes na planilha Google.</p>
          <button type="button" class="btn btn-primary" id="go-login">Entrar como administrador</button>
        </div>
        <div class="home-card">
          <h3>Defeso Fácil</h3>
          <p>Ficha do pescador, declaração de residência e anexos na pasta do Google Drive.</p>
          <button type="button" class="btn btn-primary" id="go-defeso">Abrir Defeso Fácil</button>
        </div>
        <div class="home-card">
          <h3>Consulta &amp; QR</h3>
          <p>Site público online (CPF) e QRs permanentes para imprimir na sede.</p>
          <button type="button" class="btn btn-primary" id="go-lista">Abrir lista e QRs</button>
        </div>
        <div class="home-card">
          <h3>Módulo Consulta</h3>
          <p>Planilha própria: cadastre nome, CPF, município, telefone e observação; consulte o RGP no MPA.</p>
          <button type="button" class="btn btn-primary" id="go-consulta-rgp">Abrir Consulta RGP</button>
        </div>
      </div>
      <div class="tip-box">Site gratuito: compartilhe a planilha como Leitor, publique site-publico/, cole a URL em Configurações e gere o QR Consulta.</div>
    `);
    $("#go-login").addEventListener("click", () => {
      state.afterLogin = "admin";
      navigate("login");
    });
    $("#go-defeso").addEventListener("click", goDefeso);
    $("#go-lista").addEventListener("click", () => navigate("lista"));
    $("#go-consulta-rgp").addEventListener("click", goConsultaRgp);
  }

  function renderLogin() {
    const email = state.bootstrap?.admin_email || "";
    setPage(`
      <div class="form-panel" style="max-width:400px;margin:28px auto">
        <h2 style="margin:0 0 2px;font-size:16px">Acesso administrativo</h2>
        <p class="page-sub">${esc(state.bootstrap?.org_full || "")}</p>
        <label>E-mail</label>
        <input type="email" id="login-email" value="${esc(email)}" />
        <label>Senha</label>
        <input type="password" id="login-pass" />
        <div class="form-actions" style="justify-content:flex-end">
          <button type="button" class="btn btn-primary" id="login-btn">Entrar</button>
        </div>
      </div>
    `);
    const tryLogin = async () => {
      const res = await api("login", $("#login-email").value, $("#login-pass").value);
      if (!res.ok) {
        toast(res.error || "Erro no login");
        if (res.redirect === "settings") navigate("settings");
        return;
      }
      state.loggedIn = true;
      state.adminUser = res.admin_user || $("#login-email").value;
      state.connLabel = "Conectado";
      setFooter();
      state.navHistory = [];
      const dest = state.afterLogin || "admin";
      state.afterLogin = "";
      if (dest === "defeso") navigate("defeso", { push: false });
      else if (dest === "consulta_rgp") {
        state.consultaRgpLoaded = false;
        navigate("consulta_rgp", { push: false });
        loadConsultaRgp(true);
      }
      else {
        navigate("admin", { push: false, tab: "socies" });
        loadPessoas();
        maybeBackupReminder();
      }
    };
    $("#login-btn").addEventListener("click", tryLogin);
    $("#login-pass").addEventListener("keydown", (e) => { if (e.key === "Enter") tryLogin(); });
  }

  async function maybeBackupReminder() {
    const ultimo = state.bootstrap?.ultimo_backup_em || "";
    if (!ultimo || ultimo === "Nunca") {
      if (await confirmModal("Backup", "Ainda não há backup local. Gerar agora?")) {
        api("run_backup");
      }
    }
  }

  async function renderSettings() {
    const res = await api("get_settings");
    const s = res.ok ? res.data : {};
    setPage(`
      <h1 class="page-title">Configurações</h1>
      <div class="form-panel" style="margin-top:10px">
        <label>ID da planilha Google (admin / API)</label>
        <input id="cfg-sheet" value="${esc(s.spreadsheet_id || "")}" />
        <label>ID da planilha Defeso Fácil</label>
        <input id="cfg-defeso-sheet" value="${esc(s.defeso_spreadsheet_id || "")}" placeholder="1UxDjb78h7tYUnKXPcLVniuqAfWwrbvyf" />
        <label>ID da planilha Consulta RGP (vazio = usa a do REAP, aba ConsultaRGP)</label>
        <input id="cfg-consulta-rgp-sheet" value="${esc(s.consulta_rgp_spreadsheet_id || "")}" placeholder="Opcional — planilha exclusiva do módulo" />
        <label>Pasta anexos Defeso (Google Drive no PC)</label>
        <input id="cfg-defeso-anexos" value="${esc(s.defeso_anexos_dir || "")}" placeholder="D:\\Meu Drive\\Sinapesc-Defeso" />
        <div class="btn-row" style="margin:6px 0 12px">
          <button type="button" class="btn btn-outline-dark btn-sm" id="cfg-defeso-pick">Escolher pasta…</button>
          <button type="button" class="btn btn-ghost btn-sm" id="cfg-defeso-open">Abrir pasta</button>
        </div>
        <p class="page-sub" style="margin-top:-6px">Recomendado: pasta dentro do Google Drive instalado (ex. unidade D:). O EXE grava ali e o Drive sincroniza com a sua cota.</p>
        <label>ID pasta Drive API (avançado / Shared Drive)</label>
        <input id="cfg-defeso-drive" value="${esc(s.defeso_drive_folder_id || "")}" placeholder="Só se usar Drive compartilhado via API" />
        <label>URL do site público (sem /consulta.html)</label>
        <input id="cfg-site" value="${esc(s.public_site_url || "")}" placeholder="https://anmolock.github.io/sinapesc-casanova-reap" />
        <label>E-mail do administrador</label>
        <input id="cfg-email" value="${esc(s.admin_email || "")}" />
        <label>Senha do administrador</label>
        <input id="cfg-pass" type="password" value="${esc(s.admin_password || "")}" />
        <div class="cred-label" id="cfg-cred">${esc(s.credentials_label || "")}</div>
        <input type="file" id="cfg-json" accept=".json,application/json" hidden />
        <button type="button" class="btn btn-primary btn-sm" id="cfg-import">Importar JSON da Conta de Serviço…</button>
        <div class="site-box">
          <h4>Site público online (gratuito)</h4>
          <p>1) Planilha como Leitor · 2) GitHub Pages · 3) Cole a URL acima · 4) Gere os QRs. O notebook não precisa ficar ligado.</p>
          <div class="btn-row">
            <button type="button" class="btn btn-primary btn-sm" id="cfg-qrs">Gerar QRs do site</button>
            <button type="button" class="btn btn-outline-dark btn-sm" id="cfg-qr-consulta">QR Consulta CPF</button>
            <button type="button" class="btn btn-ghost btn-sm" id="cfg-qr-pasta">Pasta dos QRs</button>
          </div>
        </div>
        <div class="form-actions">
          <button type="button" class="btn btn-outline-dark" id="cfg-save">Salvar</button>
          <button type="button" class="btn btn-primary" id="cfg-test">Testar conexão</button>
        </div>
      </div>
    `);

    const persist = () => api("save_settings", {
      spreadsheet_id: $("#cfg-sheet").value,
      defeso_spreadsheet_id: $("#cfg-defeso-sheet").value,
      consulta_rgp_spreadsheet_id: $("#cfg-consulta-rgp-sheet")?.value || "",
      defeso_anexos_dir: $("#cfg-defeso-anexos").value,
      defeso_drive_folder_id: $("#cfg-defeso-drive").value,
      public_site_url: $("#cfg-site").value,
      admin_email: $("#cfg-email").value,
      admin_password: $("#cfg-pass").value,
    });

    $("#cfg-import").addEventListener("click", () => $("#cfg-json").click());
    $("#cfg-json").addEventListener("change", async (e) => {
      const file = e.target.files[0];
      if (!file) return;
      const r = await api("import_credentials_json", await file.text());
      if (r.ok) { $("#cfg-cred").textContent = r.credentials_label; toast("Credenciais importadas."); }
      else toast(r.error);
    });
    $("#cfg-defeso-pick").addEventListener("click", async () => {
      const r = await api("pick_defeso_anexos_dir");
      if (r.ok) {
        const path = r.defeso_anexos_dir || r.data?.defeso_anexos_dir || "";
        if ($("#cfg-defeso-anexos")) $("#cfg-defeso-anexos").value = path;
        toast(path ? `Pasta Defeso: ${path}` : "Pasta salva.");
        refreshBootstrap();
      } else if (r.error && !/nenhuma pasta/i.test(r.error)) {
        toast(r.error);
      }
    });
    $("#cfg-defeso-open").addEventListener("click", async () => {
      const typed = ($("#cfg-defeso-anexos")?.value || "").trim();
      if (typed) await persist();
      const r = await api("open_defeso_anexos_dir");
      if (!r.ok) toast(r.error);
    });
    $("#cfg-save").addEventListener("click", async () => {
      const r = await persist();
      toast(r.ok ? "Configurações salvas." : r.error);
      if (r.ok) refreshBootstrap();
    });
    $("#cfg-test").addEventListener("click", async () => {
      await persist();
      const r = await api("test_connection");
      toast(r.ok ? `Conexão OK! Associados: ${r.count}` : r.error);
    });
    $("#cfg-qrs").addEventListener("click", async () => {
      await persist();
      api("generate_site_qrs", true);
    });
    $("#cfg-qr-consulta").addEventListener("click", async () => {
      await persist();
      showQr("consulta");
    });
    $("#cfg-qr-pasta").addEventListener("click", () => api("open_path", state.bootstrap?.qr_dir || ""));
  }

  function renderAdmin() {
    setPage(`
      <div>
        <span class="page-title">Sócios</span>
        <span class="page-meta" id="admin-count"></span>
        <p class="page-sub">Clique no nome para abrir o REAP</p>
      </div>
      <div class="toolbar">
        <div class="search-wrap">
          <span class="search-icon">⌕</span>
          <input type="search" id="admin-search" placeholder="Buscar por nome ou CPF" value="${esc(state.search)}" />
        </div>
        <div class="btn-row">
          <label class="filter-wrap">Localidade
            <select id="admin-localidade">
              <option value="">Todas</option>
              ${(state.adminLocalidades || []).map((loc) => `
                <option value="${esc(loc)}" ${loc === state.adminLocalidade ? "selected" : ""}>${esc(loc)}</option>
              `).join("")}
            </select>
          </label>
          <label class="filter-wrap">Filtro
            <select id="admin-sort">
              <option value="recent">Mais recente</option>
              <option value="30d">Alterados (30 dias)</option>
              <option value="1y">Alterados (1 ano)</option>
              <option value="az">A–Z</option>
            </select>
          </label>
          <button type="button" class="btn btn-outline-dark btn-sm" id="admin-refresh">↻ Atualizar</button>
          <button type="button" class="btn btn-outline-dark btn-sm" id="admin-lote">⇪ Cadastro em lote</button>
          <button type="button" class="btn btn-primary btn-sm" id="admin-new">+ Novo sócio</button>
        </div>
      </div>
      <div id="admin-list"></div>
    `);
    $("#admin-search").addEventListener("input", (e) => {
      state.search = e.target.value;
      renderAdminList();
    });
    $("#admin-localidade")?.addEventListener("change", (e) => {
      state.adminLocalidade = e.target.value || "";
      renderAdminList();
    });
    const sortSel = $("#admin-sort");
    if (sortSel) {
      const allowed = ["recent", "30d", "1y", "az"];
      if (!allowed.includes(state.sortMode)) state.sortMode = "recent";
      sortSel.value = state.sortMode;
      sortSel.addEventListener("change", () => {
        state.sortMode = sortSel.value;
        try { localStorage.setItem("sinapesc_sort", state.sortMode); } catch (_e) {}
        renderAdminList();
      });
    }
    $("#admin-refresh").addEventListener("click", loadPessoas);
    $("#admin-new").addEventListener("click", () => openPessoaModal());
    $("#admin-lote").addEventListener("click", () => openLoteModal());
    renderAdminList();
    if (!state.pessoas.length) loadPessoas();
  }

  function parseToggleDate(valor) {
    const s = String(valor || "").trim().slice(0, 19);
    if (!s) return null;
    const normalized = s.includes("T") ? s : s.replace(" ", "T");
    const dt = new Date(normalized);
    return Number.isNaN(dt.getTime()) ? null : dt;
  }

  function diasDesdeToggle(p) {
    const dt = parseToggleDate(p.ultimo_toggle_em);
    if (!dt) return null;
    return Math.max(0, (Date.now() - dt.getTime()) / 86400000);
  }

  function filteredPessoas() {
    const q = state.search.trim().toLowerCase();
    const digits = q.replace(/\D/g, "");
    let list = state.pessoas;
    if (q) {
      list = list.filter((p) =>
        p.nome.toLowerCase().includes(q) || (digits && p.cpf_raw.includes(digits))
      );
    }
    if (state.sortMode === "30d") {
      list = list.filter((p) => {
        const d = diasDesdeToggle(p);
        return d !== null && d <= 30;
      });
    } else if (state.sortMode === "1y") {
      list = list.filter((p) => {
        const d = diasDesdeToggle(p);
        return d !== null && d <= 365;
      });
    }
    if (state.adminLocalidade) {
      const loc = state.adminLocalidade.trim().toLowerCase();
      list = list.filter((p) => String(p.municipio || "").trim().toLowerCase() === loc);
    }
    return sortedPessoas(list);
  }

  function sortedPessoas(list) {
    const copy = list.map((p, i) => ({ p, i: p._idx ?? i }));
    if (state.sortMode === "az") {
      copy.sort((a, b) =>
        String(a.p.nome_display || a.p.nome || "").localeCompare(
          String(b.p.nome_display || b.p.nome || ""),
          "pt-BR",
          { sensitivity: "base" }
        )
      );
    } else {
      // Mais recente / 30d / 1y: prioriza última marca/desmarca REAP
      copy.sort((a, b) => {
        const ta = a.p.ultimo_toggle_em || "";
        const tb = b.p.ultimo_toggle_em || "";
        if (ta && tb && ta !== tb) return tb.localeCompare(ta);
        if (ta && !tb) return -1;
        if (!ta && tb) return 1;
        const ca = a.p.criado_em || "";
        const cb = b.p.criado_em || "";
        if (ca && cb && ca !== cb) return cb.localeCompare(ca);
        return b.i - a.i;
      });
    }
    return copy.map((x) => x.p);
  }

  function renderAdminList() {
    const list = $("#admin-list");
    if (!list) return;
    const pessoas = filteredPessoas();
    const count = $("#admin-count");
    if (count) {
      if (!state.pessoas.length) count.textContent = "";
      else if (pessoas.length === state.pessoas.length) count.textContent = `${state.pessoas.length} cadastrados`;
      else count.textContent = `${pessoas.length} de ${state.pessoas.length}`;
    }
    if (!pessoas.length) {
      const emptyMsg = !state.pessoas.length
        ? "Nenhum sócio cadastrado."
        : (state.sortMode === "30d" || state.sortMode === "1y")
          ? "Nenhum sócio com alteração REAP neste período."
          : "Nenhum sócio encontrado.";
      list.innerHTML = `<div class="empty-msg">${emptyMsg}</div>`;
      return;
    }
    list.innerHTML = pessoas.map((p) => pessoaCardHtml(p, true)).join("");
    bindPessoaCards(list, true);
  }

  function touchBadgeHtml(p) {
    const label = (p.ultimo_toggle_label || "").trim();
    if (!label) return "";
    const tip = p.ultimo_toggle_em
      ? `Última marca/desmarca de mês · ${p.ultimo_toggle_em}`
      : "Última marca/desmarca de mês";
    return `<span class="card-touch" title="${esc(tip)}"> — ${esc(label)}</span>`;
  }

  function pessoaCardHtml(p, editable) {
    const expanded = state.expanded.has(p.id);
    let detail = "";
    if (expanded) {
      const contact = [
        p.municipio ? `Município: ${esc(p.municipio)}` : "",
        p.uf ? `UF: ${esc(p.uf)}` : "",
        p.telefone ? `Tel: ${esc(p.telefone)}` : "",
      ].filter(Boolean).join(" · ");
      const anos = (p.anos || []).map((a) => `
        <div class="year-label">Ano ${a.ano}</div>
        <div class="pills">${renderPills(p.id, a.ano, a.meses, editable)}</div>
      `).join("") || `<div class="empty-msg" style="padding:6px 0">Nenhum ano registrado.</div>`;
      const addAno = editable ? `
        <div class="inline-row" style="margin-top:8px">
          <input type="number" id="ano-new-${p.id}" value="${new Date().getFullYear() + 1}" />
          <button type="button" class="btn btn-outline-dark btn-sm" data-add-ano="${p.id}">Adicionar ano</button>
        </div>` : "";
      detail = `<div class="card-detail">${contact ? `<p class="card-contact">${contact}</p>` : ""}${anos}${addAno}</div>`;
    }
    const actions = editable ? `
      <button type="button" class="icon-btn" data-qr="${p.id}">▦ QR</button>
      <button type="button" class="icon-btn" data-edit="${p.id}">✎ Editar</button>
      <button type="button" class="icon-btn danger" data-del="${p.id}">🗑 Excluir</button>
    ` : "";
    return `
      <div class="card" data-id="${p.id}">
        <div class="card-head">
          <div class="avatar">${esc(p.iniciais)}</div>
          <div class="card-info" data-toggle="${p.id}">
            <p class="card-name">${esc(p.nome_display)}${touchBadgeHtml(p)}</p>
            <p class="card-cpf">CPF: ${esc(formatCpf(p.cpf_raw || p.cpf))}${p.municipio ? ` · ${esc(p.municipio)}` : ""}${p.telefone ? ` · ${esc(p.telefone)}` : ""}</p>
          </div>
          <div class="card-actions">
            ${actions}
            <button type="button" class="chevron" data-toggle="${p.id}">${expanded ? "▴" : "▾"}</button>
          </div>
        </div>
        ${detail}
      </div>`;
  }

  function renderPills(personId, ano, meses, editable) {
    return mesesKeys().map((m) => {
      const on = !!meses[m];
      const cls = on ? "on" : "off";
      const mark = on ? "✓" : "!";
      const ed = editable ? `editable data-pill="${personId}|${ano}|${m}|${on ? 0 : 1}"` : "";
      const title = esc(state.bootstrap?.meses_label?.[m] || m);
      return `<button type="button" class="pill ${cls}" ${ed} title="${title}">${m.toUpperCase()} ${mark}</button>`;
    }).join("");
  }

  function paintPill(btn, on) {
    if (!btn) return;
    btn.classList.toggle("on", on);
    btn.classList.toggle("off", !on);
    const label = (btn.textContent || "").trim().split(/\s+/)[0] || "";
    btn.textContent = `${label} ${on ? "✓" : "!"}`;
    const parts = (btn.dataset.pill || "").split("|");
    if (parts.length >= 3) {
      btn.dataset.pill = `${parts[0]}|${parts[1]}|${parts[2]}|${on ? 0 : 1}`;
    }
  }

  function applyLocalMes(pid, ano, mes, on) {
    const p = state.pessoas.find((x) => x.id === pid);
    if (!p) return;
    const a = (p.anos || []).find((x) => String(x.ano) === String(ano));
    if (a && a.meses) a.meses[mes] = on;
  }

  function bindPessoaCards(root, editable) {
    root.querySelectorAll("[data-toggle]").forEach((el) => {
      el.addEventListener("click", () => {
        const id = el.dataset.toggle;
        if (state.expanded.has(id)) state.expanded.delete(id);
        else state.expanded.add(id);
        if (state.screen === "lista") renderListaCards();
        else renderAdminList();
      });
    });
    if (!editable) return;
    root.querySelectorAll("[data-qr]").forEach((b) => b.addEventListener("click", () => showQr("pessoa", b.dataset.qr)));
    root.querySelectorAll("[data-edit]").forEach((b) => b.addEventListener("click", () => {
      const p = state.pessoas.find((x) => x.id === b.dataset.edit);
      if (p) openPessoaModal(p);
    }));
    root.querySelectorAll("[data-del]").forEach((b) => b.addEventListener("click", async () => {
      const p = state.pessoas.find((x) => x.id === b.dataset.del);
      if (!p) return;
      if (!(await confirmModal("Excluir sócio", `Remover ${p.nome_display} e todo o histórico REAP?`))) return;
      api("delete_pessoa", p.id);
    }));
    root.querySelectorAll("[data-pill]").forEach((b) => b.addEventListener("click", () => {
      const [pid, ano, mes, novo] = b.dataset.pill.split("|");
      const wantOn = novo === "1";
      paintPill(b, wantOn);
      applyLocalMes(pid, ano, mes, wantOn);
      const pessoa = state.pessoas.find((x) => x.id === pid);
      if (pessoa) {
        pessoa.ultimo_toggle_label = "agora";
        pessoa.ultimo_toggle_em = nowLocalStamp();
        if (state.screen === "admin") renderAdminList();
      }
      api("toggle_mes", pid, parseInt(ano, 10), mes, wantOn).then((r) => {
        if (r && r.ok === false && !r.pending) {
          paintPill(b, !wantOn);
          applyLocalMes(pid, ano, mes, !wantOn);
          toast(r.error || "Não foi possível marcar o mês.");
        }
      }).catch(() => {
        paintPill(b, !wantOn);
        applyLocalMes(pid, ano, mes, !wantOn);
        toast("Não foi possível marcar o mês.");
      });
    }));
    root.querySelectorAll("[data-add-ano]").forEach((b) => b.addEventListener("click", () => {
      const id = b.dataset.addAno;
      const inp = document.getElementById(`ano-new-${id}`);
      if (inp) api("add_ano", id, parseInt(inp.value, 10));
    }));
  }

  function openPessoaModal(pessoa) {
    const isEdit = !!pessoa;
    const backdrop = createModal(`
      <div class="modal-head">${isEdit ? "Editar sócio" : "Novo sócio"}</div>
      <div class="modal-body">
        <label>Nome completo</label>
        <input id="m-nome" value="${esc(formatNome(pessoa?.nome || ""))}" />
        <label>CPF</label>
        <input id="m-cpf" inputmode="numeric" maxlength="14" placeholder="000.000.000-00" value="${esc(formatCpf(pessoa?.cpf_raw || pessoa?.cpf || ""))}" />
        <label>Município</label>
        <input id="m-mun" placeholder="Ex.: Casa Nova" value="${esc(pessoa?.municipio || "")}" />
        <label>Número (telefone)</label>
        <input id="m-tel" inputmode="tel" placeholder="Ex.: (74) 99999-0000" value="${esc(pessoa?.telefone || "")}" />
      </div>
      <div class="modal-foot">
        <button type="button" class="btn btn-outline-dark" data-modal-close="">Cancelar</button>
        <button type="button" class="btn btn-primary" id="m-save">Salvar</button>
      </div>
    `);
    bindNomeMask(backdrop.querySelector("#m-nome"));
    bindCpfMask(backdrop.querySelector("#m-cpf"));
    backdrop.querySelector("#m-save").addEventListener("click", async () => {
      const r = await api("save_pessoa", {
        id: pessoa?.id || "",
        nome: formatNome(backdrop.querySelector("#m-nome").value),
        cpf: backdrop.querySelector("#m-cpf").value,
        municipio: backdrop.querySelector("#m-mun")?.value || "",
        telefone: backdrop.querySelector("#m-tel")?.value || "",
      });
      if (!r.pending && !r.ok) toast(r.error);
      else backdrop._close(true);
    });
  }

  function parseLoteText(raw) {
    const itens = [];
    String(raw || "").split(/\r?\n/).forEach((line) => {
      const t = line.trim();
      if (!t || /^nome/i.test(t)) return;
      let parts;
      if (t.includes(";")) parts = t.split(";");
      else if (t.includes("\t")) parts = t.split("\t");
      else if (t.includes(",")) {
        const segs = t.split(",");
        if (segs.length >= 2) {
          parts = [segs.slice(0, -1).join(",").trim(), segs[segs.length - 1].trim()];
          if (segs.length >= 3) {
            const last = segs[segs.length - 1].trim();
            const mid = segs[segs.length - 2].trim();
            const cpfLike = last.replace(/\D/g, "").length === 11;
            if (cpfLike) {
              parts = [segs.slice(0, -1).join(",").trim(), last];
            } else {
              const cpfIdx = segs.findIndex((s, i) => i > 0 && String(s).replace(/\D/g, "").length === 11);
              if (cpfIdx > 0) {
                parts = [
                  segs.slice(0, cpfIdx).join(",").trim(),
                  segs[cpfIdx].trim(),
                  ...(segs.slice(cpfIdx + 1).map((s) => s.trim())),
                ];
              } else {
                parts = [segs[0].trim(), mid, last];
              }
            }
          }
        }
      } else {
        parts = t.split(/\s{2,}/);
      }
      if (!parts || parts.length < 2) return;
      const nome = String(parts[0] || "").replace(/^"|"$/g, "").trim();
      const cpf = String(parts[1] || "").replace(/^"|"$/g, "").trim();
      const municipio = String(parts[2] || "").replace(/^"|"$/g, "").trim();
      const telefone = String(parts[3] || "").replace(/^"|"$/g, "").trim();
      if (nome || cpf) itens.push({ nome, cpf, municipio, telefone });
    });
    return itens;
  }

  function openLoteModal(opts = {}) {
    const ano = opts.ano || new Date().getFullYear();
    const meses = opts.meses || [];
    const banner = meses.length
      ? `<div class="banner-ok">Atalho: no ano ${ano} já entram marcados: ${meses.map((m) => m.toUpperCase()).join(", ")}</div>`
      : "";
    const backdrop = createModal(`
      <div class="modal-head">Cadastro em lote</div>
      <div class="modal-body">
        <p class="page-sub">Uma linha = um sócio. Município e número são opcionais. Os dados ficam guardados se der erro.</p>
        ${banner}
        <div class="inline-row">
          <label>Ano REAP</label>
          <input type="number" id="l-ano" value="${esc(ano)}" />
        </div>
        ${meses.length ? "" : `
          ${presetButtons("lote-m")}
          <div class="month-grid">${monthChecksHtml("lote-m", [])}</div>
        `}
        <label>Colar lista (Nome;CPF;Município;Número — uma pessoa por linha)</label>
        <textarea id="l-paste" placeholder="Maria Silva;105.205.585-45;Casa Nova;(74) 99999-0000"></textarea>
        <div class="btn-row" style="margin:6px 0 8px">
          <button type="button" class="btn btn-ghost btn-sm" id="l-paste-btn">Colar nas linhas</button>
          <button type="button" class="btn btn-ghost btn-sm" id="l-add">+ Linha</button>
          <button type="button" class="btn btn-ghost btn-sm" id="l-add-10">+ 10 linhas</button>
        </div>
        <div class="lote-head">
          <span>Nome completo</span><span>CPF</span><span>Município</span><span>Número</span><span></span>
        </div>
        <div class="lote-rows" id="l-rows"></div>
        <p class="page-sub" id="l-status"></p>
      </div>
      <div class="modal-foot">
        <button type="button" class="btn btn-outline-dark" data-modal-close="">Cancelar</button>
        <button type="button" class="btn btn-primary" id="l-save">Importar</button>
      </div>
    `, "modal-wide");

    bindPresets(backdrop, "lote-m");
    const host = backdrop.querySelector("#l-rows");
    const saveBtn = backdrop.querySelector("#l-save");
    const statusEl = backdrop.querySelector("#l-status");
    state.loteBackdrop = backdrop;

    function collectRows() {
      return [...host.querySelectorAll(".lote-row")].map((r) => ({
        nome: formatNome(r.querySelector(".l-nome").value),
        cpf: r.querySelector(".l-cpf").value,
        municipio: (r.querySelector(".l-mun")?.value || "").trim(),
        telefone: (r.querySelector(".l-tel")?.value || "").trim(),
      })).filter((r) => r.nome.trim() || r.cpf.trim());
    }

    function persistDraft() {
      try {
        localStorage.setItem("sinapesc_lote_draft", JSON.stringify({
          ano: backdrop.querySelector("#l-ano").value,
          rows: collectRows(),
        }));
      } catch (_e) {}
    }

    function addRow(nome = "", cpf = "", municipio = "", telefone = "") {
      const row = document.createElement("div");
      row.className = "lote-row";
      row.innerHTML = `
        <input class="l-nome" value="${esc(formatNome(nome))}" placeholder="Nome completo" />
        <input class="l-cpf" value="${esc(formatCpf(cpf))}" placeholder="000.000.000-00" maxlength="14" />
        <input class="l-mun" value="${esc(municipio)}" placeholder="Município" />
        <input class="l-tel" value="${esc(telefone)}" placeholder="Número" />
        <button type="button" class="icon-btn danger l-del">🗑</button>
      `;
      row.querySelector(".l-del").addEventListener("click", () => {
        if (host.children.length <= 1) {
          row.querySelector(".l-nome").value = "";
          row.querySelector(".l-cpf").value = "";
          if (row.querySelector(".l-mun")) row.querySelector(".l-mun").value = "";
          if (row.querySelector(".l-tel")) row.querySelector(".l-tel").value = "";
          persistDraft();
          return;
        }
        row.remove();
        persistDraft();
      });
      row.querySelectorAll("input").forEach((inp) => inp.addEventListener("input", persistDraft));
      host.appendChild(row);
      bindNomeMask(row.querySelector(".l-nome"));
      bindCpfMask(row.querySelector(".l-cpf"));
    }

    let restored = [];
    try {
      const raw = localStorage.getItem("sinapesc_lote_draft");
      if (raw) restored = JSON.parse(raw).rows || [];
    } catch (_e) { restored = []; }

    if (restored.length) {
      restored.forEach((r) => addRow(r.nome || "", r.cpf || "", r.municipio || "", r.telefone || r.numero || ""));
      statusEl.textContent = `Rascunho restaurado: ${restored.length} linha(s).`;
    } else {
      for (let i = 0; i < 8; i++) addRow();
    }

    backdrop.querySelector("#l-add").addEventListener("click", () => addRow());
    backdrop.querySelector("#l-add-10").addEventListener("click", () => {
      for (let i = 0; i < 10; i++) addRow();
    });
    backdrop.querySelector("#l-paste-btn").addEventListener("click", () => {
      const itens = parseLoteText(backdrop.querySelector("#l-paste").value);
      if (!itens.length) {
        toast("Cole linhas no formato Nome;CPF;Município;Número.");
        return;
      }
      host.innerHTML = "";
      itens.forEach((r) => addRow(r.nome, r.cpf, r.municipio || "", r.telefone || ""));
      persistDraft();
      statusEl.textContent = `${itens.length} linha(s) coladas.`;
    });
    saveBtn.addEventListener("click", async () => {
      const rows = collectRows();
      if (!rows.length) {
        toast("Preencha pelo menos um Nome e CPF.");
        return;
      }
      persistDraft();
      const anoVal = parseInt(backdrop.querySelector("#l-ano").value, 10) || new Date().getFullYear();
      const mesesOn = meses.length ? meses : selectedMonths(backdrop, "lote-m");
      saveBtn.disabled = true;
      statusEl.textContent = `Enviando ${rows.length} sócio(s)… a janela só fecha se der certo.`;
      try {
        const r = await api("save_lote_rows", JSON.stringify(rows), anoVal, mesesOn);
        if (r && r.ok === false && !r.pending) {
          toast(r.error || "Não foi possível importar o lote.");
          statusEl.textContent = r.error || "Erro ao importar. Seus dados continuam aqui.";
          saveBtn.disabled = false;
        }
      } catch (_e) {
        toast("Erro ao enviar o lote. Seus dados foram guardados.");
        statusEl.textContent = "Erro de envio. Rascunho guardado — pode tentar de novo.";
        saveBtn.disabled = false;
      }
    });
  }

  function nowLocalStamp() {
    const d = new Date();
    const p = (n) => String(n).padStart(2, "0");
    return `${d.getFullYear()}-${p(d.getMonth() + 1)}-${p(d.getDate())} ${p(d.getHours())}:${p(d.getMinutes())}:${p(d.getSeconds())}`;
  }

  function loadPessoas() {
    api("load_pessoas");
  }

  function renderPendencias() {
    const ano = new Date().getFullYear();
    setPage(`
      <div>
        <span class="page-title">Pendências REAP</span>
        <span class="page-meta" id="pend-stats">Carregando…</span>
      </div>
      <div class="toolbar">
        <label>Ano</label>
        <input type="number" id="pend-ano" value="${ano}" style="width:80px" />
        <span id="pend-cal" style="font-size:12px;font-weight:700;color:var(--accent)"></span>
        <div class="search-wrap" style="max-width:240px;margin-left:auto">
          <input type="search" id="pend-search" placeholder="Buscar" />
        </div>
        <button type="button" class="btn btn-outline-dark btn-sm" id="pend-cal-btn">Alterar calendário…</button>
        <button type="button" class="btn btn-primary btn-sm" id="pend-marcar">Marcar pendentes desta lista</button>
        <button type="button" class="btn btn-ghost btn-sm" id="pend-refresh">Atualizar</button>
      </div>
      <div id="pend-list"></div>
    `);
    const reload = () => api("load_pendencias", parseInt($("#pend-ano").value, 10));
    $("#pend-refresh").addEventListener("click", reload);
    $("#pend-ano").addEventListener("change", reload);
    $("#pend-cal-btn").addEventListener("click", openCalendarioModal);
    $("#pend-marcar").addEventListener("click", marcarPendentesLista);
    reload();
  }

  function renderPendenciasList(data) {
    state.pendencias = data;
    const q = ($("#pend-search")?.value || "").trim().toLowerCase();
    const digits = q.replace(/\D/g, "");
    let items = data.pendentes || [];
    if (q) {
      items = items.filter((s) =>
        s.nome.toLowerCase().includes(q) || (digits && s.cpf.replace(/\D/g, "").includes(digits))
      );
    }
    const nP = (data.pendentes || []).length;
    const nR = data.regulares_count || 0;
    const stats = $("#pend-stats");
    const cal = $("#pend-cal");
    if (stats) stats.textContent = `${nP} pendente(s) · ${nR} regular(es) · ${nP + nR} sócio(s)`;
    if (cal) cal.textContent = "Calendário: " + (data.calendario_texto || "");
    const list = $("#pend-list");
    if (!list) return;
    if (!items.length) {
      list.innerHTML = `<div class="empty-msg">${nP + nR === 0 ? "Nenhum sócio cadastrado." : "Nenhum pendente nesta lista."}</div>`;
      return;
    }
    list.innerHTML = items.map((s) => {
      const pills = (s.faltando || []).map((m) =>
        `<span class="pill warn">${m.toUpperCase()} !</span>`
      ).join(" ");
      return `
      <div class="card">
        <div class="card-head">
          <div class="card-info">
            <p class="card-name">${esc(s.nome_display)}${touchBadgeHtml(s)}</p>
            <p class="card-cpf">${esc(s.rotulo)} · CPF ${esc(formatCpf(s.cpf))}</p>
            <div class="pills" style="margin-top:4px">${pills}</div>
          </div>
          <div class="card-actions">
            <button type="button" class="btn btn-primary btn-sm" data-marcar="${s.person_id}">Marcar só os pendentes</button>
            <button type="button" class="btn btn-ghost btn-sm" data-ficha="${s.person_id}">Abrir ficha</button>
          </div>
        </div>
      </div>`;
    }).join("");
    list.querySelectorAll("[data-marcar]").forEach((b) => b.addEventListener("click", async () => {
      const s = items.find((x) => x.person_id === b.dataset.marcar);
      if (!s || !s.faltando.length) return;
      const nomes = s.faltando.map((m) => m.toUpperCase()).join(", ");
      if (!(await confirmModal("Confirmar", `Marcar ${nomes} em ${s.ano} para ${s.nome_display}?`))) return;
      api("marcar_meses_massa", s.ano, s.faltando, [s.person_id], false);
    }));
    list.querySelectorAll("[data-ficha]").forEach((b) => b.addEventListener("click", () => {
      state.expanded.add(b.dataset.ficha);
      navigate("admin", { tab: "socies" });
    }));
    if ($("#pend-search")) $("#pend-search").oninput = () => renderPendenciasList(data);
  }

  function openCalendarioModal() {
    const ano = parseInt($("#pend-ano")?.value || new Date().getFullYear(), 10);
    const cal = state.pendencias?.calendario || [];
    const backdrop = createModal(`
      <div class="modal-head">Calendário REAP ${ano}</div>
      <div class="modal-body">
        <p class="page-sub">Meses obrigatórios (aba Config da planilha).</p>
        ${presetButtons("cal-m")}
        <div class="month-grid">${monthChecksHtml("cal-m", cal)}</div>
      </div>
      <div class="modal-foot">
        <button type="button" class="btn btn-outline-dark" data-modal-close="">Cancelar</button>
        <button type="button" class="btn btn-primary" id="cal-save">Salvar</button>
      </div>
    `);
    bindPresets(backdrop, "cal-m");
    backdrop.querySelector("#cal-save").addEventListener("click", () => {
      api("save_calendario", ano, selectedMonths(backdrop, "cal-m"));
      backdrop._close(true);
    });
  }

  async function marcarPendentesLista() {
    const data = state.pendencias;
    if (!data || !data.pendentes?.length) {
      toast("Nenhum pendente nesta lista.");
      return;
    }
    const ids = data.pendentes.map((s) => s.person_id);
    if (!(await confirmModal("Confirmar", `Marcar calendário ${data.calendario_texto} em ${ids.length} sócio(s)?`))) return;
    api("marcar_meses_massa", data.ano, data.calendario, ids, false);
  }

  function renderRelatorio() {
    const ano = new Date().getFullYear();
    if (!state.adminLocalidades?.length && state.loggedIn) loadPessoas();
    const locs = state.adminLocalidades || [];
    setPage(`
      <h1 class="page-title">Relatório de conformidade REAP</h1>
      <p class="page-sub">Somente administrador. CPF completo. Imprimir → PDF. Consulta pública continua mascarada.</p>
      <div class="form-panel" style="margin-top:10px">
        <div class="inline-row">
          <label>Ano</label>
          <input type="number" id="rel-ano" value="${ano}" />
          <label><input type="radio" name="rel-modo" value="diretoria" checked /> Diretoria (todos)</label>
          <label><input type="radio" name="rel-modo" value="individual" /> Comprovante individual</label>
        </div>
        <div class="inline-row" style="margin-top:8px">
          <label class="filter-wrap">Localidade
            <select id="rel-localidade">
              <option value="">Todas</option>
              ${locs.map((loc) => `
                <option value="${esc(loc)}" ${loc === state.relLocalidade ? "selected" : ""}>${esc(loc)}</option>
              `).join("")}
            </select>
          </label>
        </div>
        <label>Buscar sócio (comprovante individual)</label>
        <input id="rel-busca" />
        <div class="form-actions">
          <button type="button" class="btn btn-primary" id="rel-gerar">Gerar e abrir HTML</button>
        </div>
      </div>
    `);
    $("#rel-localidade")?.addEventListener("change", (e) => {
      state.relLocalidade = e.target.value || "";
    });
    $("#rel-gerar").addEventListener("click", () => {
      const modo = document.querySelector('input[name="rel-modo"]:checked')?.value || "diretoria";
      api(
        "generate_relatorio",
        parseInt($("#rel-ano").value, 10),
        modo,
        $("#rel-busca").value,
        state.relLocalidade || ""
      );
    });
  }

  function renderBackup() {
    const ultimo = state.bootstrap?.ultimo_backup_em || "Nunca";
    const pasta = state.bootstrap?.backup_root || "";
    setPage(`
      <h1 class="page-title">Backup local</h1>
      <p class="page-sub">Cópia CSV local. Não substitui a planilha na nuvem.</p>
      <div class="form-panel" style="margin-top:10px">
        <p style="margin:0 0 4px"><strong>Último backup:</strong> ${esc(ultimo)}</p>
        <p class="page-sub">Pasta: ${esc(pasta)}</p>
        <div class="form-actions">
          <button type="button" class="btn btn-primary" id="bk-run">Gerar backup agora</button>
          <button type="button" class="btn btn-outline-dark" id="bk-open">Abrir pasta de backups</button>
        </div>
        <div id="bk-list" style="margin-top:12px;font-size:12px"></div>
      </div>
    `);
    $("#bk-run").addEventListener("click", async () => {
      if (await confirmModal("Backup", "Copiar abas Pessoas e Reap para CSV neste computador?")) {
        api("run_backup");
      }
    });
    $("#bk-open").addEventListener("click", () => api("open_path", pasta));
    refreshBackupList();
  }

  async function refreshBackupList() {
    const r = await api("list_backups");
    const el = $("#bk-list");
    if (!el || !r.ok) return;
    el.innerHTML = r.data?.length
      ? `<strong>Backups recentes</strong><br>${r.data.map(esc).join("<br>")}`
      : "";
  }

  function renderAuditoria() {
    setPage(`
      <div><span class="page-title">Auditoria</span> <span class="page-meta" id="aud-hint">Carregando…</span></div>
      <div class="toolbar">
        <input type="search" id="aud-search" placeholder="Buscar" style="flex:0 1 260px;padding:6px 8px;border:1px solid var(--border)" />
        <button type="button" class="btn btn-ghost btn-sm" id="aud-refresh">Atualizar</button>
        <button type="button" class="btn btn-outline-dark btn-sm" id="aud-export">Exportar CSV</button>
      </div>
      <div id="aud-list"></div>
    `);
    $("#aud-refresh").addEventListener("click", () => api("load_auditoria"));
    $("#aud-search")?.addEventListener("input", () => renderAuditoriaList(state.auditoria));
    $("#aud-export").addEventListener("click", () => api("export_auditoria"));
    api("load_auditoria");
  }

  function renderAuditoriaList(eventos) {
    state.auditoria = eventos || [];
    const q = $("#aud-search")?.value || "";
    api("filter_auditoria_local", state.auditoria, q).then((r) => {
      const items = r.ok ? r.data : state.auditoria;
      const hint = $("#aud-hint");
      if (hint) hint.textContent = `${items.length} registro(s) · aba Auditoria da planilha`;
      const list = $("#aud-list");
      if (!list) return;
      if (!items.length) {
        list.innerHTML = `<div class="empty-msg">Nenhum registro ainda.</div>`;
        return;
      }
      list.innerHTML = items.map((e) => `
        <div class="audit-card">
          <div class="audit-meta">${esc(e.em)} · ${esc(e.usuario || "(sem usuário)")}</div>
          <div class="audit-text">${esc(e.detalhe || e.acao)}</div>
        </div>
      `).join("");
    });
  }

  function renderAtalhos() {
    const ano = new Date().getFullYear();
    setPage(`
      <h1 class="page-title">Config.Atalhos</h1>
      <p class="page-sub">Automações em lote — poucas chamadas à planilha, sem marcar mês a mês.</p>

      <div class="atalho-card">
        <h3>1) Lote com REAP já marcado</h3>
        <p class="desc">Cadastra vários sócios de uma vez (nome, CPF, município e número) e já deixa os meses pagos no ano escolhido.</p>
        <div class="inline-row">
          <label>Ano</label>
          <input type="number" id="at1-ano" value="${ano}" />
        </div>
        ${presetButtons("m1")}
        <div class="month-grid">${monthChecksHtml("m1", MAR_OUT)}</div>
        <button type="button" class="btn btn-primary btn-sm" id="at-lote">Abrir lote com meses marcados…</button>
      </div>

      <div class="atalho-card">
        <h3>2) Marcar meses nos sócios já cadastrados</h3>
        <p class="desc">Liga o intervalo no ano para todos, ou só os da busca atual. Não apaga meses já pagos, a menos que substitua o ano.</p>
        <div class="inline-row">
          <label>Ano</label>
          <input type="number" id="at2-ano" value="${ano}" />
          <label><input type="checkbox" id="at2-busca" /> Só quem aparece na busca da lista</label>
          <label><input type="checkbox" id="at2-sub" /> Substituir o ano</label>
        </div>
        ${presetButtons("m2")}
        <div class="month-grid">${monthChecksHtml("m2", MAR_OUT)}</div>
        <button type="button" class="btn btn-primary btn-sm" id="at-massa">Aplicar marcação em massa</button>
      </div>

      <div class="atalho-card">
        <h3>3) Copiar REAP de um ano para outro</h3>
        <p class="desc">Leva os 12 meses já marcados (ex.: 2025 → 2026). Cria o ano novo se ainda não existir.</p>
        <div class="inline-row">
          <label>De</label>
          <input type="number" id="at3-de" value="${ano - 1}" />
          <label>para</label>
          <input type="number" id="at3-para" value="${ano}" />
          <label><input type="checkbox" id="at3-busca" /> Só a busca da lista</label>
        </div>
        <button type="button" class="btn btn-primary btn-sm" id="at-copiar">Copiar ano</button>
      </div>
      <p class="page-sub">Evite clicar várias vezes enquanto o rodapé disser “Marcando…” ou “Copiando…”.</p>
    `);
    bindPresets(content, "m1");
    bindPresets(content, "m2");

    $("#at-lote").addEventListener("click", () => {
      const meses = selectedMonths(content, "m1");
      if (!meses.length) { toast("Escolha os meses (ex.: Mar → Out) antes de abrir o lote."); return; }
      openLoteModal({ ano: parseInt($("#at1-ano").value, 10), meses });
    });

    $("#at-massa").addEventListener("click", async () => {
      const mesesOn = selectedMonths(content, "m2");
      if (!mesesOn.length) { toast("Escolha pelo menos um mês."); return; }
      const ids = $("#at2-busca").checked ? filteredPessoas().map((p) => p.id) : null;
      const n = ids ? ids.length : state.pessoas.length;
      if (!n) { toast("Nenhum sócio para aplicar."); return; }
      const substituir = $("#at2-sub").checked;
      const anoN = parseInt($("#at2-ano").value, 10);
      if (!(await confirmModal("Confirmar", `Marcar ${mesesOn.map((m) => m.toUpperCase()).join(", ")} em ${anoN} para ${n} sócio(s)?`))) return;
      api("marcar_meses_massa", anoN, mesesOn, ids, substituir);
    });

    $("#at-copiar").addEventListener("click", async () => {
      const a = parseInt($("#at3-de").value, 10);
      const b = parseInt($("#at3-para").value, 10);
      const ids = $("#at3-busca").checked ? filteredPessoas().map((p) => p.id) : null;
      const n = ids ? ids.length : state.pessoas.length;
      if (!n) { toast("Nenhum sócio para copiar."); return; }
      if (!(await confirmModal("Confirmar", `Copiar meses de ${a} para ${b} em ${n} sócio(s)?`))) return;
      api("copiar_ano", a, b, ids);
    });
  }

  function renderLista() {
    setPage(`
      <div class="toolbar" style="margin-top:0">
        <span class="page-title">Lista pública</span>
        <div class="btn-row" style="margin-left:auto">
          <button type="button" class="btn btn-outline-dark btn-sm" id="qr-consulta">QR Consulta CPF</button>
          <button type="button" class="btn btn-primary btn-sm" id="qr-lista">QR Lista</button>
          <button type="button" class="btn btn-outline-dark btn-sm" id="qr-pasta">Pasta QRs</button>
        </div>
      </div>
      <p class="page-sub">Consulta online — CPF mascarado no celular.</p>
      <div class="toolbar">
        <div class="search-wrap">
          <span class="search-icon">⌕</span>
          <input type="search" id="lista-search" placeholder="Buscar por nome ou CPF" value="${esc(state.search)}" />
        </div>
      </div>
      <div id="lista-cards"></div>
    `);
    $("#qr-consulta").addEventListener("click", () => showQr("consulta"));
    $("#qr-lista").addEventListener("click", () => showQr("lista"));
    $("#qr-pasta").addEventListener("click", () => api("open_path", state.bootstrap?.qr_dir || ""));
    $("#lista-search").addEventListener("input", (e) => {
      state.search = e.target.value;
      renderListaCards();
    });
    if (!state.pessoas.length) loadPessoas();
    else renderListaCards();
  }

  function renderListaCards() {
    const list = $("#lista-cards");
    if (!list) return;
    const pessoas = filteredPessoas();
    if (!pessoas.length) {
      list.innerHTML = `<div class="empty-msg">${state.pessoas.length ? "Nenhum sócio encontrado." : "Carregando…"}</div>`;
      if (!state.pessoas.length) loadPessoas();
      return;
    }
    list.innerHTML = pessoas.map((p) => pessoaCardHtml({ ...p, cpf: maskCpf(p.cpf_raw) }, false)).join("");
    bindPessoaCards(list, false);
  }

  function maskCpf(raw) {
    const d = String(raw || "").replace(/\D/g, "");
    if (d.length !== 11) return d;
    return `***.***.${d.slice(6, 9)}-**`;
  }

  async function showQr(kind, personId) {
    const r = await api("qr_preview", kind, personId || "");
    if (!r.ok) { toast(r.error); return; }
    const backdrop = createModal(`
      <div class="modal-head">QR Code</div>
      <div class="modal-body qr-preview">
        <img id="qr-img" src="${r.data.image}" alt="QR" />
      </div>
      <div class="modal-foot">
        <button type="button" class="btn btn-outline-dark" id="qr-print">Imprimir</button>
        <button type="button" class="btn btn-primary" data-modal-close="ok">Fechar</button>
      </div>
    `);
    backdrop.querySelector("#qr-print").addEventListener("click", async () => {
      const pr = await api("print_qr", kind, personId || "");
      if (pr.ok) toast("QR aberto no navegador para imprimir.");
      else toast(pr.error || "Falha ao abrir impressão do QR.");
    });
  }

  async function refreshBootstrap() {
    const r = await api("get_bootstrap");
    if (r.ok) {
      state.bootstrap = r.data;
      $("#org-short").textContent = r.data.org_short;
      $("#org-full").textContent = r.data.org_full;
    }
  }

  function refreshAdminLocalidadeSelect() {
    const sel = $("#admin-localidade");
    if (!sel) return;
    const cur = state.adminLocalidade || "";
    sel.innerHTML = `<option value="">Todas</option>${(state.adminLocalidades || []).map((loc) => `
      <option value="${esc(loc)}" ${loc === cur ? "selected" : ""}>${esc(loc)}</option>
    `).join("")}`;
  }

  function renderDefesoLista() {
    setPage(`
      <div>
        <span class="page-title">Defeso Fácil</span>
        <span class="page-meta" id="defeso-count">Carregando…</span>
        <p class="page-sub">Sócios do REAP · abra a ficha, salve endereço e imprima a declaração</p>
      </div>
      <div class="toolbar">
        <div class="search-wrap">
          <span class="search-icon">⌕</span>
          <input type="search" id="defeso-search" placeholder="Buscar nome ou CPF" value="${esc(state.defesoSearch)}" />
        </div>
        <div class="btn-row defeso-filters">
          <label class="filter-wrap">Localidade
            <select id="defeso-localidade">
              <option value="">Todas</option>
              ${(state.defesoLocalidades || []).map((loc) => `
                <option value="${esc(loc)}" ${loc === state.defesoLocalidade ? "selected" : ""}>${esc(loc)}</option>
              `).join("")}
            </select>
          </label>
          <label class="pacote-check filter-check">
            <input type="checkbox" id="defeso-confirmadas" ${state.defesoSomenteConfirmadas ? "checked" : ""} />
            Entradas confirmadas
          </label>
          <label class="pacote-check filter-check">
            <input type="checkbox" id="defeso-parcelas" ${state.defesoSomenteParcelas ? "checked" : ""} />
            Com parcela disponível
          </label>
          <button type="button" class="btn btn-outline-dark btn-sm" id="defeso-refresh">↻ Atualizar</button>
          <button type="button" class="btn btn-primary btn-sm" id="defeso-relatorio">Relatório HTML</button>
        </div>
      </div>
      <div id="defeso-list"></div>
    `);
    $("#defeso-search").addEventListener("input", (e) => {
      state.defesoSearch = e.target.value;
      paintDefesoLista();
    });
    $("#defeso-localidade")?.addEventListener("change", (e) => {
      state.defesoLocalidade = e.target.value || "";
      paintDefesoLista();
    });
    $("#defeso-confirmadas")?.addEventListener("change", (e) => {
      state.defesoSomenteConfirmadas = !!e.target.checked;
      paintDefesoLista();
    });
    $("#defeso-parcelas")?.addEventListener("change", (e) => {
      state.defesoSomenteParcelas = !!e.target.checked;
      paintDefesoLista();
    });
    $("#defeso-refresh").addEventListener("click", () => api("load_defeso_lista"));
    $("#defeso-relatorio")?.addEventListener("click", () => {
      api(
        "generate_defeso_relatorio",
        state.defesoLocalidade || "",
        !!state.defesoSomenteConfirmadas,
        !!state.defesoSomenteParcelas
      );
    });
    paintDefesoLista();
    api("load_defeso_lista");
  }

  function refreshDefesoLocalidadeSelect() {
    const sel = $("#defeso-localidade");
    if (!sel) return;
    const cur = state.defesoLocalidade || "";
    sel.innerHTML = `<option value="">Todas</option>${(state.defesoLocalidades || []).map((loc) => `
      <option value="${esc(loc)}" ${loc === cur ? "selected" : ""}>${esc(loc)}</option>
    `).join("")}`;
  }

  function paintDefesoLista() {
    const list = $("#defeso-list");
    const count = $("#defeso-count");
    if (!list) return;
    const q = (state.defesoSearch || "").trim().toLowerCase();
    const digits = q.replace(/\D/g, "");
    let itens = state.defesoItens || [];
    if (state.defesoLocalidade) {
      const loc = state.defesoLocalidade.trim().toLowerCase();
      itens = itens.filter((x) => String(x.municipio_reap || x.municipio || "").trim().toLowerCase() === loc);
    }
    if (state.defesoSomenteConfirmadas) {
      itens = itens.filter((x) => x.confirmada);
    }
    if (state.defesoSomenteParcelas) {
      itens = itens.filter((x) => x.tem_parcela);
    }
    if (q) {
      itens = itens.filter((x) =>
        String(x.nome || "").toLowerCase().includes(q)
        || (digits && String(x.cpf || "").includes(digits))
      );
    }
    if (count) count.textContent = `${itens.length} de ${(state.defesoItens || []).length}`;
    if (!itens.length) {
      list.innerHTML = `<div class="empty-msg">${(state.defesoItens || []).length ? "Nenhum resultado." : "Carregando ou sem sócios no REAP."}</div>`;
      return;
    }
    list.innerHTML = itens.map((x) => {
      const st = x.tem_ficha ? (x.status || "salvo") : "sem ficha";
      const conf = x.confirmada ? " · confirmada" : "";
      const docs = [
        x.tem_identidade ? "ID" : null,
        x.tem_carteira_pesca ? "Pesca" : null,
        x.tem_caf ? "CAF" : null,
      ].filter(Boolean).join(" · ") || "sem anexos";
      return `
        <div class="card">
          <div class="card-head">
            <div class="card-info">
              <p class="card-name">${esc(x.nome_display || x.nome)}</p>
              <p class="card-cpf">CPF ${esc(x.cpf_formatado || x.cpf)} · ${esc(st)}${conf}${x.municipio_reap ? ` · REAP: ${esc(x.municipio_reap)}` : ""}${x.municipio_defeso ? ` · Defeso: ${esc(x.municipio_defeso)}` : ""}${x.telefone_reap ? ` · ${esc(x.telefone_reap)}` : ""}</p>
              <p class="card-cpf">${esc(docs)}</p>
            </div>
            <div class="card-actions">
              <button type="button" class="btn btn-primary btn-sm" data-defeso-open="${esc(x.person_id || "")}" data-cpf="${esc(x.cpf || "")}" data-ficha="${esc(x.ficha_id || "")}">Abrir ficha</button>
            </div>
          </div>
        </div>`;
    }).join("");
    list.querySelectorAll("[data-defeso-open]").forEach((b) => {
      b.addEventListener("click", () => {
        state.defesoFicha = {
          person_id: b.dataset.defesoOpen || "",
          cpf: b.dataset.cpf || "",
          ficha_id: b.dataset.ficha || "",
        };
        navigate("defeso_ficha");
      });
    });
  }

  function renderDefesoFicha() {
    const ref = state.defesoFicha || {};
    setPage(`
      <div>
        <span class="page-title">Ficha Defeso</span>
        <span class="page-meta" id="defeso-ficha-meta">Carregando…</span>
      </div>
      <div class="form-panel defeso-form" id="defeso-form-wrap">
        <p class="page-sub">Nome e CPF vêm do REAP. Complete o restante e salve.</p>
        <input type="hidden" id="df-id" />
        <input type="hidden" id="df-person" />
        <div class="defeso-grid">
          <div><label>Nome completo</label><input id="df-nome" /></div>
          <div><label>CPF</label><input id="df-cpf" /></div>
          <div><label>RG / CIN</label><input id="df-rg" /></div>
          <div><label>Nacionalidade</label><input id="df-nac" value="Brasileira" /></div>
          <div><label>Profissão</label><input id="df-prof" value="Pescador profissional" /></div>
          <div><label>CEP</label><input id="df-cep" placeholder="00000-000" /></div>
          <div class="span-2"><label>Endereço / rua</label><input id="df-end" /></div>
          <div><label>Número</label><input id="df-num" /></div>
          <div><label>Bairro</label><input id="df-bairro" /></div>
          <div><label>Município</label><input id="df-mun" /></div>
          <div><label>UF</label><input id="df-uf" maxlength="2" placeholder="BA" /></div>
          <div><label>Telefone (declaração)</label><input id="df-tel" /></div>
          <div><label>E-mail</label><input id="df-email" /></div>
          <div class="span-2 defeso-atalhos-contato">
            <details open>
              <summary>Atalhos rápidos — até 3 telefones e 3 e-mails (salvos neste PC)</summary>
              <p class="page-sub">Preencha e clique «Gravar atalhos». Depois use «Usar» para preencher a declaração.</p>
              <div class="atalho-bloco">
                <strong>Telefones</strong>
                <div class="atalho-row">
                  <input id="df-atalho-tel-0" placeholder="Telefone 1" />
                  <button type="button" class="btn btn-ghost btn-sm" data-usar-tel="0">Usar</button>
                </div>
                <div class="atalho-row">
                  <input id="df-atalho-tel-1" placeholder="Telefone 2" />
                  <button type="button" class="btn btn-ghost btn-sm" data-usar-tel="1">Usar</button>
                </div>
                <div class="atalho-row">
                  <input id="df-atalho-tel-2" placeholder="Telefone 3" />
                  <button type="button" class="btn btn-ghost btn-sm" data-usar-tel="2">Usar</button>
                </div>
              </div>
              <div class="atalho-bloco">
                <strong>E-mails</strong>
                <div class="atalho-row">
                  <input id="df-atalho-email-0" placeholder="E-mail 1" />
                  <button type="button" class="btn btn-ghost btn-sm" data-usar-email="0">Usar</button>
                </div>
                <div class="atalho-row">
                  <input id="df-atalho-email-1" placeholder="E-mail 2" />
                  <button type="button" class="btn btn-ghost btn-sm" data-usar-email="1">Usar</button>
                </div>
                <div class="atalho-row">
                  <input id="df-atalho-email-2" placeholder="E-mail 3" />
                  <button type="button" class="btn btn-ghost btn-sm" data-usar-email="2">Usar</button>
                </div>
              </div>
              <div class="form-actions" style="margin-top:8px">
                <button type="button" class="btn btn-outline-dark btn-sm" id="df-atalhos-gravar">Gravar atalhos</button>
              </div>
            </details>
          </div>
        </div>
        <div class="defeso-controle-box">
          <h4>Controle Defeso</h4>
          <p class="page-sub">Município/telefone REAP só para conferir e no relatório. Na declaração entra o município da ficha acima.</p>
          <div class="defeso-reap-info">
            <div><label>Município (REAP)</label><input id="df-mun-reap" readonly title="Só conferência e relatório — não entra na declaração" /></div>
            <div><label>Telefone (REAP)</label><input id="df-tel-reap" readonly placeholder="Cadastre no módulo Sócios / REAP" /></div>
          </div>
          <div class="parcelas-box">
            <p class="parcelas-title">Parcelas recebidas</p>
            <div class="parcela-row"><span>1° parcela</span><input id="df-parcela-1" placeholder="15/05/2026" maxlength="12" /></div>
            <div class="parcela-row"><span>2° parcela</span><input id="df-parcela-2" placeholder="__/__/____" maxlength="12" /></div>
            <div class="parcela-row"><span>3° parcela</span><input id="df-parcela-3" placeholder="__/__/____" maxlength="12" /></div>
            <div class="parcela-row"><span>4° parcela</span><input id="df-parcela-4" placeholder="__/__/____" maxlength="12" /></div>
          </div>
          <label class="entrada-check" for="df-entrada">
            <input type="checkbox" id="df-entrada" />
            <span>Entrada confirmada</span>
          </label>
        </div>
        <div class="form-actions defeso-actions" style="margin-top:14px">
          <button type="button" class="btn btn-outline-dark" id="df-back">← Lista</button>
          <button type="button" class="btn btn-primary" id="df-save">Salvar na planilha</button>
          <button type="button" class="btn btn-primary" id="df-print">Gerar declaração</button>
          <button type="button" class="btn btn-primary" id="df-pacote" title="Junta declaração e anexos num único PDF">Juntar PDF</button>
        </div>
        <div class="defeso-pacote-box" id="df-pacote-box">
          <div class="defeso-pacote-head">
            <strong>Montar pacote PDF</strong>
            <span class="page-sub">Marque o que entra no arquivo único</span>
          </div>
          <div class="defeso-pacote-checks" id="df-pacote-checks">
            <label class="pacote-check"><input type="checkbox" name="df-pacote-item" value="declaracao" checked /> Declaração</label>
            <label class="pacote-check"><input type="checkbox" name="df-pacote-item" value="identidade" checked /> Identidade</label>
            <label class="pacote-check"><input type="checkbox" name="df-pacote-item" value="pesca" checked /> Carteira de pescador</label>
            <label class="pacote-check"><input type="checkbox" name="df-pacote-item" value="caf" checked /> CAF</label>
          </div>
        </div>
        <div class="defeso-anexos" id="df-anexos">
          <h4>Anexos</h4>
          <p class="page-sub" id="df-drive-hint">Salve a ficha antes de anexar.</p>
          <div class="btn-row">
            <label class="btn btn-outline-dark btn-sm">Identidade<input type="file" id="df-file-id" accept=".pdf,.jpg,.jpeg,.png,.webp" hidden /></label>
            <label class="btn btn-outline-dark btn-sm">Carteira pesca<input type="file" id="df-file-pesca" accept=".pdf,.jpg,.jpeg,.png,.webp" hidden /></label>
            <label class="btn btn-outline-dark btn-sm">CAF<input type="file" id="df-file-caf" accept=".pdf,.jpg,.jpeg,.png,.webp" hidden /></label>
            <button type="button" class="btn btn-ghost btn-sm" id="df-open-anexos">Abrir pasta</button>
          </div>
          <ul id="df-anexo-list" class="defeso-anexo-list"></ul>
        </div>
        <div class="defeso-fonte-bar">
          <button type="button" class="btn-fonte" id="df-fonte-btn" title="Letra da declaração" aria-label="Letra da declaração">
            <svg class="icone-fonte" viewBox="0 0 24 24" width="20" height="20" aria-hidden="true">
              <path fill="currentColor" d="M4 19h3.2l.7-2h4.2l.7 2H16l-4.1-11h-3.8L4 19zm4.6-4.2L10.3 10h.2l1.7 4.8H8.6zM17.2 8.2c1.7 0 2.9.8 2.9 2.1 0 1-.6 1.7-1.8 2.1l1.2 1.6H18l-1-1.4h-.4v1.4h-1.5V8.2h2.1zm0 1.3h-.5v1.8h.5c.7 0 1.1-.3 1.1-.9s-.4-.9-1.1-.9z"/>
            </svg>
          </button>
          <span class="page-sub" id="df-fonte-label">Letra da declaração: Manuscrita (Allura)</span>
        </div>
      </div>
    `);
    $("#df-back").addEventListener("click", () => navigate("defeso", { push: false }));
    $("#df-save").addEventListener("click", () => {
      api("save_defeso_ficha", JSON.stringify(collectDefesoPayload()));
    });
    $("#df-print").addEventListener("click", () => {
      const payload = collectDefesoPayload();
      const fonte =
        state.bootstrap?.defeso_declaracao_fonte ||
        "allura";
      api("print_defeso_declaracao", payload.id || "", JSON.stringify(payload), fonte);
    });
    $("#df-pacote")?.addEventListener("click", () => {
      const payload = collectDefesoPayload();
      const fonte = state.bootstrap?.defeso_declaracao_fonte || "allura";
      const itens = collectDefesoPacoteItens();
      if (!itens.length) {
        toast("Marque pelo menos um item do pacote.");
        return;
      }
      api("print_defeso_pacote", payload.id || "", JSON.stringify(payload), itens.join(","), fonte);
    });
    bindDefesoUpload("df-file-id", "identidade");
    bindDefesoUpload("df-file-pesca", "pesca");
    bindDefesoUpload("df-file-caf", "caf");
    $("#df-open-anexos")?.addEventListener("click", () => {
      api("open_defeso_anexos_dir").then((r) => { if (!r.ok) toast(r.error); });
    });
    $("#df-fonte-btn")?.addEventListener("click", () => openDefesoFonteModal());
    refreshDefesoFonteLabel();
    bindDefesoAtalhosContato();
    api("load_defeso_ficha", ref.person_id || "", ref.cpf || "", ref.ficha_id || "");
  }

  function bindDefesoAtalhosContato() {
    const tels = state.bootstrap?.defeso_atalhos_telefones || ["", "", ""];
    const emails = state.bootstrap?.defeso_atalhos_emails || ["", "", ""];
    for (let i = 0; i < 3; i++) {
      const t = $(`#df-atalho-tel-${i}`);
      const e = $(`#df-atalho-email-${i}`);
      if (t) t.value = tels[i] || "";
      if (e) e.value = emails[i] || "";
    }
    document.querySelectorAll("[data-usar-tel]").forEach((btn) => {
      btn.addEventListener("click", () => {
        const i = Number(btn.getAttribute("data-usar-tel"));
        const v = ($(`#df-atalho-tel-${i}`)?.value || "").trim();
        if (!v) { toast("Preencha o atalho de telefone antes."); return; }
        if ($("#df-tel")) $("#df-tel").value = v;
        toast("Telefone aplicado na declaração.");
      });
    });
    document.querySelectorAll("[data-usar-email]").forEach((btn) => {
      btn.addEventListener("click", () => {
        const i = Number(btn.getAttribute("data-usar-email"));
        const v = ($(`#df-atalho-email-${i}`)?.value || "").trim();
        if (!v) { toast("Preencha o atalho de e-mail antes."); return; }
        if ($("#df-email")) $("#df-email").value = v;
        toast("E-mail aplicado na declaração.");
      });
    });
    $("#df-atalhos-gravar")?.addEventListener("click", async () => {
      const telefones = [0, 1, 2].map((i) => ($(`#df-atalho-tel-${i}`)?.value || "").trim());
      const emailsArr = [0, 1, 2].map((i) => ($(`#df-atalho-email-${i}`)?.value || "").trim());
      const r = await api(
        "set_defeso_atalhos_contato",
        JSON.stringify(telefones),
        JSON.stringify(emailsArr)
      );
      if (!r.ok) { toast(r.error); return; }
      const telsSaved = r.telefones || r.data?.telefones || telefones;
      const mailsSaved = r.emails || r.data?.emails || emailsArr;
      if (state.bootstrap) {
        state.bootstrap.defeso_atalhos_telefones = telsSaved;
        state.bootstrap.defeso_atalhos_emails = mailsSaved;
      }
      toast("Atalhos gravados neste computador.");
    });
  }

  function collectDefesoPacoteItens() {
    return Array.from(document.querySelectorAll('input[name="df-pacote-item"]:checked'))
      .map((el) => el.value)
      .filter(Boolean);
  }

  function fonteLabelFromId(id) {
    const map = {
      allura: "Manuscrita (Allura)",
      bairro: "Letra de bairro",
      mao: "Mão suja",
      architects: "Caderno (Architects)",
      padrao: "Padrão (Times)",
    };
    return map[id] || id || "Manuscrita (Allura)";
  }

  function refreshDefesoFonteLabel() {
    const el = $("#df-fonte-label");
    if (!el) return;
    const id = state.bootstrap?.defeso_declaracao_fonte || "allura";
    el.textContent = `Letra da declaração: ${fonteLabelFromId(id)}`;
  }

  async function openDefesoFonteModal() {
    const res = await api("get_defeso_fontes");
    const data = res.ok ? { ...(res.data || {}), ...res } : {};
    const atual = data.fonte || state.bootstrap?.defeso_declaracao_fonte || "allura";
    const fontes = (data.fontes || []).filter((f) => f && f.id);
    const list = fontes.length
      ? fontes
      : [
          { id: "allura", label: "Manuscrita (Allura)", descricao: "Cursiva de caneta" },
          { id: "bairro", label: "Letra de bairro", descricao: "Manuscrita informal" },
          { id: "mao", label: "Mão suja", descricao: "Letra irregular" },
          { id: "architects", label: "Caderno (Architects)", descricao: "Letra de caderno" },
          { id: "padrao", label: "Padrão (Times)", descricao: "Times limpo" },
        ];
    const options = list.map((f) => {
      const disabled = f.disponivel === false ? "disabled" : "";
      const checked = f.id === atual ? "checked" : "";
      return `
        <label class="fonte-option ${disabled}">
          <input type="radio" name="df-fonte" value="${esc(f.id)}" ${checked} ${disabled} />
          <span>
            <strong>${esc(f.label || f.id)}</strong>
            <small>${esc(f.descricao || "")}</small>
          </span>
        </label>`;
    }).join("");

    const backdrop = createModal(`
      <div class="modal-head">Letra da declaração</div>
      <div class="modal-body">
        <p class="page-sub" style="margin:0 0 10px">Escolha a letra (efeito de caneta no formulário oficial).</p>
        <div class="fonte-list">${options}</div>
      </div>
      <div class="modal-foot">
        <button type="button" class="btn btn-outline-dark" data-modal-close="">Cancelar</button>
        <button type="button" class="btn btn-primary" id="df-fonte-save">Salvar</button>
      </div>
    `);
    backdrop.querySelector("#df-fonte-save")?.addEventListener("click", async () => {
      const chosen = backdrop.querySelector('input[name="df-fonte"]:checked')?.value || "allura";
      const r = await api("set_defeso_fonte", chosen);
      if (!r.ok) {
        toast(r.error || "Não foi possível salvar a fonte.");
        return;
      }
      const saved = r.fonte || r.data?.fonte || chosen;
      if (state.bootstrap) state.bootstrap.defeso_declaracao_fonte = saved;
      refreshDefesoFonteLabel();
      toast(`Letra: ${fonteLabelFromId(saved)}`);
      backdrop._close(true);
    });
  }

  function collectDefesoPayload() {
    const parcelas = [1, 2, 3, 4].map((n) => ($("#df-parcela-" + n)?.value || "").trim());
    return {
      id: $("#df-id")?.value || "",
      person_id: $("#df-person")?.value || "",
      nome: $("#df-nome")?.value || "",
      cpf: $("#df-cpf")?.value || "",
      rg: $("#df-rg")?.value || "",
      nacionalidade: $("#df-nac")?.value || "",
      profissao: $("#df-prof")?.value || "",
      cep: $("#df-cep")?.value || "",
      endereco: $("#df-end")?.value || "",
      numero: $("#df-num")?.value || "",
      bairro: $("#df-bairro")?.value || "",
      municipio: ($("#df-mun")?.value || "").trim(),
      uf: $("#df-uf")?.value || "",
      telefone: $("#df-tel")?.value || "",
      email: $("#df-email")?.value || "",
      telefone_reap: ($("#df-tel-reap")?.value || "").trim(),
      parcelas,
      entrada_confirmada: !!($("#df-entrada") && $("#df-entrada").checked),
      status: "salvo",
    };
  }

  function fillDefesoForm(d) {
    if (!d) return;
    const set = (id, v) => { const el = $(id); if (el) el.value = v || ""; };
    const setChk = (id, v) => {
      const el = $(id);
      if (!el) return;
      const on = v === true || v === 1 || String(v).toLowerCase() === "sim"
        || String(v).toLowerCase() === "true" || String(v) === "1";
      el.checked = on;
    };
    set("#df-id", d.id);
    set("#df-person", d.person_id);
    set("#df-nome", d.nome_display || d.nome);
    set("#df-cpf", d.cpf_formatado || d.cpf);
    set("#df-rg", d.rg);
    set("#df-nac", d.nacionalidade || "Brasileira");
    set("#df-prof", d.profissao || "Pescador profissional");
    set("#df-cep", d.cep);
    set("#df-end", d.endereco);
    set("#df-num", d.numero);
    set("#df-bairro", d.bairro);
    set("#df-mun", d.municipio || "");
    set("#df-uf", d.uf);
    set("#df-tel", d.telefone);
    set("#df-email", d.email);
    set("#df-tel-reap", d.telefone_reap || "");
    set("#df-mun-reap", d.municipio_reap || "");
    const parcelas = Array.isArray(d.parcelas) ? d.parcelas : [];
    for (let i = 0; i < 4; i++) {
      set("#df-parcela-" + (i + 1), parcelas[i] || "");
    }
    setChk("#df-entrada", d.entrada_confirmada);
    const meta = $("#defeso-ficha-meta");
    if (meta) meta.textContent = d.atualizado_em ? `Atualizado ${d.atualizado_em}` : "Nova ficha";
    const hint = $("#df-drive-hint");
    if (hint) {
      const root = d.anexos_local_root || d.defeso_anexos_dir || "";
      const mode = d.anexos_mode || (d.defeso_anexos_dir ? "sync" : (d.drive_ok ? "drive" : "local"));
      if (!d.id) {
        hint.textContent = "Salve a ficha antes de anexar.";
      } else if (mode === "sync") {
        hint.textContent = `Anexos na pasta sincronizada: ${root}`;
      } else if (mode === "drive") {
        hint.textContent = "Anexos via API Drive (Shared Drive). Preferível: pasta do Google Drive no PC em Configurações.";
      } else {
        hint.textContent = `Anexos locais: ${root || "pasta defeso_anexos"}. Em Configurações, escolha a pasta do Google Drive (D:).`;
      }
    }
    const ul = $("#df-anexo-list");
    if (ul) {
      const anexos = d.anexos || [];
      ul.innerHTML = anexos.length
        ? anexos.map((a) => {
            const where = a.where === "sync" ? "sync" : (a.where === "local" || a.path ? "local" : "drive");
            const openAttr = a.path
              ? `data-path="${esc(a.path)}"`
              : (a.url ? `data-url="${esc(a.url)}"` : "");
            return `<li>${esc(a.name)} · ${where}${openAttr ? ` · <a href="#" ${openAttr}>abrir</a>` : ""}</li>`;
          }).join("")
        : "<li>Nenhum anexo ainda.</li>";
      ul.querySelectorAll("[data-url]").forEach((a) => {
        a.addEventListener("click", (e) => {
          e.preventDefault();
          api("open_url", a.dataset.url);
        });
      });
      ul.querySelectorAll("[data-path]").forEach((a) => {
        a.addEventListener("click", (e) => {
          e.preventDefault();
          api("open_path", a.dataset.path);
        });
      });
    }
  }

  function bindDefesoUpload(inputId, kind) {
    const input = document.getElementById(inputId);
    if (!input) return;
    input.addEventListener("change", async () => {
      const file = input.files && input.files[0];
      input.value = "";
      if (!file) return;
      const fichaId = $("#df-id")?.value || "";
      if (!fichaId) {
        toast("Salve a ficha antes de anexar.");
        return;
      }
      try {
        const dataUrl = await readFileAsDataUrl(file);
        api("upload_defeso_anexo", fichaId, kind, file.name || kind, dataUrl, file.type || "");
      } catch (_e) {
        toast("Falha ao ler o arquivo.");
      }
    });
  }

  function readFileAsDataUrl(file) {
    return new Promise((resolve, reject) => {
      const reader = new FileReader();
      reader.onload = () => resolve(String(reader.result || ""));
      reader.onerror = () => reject(reader.error || new Error("read fail"));
      reader.readAsDataURL(file);
    });
  }

  function loadConsultaRgp(force) {
    if (state.consultaRgpLoading) return;
    if (state.consultaRgpLoaded && !force) return;
    state.consultaRgpLoading = true;
    api("load_consulta_rgp");
  }

  function fmtBrNum(n) {
    const s = String(Math.max(0, Number(n) || 0));
    return s.replace(/\B(?=(\d{3})+(?!\d))/g, ".");
  }

  function filtrarConsultaRgp() {
    const q = (state.consultaRgpSearch || "").trim().toLowerCase();
    const digits = q.replace(/\D/g, "");
    const filtro = state.consultaRgpFiltro || "";
    return (state.consultaRgpItens || []).filter((r) => {
      if (filtro && String(r.situacao_rgp || "") !== filtro) return false;
      if (!q) return true;
      const blob = [
        r.nome, r.nome_display, r.cpf, r.cpf_formatado, r.telefone, r.municipio, r.observacao,
      ].map((x) => String(x || "").toLowerCase()).join(" ");
      if (blob.includes(q)) return true;
      if (digits.length >= 3 && String(r.cpf || "").includes(digits)) return true;
      return false;
    });
  }

  const RGP_CHIP_SITUACOES = [
    "Ativo",
    "Aguardando análise",
    "Pend. regularização",
    "Inativo",
    "Não consultado",
  ];

  function openConsultaSocioModal(reg) {
    const edit = !!reg;
    const backdrop = document.createElement("div");
    backdrop.className = "modal-backdrop";
    backdrop.innerHTML = `
      <div class="modal-card" style="max-width:480px">
        <div class="modal-head">${edit ? "Editar sócio" : "Cadastrar sócio"}</div>
        <p class="page-sub">${edit
          ? "Atualiza nome, CPF, município, telefone e observação na planilha Consulta."
          : "Salva na planilha e em seguida consulta o MPA automaticamente."}</p>
        <label>Nome *</label>
        <input id="rgp-ed-nome" value="${esc(reg?.nome || "")}" />
        <label>CPF *</label>
        <input id="rgp-ed-cpf" value="${esc(reg?.cpf_formatado || reg?.cpf || "")}" placeholder="000.000.000-00" />
        <label>Município</label>
        <input id="rgp-ed-mun" value="${esc(reg?.municipio || "")}" />
        <label>Telefone</label>
        <input id="rgp-ed-tel" value="${esc(reg?.telefone || "")}" placeholder="(00) 00000-0000" />
        <label>Observação</label>
        <textarea id="rgp-ed-obs" rows="3">${esc(reg?.observacao || "")}</textarea>
        <div class="form-actions" style="justify-content:flex-end;margin-top:10px">
          <button type="button" class="btn btn-outline-dark" id="rgp-ed-cancel">Cancelar</button>
          <button type="button" class="btn btn-primary" id="rgp-ed-ok">${edit ? "Salvar" : "Cadastrar e consultar"}</button>
        </div>
      </div>`;
    document.body.appendChild(backdrop);
    const close = () => backdrop.remove();
    backdrop.addEventListener("click", (e) => { if (e.target === backdrop) close(); });
    $("#rgp-ed-cancel").addEventListener("click", close);
    const cpfInput = $("#rgp-ed-cpf");
    if (cpfInput && typeof bindCpfMask === "function") bindCpfMask(cpfInput);
    $("#rgp-ed-ok").addEventListener("click", () => {
      const nome = ($("#rgp-ed-nome")?.value || "").trim();
      const cpf = ($("#rgp-ed-cpf")?.value || "").trim();
      const municipio = ($("#rgp-ed-mun")?.value || "").trim();
      const telefone = ($("#rgp-ed-tel")?.value || "").trim();
      const observacao = ($("#rgp-ed-obs")?.value || "").trim();
      if (!nome) { toast("Informe o nome."); return; }
      if ((cpf.replace(/\D/g, "")).length !== 11) { toast("CPF inválido."); return; }
      const payload = {
        id: reg?.id || "",
        person_id: reg?.person_id || "",
        nome,
        cpf,
        municipio,
        telefone,
        observacao,
        uf: reg?.uf || "",
        email: reg?.email || "",
        situacao_rgp: reg?.situacao_rgp || "",
        ultima_consulta_em: reg?.ultima_consulta_em || "",
        codigo_rgp: reg?.codigo_rgp || "",
        categoria: reg?.categoria || "",
        timeline: reg?.timeline || "",
        importado_reap_em: reg?.importado_reap_em || "",
        importado_defeso_em: reg?.importado_defeso_em || "",
        cadastro_reap_em: reg?.cadastro_reap_em || "",
      };
      close();
      if (edit && reg?.id) {
        state.consultaRgpPendingConsulta = false;
        api("save_consulta_rgp_registro", payload);
      } else {
        state.consultaRgpPendingConsulta = true;
        api("cadastrar_consulta_rgp", payload);
      }
    });
  }

  function payloadFromConsultaSide(selected) {
    return {
      id: selected.id,
      person_id: selected.person_id,
      nome: ($("#rgp-side-nome")?.value || selected.nome || "").trim(),
      cpf: ($("#rgp-side-cpf")?.value || selected.cpf || "").trim(),
      telefone: ($("#rgp-side-tel")?.value || selected.telefone || "").trim(),
      municipio: ($("#rgp-side-mun")?.value || selected.municipio || "").trim(),
      uf: selected.uf || "",
      situacao_rgp: selected.situacao_rgp,
      observacao: ($("#rgp-side-obs")?.value || selected.observacao || "").trim(),
      ultima_consulta_em: selected.ultima_consulta_em,
      codigo_rgp: selected.codigo_rgp,
      categoria: selected.categoria,
      email: selected.email,
      importado_reap_em: selected.importado_reap_em,
      importado_defeso_em: selected.importado_defeso_em,
      cadastro_reap_em: selected.cadastro_reap_em,
      timeline: selected.timeline,
    };
  }

  function renderConsultaRgp() {
    const kpis = state.consultaRgpKpis || {
      total: 0, ativos: 0, ativos_pct: 0,
      aguardando_analise: 0, aguardando_analise_pct: 0,
      pendentes: 0, pendentes_pct: 0,
    };
    const filtered = filtrarConsultaRgp();
    const pageSize = state.consultaRgpPageSize || 20;
    const pages = Math.max(1, Math.ceil(filtered.length / pageSize) || 1);
    if (state.consultaRgpPage > pages) state.consultaRgpPage = pages;
    const page = state.consultaRgpPage || 1;
    const start = (page - 1) * pageSize;
    const slice = filtered.slice(start, start + pageSize);
    const selected = (state.consultaRgpItens || []).find((r) => r.id === state.consultaRgpSelectedId) || null;
    const situacoesExtra = [...new Set((state.consultaRgpItens || []).map((r) => r.situacao_rgp).filter(Boolean))]
      .filter((s) => !RGP_CHIP_SITUACOES.includes(s))
      .sort();
    const situacoesFiltro = [...RGP_CHIP_SITUACOES, ...situacoesExtra];
    const rawUser = (state.adminUser || "").trim();
    const userName = rawUser
      ? (rawUser.includes("@") ? rawUser.split("@")[0] : rawUser)
      : "";
    const userInitials = userName
      ? userName.replace(/[^a-zA-ZÀ-ÿ0-9]/g, "").slice(0, 2).toUpperCase() || "?"
      : "";
    const loadingHint = state.consultaRgpLoading && !state.consultaRgpLoaded
      ? `<tr><td colspan="8" class="rgp-empty">Carregando planilha Consulta RGP…</td></tr>`
      : `<tr><td colspan="8" class="rgp-empty">Nenhum registro. Clique em <strong>Cadastrar sócio</strong> para gravar nome, CPF, município, telefone e observação.</td></tr>`;
    const editMode = !!(selected && state.consultaRgpEditMode);
    const reapStamp = selected?.importado_reap_em || selected?.cadastro_reap_em || "";
    const reapPill = reapStamp
      ? `<div class="rgp-sync-pill rgp-sync-ok">REAP · Sincronizado em ${esc(reapStamp)}</div>`
      : `<div class="rgp-sync-pill rgp-sync-off">REAP · Ainda não sincronizado</div>`;

    setPage(`
      <div class="rgp-shell">
        <header class="rgp-topbar">
          <div class="rgp-topbar-left">
            <div class="rgp-logo">${esc(state.bootstrap?.org_short || "SINAPESC")}</div>
            <div class="rgp-topbar-titles">
              <div class="rgp-topbar-title">Consulta RGP</div>
              <div class="rgp-topbar-sub">Registro Geral da Atividade Pesqueira</div>
            </div>
          </div>
          ${userName ? `
          <div class="rgp-topbar-user" title="${esc(rawUser)}">
            <span class="rgp-user-avatar">${esc(userInitials)}</span>
            <span>${esc(userName)}</span>
            <span class="rgp-user-chev" aria-hidden="true">▾</span>
          </div>` : `<div class="rgp-topbar-user rgp-topbar-user-empty">Sem usuário</div>`}
        </header>

        <div class="rgp-config-bar">
          <span class="rgp-config-label">CONFIGURAÇÕES</span>
          <label class="rgp-switch">
            <input type="checkbox" id="rgp-govbr" ${state.consultaRgpGovbr ? "checked" : ""} />
            <span class="rgp-switch-ui"></span>
            <span>Senha Gov.br (opcional)</span>
          </label>
          <label class="rgp-switch">
            <input type="checkbox" id="rgp-auto" ${state.consultaRgpImportAuto ? "checked" : ""} />
            <span class="rgp-switch-ui"></span>
            <span>Importar automático REAP</span>
          </label>
          <div class="rgp-config-actions">
            <button type="button" class="btn btn-primary btn-sm" id="rgp-cadastrar">＋ Cadastrar sócio</button>
            <button type="button" class="btn btn-outline-dark btn-sm" id="rgp-sync">↻ Sincronizar REAP</button>
          </div>
        </div>

        <div class="rgp-kpis">
          <div class="rgp-kpi">
            <div class="rgp-kpi-top">
              <div class="rgp-kpi-label">Total de registros</div>
              <div class="rgp-kpi-ico rgp-ico-blue">👥</div>
            </div>
            <div class="rgp-kpi-value">${esc(fmtBrNum(kpis.total))}</div>
            <div class="rgp-kpi-meta">planilha Consulta RGP</div>
          </div>
          <div class="rgp-kpi">
            <div class="rgp-kpi-top">
              <div class="rgp-kpi-label">Ativos</div>
              <div class="rgp-kpi-ico rgp-ico-green">✓</div>
            </div>
            <div class="rgp-kpi-value rgp-kpi-ok">${esc(fmtBrNum(kpis.ativos))}</div>
            <div class="rgp-kpi-meta">${esc(String(kpis.ativos_pct || 0).replace(".", ","))}% do total</div>
          </div>
          <div class="rgp-kpi">
            <div class="rgp-kpi-top">
              <div class="rgp-kpi-label">Aguardando análise</div>
              <div class="rgp-kpi-ico rgp-ico-yellow">⏱</div>
            </div>
            <div class="rgp-kpi-value rgp-kpi-warn">${esc(fmtBrNum(kpis.aguardando_analise))}</div>
            <div class="rgp-kpi-meta">${esc(String(kpis.aguardando_analise_pct || 0).replace(".", ","))}% do total</div>
          </div>
          <div class="rgp-kpi">
            <div class="rgp-kpi-top">
              <div class="rgp-kpi-label">Pendentes / Irregulares</div>
              <div class="rgp-kpi-ico rgp-ico-red">✕</div>
            </div>
            <div class="rgp-kpi-value rgp-kpi-bad">${esc(fmtBrNum(kpis.pendentes))}</div>
            <div class="rgp-kpi-meta">${esc(String(kpis.pendentes_pct || 0).replace(".", ","))}% do total</div>
          </div>
        </div>

        <div class="rgp-main ${selected ? "has-side" : ""}">
          <div class="rgp-table-wrap">
            <div class="rgp-toolbar">
              <div class="rgp-search-wrap">
                <span class="rgp-search-ico">⌕</span>
                <input type="search" id="rgp-search" placeholder="Buscar por nome, CPF ou telefone…" value="${esc(state.consultaRgpSearch)}" />
              </div>
              <select id="rgp-filtro">
                <option value="">Filtros</option>
                ${situacoesFiltro.map((s) => `<option value="${esc(s)}" ${s === state.consultaRgpFiltro ? "selected" : ""}>${esc(s)}</option>`).join("")}
              </select>
              <button type="button" class="btn-link" id="rgp-clear">Limpar filtros</button>
            </div>
            <div class="rgp-chips" role="group" aria-label="Filtros rápidos">
              <button type="button" class="rgp-chip ${!state.consultaRgpFiltro ? "active" : ""}" data-chip="">Todos</button>
              ${RGP_CHIP_SITUACOES.map((s) => `
                <button type="button" class="rgp-chip ${state.consultaRgpFiltro === s ? "active" : ""}" data-chip="${esc(s)}">${esc(s)}</button>
              `).join("")}
            </div>
            <div class="rgp-table-scroll">
              <table class="rgp-table">
                <thead>
                  <tr>
                    <th>Nome</th><th>CPF</th><th>Município</th><th>Telefone</th>
                    <th>Situação RGP</th><th>Última consulta</th><th>Observação</th><th>Ações</th>
                  </tr>
                </thead>
                <tbody>
                  ${slice.length ? slice.map((r, i) => `
                    <tr class="${r.id === state.consultaRgpSelectedId ? "selected" : ""} ${(start + i) % 2 ? "alt" : ""}" data-id="${esc(r.id)}">
                      <td>${esc(r.nome_display || r.nome || "")}</td>
                      <td>${esc(r.cpf_formatado || r.cpf || "")}</td>
                      <td>${esc([r.municipio, r.uf].filter(Boolean).join(" - ") || "—")}</td>
                      <td>${esc(r.telefone || "—")}</td>
                      <td><span class="rgp-badge ${esc(r.badge_class || "")}">${esc(r.situacao_rgp || "Não consultado")}</span></td>
                      <td>${esc(r.ultima_consulta_em || "—")}</td>
                      <td class="rgp-obs">${esc(r.observacao || "—")}</td>
                      <td class="rgp-actions">
                        <button type="button" class="btn-link" data-act="consultar" data-id="${esc(r.id)}">👁 Consultar</button>
                        <button type="button" class="btn-link" data-act="editar" data-id="${esc(r.id)}">✎ Editar</button>
                      </td>
                    </tr>
                  `).join("") : loadingHint}
                </tbody>
              </table>
            </div>
            <div class="rgp-footer">
              <span>Exibindo ${filtered.length ? start + 1 : 0} a ${Math.min(start + pageSize, filtered.length)} de ${fmtBrNum(filtered.length)} registros</span>
              <label>Registros por página
                <select id="rgp-pagesize">
                  ${[10, 20, 50, 100].map((n) => `<option value="${n}" ${n === pageSize ? "selected" : ""}>${n}</option>`).join("")}
                </select>
              </label>
              <div class="btn-row">
                <button type="button" class="btn btn-outline-dark btn-sm" id="rgp-prev" ${page <= 1 ? "disabled" : ""}>←</button>
                <span>${page}/${pages}</span>
                <button type="button" class="btn btn-outline-dark btn-sm" id="rgp-next" ${page >= pages ? "disabled" : ""}>→</button>
              </div>
            </div>
          </div>

          ${selected ? `
          <aside class="rgp-side">
            <div class="rgp-side-head">
              <div>
                <div class="rgp-side-kicker">Detalhes do registro <span class="rgp-tag">RGP</span></div>
              </div>
              <button type="button" class="btn btn-ghost btn-sm" id="rgp-side-close">✕</button>
            </div>
            <div class="rgp-side-profile">
              <div class="rgp-avatar">${esc(selected.iniciais || "?")}</div>
              <div>
                <div class="rgp-side-name">${esc(selected.nome_display || selected.nome || "")}</div>
                <div class="rgp-side-cpf">${esc(selected.cpf_formatado || selected.cpf || "")}</div>
                ${reapPill}
              </div>
            </div>
            <div class="rgp-side-toolbar">
              ${editMode
                ? `<button type="button" class="btn btn-outline-dark btn-sm" id="rgp-cancel-edit">Cancelar edição</button>
                   <button type="button" class="btn btn-primary btn-sm" id="rgp-save-cadastro">Salvar cadastro</button>`
                : `<button type="button" class="btn btn-outline-dark btn-sm" id="rgp-edit-cadastro">✎ Editar cadastro</button>
                   <button type="button" class="btn btn-primary btn-sm" id="rgp-consultar-sel">Consultar no MPA</button>`}
            </div>
            <div class="rgp-side-body">
              ${editMode ? `
                <h4>Editar cadastro</h4>
                <label>Nome *</label>
                <input id="rgp-side-nome" value="${esc(selected.nome || "")}" />
                <label>CPF *</label>
                <input id="rgp-side-cpf" value="${esc(selected.cpf_formatado || selected.cpf || "")}" />
                <label>Município</label>
                <input id="rgp-side-mun" value="${esc(selected.municipio || "")}" />
                <label>Telefone</label>
                <input id="rgp-side-tel" value="${esc(selected.telefone || "")}" />
                <label>Observação</label>
                <textarea id="rgp-side-obs" rows="3">${esc(selected.observacao || "")}</textarea>
              ` : `
                <h4>Informações principais</h4>
                <div class="rgp-field"><span>Situação RGP</span><strong><span class="rgp-badge ${esc(selected.badge_class || "")}">${esc(selected.situacao_rgp || "Não consultado")}</span></strong></div>
                <div class="rgp-field"><span>Última consulta</span><strong>${esc(selected.ultima_consulta_em || "—")}</strong></div>
                <div class="rgp-field"><span>Telefone</span><strong>${esc(selected.telefone || "—")}</strong></div>
                <div class="rgp-field"><span>E-mail</span><strong>${esc(selected.email || "—")}</strong></div>
                <div class="rgp-field"><span>Município</span><strong>${esc([selected.municipio, selected.uf].filter(Boolean).join(" - ") || "—")}</strong></div>
                <div class="rgp-field"><span>Observação</span><strong>${esc(selected.observacao || "—")}</strong></div>
                <h4>Linha do tempo</h4>
                <div class="rgp-timeline">
                  ${(selected.timeline_items || []).length
                    ? selected.timeline_items.map((t) => `
                      <div class="rgp-tl-item">
                        <div class="rgp-tl-dot"></div>
                        <div>
                          <div class="rgp-tl-event">${esc(t.evento || "")}</div>
                          <div class="rgp-tl-meta">${esc(t.em || "")} · ${esc(t.ator || "")}</div>
                        </div>
                      </div>`).join("")
                    : `<p class="page-sub">Sem eventos ainda.</p>`}
                </div>
                <label>Observações</label>
                <textarea id="rgp-obs-edit" rows="3">${esc(selected.observacao || "")}</textarea>
                <div class="btn-row" style="margin-top:8px;flex-wrap:wrap">
                  <button type="button" class="btn btn-outline-dark btn-sm" id="rgp-save-obs">Salvar observação</button>
                  <button type="button" class="btn btn-ghost btn-sm" id="rgp-open-mpa">Abrir site MPA</button>
                </div>
              `}
            </div>
          </aside>` : ""}
        </div>
      </div>
    `);

    // NÃO recarregar a planilha aqui — evita loop/quota 60

    $("#rgp-search")?.addEventListener("input", (e) => {
      state.consultaRgpSearch = e.target.value;
      state.consultaRgpPage = 1;
      renderConsultaRgp();
    });
    const setFiltro = (val) => {
      state.consultaRgpFiltro = val || "";
      state.consultaRgpPage = 1;
      renderConsultaRgp();
    };
    $("#rgp-filtro")?.addEventListener("change", (e) => setFiltro(e.target.value || ""));
    document.querySelectorAll(".rgp-chip[data-chip]").forEach((chip) => {
      chip.addEventListener("click", () => setFiltro(chip.dataset.chip || ""));
    });
    $("#rgp-clear")?.addEventListener("click", () => {
      state.consultaRgpSearch = "";
      state.consultaRgpFiltro = "";
      state.consultaRgpPage = 1;
      renderConsultaRgp();
    });
    $("#rgp-pagesize")?.addEventListener("change", (e) => {
      state.consultaRgpPageSize = Number(e.target.value) || 20;
      state.consultaRgpPage = 1;
      renderConsultaRgp();
    });
    $("#rgp-prev")?.addEventListener("click", () => {
      state.consultaRgpPage = Math.max(1, (state.consultaRgpPage || 1) - 1);
      renderConsultaRgp();
    });
    $("#rgp-next")?.addEventListener("click", () => {
      state.consultaRgpPage = (state.consultaRgpPage || 1) + 1;
      renderConsultaRgp();
    });
    $("#rgp-cadastrar")?.addEventListener("click", () => openConsultaSocioModal(null));
    $("#rgp-sync")?.addEventListener("click", () => {
      api("sync_consulta_rgp_reap");
    });
    $("#rgp-govbr")?.addEventListener("change", (e) => {
      state.consultaRgpGovbr = !!e.target.checked;
      api("save_consulta_rgp_prefs", {
        govbr_opcional: state.consultaRgpGovbr,
        importar_auto: state.consultaRgpImportAuto,
      });
    });
    $("#rgp-auto")?.addEventListener("change", (e) => {
      state.consultaRgpImportAuto = !!e.target.checked;
      api("save_consulta_rgp_prefs", {
        govbr_opcional: state.consultaRgpGovbr,
        importar_auto: state.consultaRgpImportAuto,
      });
      toast(
        state.consultaRgpImportAuto
          ? "Preferência salva: importar automático REAP ligado (quando a sync estiver ativa)."
          : "Preferência salva: importar automático REAP desligado.",
        3500
      );
    });

    document.querySelectorAll(".rgp-table tbody tr[data-id]").forEach((tr) => {
      tr.addEventListener("click", (e) => {
        if (e.target.closest("[data-act]")) return;
        state.consultaRgpSelectedId = tr.dataset.id || "";
        state.consultaRgpEditMode = false;
        renderConsultaRgp();
      });
    });
    document.querySelectorAll("[data-act=consultar]").forEach((btn) => {
      btn.addEventListener("click", (e) => {
        e.stopPropagation();
        state.consultaRgpSelectedId = btn.dataset.id || "";
        state.consultaRgpEditMode = false;
        renderConsultaRgp();
      });
    });
    document.querySelectorAll("[data-act=editar]").forEach((btn) => {
      btn.addEventListener("click", (e) => {
        e.stopPropagation();
        const id = btn.dataset.id || "";
        const reg = (state.consultaRgpItens || []).find((x) => x.id === id);
        state.consultaRgpSelectedId = id;
        state.consultaRgpEditMode = false;
        openConsultaSocioModal(reg || null);
      });
    });
    $("#rgp-side-close")?.addEventListener("click", () => {
      state.consultaRgpSelectedId = "";
      state.consultaRgpEditMode = false;
      renderConsultaRgp();
    });
    $("#rgp-edit-cadastro")?.addEventListener("click", () => {
      state.consultaRgpEditMode = true;
      renderConsultaRgp();
    });
    $("#rgp-cancel-edit")?.addEventListener("click", () => {
      state.consultaRgpEditMode = false;
      renderConsultaRgp();
    });
    $("#rgp-save-cadastro")?.addEventListener("click", () => {
      if (!selected) return;
      const payload = payloadFromConsultaSide(selected);
      if (!payload.nome) { toast("Informe o nome."); return; }
      if ((String(payload.cpf || "").replace(/\D/g, "")).length !== 11) {
        toast("CPF inválido.");
        return;
      }
      state.consultaRgpEditMode = false;
      state.consultaRgpPendingConsulta = false;
      api("save_consulta_rgp_registro", payload);
    });
    const cpfSide = $("#rgp-side-cpf");
    if (cpfSide && typeof bindCpfMask === "function") bindCpfMask(cpfSide);
    $("#rgp-save-obs")?.addEventListener("click", () => {
      if (!selected) return;
      api("save_consulta_rgp_registro", {
        id: selected.id,
        person_id: selected.person_id,
        nome: selected.nome,
        cpf: selected.cpf,
        telefone: selected.telefone,
        municipio: selected.municipio,
        uf: selected.uf,
        situacao_rgp: selected.situacao_rgp,
        observacao: $("#rgp-obs-edit")?.value || "",
        ultima_consulta_em: selected.ultima_consulta_em,
        codigo_rgp: selected.codigo_rgp,
        categoria: selected.categoria,
        email: selected.email,
        importado_reap_em: selected.importado_reap_em,
        importado_defeso_em: selected.importado_defeso_em,
        cadastro_reap_em: selected.cadastro_reap_em,
        timeline: selected.timeline,
      });
    });
    $("#rgp-consultar-sel")?.addEventListener("click", () => {
      if (selected) api("consultar_rgp_pessoa", selected.id, selected.cpf);
    });
    $("#rgp-open-mpa")?.addEventListener("click", () => {
      api("abrir_consulta_rgp_mpa", selected?.cpf || "");
    });
  }

  function applyConsultaRgpPayload(data) {
    if (!data) return;
    if (Array.isArray(data.itens)) state.consultaRgpItens = data.itens;
    if (data.kpis) state.consultaRgpKpis = data.kpis;
    if (typeof data.importar_auto === "boolean") state.consultaRgpImportAuto = data.importar_auto;
    if (typeof data.govbr_opcional === "boolean") state.consultaRgpGovbr = data.govbr_opcional;
    state.consultaRgpLoaded = true;
    state.consultaRgpLoading = false;
  }

  function wireEvents() {
    AppEvents.on("status", (p) => setStatus(p.msg));
    AppEvents.on("pessoas", (r) => {
      if (r.ok) {
        // Sempre confia na planilha (evita contador preso em "agora").
        state.pessoas = (r.data || []).map((p, i) => ({ ...p, _idx: i }));
        state.adminLocalidades = [...new Set(
          state.pessoas.map((p) => String(p.municipio || "").trim()).filter(Boolean)
        )].sort((a, b) => a.localeCompare(b, "pt-BR", { sensitivity: "base" }));
        state.connLabel = "Conectado";
        setFooter();
        if (state.screen === "admin") {
          refreshAdminLocalidadeSelect();
          renderAdminList();
        }
        if (state.screen === "lista") renderListaCards();
      } else toast(r.error);
    });
    AppEvents.on("sync_planilhas", (r) => {
      if (r.ok) {
        const msg = r.data?.mensagem || "Planilhas sincronizadas.";
        toast(msg, 5000);
        loadPessoas();
        if (state.screen === "defeso" || state.screen === "defeso_ficha") {
          api("load_defeso_lista");
        }
      } else toast(r.error);
    });
    AppEvents.on("pessoa_saved", (r) => {
      if (r.ok) { toast("Salvo."); loadPessoas(); }
      else toast(r.error);
    });
    AppEvents.on("pessoa_deleted", (r) => {
      if (r.ok) { toast("Excluído."); loadPessoas(); }
      else toast(r.error);
    });
    AppEvents.on("mes_toggled", (r) => {
      if (r.ok && r.data && r.data.person_id) {
        // Atualiza o contador na hora (sem esperar a planilha).
        const p = state.pessoas.find((x) => x.id === r.data.person_id);
        if (p) {
          p.ultimo_toggle_label = "agora";
          p.ultimo_toggle_em = nowLocalStamp();
          if (state.screen === "admin") renderAdminList();
          if (state.screen === "lista") renderListaCards();
        }
        if (state.screen === "pendencias") {
          const anoEl = $("#pend-ano");
          if (anoEl) api("load_pendencias", parseInt(anoEl.value, 10));
        }
      } else if (!r.ok) {
        toast(r.error || "Não foi possível marcar o mês.");
        loadPessoas();
      }
    });
    AppEvents.on("ano_added", (r) => {
      if (r.ok) loadPessoas();
      else toast(r.error);
    });
    AppEvents.on("lote_saved", (r) => {
      const box = state.loteBackdrop;
      const saveBtn = box && box.querySelector("#l-save");
      const statusEl = box && box.querySelector("#l-status");
      if (r.ok) {
        const d = r.data || {};
        const nOk = d.ok ?? d.criados ?? 0;
        const erros = d.erros || [];
        toast(`Lote: ${nOk} cadastrado(s)${erros.length ? ` · ${erros.length} recusado(s)` : ""}.`);
        if (erros.length) toast(erros.slice(0, 4).join(" "));
        if (nOk > 0) {
          try { localStorage.removeItem("sinapesc_lote_draft"); } catch (_e) {}
          if (box) box._close(true);
          state.loteBackdrop = null;
          loadPessoas();
        } else {
          if (statusEl) statusEl.textContent = erros.slice(0, 6).join(" ") || "Ninguém foi cadastrado. Confira CPF e nomes.";
          if (saveBtn) saveBtn.disabled = false;
        }
      } else {
        toast(r.error || "Erro no lote.");
        if (statusEl) statusEl.textContent = r.error || "Erro. Seus dados continuam nesta janela.";
        if (saveBtn) saveBtn.disabled = false;
      }
    });
    AppEvents.on("pendencias", (r) => {
      if (r.ok) renderPendenciasList(r.data);
      else toast(r.error);
    });
    AppEvents.on("calendario_saved", (r) => {
      if (r.ok) {
        toast("Calendário salvo.");
        api("load_pendencias", parseInt($("#pend-ano")?.value || new Date().getFullYear(), 10));
      } else toast(r.error);
    });
    AppEvents.on("massa_ok", (r) => {
      if (r.ok) {
        toast(`Atualizados: ${r.data?.atualizados ?? "?"} · criados: ${r.data?.criados ?? 0}`);
        if (state.screen === "pendencias") api("load_pendencias", parseInt($("#pend-ano")?.value, 10));
        else loadPessoas();
      } else toast(r.error);
    });
    AppEvents.on("copia_ok", (r) => {
      if (r.ok) {
        toast(`Copiados: ${r.data?.ok ?? 0} · pulados: ${r.data?.pulados ?? 0}`);
        loadPessoas();
      } else toast(r.error);
    });
    AppEvents.on("relatorio", (r) => {
      if (r.ok && r.data?.path) {
        api("open_path", r.data.path);
        toast("Relatório aberto no navegador para imprimir.");
      } else toast(r.error);
    });
    AppEvents.on("defeso_relatorio", (r) => {
      if (r.ok && r.data?.path) {
        api("open_path", r.data.path);
        toast(`Relatório Defeso aberto (${r.data.total || "?"} registro(s)).`);
      } else toast(r.error);
    });
    AppEvents.on("backup", (r) => {
      if (r.ok) {
        toast(`Backup: ${r.data?.pasta || "ok"}`);
        refreshBootstrap();
        refreshBackupList();
      } else toast(r.error);
    });
    AppEvents.on("auditoria", (r) => {
      if (r.ok) renderAuditoriaList(r.data);
      else toast(r.error);
    });
    AppEvents.on("auditoria_export", (r) => {
      if (r.ok) {
        toast(`CSV: ${r.data?.path}`);
        api("open_path", r.data.path);
      } else toast(r.error);
    });
    AppEvents.on("qrs", (r) => {
      toast(r.ok ? `QRs → ${r.data?.base}` : r.error);
    });
    AppEvents.on("defeso_lista", (r) => {
      if (r.ok) {
        state.defesoItens = r.data?.itens || [];
        state.defesoLocalidades = r.data?.localidades || [];
        if (state.screen === "defeso") {
          refreshDefesoLocalidadeSelect();
          paintDefesoLista();
        }
        if (r.data?.aviso) toast(r.data.aviso, 6000);
      } else toast(r.error);
    });
    AppEvents.on("defeso_ficha", (r) => {
      if (r.ok) {
        state.defesoFicha = { ...(state.defesoFicha || {}), ...r.data };
        if (state.screen === "defeso_ficha") fillDefesoForm(r.data);
      } else toast(r.error || "Erro ao abrir ficha.");
    });
    AppEvents.on("defeso_saved", (r) => {
      if (r.ok) {
        toast("Ficha Defeso salva.");
        const prev = state.defesoFicha || {};
        state.defesoFicha = {
          ...prev,
          ...r.data,
          ficha_id: r.data.id,
          municipio_reap: r.data.municipio_reap ?? prev.municipio_reap ?? "",
          anexos: prev.anexos || [],
          anexos_mode: prev.anexos_mode,
          anexos_local_root: prev.anexos_local_root,
          defeso_anexos_dir: prev.defeso_anexos_dir,
          drive_ok: prev.drive_ok,
        };
        if (state.screen === "defeso_ficha") fillDefesoForm(state.defesoFicha);
        api("load_defeso_lista");
      } else toast(r.error);
    });
    AppEvents.on("defeso_print", (r) => {
      if (r.ok) {
        toast("Declaração aberta no navegador para imprimir.");
        if (r.data?.ficha_id && $("#df-id")) $("#df-id").value = r.data.ficha_id;
      } else toast(r.error);
    });
    AppEvents.on("defeso_pacote", (r) => {
      if (r.ok) {
        const n = r.data?.incluidos?.length || 0;
        const pages = r.data?.pages || "?";
        toast(`Pacote PDF aberto no navegador (${n} doc(s), ${pages} pág.).`);
        if (r.data?.aviso) toast(r.data.aviso, 7000);
        if (r.data?.ficha_id && $("#df-id")) $("#df-id").value = r.data.ficha_id;
      } else toast(r.error);
    });
    AppEvents.on("defeso_anexo", (r) => {
      if (r.ok) {
        const w = r.data?.where;
        const where = w === "sync" ? "pasta Drive sync" : (w === "drive" ? "Drive API" : "pasta local");
        toast(`Anexo enviado (${where}): ${r.data?.name || "ok"}`);
        if (r.data?.aviso) toast(r.data.aviso, 7000);
        const ref = state.defesoFicha || {};
        api("load_defeso_ficha", ref.person_id || "", ref.cpf || $("#df-cpf")?.value || "", $("#df-id")?.value || ref.ficha_id || "");
        api("load_defeso_lista");
      } else toast(r.error);
    });
    AppEvents.on("consulta_rgp", (r) => {
      state.consultaRgpLoading = false;
      if (r.ok) {
        applyConsultaRgpPayload(r.data);
        if (state.screen === "consulta_rgp") renderConsultaRgp();
      } else {
        state.consultaRgpLoaded = true; // evita loop de retry
        toast(r.error || "Falha ao carregar Consulta RGP.");
        if (state.screen === "consulta_rgp") renderConsultaRgp();
      }
    });
    AppEvents.on("consulta_rgp_sync", (r) => {
      if (r.ok) {
        applyConsultaRgpPayload(r.data);
        toast(r.data?.mensagem || "Enviado ao REAP/Defeso.");
        if (state.screen === "consulta_rgp") renderConsultaRgp();
      } else toast(r.error);
    });
    AppEvents.on("consulta_rgp_lote", (r) => {
      if (r.ok) {
        applyConsultaRgpPayload(r.data);
        toast(r.data?.mensagem || "Importado na Consulta.");
        if (r.data?.erros?.length) toast(r.data.erros.slice(0, 3).join(" · "), 7000);
        if (state.screen === "consulta_rgp") renderConsultaRgp();
      } else toast(r.error);
    });
    AppEvents.on("consulta_rgp_cadastro", (r) => {
      if (r.ok) {
        applyConsultaRgpPayload(r.data);
        const item = r.data?.registro;
        if (item?.id) state.consultaRgpSelectedId = item.id;
        toast(r.data?.mensagem || "Sócio cadastrado.");
        if (state.consultaRgpPendingConsulta && item?.id) {
          state.consultaRgpPendingConsulta = false;
          toast("Consultando MPA…", 2500);
          api("consultar_rgp_pessoa", item.id, item.cpf || "");
        } else {
          state.consultaRgpPendingConsulta = false;
        }
        if (state.screen === "consulta_rgp") renderConsultaRgp();
      } else {
        state.consultaRgpPendingConsulta = false;
        toast(r.error || "Falha ao cadastrar.");
      }
    });
    AppEvents.on("consulta_rgp_saved", (r) => {
      if (r.ok) {
        if (r.data?.itens) applyConsultaRgpPayload(r.data);
        const item = r.data?.registro || r.data;
        if (item?.id) {
          const idx = state.consultaRgpItens.findIndex((x) => x.id === item.id);
          if (idx >= 0) state.consultaRgpItens[idx] = item;
          else if (!r.data?.itens) state.consultaRgpItens.push(item);
          state.consultaRgpSelectedId = item.id;
          if (r.data?.kpis) state.consultaRgpKpis = r.data.kpis;
        }
        toast("Registro salvo.");
        if (state.screen === "consulta_rgp") renderConsultaRgp();
      } else toast(r.error);
    });
    AppEvents.on("consulta_rgp_consulta", (r) => {
      if (r.ok) {
        const item = r.data?.registro;
        toast(r.data?.mensagem || "Consulta concluída.");
        if (item?.id) {
          const idx = state.consultaRgpItens.findIndex((x) => x.id === item.id);
          if (idx >= 0) state.consultaRgpItens[idx] = item;
          else state.consultaRgpItens.push(item);
          state.consultaRgpSelectedId = item.id;
        }
        if (r.data?.imports?.aviso) toast(r.data.imports.aviso, 6000);
        if (state.screen === "consulta_rgp") renderConsultaRgp();
      } else toast(r.error || "Falha na consulta MPA.", 7000);
    });
    AppEvents.on("consulta_rgp_import", (r) => {
      if (r.ok) {
        toast("Importado para REAP/Defeso.");
        if (r.data?.registro?.id) {
          const item = r.data.registro;
          const idx = state.consultaRgpItens.findIndex((x) => x.id === item.id);
          if (idx >= 0) state.consultaRgpItens[idx] = item;
        }
        if (r.data?.reap?.aviso) toast(r.data.reap.aviso, 5000);
        if (r.data?.defeso?.aviso) toast(r.data.defeso.aviso, 5000);
        if (state.screen === "consulta_rgp") renderConsultaRgp();
      } else toast(r.error);
    });
  }

  async function init() {
    wireEvents();
    await refreshBootstrap();
    $("#app").classList.remove("hidden");
    navigate("home", { push: false });
  }

  window.addEventListener("pywebviewready", init);
  if (window.pywebview) init();
})();
