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

  /** Função 3 — modal Exportar */
  function openExportModal() {
    const st = getState();
    const sits = [
      "", "Ativo", "Aguardando análise", "Finalizada", "Rascunho", "Aguardando atualização",
    ];
    const munis = [...new Set(((st && st.consultaRgpItens) || []).map((r) => (r.municipio || "").trim()).filter(Boolean))]
      .sort((a, b) => a.localeCompare(b, "pt-BR"));
    const backdrop = openModal(`
      <div class="modal-head">Exportar Consulta RGP</div>
      <div class="modal-body">
        <p class="page-sub">CSV + HTML com filtros, ou relatório geral (nome, CPF, município, telefone, situação RGP e senha Gov.br).</p>
        <label>Município
          <select id="rgp-ex-mun" style="width:100%;margin-top:4px">
            <option value="">Todos</option>
            ${munis.map((m) => `<option value="${esc(m)}">${esc(m)}</option>`).join("")}
          </select>
        </label>
        <label style="display:block;margin-top:10px">Situação
          <select id="rgp-ex-sit" style="width:100%;margin-top:4px">
            ${sits.map((s) => `<option value="${esc(s)}">${esc(s || "Todas")}</option>`).join("")}
          </select>
        </label>
        <div class="inline-row" style="margin-top:10px;gap:10px">
          <label>Última consulta de
            <input type="date" id="rgp-ex-de" />
          </label>
          <label>até
            <input type="date" id="rgp-ex-ate" />
          </label>
        </div>
        <p class="page-sub" id="rgp-ex-status"></p>
      </div>
      <div class="modal-foot">
        <button type="button" class="btn btn-outline-dark" data-modal-close="">Cancelar</button>
        <button type="button" class="btn btn-ghost" id="rgp-ex-geral">Relatório HTML geral</button>
        <button type="button" class="btn btn-primary" id="rgp-ex-go">Exportar CSV+HTML</button>
      </div>
    `);
    function payloadBase(modoGeral) {
      return {
        municipio: backdrop.querySelector("#rgp-ex-mun").value || "",
        situacao: backdrop.querySelector("#rgp-ex-sit").value || "",
        ultima_de: backdrop.querySelector("#rgp-ex-de").value || "",
        ultima_ate: backdrop.querySelector("#rgp-ex-ate").value || "",
        abrir_html: true,
        modo_geral: !!modoGeral,
      };
    }
    async function runExport(modoGeral) {
      backdrop.querySelector("#rgp-ex-status").textContent = modoGeral
        ? "Gerando relatório HTML geral…"
        : "Exportando…";
      try {
        const method = modoGeral ? "relatorio_geral_consulta_rgp" : "exportar_consulta_rgp";
        const r = await api(method, JSON.stringify(payloadBase(modoGeral)));
        if (r && r.ok === false && !r.pending) {
          toast(r.error || "Falha ao exportar.");
          backdrop.querySelector("#rgp-ex-status").textContent = r.error || "Erro.";
        }
      } catch (_e) {
        toast("Erro ao exportar.");
      }
    }
    backdrop.querySelector("#rgp-ex-go").addEventListener("click", () => runExport(false));
    backdrop.querySelector("#rgp-ex-geral").addEventListener("click", () => runExport(true));
  }

  function openRelatorioGeral() {
    openExportModal();
    // auto-foco no botão geral — usuário confirma filtros
    setTimeout(() => {
      const btn = document.getElementById("rgp-ex-geral");
      if (btn) btn.focus();
    }, 50);
  }

  /** Correção em lote — nome, CPF, telefone, município, observação + senha Gov.br */
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
      // sem seleção → lista filtrada na tela (via busca/filtro já aplicada no state)
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

    const senhaAtual = st.consultaRgpGovbrSenha || "";
    const origem = selectedIds.length
      ? `${regs.length} selecionado(s)`
      : `${regs.length} da lista filtrada`;

    const backdrop = openModal(`
      <div class="modal-head">Corrigir em lote — Consulta RGP</div>
      <div class="modal-body rgp-edit-lote-body">
        <p class="page-sub">Edite nome, CPF, número, município e observação. Gravação em lote (anti-cota). ${esc(origem)}.</p>
        <div class="rgp-edit-govbr">
          <label class="rgp-edit-govbr-check">
            <input type="checkbox" id="rgp-el-govbr-on" />
            Atualizar senha Gov.br do módulo
          </label>
          <input type="password" id="rgp-el-govbr" value="${esc(senhaAtual)}" placeholder="Senha Gov.br" disabled autocomplete="new-password" />
          <button type="button" class="btn btn-ghost btn-sm" id="rgp-el-govbr-toggle">Mostrar</button>
        </div>
        <div class="rgp-edit-lote-head">
          <span>Nome</span><span>CPF</span><span>Município</span><span>Número</span><span>Observação</span>
        </div>
        <div class="rgp-edit-lote-rows" id="rgp-el-rows"></div>
        <p class="page-sub" id="rgp-el-status"></p>
      </div>
      <div class="modal-foot">
        <button type="button" class="btn btn-outline-dark" data-modal-close="">Cancelar</button>
        <button type="button" class="btn btn-primary" id="rgp-el-save">Salvar correções</button>
      </div>
    `, "modal-wide modal-rgp-edit-lote");

    const host = backdrop.querySelector("#rgp-el-rows");
    const statusEl = backdrop.querySelector("#rgp-el-status");
    const saveBtn = backdrop.querySelector("#rgp-el-save");
    const govOn = backdrop.querySelector("#rgp-el-govbr-on");
    const govInput = backdrop.querySelector("#rgp-el-govbr");

    govOn.addEventListener("change", () => {
      govInput.disabled = !govOn.checked;
      if (govOn.checked) govInput.focus();
    });
    backdrop.querySelector("#rgp-el-govbr-toggle")?.addEventListener("click", () => {
      const show = govInput.type === "password";
      govInput.type = show ? "text" : "password";
      backdrop.querySelector("#rgp-el-govbr-toggle").textContent = show ? "Ocultar" : "Mostrar";
    });

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
      `;
      host.appendChild(row);
      bindNomeMask(row.querySelector(".el-nome"));
      bindCpfMask(row.querySelector(".el-cpf"));
    });

    statusEl.textContent = `${regs.length} linha(s) prontas para edição.`;

    saveBtn.addEventListener("click", async () => {
      const itens = [...host.querySelectorAll(".rgp-edit-lote-row")].map((row) => ({
        id: row.dataset.id,
        nome: formatNome(row.querySelector(".el-nome").value),
        cpf: row.querySelector(".el-cpf").value,
        municipio: (row.querySelector(".el-mun").value || "").trim(),
        telefone: (row.querySelector(".el-tel").value || "").trim(),
        observacao: (row.querySelector(".el-obs").value || "").trim(),
      })).filter((r) => r.id && (r.nome || r.cpf));

      if (!itens.length) {
        toast("Nenhuma linha válida.");
        return;
      }
      saveBtn.disabled = true;
      statusEl.textContent = `Salvando ${itens.length} correção(ões)…`;
      try {
        const payload = {
          itens,
          atualizar_govbr: !!govOn.checked,
          govbr_senha: govOn.checked ? govInput.value : undefined,
        };
        const r = await api("editar_lote_consulta_rgp", JSON.stringify(payload));
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
      <button type="button" class="rgp-btn rgp-btn-ghost" id="rgp-relatorio-geral" title="Nome, CPF, município, telefone, situação e senha Gov.br">☰ Relatório HTML</button>
      <button type="button" class="rgp-btn rgp-btn-ghost" id="rgp-exportar">⇩ Exportar</button>
    `;
  }

  function bindToolbar() {
    document.getElementById("rgp-vencidos")?.addEventListener("click", openVencidosModal);
    document.getElementById("rgp-exportar")?.addEventListener("click", openExportModal);
    document.getElementById("rgp-relatorio-geral")?.addEventListener("click", () => {
      // gera direto o relatório geral (sem filtros extras)
      (async () => {
        try {
          const r = await api("relatorio_geral_consulta_rgp", JSON.stringify({ abrir_html: true }));
          if (r && r.ok === false && !r.pending) toast(r.error || "Falha no relatório.");
        } catch (_e) {
          toast("Erro ao gerar relatório.");
        }
      })();
    });
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
