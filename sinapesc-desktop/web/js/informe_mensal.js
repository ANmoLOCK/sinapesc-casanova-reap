/* Informe Mensal — REAP mês a mês por sócio (planilha REAP) */
(function () {
  "use strict";

  const MESES_ORDEM = ["jan", "fev", "mar", "abr", "mai", "jun", "jul", "ago", "set", "out", "nov", "dez"];
  const MESES_TITULO_PADRAO = {
    jan: "Janeiro", fev: "Fevereiro", mar: "Março", abr: "Abril", mai: "Maio", jun: "Junho",
    jul: "Julho", ago: "Agosto", set: "Setembro", out: "Outubro", nov: "Novembro", dez: "Dezembro",
  };
  const PIRACEMA_PADRAO = ["jan", "fev", "nov", "dez"];

  const S = {
    ano: new Date().getFullYear(),
    loaded: false,
    loading: false,
    socios: [],
    meta: {},
    search: "",
    filtro: "todos",
    tab: "socios",
    auditoria: [],
    audSearch: "",
    audAcao: "",
    openId: "",
    selMes: "",
    edit: null,
    busy: false,
    modal: null,
    showProb: false,
  };
  window.SinapescInformeState = S;

  function api(method, ...args) {
    if (!window.pywebview || !window.pywebview.api) {
      return Promise.reject(new Error("API Python indisponível"));
    }
    return window.pywebview.api[method](...args);
  }

  function toast(msg, ms) {
    if (typeof window.sinapescToast === "function") window.sinapescToast(msg, ms);
  }

  function esc(s) {
    return String(s ?? "")
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;")
      .replace(/"/g, "&quot;");
  }

  function fmtMoney(v) {
    return Number(v || 0).toLocaleString("pt-BR", { minimumFractionDigits: 2, maximumFractionDigits: 2 });
  }

  function onScreen() {
    return typeof window.sinapescCurrentScreen === "function"
      && window.sinapescCurrentScreen() === "informe_mensal";
  }

  function titulo(m) {
    return (S.meta.meses_titulo && S.meta.meses_titulo[m]) || MESES_TITULO_PADRAO[m] || m;
  }

  function piracema() {
    return S.meta.meses_piracema || PIRACEMA_PADRAO;
  }

  function isPiracema(m) {
    return piracema().includes(m);
  }

  function piracemaLabel() {
    return S.meta.piracema_label || "ÉPOCA DE PIRACEMA";
  }

  function totalPesca() {
    return (S.meta.meses_pesca || []).length || 8;
  }

  function previsto(s, m) {
    const i = (S.meta.meses_pesca || []).indexOf(m);
    const plano = (s.resumo && s.resumo.plano) || [];
    return i >= 0 && plano[i] ? Number(plano[i]) : 0;
  }

  function probMes(m, n) {
    const p = S.meta.probabilidades && S.meta.probabilidades.por_mes && S.meta.probabilidades.por_mes[m];
    return p ? Number(p[String(n)] || 0) : 0;
  }

  function pct(v) {
    return `${(Number(v || 0) * 100).toLocaleString("pt-BR", { maximumFractionDigits: 1 })}%`;
  }

  function planoChipsHtml(s) {
    const pesca = S.meta.meses_pesca || [];
    const plano = (s.resumo && s.resumo.plano) || [];
    if (!plano.length) return `<span class="im-plano-vazio">sorteado ao gerar o 1º mês</span>`;
    return pesca.map((m, i) => {
      const n = Number(plano[i] || 0);
      const feito = !!(s.meses && s.meses[m]);
      return `<span class="im-chip ${n === 8 ? "im-chip-8" : ""} ${feito ? "im-chip-ok" : ""}" title="${esc(titulo(m))}: ${n} espécies${feito ? " (gerado)" : " (previsto)"} · chance geral ${pct(probMes(m, n))}">${esc(titulo(m).slice(0, 3))} <strong>${n}</strong></span>`;
    }).join("");
  }

  function probTabelaHtml() {
    const p = S.meta.probabilidades || {};
    const regras = S.meta.regras_probabilidade || {};
    const conts = (S.meta.contagens || [4, 5, 6, 8]).map(String);
    const pesca = S.meta.meses_pesca || [];
    if (!p.por_mes) return "";
    const linhas = conts.map((c) => `
      <tr><th>${c} espécies</th>${pesca.map((m) => `<td class="${c === "8" ? "im-prob-8" : ""}">${pct(p.por_mes[m] && p.por_mes[m][c])}</td>`).join("")}</tr>`).join("");
    const pesos = Object.entries(regras.peso_quantidade || {}).map(([k, v]) => `${k} → ${pct(v)}`).join(" · ");
    return `
      <div class="im-prob">
        <div class="im-prob-head">Cálculo de probabilidade (${esc(p.amostras || 0)} simulações do sorteio)</div>
        <div class="im-prob-text">
          Peso base: ${esc(pesos)}. Cada vez que uma quantidade já apareceu no ano, o peso dela é multiplicado por
          ${esc(regras.fator_repeticao ?? 0.45)} — por isso o cérebro tenta não repetir. Meses vizinhos nunca têm a mesma quantidade;
          4, 5 e 6 aparecem no ano; 8 espécies no máximo 1 mês e só para ~${pct(regras.chance_socio_ter_8 ?? 0.35)} dos sócios
          (mais provável no meio da safra). O plano de cada sócio é sorteado para não repetir o plano de outro sócio.
        </div>
        <div class="im-table-wrap"><table class="im-table im-prob-table">
          <thead><tr><th></th>${pesca.map((m) => `<th>${esc(titulo(m).slice(0, 3))}</th>`).join("")}</tr></thead>
          <tbody>${linhas}</tbody>
        </table></div>
        <div class="im-prob-text">Chance de o sócio ter um mês com 8: <strong>${pct(p.chance_ter_8)}</strong> · média ${esc(p.media_especies_ano || "—")} espécies-mês no ano.</div>
      </div>`;
  }

  function socioById(id) {
    return S.socios.find((s) => s.id === id) || null;
  }

  function failed(r, fallback) {
    const msg = (r && r.error) || fallback;
    if (typeof window.sinapescSessionExpired === "function" && window.sinapescSessionExpired(msg)) return;
    toast(msg, 5200);
  }

  function anosOpcoes() {
    const atual = new Date().getFullYear();
    const anos = new Set([atual - 2, atual - 1, atual, atual + 1, Number(S.ano)]);
    return [...anos].sort((a, b) => b - a);
  }

  function load(ano) {
    if (ano) S.ano = Number(ano);
    S.loading = true;
    render();
    api("load_informe_mensal", S.ano).catch((e) => toast(String(e)));
  }

  // ---------------------------------------------------------------- lista

  function matchFiltro(s) {
    const g = s.resumo?.gerados || 0;
    if (S.filtro === "pendentes") return g < totalPesca();
    if (S.filtro === "completos") return g >= totalPesca();
    if (S.filtro === "nenhum") return g === 0;
    if (S.filtro === "avisos") return (s.resumo?.avisos || []).length > 0;
    if (S.filtro === "iguais") return (s.padrao_igual || []).length > 0;
    return true;
  }

  function matchBusca(s) {
    const q = S.search.trim().toLowerCase();
    if (!q) return true;
    const qd = q.replace(/\D/g, "");
    const blob = `${s.nome} ${s.telefone} ${s.municipio}`.toLowerCase();
    if (blob.includes(q)) return true;
    if (qd && (String(s.cpf_raw || "").includes(qd) || String(s.telefone || "").replace(/\D/g, "").includes(qd))) {
      return true;
    }
    return false;
  }

  function filtrados() {
    return S.socios.filter((s) => matchFiltro(s) && matchBusca(s));
  }

  function dotsHtml(s) {
    return MESES_ORDEM.map((m) => {
      if (isPiracema(m)) return `<span class="im-dot im-dot-pir" title="${esc(titulo(m))} — ${esc(piracemaLabel())}"></span>`;
      const ok = !!(s.meses && s.meses[m]);
      return `<span class="im-dot ${ok ? "im-dot-ok" : ""}" title="${esc(titulo(m))}: ${ok ? "gerado" : "pendente"}"></span>`;
    }).join("");
  }

  function render() {
    if (!onScreen() || typeof window.sinapescSetPage !== "function") return;
    const tabs = `
      <div class="im-tabs" role="tablist">
        <button type="button" class="im-tab ${S.tab === "socios" ? "active" : ""}" data-im-tab="socios">Sócios</button>
        <button type="button" class="im-tab ${S.tab === "auditoria" ? "active" : ""}" data-im-tab="auditoria">Auditoria</button>
      </div>`;

    if (S.tab === "auditoria") {
      window.sinapescSetPage(`
        <div class="im-shell">
          ${tabs}
          <div class="im-bar">
            <div class="im-bar-title">
              <span class="page-title">Auditoria — Informe Mensal</span>
              <span class="page-meta" id="im-aud-hint">Carregando…</span>
            </div>
            <div class="im-bar-actions">
              <button type="button" class="btn btn-outline-dark btn-sm" id="im-aud-refresh">Atualizar</button>
            </div>
          </div>
          <div class="im-toolbar">
            <input type="search" id="im-aud-search" placeholder="Buscar por sócio, operador, mês…" value="${esc(S.audSearch)}" />
            <select id="im-aud-acao">
              <option value="">Todas as ações</option>
              <option value="gerar_informe" ${S.audAcao === "gerar_informe" ? "selected" : ""}>Gerou</option>
              <option value="regerar_informe" ${S.audAcao === "regerar_informe" ? "selected" : ""}>Regerou</option>
              <option value="editar_informe" ${S.audAcao === "editar_informe" ? "selected" : ""}>Alterou</option>
              <option value="excluir_informe" ${S.audAcao === "excluir_informe" ? "selected" : ""}>Excluiu</option>
              <option value="abrir_tabela_informe" ${S.audAcao === "abrir_tabela_informe" ? "selected" : ""}>Abriu tabela geral</option>
              <option value="abrir_tabela_socio" ${S.audAcao === "abrir_tabela_socio" ? "selected" : ""}>Tabela do sócio</option>
              <option value="config_especies_informe" ${S.audAcao === "config_especies_informe" ? "selected" : ""}>Peixes do cérebro</option>
            </select>
          </div>
          <div class="im-audit-list" id="im-aud-list"></div>
        </div>
      `);
      bindTabs();
      document.querySelector("#im-aud-refresh")?.addEventListener("click", () => api("load_informe_auditoria"));
      document.querySelector("#im-aud-search")?.addEventListener("input", (e) => {
        S.audSearch = e.target.value || "";
        paintAuditoria();
      });
      document.querySelector("#im-aud-acao")?.addEventListener("change", (e) => {
        S.audAcao = e.target.value || "";
        paintAuditoria();
      });
      paintAuditoria();
      api("load_informe_auditoria").catch((e) => toast(String(e)));
      return;
    }

    const anos = anosOpcoes().map((a) => `<option value="${a}" ${a === Number(S.ano) ? "selected" : ""}>${a}</option>`).join("");
    window.sinapescSetPage(`
      <div class="im-shell">
        ${tabs}
        <div class="im-bar">
          <div class="im-bar-title">
            <span class="page-title">Informe Mensal</span>
            <span class="page-meta" id="im-hint"></span>
          </div>
          <div class="im-bar-actions">
            <label class="im-ano">Ano <select id="im-ano">${anos}</select></label>
            <button type="button" class="btn btn-outline-dark btn-sm" id="im-peixes" title="Escolhe quais peixes entram no cérebro (vale para todos os sócios)">Peixes do cérebro</button>
            <button type="button" class="btn btn-primary btn-sm" id="im-tabela" title="Abre no navegador uma tabela HTML com cada sócio e os meses preenchidos">Abrir tabela no navegador</button>
            <button type="button" class="btn btn-outline-dark btn-sm" id="im-refresh">Atualizar</button>
          </div>
        </div>
        <div class="im-toolbar">
          <input type="search" id="im-search" placeholder="Buscar nome, CPF ou telefone…" value="${esc(S.search)}" />
          <select id="im-filtro">
            <option value="todos" ${S.filtro === "todos" ? "selected" : ""}>Todos</option>
            <option value="pendentes" ${S.filtro === "pendentes" ? "selected" : ""}>Com meses pendentes</option>
            <option value="nenhum" ${S.filtro === "nenhum" ? "selected" : ""}>Nenhum mês gerado</option>
            <option value="completos" ${S.filtro === "completos" ? "selected" : ""}>Completos (Mar–Out)</option>
            <option value="avisos" ${S.filtro === "avisos" ? "selected" : ""}>Com avisos do cérebro</option>
            <option value="iguais" ${S.filtro === "iguais" ? "selected" : ""}>Com padrão igual a outro sócio</option>
          </select>
          <span class="im-legend">
            <span class="im-dot im-dot-ok"></span> gerado
            <span class="im-dot"></span> pendente
            <span class="im-dot im-dot-pir"></span> piracema
          </span>
        </div>
        <div id="im-iguais"></div>
        <div class="im-table-wrap">
          <table class="im-table">
            <thead>
              <tr>
                <th>Nome</th><th>CPF</th><th>Telefone</th><th>Município</th>
                <th>Meses (Jan → Dez)</th><th class="im-num">Gerados</th><th class="im-num">Kg ano</th><th></th>
              </tr>
            </thead>
            <tbody id="im-tbody"></tbody>
          </table>
        </div>
      </div>
    `);
    bindTabs();
    document.querySelector("#im-ano")?.addEventListener("change", (e) => load(e.target.value));
    document.querySelector("#im-refresh")?.addEventListener("click", () => load());
    document.querySelector("#im-peixes")?.addEventListener("click", openConfigPeixes);
    document.querySelector("#im-tabela")?.addEventListener("click", () => {
      if (S.busy) return;
      S.busy = true;
      toast("Gerando tabela HTML…", 2200);
      api("abrir_informe_tabela", S.ano).catch((e) => {
        S.busy = false;
        toast(String(e));
      });
    });
    document.querySelector("#im-search")?.addEventListener("input", (e) => {
      S.search = e.target.value || "";
      paintTable();
    });
    document.querySelector("#im-filtro")?.addEventListener("change", (e) => {
      S.filtro = e.target.value || "todos";
      paintTable();
    });
    paintTable();
  }

  function bindTabs() {
    document.querySelectorAll("[data-im-tab]").forEach((b) => {
      b.addEventListener("click", () => {
        S.tab = b.dataset.imTab || "socios";
        render();
      });
    });
  }

  function paintTable() {
    const tbody = document.querySelector("#im-tbody");
    const hint = document.querySelector("#im-hint");
    if (!tbody) return;
    if (S.loading && !S.loaded) {
      tbody.innerHTML = `<tr><td colspan="8" class="im-empty">Carregando sócios da planilha REAP…</td></tr>`;
      if (hint) hint.textContent = "Carregando…";
      return;
    }
    paintIguais();
    const lista = filtrados();
    const completos = S.socios.filter((s) => (s.resumo?.gerados || 0) >= totalPesca()).length;
    if (hint) {
      const nPeixes = (S.meta.especies_ativas || especiesAtivasNomes() || []).length || 8;
      hint.textContent = `${lista.length} de ${S.socios.length} sócio(s) · ${completos} completo(s) em ${S.ano} · ${nPeixes} peixe(s) no cérebro · abas InformeMensal / InformeAuditoria`;
    }
    if (!lista.length) {
      tbody.innerHTML = `<tr><td colspan="8" class="im-empty">${S.socios.length ? "Nenhum sócio neste filtro." : "Nenhum sócio na planilha REAP. Cadastre em Abrir REAP."}</td></tr>`;
      return;
    }
    tbody.innerHTML = lista.map((s) => {
      const g = s.resumo?.gerados || 0;
      const avisos = (s.resumo?.avisos || []).length;
      const iguais = s.padrao_igual || [];
      const semMes = g === 0;
      return `
        <tr data-im-open="${esc(s.id)}" class="${g >= totalPesca() ? "im-row-ok" : ""}">
          <td class="im-nome">${esc(s.nome)}${avisos ? ` <span class="im-badge-warn" title="${esc((s.resumo.avisos || []).join(" · "))}">!</span>` : ""}${iguais.length ? ` <span class="im-badge-igual" title="${esc(iguais.join(" · "))}">=</span>` : ""}</td>
          <td class="im-mono">${esc(s.cpf)}</td>
          <td>${esc(s.telefone || "—")}</td>
          <td>${esc(s.municipio || "—")}</td>
          <td class="im-dots">${dotsHtml(s)}</td>
          <td class="im-num">${g}/${totalPesca()}</td>
          <td class="im-num">${s.resumo?.peso_anual || 0}</td>
          <td class="im-acoes" onclick="event.stopPropagation()">
            <div class="im-acao-cards">
              <button type="button" class="im-card-acao im-card-abrir" data-im-open="${esc(s.id)}">
                <span class="im-card-titulo">Abrir</span>
                <span class="im-card-sub">caixa do sócio</span>
              </button>
              <button type="button" class="im-card-acao im-card-tabela" data-im-tabela="${esc(s.id)}"
                ${semMes ? "disabled" : ""}
                title="${semMes ? "Gere ao menos um mês antes de abrir a tabela" : "Tabela HTML só deste sócio — meses preenchidos"}">
                <span class="im-card-titulo">Tabela</span>
                <span class="im-card-sub">${semMes ? "sem meses" : `${g} mês(es)`}</span>
              </button>
            </div>
          </td>
        </tr>`;
    }).join("");
    tbody.querySelectorAll("[data-im-open]").forEach((el) => {
      el.addEventListener("click", (e) => {
        e.stopPropagation();
        openSocio(el.dataset.imOpen || el.closest("tr")?.dataset.imOpen);
      });
    });
    tbody.querySelectorAll("[data-im-tabela]").forEach((btn) => {
      btn.addEventListener("click", (e) => {
        e.stopPropagation();
        abrirTabelaSocio(btn.dataset.imTabela);
      });
    });
  }

  function openConfigPeixes() {
    const todas = S.meta.especies_todas || (S.meta.catalogo || []).map((c) => c.nome);
    const ativas = new Set(S.meta.especies_ativas || todas);
    const min = S.meta.especies_minimo || 4;
    const precos = {};
    (S.meta.catalogo || []).forEach((c) => { precos[c.nome] = c.preco; });
    if (S.modalPeixes && S.modalPeixes.isConnected) S.modalPeixes.remove();
    const boxes = todas.map((n) => `
      <label class="im-peixe-item">
        <input type="checkbox" data-im-peixe="${esc(n)}" ${ativas.has(n) ? "checked" : ""} />
        <span class="im-peixe-nome">${esc(n)}</span>
        <span class="im-peixe-preco">R$ ${fmtMoney(precos[n] || 0)}/kg</span>
      </label>`).join("");
    S.modalPeixes = window.sinapescCreateModal(`
      <div class="im-peixes-box">
        <div class="modal-head im-head">
          <div>
            <div class="im-head-nome">Peixes do cérebro</div>
            <div class="im-head-meta">Configuração exclusiva do Informe Mensal · vale para <strong>todos</strong> os sócios</div>
          </div>
          <button type="button" class="btn btn-ghost btn-sm" id="im-peixes-close">✕</button>
        </div>
        <div class="modal-body">
          <p class="im-det-help">Marque os peixes que o cérebro pode usar ao <strong>Gerar REAP</strong>.
          Precisa de pelo menos <strong>${min}</strong>. Se marcar menos de 8, o mês com 8 espécies não entra no plano.</p>
          <div class="im-peixes-grid" id="im-peixes-grid">${boxes}</div>
          <div class="im-peixes-foot">
            <span id="im-peixes-count"></span>
            <div class="im-peixes-btns">
              <button type="button" class="btn btn-ghost btn-sm" id="im-peixes-todos">Marcar todos</button>
              <button type="button" class="btn btn-primary" id="im-peixes-salvar">Salvar seleção</button>
            </div>
          </div>
        </div>
      </div>`, "modal-wide im-modal");
    S.modalPeixes._onClose = () => { S.modalPeixes = null; };

    const syncCount = () => {
      const n = S.modalPeixes.querySelectorAll("[data-im-peixe]:checked").length;
      const el = S.modalPeixes.querySelector("#im-peixes-count");
      if (el) {
        el.textContent = `${n} de ${todas.length} selecionado(s)` +
          (n < min ? ` · mínimo ${min}` : "") +
          (n < 8 ? " · sem mês de 8 espécies" : "");
        el.classList.toggle("im-peixes-warn", n < min);
      }
      const save = S.modalPeixes.querySelector("#im-peixes-salvar");
      if (save) save.disabled = n < min || S.busy;
    };
    S.modalPeixes.querySelector("#im-peixes-close")?.addEventListener("click", () => {
      if (S.modalPeixes && S.modalPeixes._close) S.modalPeixes._close(false);
    });
    S.modalPeixes.querySelector("#im-peixes-todos")?.addEventListener("click", () => {
      S.modalPeixes.querySelectorAll("[data-im-peixe]").forEach((c) => { c.checked = true; });
      syncCount();
    });
    S.modalPeixes.querySelectorAll("[data-im-peixe]").forEach((c) => {
      c.addEventListener("change", syncCount);
    });
    S.modalPeixes.querySelector("#im-peixes-salvar")?.addEventListener("click", () => {
      const sel = [...S.modalPeixes.querySelectorAll("[data-im-peixe]:checked")].map((c) => c.dataset.imPeixe);
      if (sel.length < min) {
        toast(`Selecione pelo menos ${min} peixes.`, 4200);
        return;
      }
      if (S.busy) return;
      S.busy = true;
      toast("Salvando peixes do cérebro…", 2000);
      api("salvar_informe_especies", JSON.stringify({ especies: sel })).catch((e) => {
        S.busy = false;
        toast(String(e));
      });
    });
    syncCount();
  }

  function abrirTabelaSocio(id) {
    const s = socioById(id);
    if (!s) return;
    if (!(s.resumo?.gerados || 0)) {
      toast(`${s.nome}: nenhum mês preenchido ainda.`, 4200);
      return;
    }
    if (S.busy) return;
    S.busy = true;
    toast(`Gerando tabela de ${s.nome}…`, 2200);
    api("abrir_informe_tabela_socio", JSON.stringify({ person_id: id, ano: S.ano })).catch((e) => {
      S.busy = false;
      toast(String(e));
    });
  }

  function paintIguais() {
    const el = document.querySelector("#im-iguais");
    if (!el) return;
    const grupos = S.meta.padroes_iguais || [];
    if (!grupos.length) {
      el.innerHTML = S.loaded ? `<div class="im-iguais im-iguais-ok">Nenhum padrão igual entre sócios em ${esc(S.ano)}.</div>` : "";
      return;
    }
    el.innerHTML = `
      <details class="im-iguais">
        <summary>⚠ ${grupos.length} padrão(ões) igual(is) entre sócios — clique para ver</summary>
        ${grupos.map((g) => `<div class="im-iguais-item"><strong>${esc(g.descricao)}</strong><br>${esc((g.nomes || g.socios || []).join(", "))}</div>`).join("")}
      </details>`;
  }

  // ---------------------------------------------------------- box do sócio

  function openSocio(id) {
    const s = socioById(id);
    if (!s) return;
    S.openId = id;
    S.edit = null;
    const pendentes = (S.meta.meses_pesca || []).filter((m) => !(s.meses && s.meses[m]));
    S.selMes = pendentes[0] || (S.meta.meses_pesca || ["mar"])[0];
    if (S.modal && S.modal.isConnected) S.modal.remove();
    S.modal = window.sinapescCreateModal(`<div class="im-box" id="im-box"></div>`, "modal-wide im-modal");
    S.modal._onClose = () => {
      S.modal = null;
      S.openId = "";
      S.edit = null;
    };
    paintSocio();
  }

  function closeSocio() {
    if (S.modal && S.modal._close) S.modal._close(false);
  }

  function mesCardHtml(s, m) {
    if (isPiracema(m)) {
      return `
        <div class="im-mes im-mes-pir" aria-disabled="true" title="Não houve pesca — ${esc(piracemaLabel())}">
          <div class="im-mes-nome">${esc(titulo(m))}</div>
          <div class="im-mes-status">${esc(piracemaLabel())}</div>
        </div>`;
    }
    const r = s.meses && s.meses[m];
    const sel = S.selMes === m ? "im-mes-sel" : "";
    if (r) {
      return `
        <button type="button" class="im-mes im-mes-ok ${sel}" data-im-mes="${m}">
          <div class="im-mes-nome">${esc(titulo(m))} <span class="im-check">✓</span></div>
          <div class="im-mes-status">${r.dias} dias · ${r.n_especies} spp · ${r.peso_mes} kg</div>
        </button>`;
    }
    const n = previsto(s, m);
    return `
      <button type="button" class="im-mes im-mes-pend ${sel} ${n === 8 ? "im-mes-oito" : ""}" data-im-mes="${m}">
        <div class="im-mes-nome">${esc(titulo(m))}</div>
        <div class="im-mes-status">${n ? `Pendente — previsto ${n} spp` : "Pendente — gerar REAP"}</div>
      </button>`;
  }

  function paintSocio() {
    const box = document.querySelector("#im-box");
    const s = socioById(S.openId);
    if (!box || !s) return;
    const resumo = s.resumo || {};
    const avisos = resumo.avisos || [];
    const iguais = s.padrao_igual || [];
    const perfil = resumo.perfil || {};
    box.innerHTML = `
      <div class="modal-head im-head">
        <div>
          <div class="im-head-nome">${esc(s.nome)}</div>
          <div class="im-head-meta">CPF ${esc(s.cpf)} · Tel. ${esc(s.telefone || "—")} · ${esc(s.municipio || "sem município")} · Ano ${esc(S.ano)}</div>
        </div>
        <button type="button" class="btn btn-ghost btn-sm" id="im-close">✕</button>
      </div>
      <div class="modal-body">
        <div class="im-meses-grid">
          ${MESES_ORDEM.map((m) => mesCardHtml(s, m)).join("")}
        </div>
        <div class="im-resumo">
          <span><strong>${resumo.gerados || 0}/${resumo.total || totalPesca()}</strong> meses gerados</span>
          <span>Peso acumulado <strong>${resumo.peso_anual || 0} kg</strong> (alvo do ano ${resumo.alvo_peso_anual || "—"} kg · faixa ${S.meta.kg_ano_min || 540}–${S.meta.kg_ano_max || 650})</span>
        </div>
        <div class="im-plano">
          <span class="im-plano-label">Plano de espécies (Mar → Out)</span>
          <span class="im-chips">${planoChipsHtml(s)}</span>
          <button type="button" class="btn btn-ghost btn-sm" id="im-prob-toggle">${S.showProb ? "Ocultar cálculo" : "Ver cálculo de probabilidade"}</button>
        </div>
        ${perfil.favoritas ? `<div class="im-perfil">Perfil do pescador: pesca mais ${esc(perfil.favoritas.join(", "))} · menos ${esc((perfil.menos || []).join(", "))} · melhor fase em ${esc(titulo(perfil.pico))}</div>` : ""}
        ${S.showProb ? probTabelaHtml() : ""}
        ${iguais.length ? `<div class="im-avisos im-avisos-igual">${iguais.map((a) => `<div>= ${esc(a)}</div>`).join("")}</div>` : ""}
        ${avisos.length ? `<div class="im-avisos">${avisos.map((a) => `<div>⚠ ${esc(a)}</div>`).join("")}</div>` : ""}
        <div class="im-detalhe" id="im-detalhe"></div>
      </div>
    `;
    box.querySelector("#im-close")?.addEventListener("click", closeSocio);
    box.querySelector("#im-prob-toggle")?.addEventListener("click", () => {
      S.showProb = !S.showProb;
      paintSocio();
    });
    box.querySelectorAll("[data-im-mes]").forEach((b) => {
      b.addEventListener("click", () => {
        if (S.busy) return;
        S.selMes = b.dataset.imMes;
        S.edit = null;
        paintSocio();
      });
    });
    paintDetalhe();
  }

  function paintDetalhe() {
    const el = document.querySelector("#im-detalhe");
    const s = socioById(S.openId);
    if (!el || !s) return;
    const m = S.selMes;
    if (!m || isPiracema(m)) {
      el.innerHTML = "";
      return;
    }
    const r = s.meses && s.meses[m];
    const dis = S.busy ? "disabled" : "";

    if (!r) {
      el.innerHTML = `
        <div class="im-det-head">
          <div class="im-det-title">${esc(titulo(m))}/${esc(S.ano)} — ainda não gerado</div>
        </div>
        <p class="im-det-help">${previsto(s, m) ? `Pelo plano deste sócio, ${esc(titulo(m))} terá <strong>${previsto(s, m)} espécies</strong> (chance geral ${pct(probMes(m, previsto(s, m)))}). ` : "O 1º mês gerado sorteia o plano de quantidades do ano (4/5/6, e 8 só para alguns sócios). "}
        O cérebro escolhe dias (${S.meta.dias_min || 16}–${S.meta.dias_max || 21}), peixes da época e kg no ritmo próprio do pescador,
        sem repetir os meses já salvos nem o padrão de outros sócios. Valor = preço varejo.</p>
        <div class="im-det-actions">
          <label class="im-inline">Município
            <select id="im-mun">${municipiosOpts(s.municipio_reap)}</select>
          </label>
          <button type="button" class="btn btn-primary" id="im-gerar" ${dis}>${S.busy ? "Gerando…" : `Gerar REAP de ${esc(titulo(m))}`}</button>
        </div>`;
      el.querySelector("#im-gerar")?.addEventListener("click", () => gerar(m, el.querySelector("#im-mun")?.value || ""));
      return;
    }

    if (S.edit) {
      paintEdicao(el, s, m, r);
      return;
    }

    const linhas = (r.especies || []).map((e, i) => `
      <tr>
        <td class="im-num">${i + 1}</td>
        <td>${esc(e.nome)}</td>
        <td class="im-num">${e.kg}</td>
        <td class="im-num">R$ ${fmtMoney(e.valor)}</td>
      </tr>`).join("");
    const alterado = r.atualizado_em && r.atualizado_em !== r.gerado_em;
    el.innerHTML = `
      <div class="im-det-head">
        <div class="im-det-title">${esc(titulo(m))}/${esc(S.ano)} — Houve pesca: SIM</div>
        <div class="im-det-meta">
          Gerado ${esc(r.gerado_em || "")} por ${esc(r.gerado_por || "—")}
          ${alterado ? ` · alterado ${esc(r.atualizado_em)} por ${esc(r.atualizado_por || "—")}` : ""}
        </div>
      </div>
      <div class="im-det-grid">
        <div><span>Dias de pesca</span><strong>${r.dias}</strong></div>
        <div><span>Local</span><strong>${esc(r.local)} · ${esc(r.uf || "BAHIA")}</strong></div>
        <div><span>Município</span><strong>${esc(r.municipio)}</strong></div>
        <div><span>Ambiente / petrecho</span><strong>${esc(r.ambiente)} · ${esc(r.petrecho)}</strong></div>
      </div>
      <table class="im-esp-table">
        <thead><tr><th class="im-num">#</th><th>Espécie</th><th class="im-num">Kg</th><th class="im-num">Valor médio (R$/kg)</th></tr></thead>
        <tbody>${linhas}</tbody>
        <tfoot><tr><td></td><td>Total do mês</td><td class="im-num">${r.peso_mes}</td><td></td></tr></tfoot>
      </table>
      <div class="im-det-actions">
        <button type="button" class="btn btn-outline-dark btn-sm" id="im-copiar" ${dis}>Copiar texto</button>
        <button type="button" class="btn btn-outline-dark btn-sm" id="im-editar" ${dis}>Editar</button>
        <button type="button" class="btn btn-outline-dark btn-sm" id="im-regerar" ${dis}>${S.busy ? "Gerando…" : "Regerar"}</button>
        <button type="button" class="btn btn-outline-dark btn-sm im-btn-danger" id="im-excluir" ${dis}>Excluir mês</button>
      </div>`;
    el.querySelector("#im-copiar")?.addEventListener("click", () => copiar((s.textos || {})[m] || ""));
    el.querySelector("#im-editar")?.addEventListener("click", () => {
      S.edit = {
        dias: r.dias,
        municipio: r.municipio,
        especies: (r.especies || []).map((e) => ({ nome: e.nome, kg: e.kg })),
      };
      paintDetalhe();
    });
    el.querySelector("#im-regerar")?.addEventListener("click", async () => {
      const okConf = await confirmar(
        `Regerar ${titulo(m)}/${S.ano}?`,
        `O REAP atual de ${titulo(m)} de ${s.nome} será substituído por um novo (sem repetir os outros meses). Fica registrado na auditoria.`
      );
      if (okConf) gerar(m, r.municipio);
    });
    el.querySelector("#im-excluir")?.addEventListener("click", async () => {
      const okConf = await confirmar(
        `Excluir ${titulo(m)}/${S.ano}?`,
        `Remove o REAP de ${titulo(m)} de ${s.nome} da planilha. Fica registrado na auditoria.`
      );
      if (!okConf) return;
      S.busy = true;
      paintDetalhe();
      api("excluir_informe_mes", JSON.stringify({ person_id: s.id, ano: S.ano, mes: m }))
        .then((res) => { if (res && res.ok === false) { S.busy = false; paintDetalhe(); failed(res, "Falha ao excluir."); } })
        .catch((e) => { S.busy = false; paintDetalhe(); toast(String(e)); });
    });
  }

  function municipiosOpts(atual) {
    const lista = S.meta.municipios || ["Casa Nova", "Remanso"];
    return lista.map((mu) => `<option ${mu === atual ? "selected" : ""}>${esc(mu)}</option>`).join("");
  }

  function especiesAtivasNomes() {
    return S.meta.especies_ativas || (S.meta.catalogo || []).filter((c) => c.ativo !== false).map((c) => c.nome);
  }

  function especieOpts(atual, usados) {
    const ativas = new Set(especiesAtivasNomes());
    return (S.meta.catalogo || [])
      .filter((c) => ativas.has(c.nome) || c.nome === atual)
      .map((c) => {
        const off = usados.has(c.nome) && c.nome !== atual;
        const marca = ativas.has(c.nome) ? "" : " · fora do cérebro";
        return `<option value="${esc(c.nome)}" ${c.nome === atual ? "selected" : ""} ${off ? "disabled" : ""}>${esc(c.nome)}${marca} (R$ ${fmtMoney(c.preco)})</option>`;
      }).join("");
  }

  function paintEdicao(el, s, m, r) {
    const ed = S.edit;
    const usados = new Set(ed.especies.map((e) => e.nome));
    const kgMin = S.meta.kg_min || 5;
    const kgMax = S.meta.kg_max || 22;
    const total = ed.especies.reduce((a, e) => a + (parseInt(e.kg, 10) || 0), 0);
    const ativasN = especiesAtivasNomes();
    const podeAdd = ed.especies.length < ativasN.length;
    el.innerHTML = `
      <div class="im-det-head">
        <div class="im-det-title">Editar ${esc(titulo(m))}/${esc(S.ano)}</div>
        <div class="im-det-meta">Regras do cérebro: ${S.meta.dias_min || 16}–${S.meta.dias_max || 21} dias · 4/5/6/8 espécies · ${kgMin}–${kgMax} kg inteiros · valor = preço varejo</div>
      </div>
      <div class="im-edit-top">
        <label class="im-inline">Dias de pesca
          <input type="number" id="im-ed-dias" min="${S.meta.dias_min || 16}" max="${S.meta.dias_max || 21}" value="${esc(ed.dias)}" />
        </label>
        <label class="im-inline">Município
          <select id="im-ed-mun">${municipiosOpts(ed.municipio)}</select>
        </label>
      </div>
      <table class="im-esp-table">
        <thead><tr><th class="im-num">#</th><th>Espécie</th><th class="im-num">Kg</th><th></th></tr></thead>
        <tbody>
          ${ed.especies.map((e, i) => `
            <tr>
              <td class="im-num">${i + 1}</td>
              <td><select data-ed-nome="${i}">${especieOpts(e.nome, usados)}</select></td>
              <td class="im-num"><input type="number" data-ed-kg="${i}" min="${kgMin}" max="${kgMax}" value="${esc(e.kg)}" /></td>
              <td>
                <button type="button" class="btn btn-ghost btn-sm" data-ed-up="${i}" title="Subir">↑</button>
                <button type="button" class="btn btn-ghost btn-sm" data-ed-del="${i}" title="Remover">✕</button>
              </td>
            </tr>`).join("")}
        </tbody>
        <tfoot><tr><td></td><td>${ed.especies.length} espécie(s)</td><td class="im-num" id="im-ed-total">${total}</td><td></td></tr></tfoot>
      </table>
      <div class="im-det-actions">
        ${podeAdd ? `<button type="button" class="btn btn-ghost btn-sm" id="im-ed-add">＋ Espécie</button>` : ""}
        <span style="flex:1"></span>
        <button type="button" class="btn btn-outline-dark btn-sm" id="im-ed-cancel">Cancelar</button>
        <button type="button" class="btn btn-primary btn-sm" id="im-ed-save" ${S.busy ? "disabled" : ""}>${S.busy ? "Salvando…" : "Salvar alteração"}</button>
      </div>`;

    const syncFromDom = () => {
      ed.dias = el.querySelector("#im-ed-dias")?.value ?? ed.dias;
      ed.municipio = el.querySelector("#im-ed-mun")?.value || ed.municipio;
      el.querySelectorAll("[data-ed-nome]").forEach((sel) => { ed.especies[+sel.dataset.edNome].nome = sel.value; });
      el.querySelectorAll("[data-ed-kg]").forEach((inp) => { ed.especies[+inp.dataset.edKg].kg = inp.value; });
    };
    el.querySelectorAll("[data-ed-nome]").forEach((sel) => sel.addEventListener("change", () => { syncFromDom(); paintDetalhe(); }));
    // Sem re-render no kg: o "change" dispara no blur e engoliria o clique em Salvar.
    el.querySelectorAll("[data-ed-kg]").forEach((inp) => inp.addEventListener("input", () => {
      syncFromDom();
      const tot = el.querySelector("#im-ed-total");
      if (tot) tot.textContent = ed.especies.reduce((a, e) => a + (parseInt(e.kg, 10) || 0), 0);
    }));
    el.querySelectorAll("[data-ed-del]").forEach((b) => b.addEventListener("click", () => {
      syncFromDom();
      ed.especies.splice(+b.dataset.edDel, 1);
      paintDetalhe();
    }));
    el.querySelectorAll("[data-ed-up]").forEach((b) => b.addEventListener("click", () => {
      syncFromDom();
      const i = +b.dataset.edUp;
      if (i > 0) [ed.especies[i - 1], ed.especies[i]] = [ed.especies[i], ed.especies[i - 1]];
      paintDetalhe();
    }));
    el.querySelector("#im-ed-add")?.addEventListener("click", () => {
      syncFromDom();
      const ativas = new Set(especiesAtivasNomes());
      const livre = (S.meta.catalogo || []).find((c) => ativas.has(c.nome) && !ed.especies.some((e) => e.nome === c.nome));
      if (livre) ed.especies.push({ nome: livre.nome, kg: 10 });
      paintDetalhe();
    });
    el.querySelector("#im-ed-cancel")?.addEventListener("click", () => {
      S.edit = null;
      paintDetalhe();
    });
    el.querySelector("#im-ed-save")?.addEventListener("click", () => {
      syncFromDom();
      S.busy = true;
      paintDetalhe();
      const payload = {
        person_id: s.id,
        ano: S.ano,
        mes: m,
        dias: parseInt(ed.dias, 10),
        municipio: ed.municipio,
        especies: ed.especies.map((e) => ({ nome: e.nome, kg: parseInt(e.kg, 10) })),
      };
      api("salvar_informe_mes", JSON.stringify(payload))
        .then((res) => { if (res && res.ok === false) { S.busy = false; paintDetalhe(); failed(res, "Falha ao salvar."); } })
        .catch((e) => { S.busy = false; paintDetalhe(); toast(String(e)); });
    });
  }

  function gerar(m, municipio) {
    const s = socioById(S.openId);
    if (!s || S.busy) return;
    S.busy = true;
    paintDetalhe();
    api("gerar_informe_mes", JSON.stringify({ person_id: s.id, ano: S.ano, mes: m, municipio: municipio || "" }))
      .then((res) => { if (res && res.ok === false) { S.busy = false; paintDetalhe(); failed(res, "Falha ao gerar."); } })
      .catch((e) => { S.busy = false; paintDetalhe(); toast(String(e)); });
  }

  function confirmar(title, text) {
    if (typeof window.sinapescConfirm === "function") return window.sinapescConfirm(title, text);
    return Promise.resolve(window.confirm(`${title}\n\n${text}`));
  }

  function copiar(texto) {
    if (!texto) return;
    const fallback = () => {
      const ta = document.createElement("textarea");
      ta.value = texto;
      document.body.appendChild(ta);
      ta.select();
      try { document.execCommand("copy"); } catch (_e) { /* ignore */ }
      ta.remove();
      toast("Texto do REAP copiado.");
    };
    if (navigator.clipboard && navigator.clipboard.writeText) {
      navigator.clipboard.writeText(texto).then(() => toast("Texto do REAP copiado."), fallback);
    } else fallback();
  }

  // -------------------------------------------------------------- auditoria

  const ACAO_LABEL = {
    gerar_informe: "Gerou",
    regerar_informe: "Regerou",
    editar_informe: "Alterou",
    excluir_informe: "Excluiu",
    abrir_tabela_informe: "Abriu tabela",
    abrir_tabela_socio: "Tabela sócio",
    config_especies_informe: "Peixes do cérebro",
  };

  function paintAuditoria() {
    const list = document.querySelector("#im-aud-list");
    const hint = document.querySelector("#im-aud-hint");
    if (!list) return;
    const q = S.audSearch.trim().toLowerCase();
    let items = S.auditoria || [];
    if (S.audAcao) items = items.filter((e) => e.acao === S.audAcao);
    if (q) {
      items = items.filter((e) => {
        const blob = `${e.em} ${e.usuario} ${e.acao} ${e.detalhe} ${e.nome} ${e.ano} ${titulo(e.mes)}`.toLowerCase();
        return blob.includes(q);
      });
    }
    if (hint) hint.textContent = `${items.length} registro(s) · aba InformeAuditoria da planilha REAP`;
    if (!items.length) {
      list.innerHTML = `<div class="empty-msg">Nenhum REAP gerado ou alterado ainda.</div>`;
      return;
    }
    list.innerHTML = items.map((e) => `
      <div class="im-audit-card im-acao-${esc(e.acao)}">
        <div class="im-audit-meta">
          <span class="im-audit-tag">${esc(ACAO_LABEL[e.acao] || e.acao)}</span>
          ${esc(e.em || "")} · <strong>${esc(e.usuario || "(sem usuário)")}</strong>
          ${e.mes ? ` · ${esc(titulo(e.mes))}/${esc(e.ano)}` : ""}
        </div>
        <div class="im-audit-text">${esc(e.detalhe || "")}</div>
      </div>`).join("");
  }

  // ---------------------------------------------------------------- eventos

  function aplicarSocio(socio) {
    if (!socio) return;
    const i = S.socios.findIndex((x) => x.id === socio.id);
    if (i >= 0) S.socios[i] = socio;
    else S.socios.push(socio);
  }

  function aposMudanca(r, okMsg) {
    S.busy = false;
    if (!r.ok) {
      paintDetalhe();
      failed(r, "Falha no Informe Mensal.");
      return;
    }
    const d = r.data || {};
    if (d.socio && Array.isArray(d.padroes_iguais)) {
      d.socio.padrao_igual = d.padroes_iguais.map((g) => g.descricao);
      d.padroes_iguais.forEach((g) => toast(`Padrão igual: ${g.descricao}`, 5200));
    } else if (d.socio) {
      const atual = socioById(d.socio.id);
      d.socio.padrao_igual = (atual && atual.padrao_igual) || [];
    }
    if (Number(d.ano) === Number(S.ano)) aplicarSocio(d.socio);
    S.edit = null;
    if (okMsg) toast(okMsg);
    (d.avisos || []).forEach((a) => toast(`Cérebro: ${a}`, 5200));
    if (onScreen()) paintTable();
    if (S.openId && d.socio && d.socio.id === S.openId) paintSocio();
  }

  function wire() {
    if (!window.AppEvents) return;
    window.AppEvents.on("informe_lista", (r) => {
      S.loading = false;
      if (!r.ok) {
        failed(r, "Falha ao carregar o Informe Mensal.");
        if (onScreen()) paintTable();
        return;
      }
      const d = r.data || {};
      S.socios = d.socios || [];
      S.meta = { ...d };
      delete S.meta.socios;
      S.ano = Number(d.ano) || S.ano;
      S.loaded = true;
      if (onScreen() && S.tab === "socios") render();
      if (S.openId) paintSocio();
    });
    window.AppEvents.on("informe_gerado", (r) => {
      const d = r.data || {};
      aposMudanca(r, r.ok ? `REAP de ${titulo(d.mes)}/${d.ano} ${d.regerado ? "regerado" : "gerado"} e salvo na planilha.` : "");
    });
    window.AppEvents.on("informe_salvo", (r) => {
      const d = r.data || {};
      aposMudanca(r, r.ok ? (d.sem_mudanca ? "Nada mudou." : `Alteração de ${titulo(d.mes)}/${d.ano} salva.`) : "");
    });
    window.AppEvents.on("informe_excluido", (r) => {
      const d = r.data || {};
      aposMudanca(r, r.ok ? `REAP de ${titulo(d.mes)}/${d.ano} excluído.` : "");
    });
    window.AppEvents.on("informe_auditoria", (r) => {
      if (!r.ok) {
        failed(r, "Falha ao carregar auditoria.");
        return;
      }
      S.auditoria = (r.data && r.data.itens) || [];
      if (onScreen() && S.tab === "auditoria") paintAuditoria();
    });
    window.AppEvents.on("informe_tabela", (r) => {
      S.busy = false;
      if (!r.ok) {
        failed(r, "Falha ao gerar a tabela do Informe Mensal.");
        return;
      }
      const d = r.data || {};
      if (d.path) {
        api("open_path", d.path).catch(() => {});
        toast(
          `Tabela de ${d.ano || S.ano} aberta no navegador (${d.com_meses || 0} sócio(s) com mês preenchido).`,
          5200
        );
      }
    });
    window.AppEvents.on("informe_tabela_socio", (r) => {
      S.busy = false;
      if (!r.ok) {
        failed(r, "Falha ao gerar a tabela do sócio.");
        return;
      }
      const d = r.data || {};
      if (d.path) {
        api("open_path", d.path).catch(() => {});
        toast(
          `Tabela de ${d.nome || "sócio"} aberta (${d.meses || 0} mês(es) preenchido(s)).`,
          5200
        );
      }
    });
    window.AppEvents.on("informe_especies_salvas", (r) => {
      S.busy = false;
      if (!r.ok) {
        failed(r, "Falha ao salvar peixes do cérebro.");
        return;
      }
      const d = r.data || {};
      S.meta.especies_ativas = d.especies_ativas || [];
      S.meta.catalogo = d.catalogo || S.meta.catalogo;
      S.meta.contagens = d.contagens || S.meta.contagens;
      S.meta.permite_8 = !!d.permite_8;
      if (d.probabilidades) S.meta.probabilidades = d.probabilidades;
      toast(
        `Peixes do cérebro salvos (${(d.especies_ativas || []).length}): ${(d.especies_ativas || []).join(", ")}`,
        5200
      );
      if (S.modalPeixes && S.modalPeixes._close) S.modalPeixes._close(false);
      if (onScreen() && S.tab === "socios") paintTable();
    });
  }

  wire();

  window.SinapescInforme = { render, load, openSocio };
})();
