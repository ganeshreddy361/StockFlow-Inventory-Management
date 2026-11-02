import { useState } from "react";
import "./App.css";

const API = "http://127.0.0.1:8108";
const AUTH_API = "http://127.0.0.1:8101";
const PRODUCT_API = "http://127.0.0.1:8102";

export default function App() {
  const [token, setToken] = useState("");
  const [inputToken, setInputToken] = useState("");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [section, setSection] = useState("Overview");
  const [data, setData] = useState({});
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(false);
  const [editingProduct, setEditingProduct] = useState(null);

  async function createProduct(product) {
    setError("");
    setLoading(true);
    try {
      const response = await fetch(`${PRODUCT_API}/products`, {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          Authorization: `Bearer ${token}`,
        },
        body: JSON.stringify(product),
      });
      const result = await response.json();
      if (!response.ok) {
        throw new Error(
          typeof result.detail === "string"
            ? result.detail
            : JSON.stringify(result.detail || result)
        );
      }
      if (Number(product.stock) > 0) {
        const stockResponse = await fetch("http://127.0.0.1:8103/stock/adjust", {
          method: "POST",
          headers: {
            "Content-Type": "application/json",
            Authorization: `Bearer ${token}`,
          },
          body: JSON.stringify({
            product_id: result.id,
            change_quantity: Number(product.stock),
            reason: "Initial stock received",
          }),
        });

        const stockResult = await stockResponse.json();

        if (!stockResponse.ok) {
          throw new Error(
            "Product was created, but initial inventory could not be added: " +
            (stockResult.detail || stockResponse.status)
          );
        }
      }

      await loadDashboard(token);
      setSection("Products");
      return true;
    } catch (e) {
      setError(e.message || "Unable to create product.");
      return false;
    } finally {
      setLoading(false);
    }
  }

  async function updateProduct(product) {
    setError("");
    setLoading(true);

    try {
      const response = await fetch(`${PRODUCT_API}/products/${product.id}`, {
        method: "PUT",
        headers: {
          "Content-Type": "application/json",
          Authorization: `Bearer ${token}`,
        },
        body: JSON.stringify({
          name: product.name.trim(),
          description: product.description.trim(),
          category: product.category.trim(),
          price: Number(product.price),
          stock: Number(product.stock),
        }),
      });

      const result = await response.json();

      if (!response.ok) {
        throw new Error(
          typeof result.detail === "string"
            ? result.detail
            : JSON.stringify(result.detail || result)
        );
      }

      await loadDashboard(token);
      setEditingProduct(null);
      return true;
    } catch (e) {
      setError(e.message || "Unable to update product.");
      return false;
    } finally {
      setLoading(false);
    }
  }

  async function loadDashboard(accessToken) {
    setLoading(true);
    setError("");
    try {
      const paths = {
        Overview: "/dashboard/summary",
        Products: "/dashboard/products",
        Orders: "/dashboard/orders",
        Inventory: "/dashboard/inventory",
        Sales: "/dashboard/sales",
        Customers: "/dashboard/customers",
      };
      const results = await Promise.all(
        Object.entries(paths).map(async ([key, path]) => {
          const response = await fetch(API + path, {
            headers: { Authorization: `Bearer ${accessToken}` },
          });
          if (!response.ok) {
            throw new Error(`API ${response.status}: ${await response.text()}`);
          }
          return [key, await response.json()];
        })
      );
      setData(Object.fromEntries(results));
      setToken(accessToken);
    } catch (e) {
      setError(e.message);
    } finally {
      setLoading(false);
    }
  }

  const money = (v) =>
    new Intl.NumberFormat("en-IN", {
      style: "currency",
      currency: "INR",
      maximumFractionDigits: 2,
    }).format(Number(v || 0));

  if (!token) {
    return (
      <main className="login">
        <form className="login-card" onSubmit={async (e) => {
          e.preventDefault();
          setLoading(true);
          setError("");
          try {
            const response = await fetch(`${AUTH_API}/login`, {
              method: "POST",
              headers: { "Content-Type": "application/json" },
              body: JSON.stringify({ email: email.trim(), password }),
            });
            const result = await response.json();
            if (!response.ok) {
              throw new Error(result.detail || `Login failed (${response.status})`);
            }
            if (result.user?.role !== "Admin") {
              throw new Error("This account is not an Admin account.");
            }
            await loadDashboard(result.access_token);
          } catch (err) {
            setError(err.message || "Unable to sign in.");
          } finally {
            setLoading(false);
          }
        }}>
          <div className="logo">S</div>
          <p className="eyebrow">INVENTORY MANAGEMENT</p>
          <h1>Admin Dashboard</h1>
          <p className="muted">Connect to your existing FastAPI service.</p>
          <label>Email address</label>
          <input type="email" value={email}
            onChange={(e) => setEmail(e.target.value)}
            placeholder="admin_test@example.com" required />
          <label>Password</label>
          <input type="password" value={password}
            onChange={(e) => setPassword(e.target.value)}
            placeholder="Enter your password" required />
          <button className="primary" disabled={loading}>
            {loading ? "Signing in..." : "Sign in"}
          </button>
          {error && <p className="error">{error}</p>}
          <p className="muted small">Sign in with your existing Admin account.</p>
        </form>
      </main>
    );
  }

  const summary = data.Overview || {};
  const titles = ["Overview", "Products", "Orders", "Inventory", "Sales", "Customers", "Reports"];
  const rows = {
    Products: data.Products?.products || [],
    Orders: data.Orders?.orders || [],
    Inventory: data.Inventory?.inventory || [],
  };

  return (
    <div className="layout">
      <aside className="sidebar">
        <div className="brand"><span className="logo">S</span><div><b>StockFlow</b><small>ADMIN PANEL</small></div></div>
        <p className="eyebrow">WORKSPACE</p>
        {titles.map((s, i) => (
          <button key={s} className={`nav ${section === s ? "selected" : ""}`}
            onClick={() => setSection(s)}>
            <span>{["⌂", "▦", "▤", "▣", "↗", "♙", "⇩"][i]}</span>{s}
          </button>
        ))}
        <div className="side-bottom">● API connection ready
          <button className="logout" onClick={() => { setToken(""); setInputToken(""); setData({}); }}>Log out</button>
        </div>
      </aside>

      <main className="main">
        <header className="topbar">
          <div><p className="eyebrow">INVENTORY & ORDER MANAGEMENT</p><h1>{section}</h1></div>
          <button className="secondary" onClick={() => loadDashboard(token)}>↻ Refresh</button>
        </header>

        {error && <div className="error">{error}</div>}
        {loading && <p className="muted">Loading data...</p>}

        {section === "Overview" && (
          <>
            <section className="hero">
              <div><p className="eyebrow">BUSINESS OVERVIEW</p><h2>Your operations, at a glance.</h2>
              <p>Monitor orders, stock and payment performance in one place.</p></div>
              <span className="hero-icon">↗</span>
            </section>
            <div className="metrics">
              <Metric label="Total Products" value={summary.products?.total ?? "—"} icon="▦" />
              <Metric label="Total Orders" value={summary.orders?.total ?? "—"} icon="▤" />
              <Metric label="Available Units" value={summary.inventory?.total_units_available ?? "—"} icon="▣" />
              <Metric label="Successful Revenue" value={money(summary.sales?.successful_payment_revenue)} icon="₹" />
            </div>
            <div className="grid">
              <section className="panel"><h3>Order status</h3>
                {Object.entries(summary.orders?.by_status || {}).map(([status, count]) =>
                  <div className="stat" key={status}><span>{status}</span><b>{count}</b></div>)}
                {!Object.keys(summary.orders?.by_status || {}).length && <p className="muted">No order data.</p>}
              </section>
              <section className="panel"><h3>Inventory health</h3>
                <div className="stat"><span>Tracked products</span><b>{summary.inventory?.tracked_products ?? 0}</b></div>
                <div className="stat"><span>Low stock (≤ 5)</span><b className="warning">{summary.inventory?.low_stock_products ?? 0}</b></div>
                <div className="stat"><span>Out of stock</span><b className="danger">{summary.inventory?.out_of_stock_products ?? 0}</b></div>
              </section>
            </div>
          </>
        )}

        {section === "Products" && (
          <>
            <ProductForm onCreate={createProduct} loading={loading} />

            {editingProduct && (
              <ProductEditForm
                key={editingProduct.id}
                product={editingProduct}
                onSave={updateProduct}
                onCancel={() => setEditingProduct(null)}
                loading={loading}
              />
            )}

            <Table
              title="Product catalog"
              rows={rows.Products}
              columns={[
                ["id", "ID"],
                ["name", "Product"],
                ["category", "Category"],
                ["price", "Price"],
                ["stock", "Catalog stock"],
              ]}
              format={(key, value) => key === "price" ? money(value) : value}
              renderActions={(product) => (
                <button
                  type="button"
                  className="secondary"
                  onClick={() => setEditingProduct(product)}
                >
                  Edit
                </button>
              )}
            />
          </>
        )}

        {section === "Orders" && (
          <OrderManagement
            rows={rows.Orders}
            token={token}
            onRefresh={() => loadDashboard(token)}
            money={money}
          />
        )}

        {section === "Inventory" && (
          <InventoryManagement
            rows={rows.Inventory}
            token={token}
            onRefresh={() => loadDashboard(token)}
          />
        )}

        {section === "Sales" && (
          <section className="panel"><h3>Payments by status</h3>
            <div className="metrics two">
              <Metric label="Successful Payments" value={summary.sales?.successful_payment_count ?? 0} icon="✓" />
              <Metric label="Successful Revenue" value={money(summary.sales?.successful_payment_revenue)} icon="₹" />
            </div>
            <Table title="Payment totals" rows={data.Sales?.payments_by_status || []}
              columns={[["status", "Status"], ["payment_count", "Payments"], ["total_amount", "Amount"]]}
              format={(key, value) => key === "total_amount" ? money(value) : value} />
            <Table title="Daily successful sales" rows={data.Sales?.successful_sales_by_day || []}
              columns={[["date", "Date"], ["payment_count", "Payments"], ["revenue", "Revenue"]]}
              format={(key, value) => key === "revenue" ? money(value) : value} />
            <p className="muted small">Revenue is based on successful payment records; refunds are not deducted.</p>
          </section>
        )}
        {section === "Reports" && (
          <ReportsManagement
            data={data}
            money={money}
          />
        )}

        {section === "Customers" && (
          <CustomerManagement
            rows={data.Customers?.customers || []}
            token={token}
            api={API}
            money={money}
          />
        )}

        <footer>StockFlow Admin · Connected to your local API</footer>
      </main>
    </div>
  );
}

