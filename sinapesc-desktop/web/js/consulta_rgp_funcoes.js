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

  /** Marca linhas com alerta (função 2) */
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
