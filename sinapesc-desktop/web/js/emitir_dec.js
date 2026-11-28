/* EmitirDec — escolha: declaração de residência ou declaração de filiação. */
(function () {
  const FONTES = [
    { id: "times", label: "Times New Roman", css: '"Times New Roman", Times, serif' },
    { id: "arial", label: "Arial", css: "Arial, Helvetica, sans-serif" },
    { id: "calibri", label: "Calibri", css: 'Calibri, Carlito, "Segoe UI", sans-serif' },
  ];
  const TIPOS = {
    endereco: {
      titulo: "Declaração de Residência",
      dica: "Preenche a parte de cima. Local, data, assinatura e testemunhas ficam em branco para a caneta.",
    },
    filiacao: {
      titulo: "Declaração de Filiação",
      dica: "Preenche nome, CPF, RG, residência e data de filiação. Local, data e assinaturas ficam em branco para a caneta.",
    },
  };

  function esc(s) {
    return String(s ?? "")
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;")
      .replace(/"/g, "&quot;");
  }

  function toast(msg) {
    const root = document.getElementById("toast-root");
    if (!root) return;
    const el = document.createElement("div");
    el.className = "toast";
    el.textContent = msg;
    root.appendChild(el);
    setTimeout(() => el.remove(), 3600);
  }

  function campo(id, label, value, extra) {
    return `
      <label for="${id}">${label}</label>
      <input id="${id}" value="${esc(value || "")}" ${extra || ""} />`;
  }

  function modal(html) {
    const root = document.getElementById("modal-root");
    if (!root) return null;
    const backdrop = document.createElement("div");
    backdrop.className = "modal-backdrop";
    backdrop.innerHTML = html;
    backdrop.addEventListener("click", (e) => {
      if (e.target === backdrop) backdrop.remove();
    });
    backdrop.querySelectorAll("[data-ed-close]").forEach((b) => b.addEventListener("click", () => backdrop.remove()));
    root.appendChild(backdrop);
    return backdrop;
  }

  /** Abre o módulo: primeiro escolhe qual declaração emitir. */
  function open(reg) {
    const r = reg || {};
    const backdrop = modal(`
      <div class="modal">
        <div class="modal-head">EmitirDec</div>
        <div class="modal-body">
          <p class="ed-hint">Escolha a declaração que vai emitir.</p>
          <div class="ed-escolha">
            <button type="button" class="btn btn-primary" data-ed-tipo="endereco">Emitir Declaração de Residência</button>
            <button type="button" class="btn btn-primary" data-ed-tipo="filiacao">Emitir Declaração de Filiação</button>
          </div>
        </div>
        <div class="modal-foot">
          <button type="button" class="btn btn-outline-dark" data-ed-close="">Cancelar</button>
        </div>
      </div>`);
    if (!backdrop) return;
    backdrop.querySelectorAll("[data-ed-tipo]").forEach((btn) => {
      btn.addEventListener("click", () => {
        backdrop.remove();
        abrirFormulario(btn.getAttribute("data-ed-tipo"), r);
      });
    });
  }

  function camposResidencia(r) {
    const civis = ["", "Solteiro(a)", "Casado(a)", "Divorciado(a)", "Viúvo(a)", "União estável"];
    return `
      <div class="span-2">${campo("ed-nome", "Nome completo", r.nome)}</div>
      ${campo("ed-cpf", "CPF", r.cpf, 'inputmode="numeric"')}
      ${campo("ed-rg", "RG", "")}
      ${campo("ed-nac", "Nacionalidade", "Brasileira")}
      <div>
        <label for="ed-civil">Estado civil</label>
        <select id="ed-civil">${civis.map((c) => `<option value="${esc(c)}">${esc(c || "Selecionar")}</option>`).join("")}</select>
      </div>
      <div class="span-2">${campo("ed-prof", "Profissão", "Pescador profissional")}</div>
      ${campo("ed-end-rua", "Endereço", "")}
      ${campo("ed-num", "Número", "")}
      ${campo("ed-bairro", "Bairro", "")}
      ${campo("ed-mun", "Município", r.municipio)}
      ${campo("ed-uf", "UF", "BA", 'maxlength="2"')}
      ${campo("ed-cep", "CEP", "")}
      ${campo("ed-tel", "Telefone", r.telefone)}
      <div class="span-2">${campo("ed-email", "E-mail", "")}</div>`;
  }

  function camposFiliacao(r) {
    return `
      <div class="span-2">${campo("ed-nome", "Nome completo", r.nome)}</div>
      ${campo("ed-cpf", "CPF", r.cpf, 'inputmode="numeric"')}
      ${campo("ed-rg", "RG", "")}
      <div class="span-2">${campo("ed-residente", "Residente em", "", 'placeholder="Rua, número, bairro, Casa Nova-BA"')}</div>
      <div class="span-2">${campo("ed-filiacao", "Data de filiação", "", 'placeholder="Ex.: 15 de março de 2019"')}</div>`;
  }

  function abrirFormulario(tipo, reg) {
    const meta = TIPOS[tipo];
    if (!meta) return;
    const r = {
      nome: reg.nome_display || reg.nome || "",
      cpf: reg.cpf_formatado || reg.cpf || "",
      telefone: reg.telefone || "",
      municipio: reg.municipio || "Casa Nova",
    };
    const fontes = FONTES.map((f, i) => `
      <label class="ed-fonte">
        <input type="radio" name="ed-fonte" value="${f.id}" ${i === 0 ? "checked" : ""} />
        <span class="ed-fonte-nome" style="font-family:${f.css}">${esc(f.label)}</span>
        <small>Aa Bb Cc 123</small>
      </label>`).join("");
    const backdrop = modal(`
      <div class="modal modal-wide">
        <div class="modal-head">${esc(meta.titulo)}</div>
        <div class="modal-body">
          <p class="ed-hint">${esc(meta.dica)}</p>
          <div class="ed-grid">${tipo === "endereco" ? camposResidencia(r) : camposFiliacao(r)}</div>
          <label>Letra</label>
          <div class="ed-fontes">${fontes}</div>
        </div>
        <div class="modal-foot">
          <button type="button" class="btn btn-outline-dark" data-ed-voltar="">Voltar</button>
          <button type="button" class="btn btn-outline-dark" data-ed-close="">Cancelar</button>
          <button type="button" class="btn btn-primary" id="ed-gerar">Gerar PDF</button>
        </div>
      </div>`);
    if (!backdrop) return;
    backdrop.querySelector("[data-ed-voltar]")?.addEventListener("click", () => {
      backdrop.remove();
      open(reg);
    });
    const masks = window.SinapescMasks;
    if (masks) {
      const nomeInput = backdrop.querySelector("#ed-nome");
      const cpfInput = backdrop.querySelector("#ed-cpf");
      if (nomeInput && masks.bindNomeMask) masks.bindNomeMask(nomeInput);
      if (cpfInput && masks.bindCpfMask) masks.bindCpfMask(cpfInput);
    }
    backdrop.querySelector("#ed-gerar")?.addEventListener("click", () => gerar(backdrop, tipo));
    backdrop.querySelector("#ed-nome")?.focus();
  }

  let aguardando = null;

  function val(backdrop, id) {
    return (backdrop.querySelector("#" + id)?.value || "").trim();
  }

  async function gerar(backdrop, tipo) {
    const nome = val(backdrop, "ed-nome");
    if (!nome) {
      toast("Informe o nome completo.");
      return;
    }
    const fonte = backdrop.querySelector('input[name="ed-fonte"]:checked')?.value || "times";
    const payload = {
      nome,
      cpf: val(backdrop, "ed-cpf"),
      rg: val(backdrop, "ed-rg"),
      quais: [tipo],
      fonte,
    };
    if (tipo === "endereco") {
      Object.assign(payload, {
        nacionalidade: val(backdrop, "ed-nac"),
        estado_civil: val(backdrop, "ed-civil"),
        profissao: val(backdrop, "ed-prof"),
        endereco: val(backdrop, "ed-end-rua"),
        numero: val(backdrop, "ed-num"),
        bairro: val(backdrop, "ed-bairro"),
        municipio: val(backdrop, "ed-mun"),
        uf: val(backdrop, "ed-uf"),
        cep: val(backdrop, "ed-cep"),
        telefone: val(backdrop, "ed-tel"),
        email: val(backdrop, "ed-email"),
      });
    } else {
      Object.assign(payload, {
        residente: val(backdrop, "ed-residente"),
        data_filiacao: val(backdrop, "ed-filiacao"),
      });
    }
    const btn = backdrop.querySelector("#ed-gerar");
    if (btn) btn.disabled = true;
    try {
      if (!window.pywebview || !window.pywebview.api) {
        toast("API Python indisponível.");
        if (btn) btn.disabled = false;
        return;
      }
      const r = await window.pywebview.api.emitir_declaracao(payload, fonte);
      if (r && r.ok === false) {
        toast(r.error || "Não foi possível gerar o PDF.");
        if (btn) btn.disabled = false;
        return;
      }
      aguardando = backdrop;
      toast("Gerando o PDF… ele abre no navegador para imprimir.");
    } catch (e) {
      toast(e && e.message ? e.message : "Não foi possível gerar o PDF.");
      if (btn) btn.disabled = false;
    }
  }

  if (window.AppEvents) {
    window.AppEvents.on("emitir_dec", (r) => {
      if (r && r.ok) {
        toast("Declaração aberta no navegador para imprimir.");
        if (aguardando) aguardando.remove();
        aguardando = null;
        return;
      }
      toast((r && r.error) || "Não foi possível gerar o PDF.");
      const btn = aguardando && aguardando.querySelector("#ed-gerar");
      if (btn) btn.disabled = false;
    });
  }

  window.SinapescEmitirDec = { open };
})();