function Metric({ label, value, icon }) {
  return <section className="metric"><div className="metric-head"><span>{label}</span><i>{icon}</i></div><strong>{value}</strong><small>From existing database</small></section>;
}

function Table({
  title,
  rows,
  columns,
  format = (_, value) => value,
  renderActions,
}) {
  const [search, setSearch] = useState("");
  const [statusFilter, setStatusFilter] = useState("All");

  const statuses = [...new Set(
    rows.map((row) => row.status).filter(Boolean)
  )];

  const filteredRows = rows.filter((row) => {
    const query = search.trim().toLowerCase();
    const matchesSearch = !query || columns.some(([key]) =>
      String(row[key] ?? "").toLowerCase().includes(query)
    );
    const matchesStatus =
      statusFilter === "All" ||
      String(row.status ?? "") === statusFilter;
    return matchesSearch && matchesStatus;
  });

  return (
    <section className="panel">
      <div className="table-heading">
        <h3>{title}</h3>
        <span className="row-count">{filteredRows.length} records</span>
      </div>

      <div className="table-tools">
        <input
          className="table-search"
          type="search"
          placeholder="Search this table..."
          value={search}
          onChange={(e) => setSearch(e.target.value)}
          aria-label={"Search " + title}
        />

        {statuses.length > 0 && (
          <select
            className="table-filter"
            value={statusFilter}
            onChange={(e) => setStatusFilter(e.target.value)}
            aria-label="Filter by status"
          >
            <option value="All">All statuses</option>
            {statuses.map((status) => (
              <option key={status} value={status}>{status}</option>
            ))}
          </select>
        )}
      </div>

      <div className="table-scroll">
        <table>
          <thead>
            <tr>
              {columns.map(([key, label]) => (
                <th key={key}>{label}</th>
              ))}
              {renderActions && <th>Actions</th>}
            </tr>
          </thead>
          <tbody>
            {filteredRows.map((row, i) => (
              <tr key={row.id ?? row.product_id ?? row.order_id ?? row.date ?? i}>
                {columns.map(([key]) => (
                  <td key={key}>
                    {String(format(key, row[key] ?? "—") ?? "—")}
                  </td>
                ))}
                {renderActions && (
                  <td className="table-actions">{renderActions(row)}</td>
                )}
              </tr>
            ))}
            {!filteredRows.length && (
              <tr>
                <td colSpan={columns.length + (renderActions ? 1 : 0)} className="empty">
                  No matching records found.
                </td>
              </tr>
            )}
          </tbody>
        </table>
      </div>
    </section>
  );
}


