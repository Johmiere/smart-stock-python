let csrfValue = "";
let currentUser = null;
let specialDiscountRate = 0.20;

async function api(path, options) {
  const opts = options || {};
  const method = (opts.method || "GET").toUpperCase();
  const headers = new Headers(opts.headers || {});
  let body = opts.body;
  if (body && !(body instanceof FormData) && typeof body !== "string") {
    headers.set("Content-Type", "application/json");
    body = JSON.stringify(body);
  }
  if (method !== "GET" && method !== "HEAD") {
    if (!csrfValue) await refreshCsrf();
    headers.set("X-CSRF-Token", csrfValue);
  }
  const response = await fetch(path, {
    method: method,
    headers: headers,
    body: body,
    credentials: "same-origin"
  });
  let data = {};
  try { data = await response.json(); } catch (_) { data = {}; }
  if (!response.ok) {
    if (response.status === 401 && document.body.dataset.page) {
      window.location.href = "/";
    }
    throw new Error(data.detail || "Request failed. Check the API and database.");
  }
  return data;
}

async function refreshCsrf() {
  const response = await fetch("/api/auth/csrf", { credentials: "same-origin" });
  const data = await response.json();
  csrfValue = data.csrf_token || "";
  return csrfValue;
}

function showMessage(target, message, kind) {
  if (!target) return;
  target.textContent = message || "";
  target.className = "notice" + (kind ? " " + kind : "");
}

function addCell(row, value) {
  const cell = document.createElement("td");
  cell.textContent = value === null || value === undefined || value === "" ? "—" : String(value);
  row.appendChild(cell);
  return cell;
}

function buildTable(container, headers, dataRows) {
  container.replaceChildren();
  const table = document.createElement("table");
  table.className = "product-table";
  const thead = document.createElement("thead");
  const headerRow = document.createElement("tr");
  headers.forEach(function (label) {
    const th = document.createElement("th");
    th.textContent = label;
    headerRow.appendChild(th);
  });
  thead.appendChild(headerRow);
  const tbody = document.createElement("tbody");
  if (!dataRows.length) {
    const row = document.createElement("tr");
    const cell = document.createElement("td");
    cell.colSpan = headers.length;
    cell.textContent = "No records yet.";
    row.appendChild(cell);
    tbody.appendChild(row);
  }
  dataRows.forEach(function (values) {
    const tr = document.createElement("tr");
    values.forEach(function (value) { addCell(tr, value); });
    tbody.appendChild(tr);
  });
  table.append(thead, tbody);
  container.appendChild(table);
}

function makeStatus(status) {
  const badge = document.createElement("span");
  badge.className = "status-badge status-" + (status || "unknown");
  badge.textContent = status || "unknown";
  return badge;
}

async function loadProfile() {
  currentUser = await api("/api/auth/me");
  const name = document.getElementById("profile-name");
  const role = document.getElementById("profile-role");
  const avatar = document.getElementById("avatar");
  if (name) name.textContent = (currentUser.first_name + " " + currentUser.last_name).trim();
  if (role) role.textContent = currentUser.role;
  if (avatar) avatar.textContent = (currentUser.first_name || "S").slice(0, 1).toUpperCase();
}

function attachLogout() {
  document.querySelectorAll("[data-logout]").forEach(function (button) {
    button.addEventListener("click", async function () {
      try {
        await api("/api/auth/logout", { method: "POST" });
        window.location.href = "/";
      } catch (error) {
        alert(error.message);
      }
    });
  });
}

