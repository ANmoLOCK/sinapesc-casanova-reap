/* Máscaras de input compartilhadas (REAP, Defeso, Consulta RGP).
 * Separado de app.js para não misturar regras de módulo e evitar
 * bugs de digitação (CPF com pad/recover no meio da digitação).
 */
(function (global) {
  "use strict";

  function onlyDigits(value, max) {
    const d = String(value ?? "").replace(/\D/g, "");
    return typeof max === "number" ? d.slice(0, max) : d;
  }

  function cpfDigitsOk(d) {
    if (!/^\d{11}$/.test(d) || /^(\d)\1{10}$/.test(d)) return false;
    const n = d.split("").map(Number);
    let s = 0;
    for (let i = 0; i < 9; i++) s += n[i] * (10 - i);
    let r = (s * 10) % 11;
    if (r === 10) r = 0;
    if (r !== n[9]) return false;
    s = 0;
    for (let i = 0; i < 10; i++) s += n[i] * (11 - i);
    r = (s * 10) % 11;
    if (r === 10) r = 0;
    return r === n[10];
  }

  /**
   * Recover de float .0 — só troca se atual inválido, ou se fromNumber
   * (nunca inventar outro CPF válido: 10683919520 → 01068391952).
   */
  function fixCpfDigits(d, fromNumber) {
    if (d.length !== 11) return d;
    if (d.endsWith("0")) {
      const base = d.slice(0, -1);
      if (base.length === 10) {
        const cand = base.padStart(11, "0");
        if (cand !== d && cpfDigitsOk(cand)) {
          if (!cpfDigitsOk(d)) return cand;
          if (fromNumber && cand.startsWith("0") && !d.startsWith("0")) return cand;
        }
      }
    }
    return d;
  }

  /**
   * Normaliza CPF completo (salvar/consultar).
   * 11 dígitos da máscara → preservar. Pad só para number / "….0".
   * Nunca: 9156476051 (string) → 09156476051.
   */
  function normalizeCpf(value) {
    if (value == null || value === "") return "";
    if (typeof value === "number" && Number.isFinite(value)) {
      let d = String(Math.abs(Math.round(value)));
      if (d.length >= 9 && d.length < 11) d = d.padStart(11, "0");
      return fixCpfDigits(d.slice(0, 11), true);
    }
    let s = String(value).trim();
    if (s.startsWith("'")) s = s.slice(1).trim();
    let fromNumber = false;
    if (/^\d+\.0+$/.test(s)) {
      s = s.split(".")[0];
      fromNumber = true;
    }
    const sci = s.replace(",", ".");
    if (/^\d+\.?\d*[eE][+-]?\d+$/.test(sci)) {
      const n = Number(sci);
      if (Number.isFinite(n)) {
        s = String(Math.abs(Math.round(n)));
        fromNumber = true;
      }
    }
    let d = s.replace(/\D/g, "");
    if (!d) return "";
    const explicit11 = !fromNumber && d.length >= 11;
    if (d.length === 12 && d.endsWith("0")) {
      d = d.slice(0, -1);
      fromNumber = true;
    }
    if (d.length > 11) d = d.slice(-11);
    if (explicit11 && d.length === 11) {
      // Preservar digitação; só recover se DV inválido (artefato …00 gravado)
      if (!cpfDigitsOk(d)) return fixCpfDigits(d, false);
      return d;
    }
    // Pad 9–10: zeros à esquerda perdidos (planilha). UI só salva com 11.
    if (d.length >= 9 && d.length < 11) d = d.padStart(11, "0");
    return fixCpfDigits(d.slice(0, 11), fromNumber);
  }

  /** Formata só para digitação — NÃO dá padStart nem recover (evita bug no REAP). */
  function formatCpfInput(value) {
    const digits = onlyDigits(value, 11);
    const p1 = digits.slice(0, 3);
    const p2 = digits.slice(3, 6);
    const p3 = digits.slice(6, 9);
    const p4 = digits.slice(9, 11);
    let out = p1;
    if (p2) out += `.${p2}`;
    if (p3) out += `.${p3}`;
    if (p4) out += `-${p4}`;
    return out;
  }

  /** Formata CPF já completo/salvo (com normalize). */
  function formatCpf(value) {
    const d = normalizeCpf(value);
    const digits = d.length === 11 ? d : onlyDigits(value, 11);
    return formatCpfInput(digits);
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
    if (!input || input.dataset.nomeMaskBound) return;
    input.dataset.nomeMaskBound = "1";
    const paint = () => { input.value = formatNome(input.value); };
    input.addEventListener("blur", paint);
    input.addEventListener("change", paint);
  }

  function bindCpfMask(input) {
    if (!input || input.dataset.cpfMaskBound) return;
    input.dataset.cpfMaskBound = "1";
    input.setAttribute("maxlength", "14");
    input.setAttribute("inputmode", "numeric");
    input.addEventListener("input", () => {
      const start = input.selectionStart || 0;
      const digitsBefore = onlyDigits(input.value.slice(0, start)).length;
      const formatted = formatCpfInput(input.value);
      input.value = formatted;
      let pos = formatted.length;
      let seen = 0;
      for (let i = 0; i < formatted.length; i++) {
        if (/\d/.test(formatted[i])) {
          seen += 1;
          if (seen >= digitsBefore) {
            pos = i + 1;
            break;
          }
        }
      }
      if (digitsBefore === 0) pos = 0;
      try {
        input.setSelectionRange(pos, pos);
      } catch (_e) { /* ignore */ }
    });
    // formata valor inicial sem pad (já vem completo ou vazio)
    if (input.value) input.value = formatCpfInput(input.value);
  }

  global.SinapescMasks = {
    onlyDigits,
    cpfDigitsOk,
    fixCpfDigits,
    normalizeCpf,
    formatCpfInput,
    formatCpf,
    formatNome,
    bindNomeMask,
    bindCpfMask,
  };
})(typeof window !== "undefined" ? window : globalThis);
