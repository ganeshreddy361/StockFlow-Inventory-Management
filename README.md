# StockFlow – Inventory & Order Management System

StockFlow is a full-stack inventory and order management application built using React, FastAPI, and SQLite.

## Features
- JWT-based user authentication
- Product management
- Inventory and stock tracking
- Shopping cart management
- Order creation and cancellation
- Payment processing
- Notification service
- Admin dashboard
- Customer management and order history
- Sales and inventory reports
- CSV report downloads

## Technology Stack
- Frontend: React 19, Vite 8, JavaScript
- Backend: Python, FastAPI, Uvicorn
- Database: SQLite
- Authentication: JWT
- HTTP Client: HTTPX

## Backend Services

| Service | Port |
|---|---:|
| API Gateway | 8000 |
| Authentication | 8101 |
| Product | 8102 |
| Inventory | 8103 |
| Cart | 8104 |
| Order | 8105 |
| Payment | 8106 |
| Notification | 8107 |
| Admin Dashboard | 8108 |

## Installation

### Backend

```bash
python3 -m venv backend/venv
source backend/venv/bin/activate
pip install -r requirements.txt
```

### Frontend

```bash
cd frontend
npm install
npm run dev
```

## Running Backend Services

Run each command from the project root in a separate Terminal tab:

```bash
uvicorn backend.api_gateway.main:app --host 127.0.0.1 --port 8000
uvicorn backend.auth_service.main:app --host 127.0.0.1 --port 8101
uvicorn backend.product_service.main:app --host 127.0.0.1 --port 8102
uvicorn backend.inventory_service.main:app --host 127.0.0.1 --port 8103
uvicorn backend.cart_service.main:app --host 127.0.0.1 --port 8104
uvicorn backend.order_service.main:app --host 127.0.0.1 --port 8105
uvicorn backend.payment_service.main:app --host 127.0.0.1 --port 8106
uvicorn backend.notification_service.main:app --host 127.0.0.1 --port 8107
uvicorn backend.admin_dashboard.main:app --host 127.0.0.1 --port 8108
```

## Frontend URL

http://localhost:5173

## Security

Never commit database files, passwords, API keys, environment files, or virtual environments.

---

Developed as a full-stack inventory and order management project.