async function initAuthPage() {
  await refreshCsrf();
  const loginForm = document.getElementById("login-form");
  const registerForm = document.getElementById("register-form");
  const message = document.getElementById("auth-message");
  document.querySelectorAll("[data-auth-tab]").forEach(function (button) {
    button.addEventListener("click", function () {
      const register = button.dataset.authTab === "register";
      loginForm.hidden = register;
      registerForm.hidden = !register;
      showMessage(message, "", "");
    });
  });

  async function fillSelect(url, select, valueKey, labelKey) {
    const list = await api(url);
    list.forEach(function (item) {
      const option = document.createElement("option");
      option.value = item[valueKey];
      option.textContent = item[labelKey];
      select.appendChild(option);
    });
  }
  try {
    await fillSelect("/api/locations/provinces", document.getElementById("province"), "prov_id", "prov_name");
    await fillSelect("/api/locations/stores", document.getElementById("store-select"), "store_id", "store_name");
  } catch (error) {
    showMessage(message, "Cannot load registration lists. " + error.message, "error");
  }
  const province = document.getElementById("province");
  const municipality = document.getElementById("municipality");
  const barangay = document.getElementById("barangay");
  province.addEventListener("change", async function () {
    municipality.replaceChildren(new Option("Select municipality", ""));
    barangay.replaceChildren(new Option("Select barangay", ""));
    municipality.disabled = true;
    barangay.disabled = true;
    if (!province.value) return;
    try {
      await fillSelect("/api/locations/municipalities?province_id=" + encodeURIComponent(province.value), municipality, "mun_id", "mun_name");
      municipality.disabled = false;
    } catch (error) { showMessage(message, error.message, "error"); }
  });
  municipality.addEventListener("change", async function () {
    barangay.replaceChildren(new Option("Select barangay", ""));
    barangay.disabled = true;
    if (!municipality.value) return;
    try {
      await fillSelect("/api/locations/barangays?municipality_id=" + encodeURIComponent(municipality.value), barangay, "brgy_id", "brgy_name");
      barangay.disabled = false;
    } catch (error) { showMessage(message, error.message, "error"); }
  });
  document.querySelectorAll('input[name="store-option"]').forEach(function (radio) {
    radio.addEventListener("change", function () {
      const creating = document.querySelector('input[name="store-option"]:checked').value === "new";
      document.getElementById("existing-store-group").hidden = creating;
      document.getElementById("new-store-group").hidden = !creating;
      document.getElementById("store-select").required = !creating;
      document.getElementById("new-store-name").required = creating;
    });
  });
  loginForm.addEventListener("submit", async function (event) {
    event.preventDefault();
    showMessage(message, "Signing in…", "");
    try {
      const data = await api("/api/auth/login", {
        method: "POST",
        body: {
          email: document.getElementById("login-email").value,
          password: document.getElementById("login-password").value
        }
      });
      window.location.href = data.next || "/dashboard.html";
    } catch (error) { showMessage(message, error.message, "error"); }
  });
  registerForm.addEventListener("submit", async function (event) {
    event.preventDefault();
    showMessage(message, "Creating account…", "");
    const storeOption = document.querySelector('input[name="store-option"]:checked').value;
    try {
      const data = await api("/api/auth/register", {
        method: "POST",
        body: {
          first_name: document.getElementById("first-name").value,
          middle_name: document.getElementById("middle-name").value,
          suffix_name: document.getElementById("suffix-name").value,
          last_name: document.getElementById("last-name").value,
          email: document.getElementById("register-email").value,
          password: document.getElementById("register-password").value,
          confirm_password: document.getElementById("confirm-password").value,
          barangay_id: Number(barangay.value),
          store_option: storeOption,
          store_id: storeOption === "existing" ? Number(document.getElementById("store-select").value) : null,
          custom_store_name: document.getElementById("new-store-name").value
        }
      });
      const registeredEmail = document.getElementById("register-email").value;
      registerForm.reset();
      loginForm.hidden = false;
      registerForm.hidden = true;
      document.getElementById("login-email").value = registeredEmail;
      showMessage(message, data.message + " Your role is " + data.role + ".", "success");
      await refreshCsrf();
    } catch (error) { showMessage(message, error.message, "error"); }
  });
}

async function loadDashboard() {
  const summary = await api("/api/dashboard/summary");
  document.getElementById("store-name").textContent = summary.store_name || "Store overview";
  document.getElementById("weekly-sales").textContent = summary.weekly_sales_quantity;
  document.getElementById("weekly-orders").textContent = summary.weekly_sale_lines;
  document.getElementById("products-count").textContent = summary.products_count;
  document.getElementById("stock-units").textContent = summary.stock_units;
  const chart = document.getElementById("sales-chart");
  chart.replaceChildren();
  const max = Math.max(1, ...summary.chart.map(function (d) { return d.quantity; }));
  summary.chart.forEach(function (day) {
    const col = document.createElement("div");
    col.className = "chart-column";
    const value = document.createElement("strong");
    value.textContent = day.quantity;
    const bar = document.createElement("div");
    bar.className = "chart-bar";
    bar.style.height = Math.max(3, Math.round((day.quantity / max) * 100)) + "px";
    const label = document.createElement("span");
    label.textContent = day.label;
    col.append(value, bar, label);
    chart.appendChild(col);
  });
  const ai = await api("/api/ai/items");
  document.getElementById("model-label").textContent = ai.chronos_loaded ? "Chronos-Bolt · " + ai.model : "Moving-average fallback · Chronos not loaded";
  renderAiTable(document.getElementById("ai-table-wrap"), ai.items);
}

