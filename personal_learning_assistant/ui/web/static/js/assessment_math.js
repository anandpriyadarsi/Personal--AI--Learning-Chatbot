(() => {
  "use strict";

  const SYMBOLS = new Map([
    ["\\lambda", "λ"], ["\\mu", "μ"], ["\\alpha", "α"], ["\\beta", "β"],
    ["\\gamma", "γ"], ["\\theta", "θ"], ["\\pi", "π"], ["\\Delta", "Δ"],
    ["\\cap", "∩"], ["\\cup", "∪"], ["\\subseteq", "⊆"], ["\\subset", "⊂"],
    ["\\supseteq", "⊇"], ["\\in", "∈"], ["\\notin", "∉"], ["\\neq", "≠"],
    ["\\leq", "≤"], ["\\le", "≤"], ["\\geq", "≥"], ["\\ge", "≥"],
    ["\\times", "×"], ["\\cdot", "·"], ["\\to", "→"], ["\\Rightarrow", "⇒"],
    ["\\sum", "∑"], ["\\prod", "∏"], ["\\ell", "ℓ"], ["\\forall", "∀"],
    ["\\exists", "∃"], ["\\therefore", "∴"], ["\\because", "∵"], ["\\emptyset", "∅"],
    ["\\infty", "∞"], ["\\pm", "±"], ["\\mathbb{R}", "ℝ"], ["\\mathbb{C}", "ℂ"],
    ["\\mathbb{Q}", "ℚ"], ["\\mathbb{Z}", "ℤ"], ["\\mathbb{N}", "ℕ"],
  ]);

  const replaceSymbols = (value) => {
    let text = String(value ?? "")
      .replace(/\\operatorname\{span\}/g, "span")
      .replace(/\\operatorname\{rank\}/g, "rank")
      .replace(/\\det\b/g, "det")
      .replace(/\\dim\b/g, "dim")
      .replace(/\\,/g, " ")
      .replace(/\\;/g, " ");
    for (const [source, target] of SYMBOLS) text = text.split(source).join(target);
    return text
      .replace(/\b(?:sum|sigma)\s*\(\s*([A-Za-z][A-Za-z0-9]*)\s*=\s*([^()]+?)\s+to\s+([^()]+?)\s*\)/gi, "∑_{$1=$2}^{$3}")
      .replace(/[Σ∑]\s*\(\s*([A-Za-z][A-Za-z0-9]*)\s*=\s*([^()]+?)\s+to\s+([^()]+?)\s*\)/g, "∑_{$1=$2}^{$3}")
      .replace(/\b(?:prod|product)\s*\(\s*([A-Za-z][A-Za-z0-9]*)\s*=\s*([^()]+?)\s+to\s+([^()]+?)\s*\)/gi, "∏_{$1=$2}^{$3}")
      .replace(/∏\s*\(\s*([A-Za-z][A-Za-z0-9]*)\s*=\s*([^()]+?)\s+to\s+([^()]+?)\s*\)/g, "∏_{$1=$2}^{$3}")
      .replace(/E(\d+)(?=E|A|\s|$)/g, "E_$1 ")
      .replace(/\bE(\d+)\b/g, "E_$1")
      .replace(/\bb(\d+)\b/g, "b_$1")
      .replace(/\bu(\d+)\b/g, "u_$1")
      .replace(/\bl(\d+)\b/g, "ℓ_$1")
      .replace(/ℓ(\d+)\b/g, "ℓ_$1")
      .replace(/!=/g, "≠")
      .replace(/<=/g, "≤")
      .replace(/>=/g, "≥");
  };

  const readScriptToken = (text, start) => {
    if (text[start] === "{") {
      let depth = 1;
      let index = start + 1;
      while (index < text.length && depth) {
        if (text[index] === "{") depth += 1;
        if (text[index] === "}") depth -= 1;
        index += 1;
      }
      return {value: text.slice(start + 1, Math.max(start + 1, index - 1)), end: index};
    }
    let index = start;
    if (text[index] === "-") index += 1;
    while (index < text.length && /[A-Za-z0-9+−-]/.test(text[index])) index += 1;
    if (index === start || (index === start + 1 && text[start] === "-")) index = Math.min(text.length, start + 1);
    return {value: text.slice(start, index), end: index};
  };

  const createScript = (documentRef, tag, value) => {
    const node = documentRef.createElement(tag);
    node.className = `assessment-math-${tag}`;
    node.textContent = replaceSymbols(value);
    return node;
  };

  const appendInlineMath = (documentRef, parent, raw) => {
    const text = replaceSymbols(raw)
      .replace(/\\\((.*?)\\\)/g, "$1")
      .replace(/\\\[(.*?)\\\]/g, "$1")
      .replace(/\$\$(.*?)\$\$/g, "$1")
      .replace(/\$(.*?)\$/g, "$1");
    let buffer = "";
    const flush = () => {
      if (!buffer) return;
      parent.appendChild(documentRef.createTextNode(buffer));
      buffer = "";
    };
    for (let i = 0; i < text.length;) {
      const marker = text[i];
      if ((marker === "^" || marker === "_") && i + 1 < text.length) {
        flush();
        const token = readScriptToken(text, i + 1);
        parent.appendChild(createScript(documentRef, marker === "^" ? "sup" : "sub", token.value));
        i = token.end;
        continue;
      }
      buffer += marker;
      i += 1;
    }
    flush();
  };

  const parseBigOperatorAt = (text, start) => {
    const symbol = text[start];
    if (symbol !== "∑" && symbol !== "∏") return null;
    let index = start + 1;
    let lower = "";
    let upper = "";
    for (let count = 0; count < 2; count += 1) {
      while (index < text.length && /\s/.test(text[index])) index += 1;
      const marker = text[index];
      if (marker !== "_" && marker !== "^") break;
      const token = readScriptToken(text, index + 1);
      if (marker === "_") lower = token.value;
      else upper = token.value;
      index = token.end;
    }
    if (!lower && !upper) return null;
    return {symbol, lower, upper, end: index};
  };

  const createBigOperator = (documentRef, parsed) => {
    const shell = documentRef.createElement("span");
    shell.className = "assessment-big-operator";
    shell.setAttribute("role", "math");

    const upper = documentRef.createElement("span");
    upper.className = "assessment-big-operator-upper";
    if (parsed.upper) appendInlineMath(documentRef, upper, parsed.upper);

    const symbol = documentRef.createElement("span");
    symbol.className = "assessment-big-operator-symbol";
    symbol.textContent = parsed.symbol;

    const lower = documentRef.createElement("span");
    lower.className = "assessment-big-operator-lower";
    if (parsed.lower) appendInlineMath(documentRef, lower, parsed.lower);

    shell.append(upper, symbol, lower);
    return shell;
  };

  const parseMatrixAt = (text, start) => {
    if (text.slice(start, start + 2) !== "[[") return null;
    let depth = 0;
    for (let i = start; i < text.length; i += 1) {
      if (text[i] === "[") depth += 1;
      else if (text[i] === "]") {
        depth -= 1;
        if (depth === 0) {
          const source = text.slice(start, i + 1);
          const inner = source.slice(2, -2);
          const rows = inner.split(/\]\s*,\s*\[/).map(row => row.split(",").map(cell => cell.trim()));
          if (rows.length >= 2 && rows.every(row => row.length === rows[0].length && row.length >= 1)) {
            return {rows, end: i + 1};
          }
          return null;
        }
      }
    }
    return null;
  };

  const createMatrix = (documentRef, rows, delimiter = "brackets") => {
    const delimiters = {
      brackets: ["[", "]"],
      parentheses: ["(", ")"],
      determinant: ["|", "|"],
      none: ["", ""],
    };
    const pair = delimiters[delimiter] || delimiters.brackets;
    const shell = documentRef.createElement("span");
    shell.className = `assessment-matrix assessment-matrix-${delimiter}`;
    shell.setAttribute("role", "math");
    shell.setAttribute(
      "aria-label",
      `${delimiter === "determinant" ? "determinant" : "matrix"} with ${rows.length} rows and ${rows[0].length} columns`
    );
    const left = documentRef.createElement("span");
    const right = documentRef.createElement("span");
    left.className = "assessment-matrix-bracket assessment-matrix-bracket-left";
    right.className = "assessment-matrix-bracket assessment-matrix-bracket-right";
    left.textContent = pair[0];
    right.textContent = pair[1];
    const grid = documentRef.createElement("span");
    grid.className = "assessment-matrix-grid";
    grid.style.setProperty("--matrix-columns", String(rows[0].length));
    for (const row of rows) {
      for (const cell of row) {
        const item = documentRef.createElement("span");
        item.className = "assessment-matrix-cell";
        appendInlineMath(documentRef, item, cell);
        grid.appendChild(item);
      }
    }
    shell.append(left, grid, right);
    return shell;
  };

  const parseDeterminantAt = (text, start) => {
    const match = text.slice(start).match(/^det\s*\(/i);
    if (!match) return null;
    let matrixStart = start + match[0].length;
    while (matrixStart < text.length && /\s/.test(text[matrixStart])) matrixStart += 1;
    const matrix = parseMatrixAt(text, matrixStart);
    if (!matrix) return null;
    let end = matrix.end;
    while (end < text.length && /\s/.test(text[end])) end += 1;
    if (text[end] !== ")") return null;
    return {rows: matrix.rows, end: end + 1, delimiter: "determinant"};
  };

  const parseLatexMatrixAt = (text, start) => {
    const match = text.slice(start).match(/^\\begin\{(bmatrix|pmatrix|vmatrix|matrix)\}/);
    if (!match) return null;
    const environment = match[1];
    const bodyStart = start + match[0].length;
    const endMarker = `\\end{${environment}}`;
    const endIndex = text.indexOf(endMarker, bodyStart);
    if (endIndex < 0) return null;
    const body = text.slice(bodyStart, endIndex).trim();
    const rows = body
      .split(/\\\\/)
      .map(row => row.split("&").map(cell => cell.trim()))
      .filter(row => row.some(Boolean));
    if (!rows.length || !rows[0].length) return null;
    if (!rows.every(row => row.length === rows[0].length)) return null;
    const delimiter = environment === "pmatrix"
      ? "parentheses"
      : environment === "vmatrix"
        ? "determinant"
        : environment === "matrix"
          ? "none"
          : "brackets";
    return {rows, end: endIndex + endMarker.length, delimiter};
  };

  const renderText = (documentRef, raw) => {
    const fragment = documentRef.createDocumentFragment();
    const text = replaceSymbols(String(raw ?? ""));
    let cursor = 0;
    let plainStart = 0;
    const flushPlain = (end) => {
      if (end <= plainStart) return;
      const span = documentRef.createElement("span");
      appendInlineMath(documentRef, span, text.slice(plainStart, end));
      while (span.firstChild) fragment.appendChild(span.firstChild);
    };
    while (cursor < text.length) {
      const bigOperator = parseBigOperatorAt(text, cursor);
      if (bigOperator) {
        flushPlain(cursor);
        fragment.appendChild(createBigOperator(documentRef, bigOperator));
        cursor = bigOperator.end;
        plainStart = cursor;
        continue;
      }
      const determinant = parseDeterminantAt(text, cursor);
      if (determinant) {
        flushPlain(cursor);
        fragment.appendChild(
          createMatrix(documentRef, determinant.rows, determinant.delimiter)
        );
        cursor = determinant.end;
        plainStart = cursor;
        continue;
      }
      const latexMatrix = parseLatexMatrixAt(text, cursor);
      if (latexMatrix) {
        flushPlain(cursor);
        fragment.appendChild(
          createMatrix(documentRef, latexMatrix.rows, latexMatrix.delimiter)
        );
        cursor = latexMatrix.end;
        plainStart = cursor;
        continue;
      }
      const matrix = parseMatrixAt(text, cursor);
      if (matrix) {
        flushPlain(cursor);
        fragment.appendChild(createMatrix(documentRef, matrix.rows));
        cursor = matrix.end;
        plainStart = cursor;
        continue;
      }
      cursor += 1;
    }
    flushPlain(text.length);
    return fragment;
  };

  const renderElement = (element) => {
    if (!element || element.dataset.mathRendered === "1") return;
    const documentRef = element.ownerDocument || document;
    const source = element.textContent || "";
    element.replaceChildren(renderText(documentRef, source));
    element.dataset.mathRendered = "1";
  };

  const renderAll = (root = document) => {
    if (!root || typeof root.querySelectorAll !== "function") return;
    root.querySelectorAll("[data-assessment-math]").forEach(renderElement);
  };

  const api = {
    replaceSymbols,
    readScriptToken,
    parseBigOperatorAt,
    parseMatrixAt,
    parseDeterminantAt,
    parseLatexMatrixAt,
  };
  if (typeof module !== "undefined" && module.exports) module.exports = api;
  if (typeof window !== "undefined") {
    window.ANVAYAAssessmentMath = api;
    if (typeof document !== "undefined") {
      if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", () => renderAll(document));
      else renderAll(document);
    }
  }
})();