function ProductForm({ onCreate, loading }) {
  const [name, setName] = useState("");
  const [category, setCategory] = useState("");
  const [description, setDescription] = useState("");
  const [price, setPrice] = useState("");
  const [stock, setStock] = useState("0");
  const [message, setMessage] = useState("");

  async function submit(e) {
    e.preventDefault();
    setMessage("");
    const success = await onCreate({
      name: name.trim(),
      category: category.trim(),
      description: description.trim(),
      price: Number(price),
      stock: Number(stock),
    });
    if (success) {
      setName("");
      setCategory("");
      setDescription("");
      setPrice("");
      setStock("0");
      setMessage("Product created successfully.");
    }
  }

  return (
    <section className="panel">
      <h3>Add a product</h3>
      <form className="product-form" onSubmit={submit}>
        <label>
          Product name
          <input value={name} onChange={e => setName(e.target.value)}
            minLength={2} maxLength={150} required />
        </label>
        <label>
          Category
          <input value={category} onChange={e => setCategory(e.target.value)}
            minLength={2} maxLength={100} required />
        </label>
        <label className="form-wide">
          Description
          <textarea value={description}
            onChange={e => setDescription(e.target.value)} maxLength={2000} />
        </label>
        <label>
          Price (₹)
          <input type="number" value={price}
            onChange={e => setPrice(e.target.value)}
            min="0" max="100000000" step="0.01" required />
        </label>
        <label>
          Initial stock
          <input type="number" value={stock}
            onChange={e => setStock(e.target.value)}
            min="0" max="100000000" step="1" required />
        </label>
        <div className="form-wide">
          <button className="primary" disabled={loading}>
            {loading ? "Saving..." : "Add product"}
          </button>
          {message && <p className="success-message">{message}</p>}
        </div>
      </form>
    </section>
  );
}