function renderAiTable(container, items) {
  container.replaceChildren();
  const table = document.createElement("table");
  table.className = "product-table";
  const headers = ["Product", "Stock", "Nearest expiry", "Forecast until expiry", "Range", "Status", "Low stock"];
  const trHead = document.createElement("tr");
  headers.forEach(function (label) { const th = document.createElement("th"); th.textContent = label; trHead.appendChild(th); });
  const thead = document.createElement("thead");
  thead.appendChild(trHead);
  const tbody = document.createElement("tbody");
  if (!items.length) {
    const tr = document.createElement("tr");
    const td = document.createElement("td");
    td.colSpan = headers.length;
    td.textContent = "No products yet. Add a product to see monitoring.";
    tr.appendChild(td);
    tbody.appendChild(tr);
  }
  items.forEach(function (item) {
    const tr = document.createElement("tr");
    addCell(tr, item.product_name);
    addCell(tr, item.current_stock + " " + item.unit);
    addCell(tr, item.nearest_expiry || "Expiry unknown");
    addCell(tr, item.forecast_until_expiry === null ? "—" : item.forecast_until_expiry);
    addCell(tr, item.forecast_low === null ? "—" :
      (item.forecast_range_available ? item.forecast_low + "–" + item.forecast_high : "No interval"));
    const statusCell = document.createElement("td");
    statusCell.appendChild(makeStatus(item.status));
    tr.appendChild(statusCell);
    const lowCell = document.createElement("td");
    if (item.low_stock) {
      const badge = makeStatus("blue");
      badge.textContent = "Reorder";
      lowCell.appendChild(badge);
    } else {
      lowCell.textContent = "—";
    }
    tr.appendChild(lowCell);
    tbody.appendChild(tr);
  });
  table.append(thead, tbody);
  container.appendChild(table);
}

async function loadProducts() {
  const products = await api("/api/products");
  document.getElementById("product-count").textContent = products.length + " products";
  const select = document.getElementById("adjust-product");
  select.replaceChildren(new Option("Select product", ""));
  products.forEach(function (product) {
    const option = document.createElement("option");
    option.value = product.product_id;
    option.textContent = product.product_name + " (" + product.product_quantity + ")";
    select.appendChild(option);
  });
  const wrap = document.getElementById("products-table");
  const headers = ["ID", "Name", "Barcode", "Stock", "Price", "Date added", "Store", "Action"];
  wrap.replaceChildren();
  const table = document.createElement("table");
  table.className = "product-table";
  const head = document.createElement("thead");
  const rowHead = document.createElement("tr");
  headers.forEach(function (name) { const th = document.createElement("th"); th.textContent = name; rowHead.appendChild(th); });
  head.appendChild(rowHead);
  const body = document.createElement("tbody");
  if (!products.length) {
    const row = document.createElement("tr"); const cell = document.createElement("td");
    cell.colSpan = headers.length; cell.textContent = "No products yet."; row.appendChild(cell); body.appendChild(row);
  }
  products.forEach(function (product) {
    const tr = document.createElement("tr");
    addCell(tr, product.product_id);
    addCell(tr, product.product_name);
    addCell(tr, product.product_barcode);
    addCell(tr, product.product_quantity + " " + (product.product_unit || "pieces"));
    addCell(tr, "₱" + Number(product.product_price || 0).toFixed(2));
    addCell(tr, product.product_date_added || "—");
    addCell(tr, product.store_name);
    const action = document.createElement("td");
    if (currentUser.role === "owner" && !Number(product.has_sales) && !Number(product.has_movements)) {
      const button = document.createElement("button");
      button.className = "btn btn-danger";
      button.textContent = "Delete";
      button.addEventListener("click", async function () {
        if (!confirm("Delete this product?")) return;
        try { await api("/api/products/" + product.product_id, { method: "DELETE" }); await loadProducts(); }
        catch (error) { showMessage(document.getElementById("page-message"), error.message, "error"); }
      });
      action.appendChild(button);
    } else {
      action.textContent = Number(product.has_sales) || Number(product.has_movements) ? "History retained" : "—";
    }
    tr.appendChild(action);
    body.appendChild(tr);
  });
  table.append(head, body);
  wrap.appendChild(table);
  document.getElementById("add-product-panel").hidden = currentUser.role !== "owner";
}

