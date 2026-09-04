/* Consulta RGP — funções extras (4/3/2/1) — arquivo separado de app.js */
(function () {
  "use strict";

  function api(method, ...args) {
    if (!window.pywebview || !window.pywebview.api) {
      return Promise.reject(new Error("API Python indisponível"));
    }
    return window.pywebview.api[method](...args);
  }

  function toast(msg, ms) {
    if (typeof window.sinapescToast === "function") {
      window.sinapescToast(msg, ms);
      return;
    }
    const root = document.querySelector("#toast-root");
    if (!root) return;
    const el = document.createElement("div");
    el.className = "toast";
    el.textContent = msg;
    root.appendChild(el);
    setTimeout(() => el.remove(), ms || 3200);
  }

  function esc(s) {
    return String(s ?? "")
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;")
      .replace(/"/g, "&quot;");
  }

  function getState() {
    return window.SinapescRgpState || null;
  }

  function openModal(html, className) {
    if (typeof window.sinapescCreateModal === "function") {
      return window.sinapescCreateModal(html, className || "");
    }
    const backdrop = document.createElement("div");
    backdrop.className = "modal-backdrop";
    backdrop.innerHTML = `<div class="modal ${className || ""}">${html}</div>`;
    document.body.appendChild(backdrop);
    backdrop.addEventListener("click", (e) => {
      if (e.target === backdrop) backdrop.remove();
    });
    backdrop.querySelectorAll("[data-modal-close]").forEach((b) => {
      b.addEventListener("click", () => backdrop.remove());
    });
    return backdrop;
  }

  /** Função 4 — modal Reconsultar vencidos */
  function openVencidosModal() {
    const st = getState();
    const dias = (st && st.consultaRgpDiasVencidos) || 30;
    const backdrop = openModal(`
      <div class="modal-head">Reconsultar vencidos</div>
      <div class="modal-body">
        <p class="page-sub">Consulta só quem está <strong>Não consultado</strong> ou com última consulta há mais de N dias.</p>
        <label>Dias sem consulta
          <input type="number" id="rgp-venc-dias" min="1" max="365" value="${esc(dias)}" style="width:90px;margin-left:8px" />
        </label>
        <p class="page-sub" id="rgp-venc-status">Clique em «Listar» para ver quantos entram.</p>
      </div>
      <div class="modal-foot">
        <button type="button" class="btn btn-outline-dark" data-modal-close="">Cancelar</button>
        <button type="button" class="btn btn-ghost" id="rgp-venc-listar">Listar</button>
        <button type="button" class="btn btn-primary" id="rgp-venc-start" disabled>Consultar vencidos</button>
      </div>
    `);
    let ids = [];
    const statusEl = backdrop.querySelector("#rgp-venc-status");
    const startBtn = backdrop.querySelector("#rgp-venc-start");
    window._rgpVencidosModal = { backdrop, statusEl, startBtn, setIds: (v) => { ids = v || []; } };

    backdrop.querySelector("#rgp-venc-listar").addEventListener("click", async () => {
      const d = parseInt(backdrop.querySelector("#rgp-venc-dias").value, 10) || 30;
      if (st) st.consultaRgpDiasVencidos = d;
      statusEl.textContent = "Listando…";
      try {
        const r = await api("listar_consulta_rgp_vencidos", d);
        if (r && r.ok === false && !r.pending) {
          statusEl.textContent = r.error || "Falha ao listar.";
          return;
        }
        statusEl.textContent = "Aguardando lista…";
      } catch (_e) {
        statusEl.textContent = "Erro ao listar.";
      }
    });

    const onClose = () => {
      if (window._rgpVencidosModal && window._rgpVencidosModal.backdrop === backdrop) {
        window._rgpVencidosModal = null;
      }
    };
    backdrop.addEventListener("click", (e) => {
      if (e.target === backdrop) onClose();
    });
    backdrop.querySelectorAll("[data-modal-close]").forEach((b) => {
      b.addEventListener("click", onClose);
    });

    startBtn.addEventListener("click", async () => {
      if (!ids.length) {
        toast("Nenhum vencido para consultar.");
        return;
      }
      backdrop.remove();
      if (typeof window.sinapescOpenConsultaAutomatica === "function") {
        window.sinapescOpenConsultaAutomatica({ todos: false, ids });
      } else {
        toast(`Iniciando ${ids.length} consulta(s)…`);
        api("consultar_rgp_lote", JSON.stringify({ todos: false, ids, max_falhas_seguidas: 3 }));
      }
    });
  }

  /** Função 3 — modal Exportar (CSV + HTML) */
  function openExportModal() {
    openRelatorioHtmlModal({ modo: "export" });
  }

  function selectedIdsFromState(st) {
    return Object.keys((st && st.consultaRgpSelectedIds) || {}).filter(
      (id) => st.consultaRgpSelectedIds[id]
    );
  }

  function filteredIdsFromState(st) {
    const q = String((st && st.consultaRgpSearch) || "").trim().toLowerCase();
    const digits = q.replace(/\D/g, "");
    const filtro = (st && st.consultaRgpFiltro) || "";
    return ((st && st.consultaRgpItens) || [])
      .filter((r) => {
        if (filtro) {
          const a = String(r.situacao_rgp || "").trim().toLowerCase();
          const b = filtro.toLowerCase();
          if (a !== b && !(b.startsWith("aguardando atualiza") && a.startsWith("aguardando atualiza"))) {
            return false;
          }
        }
        if (!q) return true;
        const blob = [r.nome, r.cpf, r.telefone, r.municipio, r.observacao]
          .map((x) => String(x || "").toLowerCase()).join(" ");
        if (blob.includes(q)) return true;
        if (digits.length >= 3 && String(r.cpf || "").includes(digits)) return true;
        return false;
      })
      .map((r) => r.id)
      .filter(Boolean);
  }

  function previewCountLocal(st, opts) {
    const itens = (st && st.consultaRgpItens) || [];
    let list = itens.slice();
    if (opts.escopo === "selecionados") {
      const idset = new Set(opts.ids || []);
      list = list.filter((r) => idset.has(r.id));
    } else if (opts.escopo === "filtrados") {
      const idset = new Set(opts.ids || filteredIdsFromState(st));
      list = list.filter((r) => idset.has(r.id));
    }
    if (opts.municipios && opts.municipios.length) {
      const mset = opts.municipios.map((m) => m.toLowerCase());
      list = list.filter((r) => {
        const mun = String(r.municipio || "").trim().toLowerCase();
        return mset.some((m) => mun === m || mun.includes(m));
      });
    }
    if (opts.situacoes && opts.situacoes.length) {
      const sset = opts.situacoes.map((s) => s.toLowerCase());
      list = list.filter((r) => {
        const a = String(r.situacao_rgp || "").trim().toLowerCase();
        return sset.some((b) => a === b || (b.startsWith("aguardando atualiza") && a.startsWith("aguardando atualiza")));
      });
    }
    if (opts.busca) {
      const q = opts.busca.toLowerCase();
      const digits = q.replace(/\D/g, "");
      list = list.filter((r) => {
        const blob = [r.nome, r.cpf, r.telefone, r.municipio, r.observacao]
          .map((x) => String(x || "").toLowerCase()).join(" ");
        if (blob.includes(q)) return true;
        if (digits.length >= 3 && String(r.cpf || "").includes(digits)) return true;
        return false;
      });
    }
    if (opts.com_senha === "com") {
      list = list.filter((r) => String(r.govbr_senha || "").trim());
    } else if (opts.com_senha === "sem") {
      list = list.filter((r) => !String(r.govbr_senha || "").trim());
    }
    // datas: preview aproximado (só YYYY-MM-DD no campo)
    if (opts.ultima_de || opts.ultima_ate) {
      list = list.filter((r) => {
        const raw = String(r.ultima_consulta_em || "").trim();
        if (!raw) return false;
        const day = raw.slice(0, 10).replace(/\//g, "-");
        // aceita DD/MM/YYYY ou YYYY-MM-DD
        let iso = day;
        const m = raw.match(/^(\d{2})\/(\d{2})\/(\d{4})/);
        if (m) iso = `${m[3]}-${m[2]}-${m[1]}`;
        if (opts.ultima_de && iso < opts.ultima_de) return false;
        if (opts.ultima_ate && iso > opts.ultima_ate) return false;
        return true;
      });
    }
    return list.length;
  }

  /** Relatório HTML com seleção de escopo, filtros e colunas */
  function openRelatorioHtmlModal(opts) {
    opts = opts || {};
    const modoExport = opts.modo === "export";
    const st = getState();
    const itens = (st && st.consultaRgpItens) || [];
    const selIds = selectedIdsFromState(st);
    const filtIds = filteredIdsFromState(st);
    const munis = [...new Set(itens.map((r) => (r.municipio || "").trim()).filter(Boolean))]
      .sort((a, b) => a.localeCompare(b, "pt-BR"));
    const sits = [
      "Ativo",
      "Aguardando análise",
      "Finalizada",
      "Rascunho",
      "Aguardando atualização",
      "Não consultado",
      "Suspenso",
      "Cancelado",
      "Em análise",
    ];
    const colsDefault = modoExport
      ? ["nome", "cpf", "telefone", "municipio", "situacao", "ultima_consulta", "observacao"]
      : ["nome", "cpf", "municipio", "telefone", "situacao", "govbr_senha"];
    const colDefs = [
      ["nome", "Nome"],
      ["cpf", "CPF"],
      ["municipio", "Município"],
      ["telefone", "Telefone"],
      ["situacao", "Situação RGP"],
      ["govbr_senha", "Senha Gov.br"],
      ["ultima_consulta", "Última consulta"],
      ["observacao", "Observação"],
      ["email", "E-mail"],
      ["uf", "UF"],
      ["codigo_rgp", "Código RGP"],
    ];
    const escopoInicial = selIds.length ? "selecionados" : "todos";

    const backdrop = openModal(`
      <div class="modal-head">${modoExport ? "Exportar Consulta RGP" : "Relatório HTML — Consulta RGP"}</div>
      <div class="modal-body rgp-relatorio-body">
        <p class="page-sub">Escolha o escopo, filtros e colunas. O contador mostra quantos registros entrarão no arquivo.</p>

        <div class="rgp-rel-section">
          <div class="rgp-rel-label">Escopo</div>
          <div class="rgp-rel-radios">
            <label><input type="radio" name="rgp-rel-escopo" value="todos" ${escopoInicial === "todos" ? "checked" : ""} /> Todos (${itens.length})</label>
            <label><input type="radio" name="rgp-rel-escopo" value="selecionados" ${escopoInicial === "selecionados" ? "checked" : ""} ${selIds.length ? "" : "disabled"} /> Selecionados na tabela (${selIds.length})</label>
            <label><input type="radio" name="rgp-rel-escopo" value="filtrados" /> Lista filtrada da tela (${filtIds.length})</label>
          </div>
        </div>

        <div class="rgp-rel-grid">
          <label>Busca (nome / CPF / telefone)
            <input type="search" id="rgp-rel-busca" placeholder="Opcional" />
          </label>
          <label>Senha Gov.br
            <select id="rgp-rel-senha">
              <option value="">Todas</option>
              <option value="com">Somente com senha</option>
              <option value="sem">Somente sem senha</option>
            </select>
          </label>
          <label>Última consulta de
            <input type="date" id="rgp-rel-de" />
          </label>
          <label>até
            <input type="date" id="rgp-rel-ate" />
          </label>
        </div>

        <div class="rgp-rel-section">
          <div class="rgp-rel-label">Situações <button type="button" class="rgp-link" id="rgp-rel-sit-all">todas</button> · <button type="button" class="rgp-link" id="rgp-rel-sit-none">limpar</button></div>
          <div class="rgp-rel-checks" id="rgp-rel-sits">
            ${sits.map((s) => `<label><input type="checkbox" class="rgp-rel-sit" value="${esc(s)}" /> ${esc(s)}</label>`).join("")}
          </div>
        </div>

        <div class="rgp-rel-section">
          <div class="rgp-rel-label">Municípios <button type="button" class="rgp-link" id="rgp-rel-mun-all">todos</button> · <button type="button" class="rgp-link" id="rgp-rel-mun-none">limpar</button></div>
          <div class="rgp-rel-checks rgp-rel-munis" id="rgp-rel-muns">
            ${munis.length
              ? munis.map((m) => `<label><input type="checkbox" class="rgp-rel-mun" value="${esc(m)}" /> ${esc(m)}</label>`).join("")
              : "<span class=\"page-sub\">Nenhum município cadastrado.</span>"}
          </div>
        </div>

        <div class="rgp-rel-section">
          <div class="rgp-rel-label">Colunas do relatório</div>
          <div class="rgp-rel-checks" id="rgp-rel-cols">
            ${colDefs.map(([k, lab]) => `
              <label><input type="checkbox" class="rgp-rel-col" value="${k}" ${colsDefault.includes(k) ? "checked" : ""} /> ${esc(lab)}</label>
            `).join("")}
          </div>
        </div>

        <label class="rgp-rel-print">
          <input type="checkbox" id="rgp-rel-print" checked />
          Abrir diálogo de impressão automaticamente
        </label>

        <p class="rgp-rel-preview" id="rgp-rel-status">Prévia: — registro(s)</p>
      </div>
      <div class="modal-foot">
        <button type="button" class="btn btn-outline-dark" data-modal-close="">Cancelar</button>
        <button type="button" class="btn btn-primary" id="rgp-rel-go">${modoExport ? "Exportar CSV+HTML" : "Gerar relatório HTML"}</button>
      </div>
    `, "modal-wide modal-rgp-relatorio");

    function readOpts() {
      const escopo = (backdrop.querySelector('input[name="rgp-rel-escopo"]:checked') || {}).value || "todos";
      let ids = [];
      if (escopo === "selecionados") ids = selIds.slice();
      if (escopo === "filtrados") ids = filtIds.slice();
      const situacoes = [...backdrop.querySelectorAll(".rgp-rel-sit:checked")].map((el) => el.value);
      const municipios = [...backdrop.querySelectorAll(".rgp-rel-mun:checked")].map((el) => el.value);
      const colunas = [...backdrop.querySelectorAll(".rgp-rel-col:checked")].map((el) => el.value);
      return {
        escopo,
        ids,
        busca: (backdrop.querySelector("#rgp-rel-busca").value || "").trim(),
        com_senha: backdrop.querySelector("#rgp-rel-senha").value || "",
        ultima_de: backdrop.querySelector("#rgp-rel-de").value || "",
        ultima_ate: backdrop.querySelector("#rgp-rel-ate").value || "",
        situacoes,
        municipios,
        colunas,
        auto_print: !!backdrop.querySelector("#rgp-rel-print").checked,
      };
    }

    function refreshPreview() {
      const o = readOpts();
      const n = previewCountLocal(st, o);
      const status = backdrop.querySelector("#rgp-rel-status");
      if (status) {
        status.textContent = `Prévia: ${n} registro(s) com os filtros atuais`;
      }
      const go = backdrop.querySelector("#rgp-rel-go");
      if (go) go.disabled = n === 0 || !(o.colunas && o.colunas.length);
    }

    backdrop.querySelectorAll("input, select").forEach((el) => {
      el.addEventListener("change", refreshPreview);
      el.addEventListener("input", refreshPreview);
    });
    backdrop.querySelector("#rgp-rel-sit-all")?.addEventListener("click", () => {
      backdrop.querySelectorAll(".rgp-rel-sit").forEach((c) => { c.checked = true; });
      refreshPreview();
    });
    backdrop.querySelector("#rgp-rel-sit-none")?.addEventListener("click", () => {
      backdrop.querySelectorAll(".rgp-rel-sit").forEach((c) => { c.checked = false; });
      refreshPreview();
    });
    backdrop.querySelector("#rgp-rel-mun-all")?.addEventListener("click", () => {
      backdrop.querySelectorAll(".rgp-rel-mun").forEach((c) => { c.checked = true; });
      refreshPreview();
    });
    backdrop.querySelector("#rgp-rel-mun-none")?.addEventListener("click", () => {
      backdrop.querySelectorAll(".rgp-rel-mun").forEach((c) => { c.checked = false; });
      refreshPreview();
    });

    refreshPreview();

    backdrop.querySelector("#rgp-rel-go")?.addEventListener("click", async () => {
      const o = readOpts();
      if (!o.colunas.length) {
        toast("Selecione ao menos uma coluna.");
        return;
      }
      if (o.escopo === "selecionados" && !o.ids.length) {
        toast("Nenhum sócio selecionado na tabela.");
        return;
      }
      const de = o.ultima_de;
      const ate = o.ultima_ate;
      if (de && ate && de > ate) {
        toast("Data «de» não pode ser maior que «até».");
        return;
      }
      const status = backdrop.querySelector("#rgp-rel-status");
      const go = backdrop.querySelector("#rgp-rel-go");
      if (status) status.textContent = modoExport ? "Exportando…" : "Gerando relatório HTML…";
      if (go) go.disabled = true;
      const payload = {
        escopo: o.escopo,
        ids: o.ids.length ? o.ids : undefined,
        busca: o.busca || undefined,
        municipios: o.municipios.length ? o.municipios : undefined,
        situacoes: o.situacoes.length ? o.situacoes : undefined,
        ultima_de: o.ultima_de || undefined,
        ultima_ate: o.ultima_ate || undefined,
        com_senha: o.com_senha || undefined,
        colunas: o.colunas,
        auto_print: o.auto_print,
        abrir_html: true,
        modo_geral: !modoExport,
      };
      try {
        const method = modoExport ? "exportar_consulta_rgp" : "relatorio_geral_consulta_rgp";
        const r = await api(method, JSON.stringify(payload));
        if (r && r.ok === false && !r.pending) {
          toast(r.error || "Falha ao gerar.");
          if (status) status.textContent = r.error || "Erro.";
          if (go) go.disabled = false;
        } else {
          backdrop.remove();
        }
      } catch (_e) {
        toast("Erro ao gerar relatório.");
        if (go) go.disabled = false;
      }
    });
  }

  function openRelatorioGeral() {
    openRelatorioHtmlModal({ modo: "html" });
  }

  /** Correção em lote — nome, CPF, telefone, município, observação + senha Gov.br por sócio */
  function openEditarLoteModal(opts) {
    opts = opts || {};
    const st = getState();
    if (!st) {
      toast("Consulta RGP não carregada.");
      return;
    }
    const formatNome = opts.formatNome || ((v) => String(v || "").trim());
    const formatCpf = opts.formatCpf || ((v) => String(v || "").trim());
    const bindNomeMask = opts.bindNomeMask || (() => {});
    const bindCpfMask = opts.bindCpfMask || (() => {});

    const selectedIds = opts.selectedIds || Object.keys(st.consultaRgpSelectedIds || {}).filter((id) => st.consultaRgpSelectedIds[id]);
    let regs = [];
    if (selectedIds.length) {
      const idset = new Set(selectedIds);
      regs = (st.consultaRgpItens || []).filter((r) => idset.has(r.id));
    } else {
      const q = (st.consultaRgpSearch || "").trim().toLowerCase();
      const digits = q.replace(/\D/g, "");
      const filtro = st.consultaRgpFiltro || "";
      regs = (st.consultaRgpItens || []).filter((r) => {
        if (filtro) {
          const a = String(r.situacao_rgp || "").trim().toLowerCase();
          const b = filtro.toLowerCase();
          if (a !== b && !(b.startsWith("aguardando atualiza") && a.startsWith("aguardando atualiza"))) {
            return false;
          }
        }
        if (!q) return true;
        const blob = [r.nome, r.cpf, r.telefone, r.municipio, r.observacao]
          .map((x) => String(x || "").toLowerCase()).join(" ");
        if (blob.includes(q)) return true;
        if (digits.length >= 3 && String(r.cpf || "").includes(digits)) return true;
        return false;
      });
    }

    const MAX = 200;
    if (!regs.length) {
      toast("Selecione sócios na tabela ou use busca/filtro antes de corrigir em lote.");
      return;
    }
    if (regs.length > MAX) {
      toast(`Muitos registros (${regs.length}). Selecione até ${MAX} ou refine o filtro.`);
      return;
    }

    const origem = selectedIds.length
      ? `${regs.length} selecionado(s)`
      : `${regs.length} da lista filtrada`;

    const backdrop = openModal(`
      <div class="modal-head">Corrigir em lote — Consulta RGP</div>
      <div class="modal-body rgp-edit-lote-body">
        <p class="page-sub">Edite nome, CPF, número, município, observação e <strong>senha Gov.br de cada sócio</strong>. Gravação em lote (anti-cota). ${esc(origem)}.</p>
        <div class="rgp-edit-lote-head">
          <span>Nome</span><span>CPF</span><span>Município</span><span>Número</span><span>Observação</span><span>Senha Gov.br</span>
        </div>
        <div class="rgp-edit-lote-rows" id="rgp-el-rows"></div>
        <p class="page-sub" id="rgp-el-status"></p>
      </div>
      <div class="modal-foot">
        <button type="button" class="btn btn-outline-dark" data-modal-close="">Cancelar</button>
        <button type="button" class="btn btn-ghost btn-sm" id="rgp-el-toggle-senhas">Mostrar senhas</button>
        <button type="button" class="btn btn-primary" id="rgp-el-save">Salvar correções</button>
      </div>
    `, "modal-wide modal-rgp-edit-lote");

    const host = backdrop.querySelector("#rgp-el-rows");
    const statusEl = backdrop.querySelector("#rgp-el-status");
    const saveBtn = backdrop.querySelector("#rgp-el-save");

    regs.forEach((r) => {
      const row = document.createElement("div");
      row.className = "rgp-edit-lote-row";
      row.dataset.id = r.id;
      row.innerHTML = `
        <input class="el-nome" value="${esc(formatNome(r.nome || ""))}" placeholder="Nome" />
        <input class="el-cpf" value="${esc(formatCpf(r.cpf_formatado || r.cpf || ""))}" placeholder="000.000.000-00" maxlength="14" />
        <input class="el-mun" value="${esc(r.municipio || "")}" placeholder="Município" />
        <input class="el-tel" value="${esc(r.telefone || "")}" placeholder="Número" />
        <input class="el-obs" value="${esc(r.observacao || "")}" placeholder="Observação" />
        <input class="el-govbr" type="password" value="${esc(r.govbr_senha || "")}" placeholder="Senha Gov.br" autocomplete="new-password" />
      `;
      host.appendChild(row);
      bindNomeMask(row.querySelector(".el-nome"));
      bindCpfMask(row.querySelector(".el-cpf"));
    });

    statusEl.textContent = `${regs.length} linha(s) prontas para edição.`;

    backdrop.querySelector("#rgp-el-toggle-senhas")?.addEventListener("click", (e) => {
      const btn = e.currentTarget;
      const inputs = [...host.querySelectorAll(".el-govbr")];
      const show = inputs.some((inp) => inp.type === "password");
      inputs.forEach((inp) => { inp.type = show ? "text" : "password"; });
      btn.textContent = show ? "Ocultar senhas" : "Mostrar senhas";
    });

    saveBtn.addEventListener("click", async () => {
      const itens = [...host.querySelectorAll(".rgp-edit-lote-row")].map((row) => ({
        id: row.dataset.id,
        nome: formatNome(row.querySelector(".el-nome").value),
        cpf: row.querySelector(".el-cpf").value,
        municipio: (row.querySelector(".el-mun").value || "").trim(),
        telefone: (row.querySelector(".el-tel").value || "").trim(),
        observacao: (row.querySelector(".el-obs").value || "").trim(),
        govbr_senha: (row.querySelector(".el-govbr").value || "").trim(),
      })).filter((r) => r.id && (r.nome || r.cpf));

      if (!itens.length) {
        toast("Nenhuma linha válida.");
        return;
      }
      saveBtn.disabled = true;
      statusEl.textContent = `Salvando ${itens.length} correção(ões)…`;
      try {
        const r = await api("editar_lote_consulta_rgp", JSON.stringify({ itens }));
        if (r && r.ok === false && !r.pending) {
          toast(r.error || "Falha ao salvar.");
          statusEl.textContent = r.error || "Erro.";
          saveBtn.disabled = false;
        } else {
          backdrop.remove();
        }
      } catch (_e) {
        toast("Erro ao salvar correções.");
        statusEl.textContent = "Erro de envio.";
        saveBtn.disabled = false;
      }
    });
  }

  function markAlertaRows(alertas) {
    const st = getState();
    if (!st) return;
    st.consultaRgpAlertas = alertas || [];
    const ids = new Set((alertas || []).map((a) => a.id).filter(Boolean));
    document.querySelectorAll(".rgp-table tbody tr[data-id]").forEach((tr) => {
      tr.classList.toggle("rgp-alerta-sit", ids.has(tr.dataset.id));
    });
    (alertas || []).slice(0, 5).forEach((a) => {
      if (a.mensagem) toast(a.mensagem, 7000);
    });
  }

  function toolbarButtonsHtml() {
    return `
      <button type="button" class="rgp-btn rgp-btn-ghost" id="rgp-vencidos" title="Não consultado ou consulta antiga">↻ Vencidos</button>
      <button type="button" class="rgp-btn rgp-btn-ghost" id="rgp-relatorio-geral" title="Relatório HTML com filtros, seleção e colunas">☰ Relatório HTML</button>
      <button type="button" class="rgp-btn rgp-btn-ghost" id="rgp-exportar">⇩ Exportar</button>
    `;
  }

  function bindToolbar() {
    document.getElementById("rgp-vencidos")?.addEventListener("click", openVencidosModal);
    document.getElementById("rgp-exportar")?.addEventListener("click", openExportModal);
    document.getElementById("rgp-relatorio-geral")?.addEventListener("click", openRelatorioGeral);
  }

  function wireFuncoesEvents() {
    if (!window.AppEvents || window.__rgpFuncoesWired) return;
    window.__rgpFuncoesWired = true;

    window.AppEvents.on("consulta_rgp_export", (r) => {
      if (r.ok) {
        toast(r.data?.mensagem || "Exportação concluída.", 5000);
        if (r.data?.csv_path) toast(`CSV: ${r.data.csv_path}`, 6000);
      } else toast(r.error || "Falha na exportação.");
    });

    window.AppEvents.on("consulta_rgp_vencidos", (r) => {
      const m = window._rgpVencidosModal;
      if (!m || !m.backdrop || !m.backdrop.isConnected) return;
      if (!r.ok) {
        m.statusEl.textContent = r.error || "Falha.";
        m.startBtn.disabled = true;
        return;
      }
      const ids = r.data?.ids || [];
      m.setIds(ids);
      const n = r.data?.total || 0;
      const mins = r.data?.minutos_estimados || 0;
      let txt = r.data?.mensagem || `${n} vencido(s).`;
      if (mins) txt += ` Estimativa: ~${mins} min.`;
      m.statusEl.textContent = txt;
      m.startBtn.disabled = n === 0;
      const st = getState();
      if (st) st._rgpVencidosIds = ids;
    });

    window.AppEvents.on("consulta_rgp_lote_progress", (p) => {
      if (p && p.alerta) {
        const st = getState();
        const list = (st && st.consultaRgpAlertas) || [];
        list.push(p.alerta);
        if (st) st.consultaRgpAlertas = list;
        if (p.alerta.mensagem) toast(p.alerta.mensagem, 7000);
        markAlertaRows(list);
      }
      if (p && p.fase === "pausa") {
        toast(p.mensagem || "Fila pausada por falhas seguidas.", 8000);
      }
    });

    // reforça handler de fim de lote (alertas + CSV erros)
    window.AppEvents.on("consulta_rgp_consulta_lote", (r) => {
      if (!r.ok) return;
      if (r.data?.alertas?.length) {
        markAlertaRows(r.data.alertas);
      }
      if (r.data?.csv_erros_path) {
        toast(`Erros exportados: ${r.data.csv_erros_path}`, 8000);
      }
      if (r.data?.pausado_por_falhas) {
        toast("Fila pausada após falhas seguidas. Retome quando o MPA estabilizar.", 8000);
      }
    });
  }

  window.SinapescRgpFuncoes = {
    openVencidosModal,
    openExportModal,
    openRelatorioGeral,
    openRelatorioHtmlModal,
    openEditarLoteModal,
    toolbarButtonsHtml,
    bindToolbar,
    wireFuncoesEvents,
    markAlertaRows,
  };

  // auto-wire quando o DOM estiver pronto
  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", wireFuncoesEvents);
  } else {
    wireFuncoesEvents();
  }
})();