function ProductEditForm({ product, onSave, onCancel, loading }) {
  const [name, setName] = useState(product.name || "");
  const [category, setCategory] = useState(product.category || "");
  const [description, setDescription] = useState(product.description || "");
  const [price, setPrice] = useState(String(product.price ?? ""));

  async function submit(e) {
    e.preventDefault();

    await onSave({
      id: product.id,
      name,
      category,
      description,
      price,
      // Preserve catalogue stock; actual inventory is managed separately.
      stock: product.stock,
    });
  }

  return (
    <section className="panel">
      <h3>Edit product #{product.id}</h3>

      <form className="product-form" onSubmit={submit}>
        <label>
          Product name
          <input value={name} onChange={e => setName(e.target.value)}
            minLength={2} maxLength={150} required />
        </label>

        <label>
          Category
          <input value={category} onChange={e => setCategory(e.target.value)}
            minLength={2} maxLength={100} required />
        </label>

        <label className="form-wide">
          Description
          <textarea value={description}
            onChange={e => setDescription(e.target.value)}
            maxLength={2000} />
        </label>

        <label>
          Price (₹)
          <input type="number" value={price}
            onChange={e => setPrice(e.target.value)}
            min="0" max="100000000" step="0.01" required />
        </label>

        <div className="form-wide">
          <button className="primary" disabled={loading}>
            {loading ? "Updating..." : "Save changes"}
          </button>
          <button type="button" className="secondary"
            onClick={onCancel} disabled={loading}>
            Cancel
          </button>
        </div>
      </form>
    </section>
  );
}