function initProducts() {
  const productForm = document.getElementById("product-form");
  productForm.addEventListener("submit", async function (event) {
    event.preventDefault();
    try {
      await api("/api/products", {
        method: "POST",
        body: {
          product_name: document.getElementById("product-name").value,
          product_barcode: document.getElementById("product-barcode").value,
          product_quantity: Number(document.getElementById("product-quantity").value),
          category: document.getElementById("product-category").value,
          unit: document.getElementById("product-unit").value,
          price: Number(document.getElementById("product-price").value),
          reorder_level: Number(document.getElementById("reorder-level").value),
          supplier_lead_time_days: Number(document.getElementById("lead-time").value),
          safety_stock_units: Number(document.getElementById("safety-stock").value),
          expiry_date: document.getElementById("product-expiry").value || null
        }
      });
      productForm.reset();
      showMessage(document.getElementById("page-message"), "Product added.", "success");
      await loadProducts();
    } catch (error) { showMessage(document.getElementById("page-message"), error.message, "error"); }
  });
  document.getElementById("adjust-form").addEventListener("submit", async function (event) {
    event.preventDefault();
    try {
      const id = document.getElementById("adjust-product").value;
      await api("/api/products/" + id + "/stock-adjustments", {
        method: "POST",
        body: {
          action: document.getElementById("adjust-action").value,
          quantity: Number(document.getElementById("adjust-quantity").value),
          notes: document.getElementById("adjust-notes").value,
          expiry_date: document.getElementById("adjust-expiry").value || null
        }
      });
      showMessage(document.getElementById("page-message"), "Stock updated.", "success");
      event.target.reset();
      await loadProducts();
    } catch (error) { showMessage(document.getElementById("page-message"), error.message, "error"); }
  });
}

let cart = [];
async function lookupSaleBarcode() {
  const barcode = document.getElementById("sale-barcode").value.trim();
  const preview = document.getElementById("scan-preview");
  if (!barcode) return null;
  try {
    const product = await api("/api/products/lookup?barcode=" + encodeURIComponent(barcode));
    preview.textContent = product.product_name + " · " + product.product_quantity + " in stock · ₱" + Number(product.product_price || 0).toFixed(2);
    preview.className = "muted-text notice success";
    return product;
  } catch (error) {
    preview.textContent = error.message;
    preview.className = "muted-text notice error";
    return null;
  }
}

function paintCart() {
  const wrap = document.getElementById("cart-table");
  wrap.replaceChildren();
  const table = document.createElement("table");
  table.className = "product-table";
  const head = document.createElement("thead");
  const hrow = document.createElement("tr");
  ["Product", "Barcode", "Qty", "Unit price", "Subtotal", ""].forEach(function (label) {
    const th = document.createElement("th"); th.textContent = label; hrow.appendChild(th);
  });
  head.appendChild(hrow);
  const body = document.createElement("tbody");
  let subtotal = 0;
  cart.forEach(function (line, index) {
    const tr = document.createElement("tr");
    addCell(tr, line.product.product_name);
    addCell(tr, line.product.product_barcode);
    addCell(tr, line.quantity);
    addCell(tr, "₱" + Number(line.product.product_price || 0).toFixed(2));
    const lineTotal = Number(line.product.product_price || 0) * line.quantity;
    subtotal += lineTotal;
    addCell(tr, "₱" + lineTotal.toFixed(2));
    const td = document.createElement("td");
    const remove = document.createElement("button"); remove.type = "button"; remove.className = "btn btn-danger cart-remove"; remove.textContent = "Remove";
    remove.addEventListener("click", function () { cart.splice(index, 1); paintCart(); });
    td.appendChild(remove); tr.appendChild(td); body.appendChild(tr);
  });
  if (!cart.length) {
    const tr = document.createElement("tr"); const td = document.createElement("td");
    td.colSpan = 6; td.textContent = "Cart is empty."; tr.appendChild(td); body.appendChild(tr);
  }
  table.append(head, body); wrap.appendChild(table);
  const discountType = document.getElementById("discount-type").value;
  const total = discountType === "none" ? subtotal : subtotal * (1 - specialDiscountRate);
  document.getElementById("cart-total").textContent = "Total: ₱" + total.toFixed(2);
}

