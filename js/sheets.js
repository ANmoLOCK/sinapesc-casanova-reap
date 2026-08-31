/**
 * Leitura da planilha Google publicada / compartilhada (Opção A).
 * Usa gviz JSONP para evitar CORS.
 */
(function () {
  const MESES = ["jan","fev","mar","abr","mai","jun","jul","ago","set","out","nov","dez"];

  function onlyDigits(v) {
    return String(v || "").replace(/\D/g, "").slice(0, 11);
  }

  function maskCpf(digits) {
    const d = onlyDigits(digits);
    if (d.length !== 11) return d;
    return `***.***.${d.slice(6, 9)}-**`;
  }

  function parseGvizTable(data) {
    const cols = (data.table.cols || []).map((c) => (c.label || c.id || "").trim());
    const rows = [];
    for (const row of data.table.rows || []) {
      const cells = (row.c || []).map((c) => {
        if (!c) return "";
        if (c.v === null || c.v === undefined) return "";
        return String(c.v);
      });
      rows.push(cells);
    }
    return { cols, rows };
  }

  function loadSheetJsonp(spreadsheetId, sheetName) {
    return new Promise((resolve, reject) => {
      const cb = "sinapesc_cb_" + Math.random().toString(36).slice(2);
      const timeout = setTimeout(() => {
        cleanup();
        reject(new Error("Tempo esgotado ao ler a planilha. Verifique o compartilhamento."));
      }, 20000);

      function cleanup() {
        clearTimeout(timeout);
        try { delete window[cb]; } catch (_) {}
        if (script && script.parentNode) script.parentNode.removeChild(script);
      }

      window[cb] = function (payload) {
        cleanup();
        try {
          resolve(parseGvizTable(payload));
        } catch (e) {
          reject(e);
        }
      };

      const script = document.createElement("script");
      const url =
        "https://docs.google.com/spreadsheets/d/" +
        encodeURIComponent(spreadsheetId) +
        "/gviz/tq?tqx=out:json;responseHandler:" +
        cb +
        "&sheet=" +
        encodeURIComponent(sheetName);
      script.onerror = function () {
        cleanup();
        reject(new Error("Falha ao carregar a aba " + sheetName));
      };
      script.src = url;
      document.head.appendChild(script);
    });
  }

  async function loadCsv(url) {
    const res = await fetch(url, { cache: "no-store" });
    if (!res.ok) throw new Error("Falha ao baixar CSV");
    const text = await res.text();
    const lines = text.replace(/^\uFEFF/, "").split(/\r?\n/).filter(Boolean);
    if (!lines.length) return { cols: [], rows: [] };
    const split = (line) => {
      // CSV simples com aspas
      const out = [];
      let cur = "";
      let q = false;
      for (let i = 0; i < line.length; i++) {
        const ch = line[i];
        if (ch === '"') {
          if (q && line[i + 1] === '"') { cur += '"'; i++; }
          else q = !q;
        } else if (ch === "," && !q) {
          out.push(cur); cur = "";
        } else cur += ch;
      }
      out.push(cur);
      return out;
    };
    const cols = split(lines[0]);
    const rows = lines.slice(1).map(split);
    return { cols, rows };
  }

  function rowsToPessoas(pessoasTable, reapTable) {
    const pessoas = [];
    for (const r of pessoasTable.rows) {
      if (!r[0]) continue;
      // gviz às vezes devolve o cabeçalho como 1ª linha (id/nome/cpf)
      const id = String(r[0] || "").trim();
      const nome = String(r[1] || "").trim();
      const cpf = onlyDigits(r[2] || "");
      if (!id || id.toLowerCase() === "id") continue;
      if (!nome || nome.toLowerCase() === "nome") continue;
      pessoas.push({
        id,
        nome,
        cpf,
        anos: [],
      });
    }
    const byId = Object.fromEntries(pessoas.map((p) => [p.id, p]));
    for (const r of reapTable.rows) {
      if (!r[0] || !r[1]) continue;
      const rid = String(r[0] || "").trim();
      if (rid.toLowerCase() === "id") continue;
      const personId = String(r[1]);
      const p = byId[personId];
      if (!p) continue;
      const meses = {};
      MESES.forEach((m, i) => {
        const raw = String(r[3 + i] || "").trim().toUpperCase();
        meses[m] = raw === "TRUE" || raw === "VERDADEIRO" || raw === "1";
      });
      p.anos.push({
        id: rid,
        personId,
        ano: Number(r[2]) || 0,
        meses,
      });
    }
    for (const p of pessoas) {
      p.anos.sort((a, b) => b.ano - a.ano);
    }
    return pessoas;
  }

  async function loadAll() {
    const cfg = window.SINAPESC_CONFIG || {};
    let pessoasTable;
    let reapTable;

    if (cfg.pessoasCsvUrl && cfg.reapCsvUrl) {
      [pessoasTable, reapTable] = await Promise.all([
        loadCsv(cfg.pessoasCsvUrl),
        loadCsv(cfg.reapCsvUrl),
      ]);
    } else if (cfg.spreadsheetId) {
      [pessoasTable, reapTable] = await Promise.all([
        loadSheetJsonp(cfg.spreadsheetId, "Pessoas"),
        loadSheetJsonp(cfg.spreadsheetId, "Reap"),
      ]);
    } else {
      throw new Error(
        "Configure spreadsheetId (ou URLs CSV) em config.js e compartilhe a planilha como leitor."
      );
    }
    return rowsToPessoas(pessoasTable, reapTable);
  }

  function monthsHtml(meses) {
    return (
      '<div class="months">' +
      MESES.map((m) => {
        const on = !!meses[m];
        return `<div class="m${on ? " on" : ""}">${m}<br>${on ? "✓" : "·"}</div>`;
      }).join("") +
      "</div>"
    );
  }

  function yearsHtml(pessoa) {
    if (!pessoa.anos || !pessoa.anos.length) {
      return '<p class="empty">Nenhum ano registrado.</p>';
    }
    return pessoa.anos
      .map((a) => `<div class="year"><h3>${a.ano}</h3>${monthsHtml(a.meses)}</div>`)
      .join("");
  }

  window.SinapescSheets = {
    MESES,
    onlyDigits,
    maskCpf,
    loadAll,
    monthsHtml,
    yearsHtml,
  };
})();