function InventoryManagement({ rows, token, onRefresh }) {
  const [selected, setSelected] = useState(null);
  const [mode, setMode] = useState("add");
  const [quantity, setQuantity] = useState("");
  const [reason, setReason] = useState("");
  const [movements, setMovements] = useState([]);
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState("");
  const [error, setError] = useState("");

  async function loadHistory(productId) {
    setError("");
    try {
      const response = await fetch(
        `http://127.0.0.1:8103/stock/${productId}/history`,
        { headers: { Authorization: `Bearer ${token}` } }
      );
      const result = await response.json();

      if (!response.ok) {
        throw new Error(result.detail || "Unable to load stock history.");
      }

      setMovements(result.movements || []);
    } catch (e) {
      setError(e.message);
      setMovements([]);
    }
  }

  async function selectProduct(product) {
    setSelected(product);
    setQuantity("");
    setReason("");
    setMessage("");
    setError("");
    await loadHistory(product.product_id);
  }

  async function submitAdjustment(e) {
    e.preventDefault();
    setError("");
    setMessage("");

    const amount = Number(quantity);

    if (!Number.isInteger(amount) || amount <= 0) {
      setError("Enter a valid whole number greater than zero.");
      return;
    }

    if (reason.trim().length < 3) {
      setError("Please enter a reason with at least 3 characters.");
      return;
    }

    const delta = mode === "add" ? amount : -amount;

    setBusy(true);
    try {
      const response = await fetch("http://127.0.0.1:8103/stock/adjust", {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          Authorization: `Bearer ${token}`,
        },
        body: JSON.stringify({
          product_id: selected.product_id,
          change_quantity: delta,
          reason: reason.trim(),
        }),
      });

      const result = await response.json();

      if (!response.ok) {
        throw new Error(
          typeof result.detail === "string"
            ? result.detail
            : JSON.stringify(result.detail || result)
        );
      }

      setMessage(
        `Stock updated successfully. Previous: ${result.previous_quantity}, New: ${result.new_quantity}.`
      );
      setQuantity("");
      setReason("");

      await onRefresh();
      await loadHistory(selected.product_id);
    } catch (e) {
      setError(e.message || "Stock adjustment failed.");
    } finally {
      setBusy(false);
    }
  }

  return (
    <section className="panel">
      <div className="table-heading">
        <h3>Inventory Management</h3>
        <span className="row-count">{rows.length} products</span>
      </div>

      <div className="table-wrap">
        <table>
          <thead>
            <tr>
              <th>Product</th>
              <th>Category</th>
              <th>Available stock</th>
              <th>Last updated</th>
              <th>Low stock</th>
              <th>Action</th>
            </tr>
          </thead>
          <tbody>
            {rows.map((product) => (
              <tr key={product.product_id}>
                <td>{product.product_name}</td>
                <td>{product.category}</td>
                <td>{product.quantity}</td>
                <td>{product.updated_at || "—"}</td>
                <td>{product.low_stock ? "Yes" : "No"}</td>
                <td>
                  <button
                    type="button"
                    className="secondary"
                    onClick={() => selectProduct(product)}
                  >
                    Manage stock
                  </button>
                </td>
              </tr>
            ))}
            {rows.length === 0 && (
              <tr><td colSpan="6">No inventory records found.</td></tr>
            )}
          </tbody>
        </table>
      </div>

      {selected && (
        <div className="stock-manager">
          <h3>Manage stock: {selected.product_name}</h3>
          <p>Current available quantity: <strong>{selected.quantity}</strong></p>

          <form onSubmit={submitAdjustment} className="stock-form">
            <label>
              Adjustment type
              <select value={mode} onChange={(e) => setMode(e.target.value)}>
                <option value="add">Add stock</option>
                <option value="reduce">Reduce stock</option>
              </select>
            </label>

            <label>
              Quantity
              <input
                type="number"
                min="1"
                step="1"
                value={quantity}
                onChange={(e) => setQuantity(e.target.value)}
                placeholder="Enter quantity"
                required
              />
            </label>

            <label>
              Reason
              <input
                type="text"
                minLength="3"
                maxLength="200"
                value={reason}
                onChange={(e) => setReason(e.target.value)}
                placeholder="Example: Additional stock received"
                required
              />
            </label>

            <div className="stock-buttons">
              <button type="submit" disabled={busy}>
                {busy ? "Updating..." : mode === "add" ? "Add Stock" : "Reduce Stock"}
              </button>
              <button
                type="button"
                className="secondary"
                onClick={() => {
                  setSelected(null);
                  setMovements([]);
                  setMessage("");
                  setError("");
                }}
              >
                Close
              </button>
            </div>
          </form>

          {message && <p className="stock-success">{message}</p>}
          {error && <p className="stock-error">{error}</p>}

          <h3>Stock History</h3>
          <div className="table-wrap">
            <table>
              <thead>
                <tr>
                  <th>Date</th>
                  <th>Change</th>
                  <th>Reason</th>
                </tr>
              </thead>
              <tbody>
                {movements.map((movement) => (
                  <tr key={movement.id}>
                    <td>{movement.created_at}</td>
                    <td>{movement.change_quantity > 0 ? "+" : ""}
                      {movement.change_quantity}</td>
                    <td>{movement.reason}</td>
                  </tr>
                ))}
                {movements.length === 0 && (
                  <tr><td colSpan="3">No stock movements found.</td></tr>
                )}
              </tbody>
            </table>
          </div>
        </div>
      )}
    </section>
  );
}