async function loadSalesPage() {
  const discountConfig = await api("/api/public-config");
  specialDiscountRate = Number(discountConfig.special_discount_rate || 0);
  document.querySelector(".small-note").textContent =
    "Special discount rate: " + (specialDiscountRate * 100).toFixed(0) +
    "%. Confirm the store's required discount and tax policy before real transactions.";
  const barcode = document.getElementById("sale-barcode");
  document.getElementById("add-cart-item").addEventListener("click", async function () {
    const product = await lookupSaleBarcode();
    if (!product) return;
    const quantity = Number(document.getElementById("sale-quantity").value);
    if (!Number.isInteger(quantity) || quantity < 1) return;
    const found = cart.find(function (line) { return line.product.product_id === product.product_id; });
    if (found) found.quantity += quantity;
    else cart.push({ product: product, quantity: quantity });
    barcode.value = "";
    document.getElementById("sale-quantity").value = "1";
    document.getElementById("scan-preview").textContent = "Scan another item or complete checkout.";
    paintCart();
    barcode.focus();
  });
  barcode.addEventListener("keydown", async function (event) {
    if (event.key === "Enter") {
      event.preventDefault();
      document.getElementById("add-cart-item").click();
    }
  });
  document.getElementById("discount-type").addEventListener("change", paintCart);
  document.getElementById("complete-sale").addEventListener("click", async function () {
    if (!cart.length) return showMessage(document.getElementById("page-message"), "Add at least one product.", "error");
    if (!confirm("Has checkout been completed? Record this sale?")) return;
    try {
      const result = await api("/api/sales", {
        method: "POST",
        body: {
          items: cart.map(function (line) { return { product_id: line.product.product_id, quantity: line.quantity }; }),
          discount_type: document.getElementById("discount-type").value,
          discount_reference: document.getElementById("discount-reference").value
        }
      });
      cart = [];
      paintCart();
      showMessage(document.getElementById("page-message"), result.message + " Total: ₱" + result.total.toFixed(2), "success");
      await loadSalesData();
    } catch (error) { showMessage(document.getElementById("page-message"), error.message, "error"); }
  });
  paintCart();
  await loadSalesData();
}

async function loadSalesData() {
  const ai = await api("/api/ai/items");
  document.getElementById("sales-model-label").textContent = ai.chronos_loaded ? "Chronos-Bolt" : "Moving-average fallback";
  renderAiTable(document.getElementById("sales-ai-table"), ai.items);
  const bestSellers = await api("/api/sales/best-sellers");
  buildTable(document.getElementById("best-sellers"), ["Product", "Barcode", "Sold"],
    bestSellers.map(function (item) { return [item.product_name, item.product_barcode, item.sold_last_30_days]; }));
  const sales = await api("/api/sales?limit=25");
  buildTable(document.getElementById("recent-sales"), ["Date & time", "Product", "Barcode", "Quantity", "Price", "Discount"], sales.map(function (item) {
    return [item.sale_date, item.product_name, item.product_barcode, item.sale_quantity, "₱" + Number(item.sale_unit_price || 0).toFixed(2), item.discount_type || "none"];
  }));
}

let historyPage = 1;
async function loadHistory() {
  const params = new URLSearchParams({ page: String(historyPage), page_size: "25" });
  const type = document.getElementById("history-type").value;
  const from = document.getElementById("history-from").value;
  const to = document.getElementById("history-to").value;
  if (type) params.set("movement_type", type);
  if (from) params.set("date_from", from);
  if (to) params.set("date_to", to);
  const movements = await api("/api/stock/movements?" + params.toString());
  document.getElementById("movement-count").textContent = movements.total + " records";
  document.getElementById("history-page").textContent = "Page " + movements.page;
  buildTable(document.getElementById("movement-table"),
    ["Date & time", "Product", "Change", "Qty", "Before", "After", "Recorded by", "Notes"],
    movements.items.map(function (m) {
      return [m.movement_date, m.product_name, m.movement_type, m.quantity, m.previous_quantity, m.new_quantity,
        ((m.users_fname || "") + " " + (m.users_lname || "")).trim(), m.notes];
    })
  );
  const stock = await api("/api/stock");
  buildTable(document.getElementById("current-stock"), ["Product", "Barcode", "On hand", "Nearest expiry"],
    stock.map(function (p) { return [p.product_name, p.product_barcode, p.current_stock, p.nearest_expiry]; }));
  document.getElementById("history-prev").disabled = historyPage <= 1;
  document.getElementById("history-next").disabled = historyPage * 25 >= movements.total;
}

