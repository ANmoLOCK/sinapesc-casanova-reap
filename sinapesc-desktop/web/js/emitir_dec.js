/* EmitirDec — declaração de endereço e declaração de afiliação. */
(function () {
  const MESES = [
    "janeiro", "fevereiro", "março", "abril", "maio", "junho",
    "julho", "agosto", "setembro", "outubro", "novembro", "dezembro",
  ];
  const FONTES = [
    { id: "times", label: "Times New Roman", css: '"Times New Roman", Times, serif' },
    { id: "arial", label: "Arial", css: "Arial, Helvetica, sans-serif" },
    { id: "calibri", label: "Calibri", css: 'Calibri, Carlito, "Segoe UI", sans-serif' },
  ];

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

  function hoje() {
    const d = new Date();
    return { dia: String(d.getDate()), mes: MESES[d.getMonth()], ano: String(d.getFullYear()) };
  }

  function campo(id, label, value, extra) {
    return `
      <label for="${id}">${label}</label>
      <input id="${id}" value="${esc(value || "")}" ${extra || ""} />`;
  }

  function open(reg) {
    const r = reg || {};
    const data = hoje();
    const nome = r.nome_display || r.nome || "";
    const cpf = r.cpf_formatado || r.cpf || "";
    const telefone = r.telefone || "";
    const municipio = r.municipio || "Casa Nova";
    const civis = ["", "Solteiro(a)", "Casado(a)", "Divorciado(a)", "Viúvo(a)", "União estável"];
    const fontes = FONTES.map((f, i) => `
      <label class="ed-fonte">
        <input type="radio" name="ed-fonte" value="${f.id}" ${i === 0 ? "checked" : ""} />
        <span class="ed-fonte-nome" style="font-family:${f.css}">${esc(f.label)}</span>
        <small>Aa Bb Cc 123</small>
      </label>`).join("");
    const meses = MESES.map((m) => `<option value="${m}" ${m === data.mes ? "selected" : ""}>${m}</option>`).join("");

    const root = document.getElementById("modal-root");
    if (!root) return;
    const backdrop = document.createElement("div");
    backdrop.className = "modal-backdrop";
    backdrop.innerHTML = `
      <div class="modal modal-wide">
        <div class="modal-head">EmitirDec</div>
        <div class="modal-body">
          <p class="ed-hint">Preencha uma vez. O PDF junta a declaração de endereço e a de afiliação e abre no navegador para imprimir. Assinatura e testemunha ficam em branco para a caneta.</p>
          <div class="ed-checks">
            <label><input type="checkbox" id="ed-end" checked /> Declaração de endereço</label>
            <label><input type="checkbox" id="ed-fil" checked /> Declaração de afiliação</label>
          </div>
          <div class="ed-grid">
            <div class="span-2">${campo("ed-nome", "Nome completo", nome)}</div>
            ${campo("ed-cpf", "CPF", cpf, 'inputmode="numeric"')}
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
            ${campo("ed-mun", "Município", municipio)}
            ${campo("ed-uf", "UF", "BA", 'maxlength="2"')}
            ${campo("ed-cep", "CEP", "")}
            ${campo("ed-tel", "Telefone", telefone)}
            <div class="span-2">${campo("ed-email", "E-mail", "")}</div>
            ${campo("ed-local", "Local", municipio)}
            ${campo("ed-dia", "Dia", data.dia, 'inputmode="numeric"')}
            <div>
              <label for="ed-mes">Mês</label>
              <select id="ed-mes">${meses}</select>
            </div>
            ${campo("ed-ano", "Ano", data.ano, 'inputmode="numeric"')}
            <div class="span-2">${campo("ed-filiacao", "Data de filiação", "", 'placeholder="Ex.: 15 de março de 2019"')}</div>
          </div>
          <label>Letra</label>
          <div class="ed-fontes">${fontes}</div>
        </div>
        <div class="modal-foot">
          <button type="button" class="btn btn-outline-dark" data-ed-close="">Cancelar</button>
          <button type="button" class="btn btn-primary" id="ed-gerar">Gerar PDF</button>
        </div>
      </div>`;
    function close() { backdrop.remove(); }
    backdrop.addEventListener("click", (e) => {
      if (e.target === backdrop) close();
    });
    backdrop.querySelector("[data-ed-close]")?.addEventListener("click", close);
    const masks = window.SinapescMasks;
    if (masks) {
      const nomeInput = backdrop.querySelector("#ed-nome");
      const cpfInput = backdrop.querySelector("#ed-cpf");
      if (nomeInput && masks.bindNomeMask) masks.bindNomeMask(nomeInput);
      if (cpfInput && masks.bindCpfMask) masks.bindCpfMask(cpfInput);
    }
    backdrop.querySelector("#ed-gerar")?.addEventListener("click", () => gerar(backdrop));
    root.appendChild(backdrop);
    backdrop.querySelector("#ed-nome")?.focus();
  }

  let aguardando = null;

  function val(backdrop, id) {
    return (backdrop.querySelector("#" + id)?.value || "").trim();
  }

  async function gerar(backdrop) {
    const quais = [];
    if (backdrop.querySelector("#ed-end")?.checked) quais.push("endereco");
    if (backdrop.querySelector("#ed-fil")?.checked) quais.push("filiacao");
    if (!quais.length) {
      toast("Marque a declaração de endereço, a de afiliação, ou as duas.");
      return;
    }
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
      local: val(backdrop, "ed-local"),
      dia: val(backdrop, "ed-dia"),
      mes: val(backdrop, "ed-mes"),
      ano: val(backdrop, "ed-ano"),
      data_filiacao: val(backdrop, "ed-filiacao"),
      quais,
      fonte,
    };
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
        toast("Declarações abertas no navegador para imprimir.");
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