function OrderManagement({ rows, token, onRefresh, money }) {
  const [selectedOrder, setSelectedOrder] = useState(null);
  const [details, setDetails] = useState(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [message, setMessage] = useState("");

  async function viewDetails(order) {
    setSelectedOrder(order);
    setDetails(null);
    setError("");
    setMessage("");
    setBusy(true);

    try {
      const response = await fetch(
        `http://127.0.0.1:8105/orders/${order.id}`,
        { headers: { Authorization: `Bearer ${token}` } }
      );

      const result = await response.json();

      if (!response.ok) {
        throw new Error(
          typeof result.detail === "string"
            ? result.detail
            : JSON.stringify(result.detail || result)
        );
      }

      setDetails(result);
    } catch (e) {
      setError(e.message || "Unable to load order details.");
    } finally {
      setBusy(false);
    }
  }

  async function cancelOrder(order) {
    const confirmed = window.confirm(
      `Are you sure you want to cancel order ${order.order_number}? Reserved stock will be released.`
    );

    if (!confirmed) return;

    setBusy(true);
    setError("");
    setMessage("");

    try {
      const response = await fetch(
        `http://127.0.0.1:8105/orders/${order.id}/cancel`,
        {
          method: "POST",
          headers: { Authorization: `Bearer ${token}` },
        }
      );

      const result = await response.json();

      if (!response.ok) {
        throw new Error(
          typeof result.detail === "string"
            ? result.detail
            : JSON.stringify(result.detail || result)
        );
      }

      setMessage(result.message || "Order cancelled successfully.");
      setDetails(null);
      setSelectedOrder(null);

      await onRefresh();
    } catch (e) {
      setError(e.message || "Unable to cancel order.");
    } finally {
      setBusy(false);
    }
  }

  return (
    <section className="panel">
      <div className="table-heading">
        <h3>Order Management</h3>
        <span className="row-count">{rows.length} orders</span>
      </div>

      {message && <p className="stock-success">{message}</p>}
      {error && <p className="stock-error">{error}</p>}

      <div className="table-wrap">
        <table>
          <thead>
            <tr>
              <th>Order</th>
              <th>Customer ID</th>
              <th>Date</th>
              <th>Items</th>
              <th>Total</th>
              <th>Status</th>
              <th>Actions</th>
            </tr>
          </thead>
          <tbody>
            {rows.map((order) => (
              <tr key={order.id}>
                <td>{order.order_number}</td>
                <td>{order.user_id}</td>
                <td>{order.created_at}</td>
                <td>{order.total_item_quantity ?? order.item_line_count}</td>
                <td>{money(order.total_amount)}</td>
                <td>{order.status}</td>
                <td>
                  <div className="order-actions">
                    <button
                      type="button"
                      className="secondary"
                      disabled={busy}
                      onClick={() => viewDetails(order)}
                    >
                      View Details
                    </button>

                    {["Pending", "Confirmed"].includes(order.status) && (
                      <button
                        type="button"
                        className="danger-button"
                        disabled={busy}
                        onClick={() => cancelOrder(order)}
                      >
                        Cancel
                      </button>
                    )}
                  </div>
                </td>
              </tr>
            ))}

            {rows.length === 0 && (
              <tr><td colSpan="7">No orders found.</td></tr>
            )}
          </tbody>
        </table>
      </div>

      {busy && <p className="muted">Processing request...</p>}

      {selectedOrder && (
        <div className="order-details">
          <div className="table-heading">
            <h3>Order Details: {selectedOrder.order_number}</h3>
            <button
              type="button"
              className="secondary"
              onClick={() => {
                setSelectedOrder(null);
                setDetails(null);
                setError("");
              }}
            >
              Close
            </button>
          </div>

          {details && (
            <>
              <p><strong>Customer ID:</strong> {details.user_id}</p>
              <p><strong>Order status:</strong> {details.status}</p>
              <p><strong>Created:</strong> {details.created_at}</p>

              <div className="table-wrap">
                <table>
                  <thead>
                    <tr>
                      <th>Product</th>
                      <th>Product ID</th>
                      <th>Unit Price</th>
                      <th>Quantity</th>
                      <th>Subtotal</th>
                    </tr>
                  </thead>
                  <tbody>
                    {(details.items || []).map((item) => (
                      <tr key={item.product_id}>
                        <td>{item.product_name}</td>
                        <td>{item.product_id}</td>
                        <td>{money(item.unit_price)}</td>
                        <td>{item.quantity}</td>
                        <td>{money(item.unit_price * item.quantity)}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>

              <h3>Order Total: {money(details.total_amount)}</h3>

              {["Pending", "Confirmed"].includes(details.status) && (
                <button
                  type="button"
                  className="danger-button"
                  disabled={busy}
                  onClick={() => cancelOrder(details)}
                >
                  Cancel This Order
                </button>
              )}
            </>
          )}
        </div>
      )}
    </section>
  );
}


function CustomerManagement({ rows, token, api, money }) {
  const [search, setSearch] = useState("");
  const [selectedCustomer, setSelectedCustomer] = useState(null);
  const [history, setHistory] = useState(null);
  const [busy, setBusy] = useState(false);
  const [customerError, setCustomerError] = useState("");

  const filteredCustomers = rows.filter((customer) => {
    const query = search.trim().toLowerCase();
    return (
      !query ||
      customer.username?.toLowerCase().includes(query) ||
      customer.email?.toLowerCase().includes(query)
    );
  });

  async function viewOrders(customer) {
    setBusy(true);
    setCustomerError("");
    setSelectedCustomer(customer);
    setHistory(null);

    try {
      const response = await fetch(
        `${api}/dashboard/customers/${customer.id}/orders`,
        {
          headers: { Authorization: `Bearer ${token}` },
        }
      );

      const result = await response.json();

      if (!response.ok) {
        throw new Error(result.detail || "Unable to load customer orders.");
      }

      setHistory(result);
    } catch (error) {
      setCustomerError(error.message);
    } finally {
      setBusy(false);
    }
  }

  function formatDate(value) {
    if (!value) return "—";
    const date = new Date(value);
    return Number.isNaN(date.getTime())
      ? value
      : date.toLocaleDateString("en-IN", {
          day: "2-digit",
          month: "short",
          year: "numeric",
        });
  }

  const totalOrders = rows.reduce(
    (sum, customer) => sum + Number(customer.total_orders || 0), 0
  );

  const confirmedOrders = rows.reduce(
    (sum, customer) => sum + Number(customer.confirmed_orders || 0), 0
  );

  const totalPurchases = rows.reduce(
    (sum, customer) =>
      sum + Number(customer.confirmed_purchase_total ?? customer.purchase_total ?? 0), 0
  );

  return (
    <>
      <div className="metrics">
        <Metric label="Total Customers" value={rows.length} icon="♙" />
        <Metric label="Total Orders" value={totalOrders} icon="▤" />
        <Metric label="Confirmed Orders" value={confirmedOrders} icon="✓" />
        <Metric label="Confirmed Purchase Amount" value={money(totalPurchases)} icon="₹" />
      </div>

      <section className="panel">
      <div className="table-heading">
        <div>
          <h3>Customer Management</h3>
          <p className="muted">
            Registered customers and their purchase activity
          </p>
        </div>
        <strong>{rows.length} Customers</strong>
      </div>

      <input
        type="search"
        value={search}
        onChange={(e) => setSearch(e.target.value)}
        style={{ width: "100%", maxWidth: "520px", margin: "16px 0" }}
        placeholder="Search by customer name or email..."
        aria-label="Search customers"
      />

      <div className="table-wrap">
        <table>
          <thead>
            <tr>
              <th>ID</th>
              <th>Customer</th>
              <th>Email</th>
              <th>Registered</th>
              <th>Total Orders</th>
              <th>Confirmed Orders</th>
              <th>Purchase Amount</th>
              <th>Action</th>
            </tr>
          </thead>
          <tbody>
            {filteredCustomers.map((customer) => (
              <tr key={customer.id}>
                <td>{customer.id}</td>
                <td>{customer.username}</td>
                <td>{customer.email}</td>
                <td>{formatDate(customer.created_at)}</td>
                <td>{customer.total_orders ?? 0}</td>
                <td>{customer.confirmed_orders ?? 0}</td>
                <td>{money(customer.confirmed_purchase_total ?? customer.purchase_total)}</td>
                <td>
                  <button
                    type="button"
                    className="secondary"
                    disabled={busy}
                    onClick={() => viewOrders(customer)}
                  >
                    View Orders
                  </button>
                </td>
              </tr>
            ))}

            {filteredCustomers.length === 0 && (
              <tr>
                <td colSpan="8">No customers found.</td>
              </tr>
            )}
          </tbody>
        </table>
      </div>

      {selectedCustomer && (
        <div className="order-details">
          <div className="table-heading">
            <div>
              <h3>Customer Order History</h3>
              <p>
                <strong>{selectedCustomer.username}</strong> · {selectedCustomer.email}
              </p>
            </div>
            <button
              type="button"
              className="secondary"
              onClick={() => {
                setSelectedCustomer(null);
                setHistory(null);
                setCustomerError("");
              }}
            >
              Close
            </button>
          </div>

          {busy && <p className="muted">Loading customer orders...</p>}
          {customerError && <p className="error">{customerError}</p>}

          {history && (
            <>
              <div className="metrics two">
                <Metric
                  label="Customer ID"
                  value={selectedCustomer.id}
                  icon="#"
                />
                <Metric
                  label="Registration Date"
                  value={formatDate(selectedCustomer.created_at)}
                  icon="◷"
                />
                <Metric
                  label="Total Orders"
                  value={selectedCustomer.total_orders ?? history.count}
                  icon="▤"
                />
                <Metric
                  label="Confirmed Purchase Amount"
                  value={money(
                    selectedCustomer.confirmed_purchase_total ??
                    selectedCustomer.purchase_total
                  )}
                  icon="₹"
                />
              </div>

              <p><strong>Total Orders:</strong> {history.count}</p>

              {history.orders.map((order) => (
                <div className="panel" key={order.id}>
                  <h4>Order #{order.order_number || order.id}</h4>
                  <p><strong>Status:</strong> {order.status}</p>
                  <p><strong>Date:</strong> {formatDate(order.created_at)}</p>
                  <p><strong>Total:</strong> {money(order.total_amount)}</p>

                  <div className="table-wrap">
                    <table>
                      <thead>
                        <tr>
                          <th>Product</th>
                          <th>Quantity</th>
                          <th>Unit Price</th>
                          <th>Subtotal</th>
                        </tr>
                      </thead>
                      <tbody>
                        {(order.items || []).map((item, index) => (
                          <tr key={`${item.product_id}-${index}`}>
                            <td>{item.product_name}</td>
                            <td>{item.quantity}</td>
                            <td>{money(item.unit_price)}</td>
                            <td>{money(item.unit_price * item.quantity)}</td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                </div>
              ))}

              {history.orders.length === 0 && (
                <p className="muted">This customer has not placed any orders.</p>
              )}
            </>
          )}
        </div>
      )}
      </section>
    </>
  );
}


function ReportsManagement({ data, money }) {
  function downloadCSV(filename, columns, rows) {
    const escapeCSV = (value) => {
      const text = value === null || value === undefined ? "" : String(value);
      return '"' + text.replace(/"/g, '""') + '"';
    };

    const content = [
      columns.map(escapeCSV).join(","),
      ...rows.map(row => row.map(escapeCSV).join(","))
    ].join("\\r\\n");

    const blob = new Blob(["\\uFEFF" + content], {
      type: "text/csv;charset=utf-8;"
    });

    const url = URL.createObjectURL(blob);
    const link = document.createElement("a");
    link.href = url;
    link.download = filename;
    document.body.appendChild(link);
    link.click();
    link.remove();
    URL.revokeObjectURL(url);
  }

  const products = data.Products?.products || [];
  const inventory = data.Inventory?.inventory || [];
  const orders = data.Orders?.orders || [];
  const customers = data.Customers?.customers || [];
  const sales = data.Sales || {};

  const reports = [
    {
      title: "Products Report",
      description: "Product catalogue, prices and catalogue stock.",
      count: products.length,
      filename: "stockflow_products.csv",
      columns: ["Product ID", "Name", "Category", "Price", "Catalog Stock"],
      rows: products.map(p => [
        p.id, p.name, p.category, p.price, p.stock
      ])
    },
    {
      title: "Inventory Report",
      description: "Available stock quantities and low-stock status.",
      count: inventory.length,
      filename: "stockflow_inventory.csv",
      columns: ["Product ID", "Product Name", "Category", "Available Quantity", "Price", "Low Stock", "Last Updated"],
      rows: inventory.map(p => [
        p.product_id, p.product_name, p.category, p.quantity,
        p.price, p.low_stock ? "Yes" : "No", p.updated_at
      ])
    },
    {
      title: "Orders Report",
      description: "Order dates, customer IDs, statuses and totals.",
      count: orders.length,
      filename: "stockflow_orders.csv",
      columns: ["Order ID", "Order Number", "Customer ID", "Date", "Status", "Total Amount"],
      rows: orders.map(o => [
        o.id, o.order_number, o.user_id, o.created_at, o.status, o.total_amount
      ])
    },
    {
      title: "Customers Report",
      description: "Customer registration and purchase statistics.",
      count: customers.length,
      filename: "stockflow_customers.csv",
      columns: ["Customer ID", "Name", "Email", "Registration Date", "Total Orders", "Confirmed Orders", "Confirmed Purchase Amount"],
      rows: customers.map(c => [
        c.id, c.username, c.email, c.created_at,
        c.total_orders, c.confirmed_orders,
        c.confirmed_purchase_total ?? c.purchase_total
      ])
    },
    {
      title: "Sales Report",
      description: "Payment counts and amounts grouped by payment status.",
      count: (sales.payments_by_status || []).length,
      filename: "stockflow_sales.csv",
      columns: ["Payment Status", "Payment Count", "Total Amount"],
      rows: (sales.payments_by_status || []).map(p => [
        p.status, p.payment_count, p.total_amount
      ])
    }
  ];

  return (
    <section className="panel">
      <div className="table-heading">
        <div>
          <h3>Reports & CSV Export</h3>
          <p className="muted">
            Download reports from your existing dashboard data.
          </p>
        </div>
      </div>

      <div className="grid">
        {reports.map(report => (
          <div className="panel" key={report.filename}>
            <h3>{report.title}</h3>
            <p className="muted">{report.description}</p>
            <p><strong>{report.count}</strong> records</p>
            <button
              type="button"
              className="primary"
              onClick={() => downloadCSV(
                report.filename,
                report.columns,
                report.rows
              )}
            >
              Download CSV
            </button>
          </div>
        ))}
      </div>

      <p className="muted small">
        CSV files contain the records currently loaded in the dashboard.
        Customer reports include the customers returned by the dashboard API.
      </p>
    </section>
  );
}