async function loadLowStock() {
  const data = await api("/api/ai/items?status=blue");
  document.getElementById("low-stock-model").textContent = data.chronos_loaded ? "Chronos-Bolt" : "Moving-average fallback";
  buildTable(document.getElementById("low-stock-table"),
    ["Product", "Stock", "Lead time demand", "Safety stock", "Suggested action"],
    data.items.map(function (p) {
      return [p.product_name, p.current_stock + " " + p.unit, p.lead_time_demand, p.safety_stock_units, p.low_stock_action || "Review reorder level"];
    })
  );
}

async function loadReports() {
  const ai = await api("/api/ai/items");
  document.getElementById("report-model-status").textContent = ai.chronos_loaded ? "Chronos loaded" : "Fallback active";
  document.getElementById("report-model-detail").textContent = ai.chronos_loaded
    ? "Model: " + ai.model
    : "Chronos model is not loaded. Current forecasts identify their method as moving_average_fallback.";
  const result = await api("/api/ai/evaluation");
  document.getElementById("evaluation-message").textContent = result.message || "Evaluation results loaded.";
  buildTable(document.getElementById("evaluation-table"), ["Model", "MAE", "RMSE", "WAPE", "Precision", "Recall", "F1"],
    (result.results || []).map(function (r) {
      return [r.model, r.mae, r.rmse, r.wape, r.precision, r.recall, r.f1];
    })
  );
  const importForm = document.getElementById("sales-import-form");
  if (!importForm.dataset.bound) {
    importForm.dataset.bound = "true";
    importForm.addEventListener("submit", async function (event) {
      event.preventDefault();
      const file = document.getElementById("sales-csv").files[0];
      if (!file) return;
      const form = new FormData(); form.append("file", file);
      try {
        const imported = await api("/api/imports/sales", { method: "POST", body: form });
        document.getElementById("import-result").textContent = JSON.stringify(imported, null, 2);
        await loadReports();
      } catch (error) { document.getElementById("import-result").textContent = error.message; }
    });
  }
}

async function loadUsers() {
  try {
    const users = await api("/api/users");
    document.getElementById("users-message").textContent = "";
    buildTable(document.getElementById("users-table"), ["ID", "Name", "Email", "Role"],
      users.map(function (u) { return [u.users_id, (u.users_fname || "") + " " + (u.users_lname || ""), u.cre_username, u.users_role]; }));
  } catch (error) {
    showMessage(document.getElementById("users-message"), error.message, "error");
  }
}

function initAssistant() {
  const form = document.getElementById("assistant-form");
  form.addEventListener("submit", async function (event) {
    event.preventDefault();
    const answer = document.getElementById("assistant-answer");
    answer.textContent = "Checking current inventory…";
    try {
      const result = await api("/api/assistant/ask", {
        method: "POST",
        body: { question: document.getElementById("assistant-question").value }
      });
      answer.textContent = result.answer;
      document.getElementById("assistant-data").textContent = JSON.stringify(result.data_used, null, 2);
    } catch (error) { answer.textContent = error.message; }
  });
}

async function initAppPage(page) {
  await refreshCsrf();
  try { await loadProfile(); }
  catch (_) { window.location.href = "/"; return; }
  attachLogout();
  if (page === "dashboard") { await loadDashboard(); initAssistant(); }
  if (page === "products") { initProducts(); await loadProducts(); }
  if (page === "sales") { await loadSalesPage(); }
  if (page === "stock-history") {
    document.getElementById("history-filter").addEventListener("submit", function (event) { event.preventDefault(); historyPage = 1; loadHistory(); });
    document.getElementById("history-prev").addEventListener("click", function () { historyPage = Math.max(1, historyPage - 1); loadHistory(); });
    document.getElementById("history-next").addEventListener("click", function () { historyPage += 1; loadHistory(); });
    await loadHistory();
  }
  if (page === "low-stock") await loadLowStock();
  if (page === "reports") await loadReports();
  if (page === "users") await loadUsers();
}

document.addEventListener("DOMContentLoaded", function () {
  const page = document.body.dataset.page;
  if (page) initAppPage(page).catch(function (error) {
    const message = document.getElementById("page-message");
    if (message) showMessage(message, error.message, "error");
    else console.error(error);
  });
  else initAuthPage().catch(function (error) {
    showMessage(document.getElementById("auth-message"), error.message, "error");
  });
});
