# Meridinate

> **Professional Solana Token Analysis Toolkit** - Enterprise-grade monorepo for analyzing Solana tokens with early bidder detection, wallet tracking, and real-time market cap monitoring.

[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)](LICENSE)
[![Python 3.11+](https://img.shields.io/badge/python-3.11+-blue.svg)](https://www.python.org/downloads/)
[![Next.js 15](https://img.shields.io/badge/Next.js-15-black)](https://nextjs.org/)
[![FastAPI](https://img.shields.io/badge/FastAPI-0.109+-green.svg)](https://fastapi.tiangolo.com/)

---

## Table of Contents

- [Overview](#overview)
- [Project Structure](#project-structure)
- [Quick Start](#quick-start)
- [Services](#services)
- [Documentation](#documentation)
- [Development](#development)
- [Docker](#docker)
- [Contributing](#contributing)

---

## Overview

Meridinate is a comprehensive Solana token analysis platform that combines:

- **FastAPI Backend** - High-performance async REST API + WebSocket for real-time notifications
- **Next.js Frontend** - Modern React 18 UI with Turbopack, shadcn/ui components, and real-time data
- **AutoHotkey Integration** - Desktop automation for rapid token analysis workflows
- **Database** - SQLite for persistent token data with automatic market cap tracking

**Key Features:**
- Early bidder detection for new Solana tokens
- Automated token ingestion pipeline (DexScreener discovery, Helius enrichment, auto-promotion)
- Wallet watchlist and tagging system
- Token classification system with GEM/DUD tagging
- Advanced filtering and smart search for Multi-Token Early Wallets with fuzzy matching
- Real-time market cap monitoring with ATH tracking
- Top holders analysis with configurable limits
- WebSocket notifications for analysis completion
- Docker containerization ready
- Full CI/CD with GitHub Actions

---

## Project Structure

```
Meridinate/
├── apps/                           # Application code
│   ├── backend/                    # FastAPI backend service
│   │   ├── src/meridinate/         # Python package
│   │   │   ├── api/                # Future: API versioning
│   │   │   ├── core/               # Future: Core utilities
│   │   │   ├── models/             # Pydantic data models
│   │   │   ├── routers/            # FastAPI route handlers
│   │   │   ├── services/           # Business logic
│   │   │   ├── database/           # Database utilities
│   │   │   ├── observability/      # Logging/monitoring
│   │   │   └── main.py             # FastAPI app entry point
│   │   ├── tests/                  # Backend tests
│   │   ├── scripts/                # Utility scripts
│   │   ├── data/                   # Data files (gitignored)
│   │   │   ├── db/                 # SQLite database
│   │   │   ├── backups/            # DB backups
│   │   │   ├── analysis_results/   # Analysis outputs
│   │   │   └── axiom_exports/      # Axiom data exports
│   │   ├── logs/                   # Log files (gitignored)
│   │   ├── docker/                 # Docker configs
│   │   ├── pyproject.toml          # Python project config
│   │   ├── requirements.txt        # Production dependencies
│   │   └── README.md
│   │
│   └── frontend/                   # Next.js frontend
│       ├── src/
│       │   ├── app/                # Next.js 13+ App Router
│       │   ├── components/         # React components
│       │   ├── lib/                # Utilities & API client
│       │   ├── hooks/              # Custom React hooks
│       │   ├── types/              # TypeScript types
│       │   └── config/             # App configuration
│       ├── public/                 # Static assets
│       ├── tests/                  # E2E and unit tests
│       ├── scripts/                # Build/sync scripts
│       ├── package.json
│       └── README.md
│
├── tools/                          # Development tools
│   ├── autohotkey/                 # Desktop automation
│   │   ├── action_wheel.ahk        # Main action wheel interface
│   │   ├── action_wheel_settings.ini
│   │   └── lib/                    # AHK libraries
│   │
│   └── browser/                    # Browser extensions
│       └── userscripts/            # Tampermonkey scripts
│
├── scripts/                        # Build/deployment scripts
│   ├── start.bat                   # Windows: Start all services
│   ├── start.sh                    # Unix: Start all services
│   ├── start-backend.bat           # Backend only
│   └── start-frontend.bat          # Frontend only
│
├── docs/                           # Documentation
│   ├── migration/                  # Migration guides
│   ├── progress/                   # Development logs
│   ├── security/                   # Security documentation
│   ├── ci-cd/                      # CI/CD guides
│   └── architecture/               # Architecture docs
│
├── .gitignore
├── LICENSE
└── README.md                       # This file
```

---

## Quick Start

### Prerequisites

- **Python 3.11+** with pip
- **Node.js 20+** with pnpm
- **AutoHotkey v2** (Windows only, optional)
- **Git**

### Installation

1. **Clone the repository**
   ```bash
   git clone https://github.com/your-org/meridinate.git
   cd meridinate
   ```

2. **Backend Setup**
   ```bash
   cd apps/backend

   # Create virtual environment
   python -m venv .venv
   source .venv/bin/activate  # On Windows: .venv\Scripts\activate

   # Install dependencies
   pip install -r requirements.txt

   # Copy config template
   cp config.example.json config.json
   # Edit config.json with your API keys
   ```

3. **Frontend Setup**
   ```bash
   cd apps/frontend

   # Install dependencies
   pnpm install

   # Copy environment template
   cp .env.local.example .env.local
   # Edit .env.local with your settings
   ```

4. **Start All Services**

   **Windows:**
   ```cmd
   scripts\start.bat
   ```

   **macOS/Linux:**
   ```bash
   chmod +x scripts/start.sh
   ./scripts/start.sh
   ```

5. **Access the Application**
   - **Frontend:** http://localhost:3000
   - **Backend API:** http://localhost:5003
   - **API Docs:** http://localhost:5003/docs
   - **Health Check:** http://localhost:5003/health

---

## 🛠️ Services

### Backend (FastAPI)

- **Port:** 5003
- **Tech Stack:** Python 3.11, FastAPI, SQLite, WebSockets
- **Features:**
  - RESTful API for token analysis
  - WebSocket endpoint for real-time notifications
  - Automatic market cap refresh
  - Wallet watchlist management
  - Tag system for wallet and token categorization

**Start individually:**
```bash
cd apps/backend/src
python -m meridinate.main
```

### Frontend (Next.js)

- **Port:** 3000
- **Tech Stack:** Next.js 15, React 18, TypeScript, Tailwind CSS, shadcn/ui
- **Features:**
  - Token dashboard with real-time updates via WebSocket
  - Wallet analysis and tagging
  - Dark mode support
  - Type-safe API client (auto-generated)
  - Optimized performance with CSS transitions and memoization

**Start individually:**
```bash
cd apps/frontend
pnpm dev
```

**WebSocket Resource Management:**

The frontend uses a singleton WebSocket connection to receive real-time analysis notifications from the backend. To prevent browser resource exhaustion:

- **One connection per tab** - Singleton pattern ensures multiple components share a single WebSocket
- **Automatic cleanup** - Connections close after 30 seconds when tab is hidden or inactive
- **Smart reconnection** - Only reconnects when tab is visible, with linear backoff (3s, 6s, 9s, 12s, 15s intervals, max 30s)
- **Max retry limit** - Stops after 5 failed attempts, shows user notification
- **Page Visibility API** - Monitors tab state to intelligently manage connection lifecycle

This prevents "insufficient resources" errors when users have multiple tabs open or leave tabs running in the background.

### AutoHotkey (Desktop Automation)

- **Platform:** Windows only
- **Purpose:** Rapid token analysis workflows via action wheel interface
- **Location:** `tools/autohotkey/action_wheel.ahk`

**Run:**
```cmd
cd tools\autohotkey
action_wheel.ahk
```

---

## 📚 Documentation

Comprehensive documentation is available in the `docs/` directory:

- **[Migration Guide](docs/migration/)** - Project migration history and restructuring
- **[Security Policy](docs/security/SECURITY.md)** - Security best practices and OPSEC
- **[CI/CD Guide](docs/ci-cd/)** - GitHub Actions workflows and automation
- **[Progress Logs](docs/progress/)** - Development progress and bug fixes
- **[Architecture](docs/architecture/)** - System architecture and design decisions

---

## 💻 Development

### Running Tests

**Backend:**
```bash
cd apps/backend
pytest tests/ -v --cov=meridinate
```

**Frontend:**
```bash
cd apps/frontend
pnpm test        # Unit tests
pnpm test:e2e    # E2E tests with Playwright
```

### Code Quality

**Backend:**
```bash
cd apps/backend
black src/meridinate/           # Format code
flake8 src/meridinate/          # Lint code
mypy src/meridinate/            # Type check
```

**Frontend:**
```bash
cd apps/frontend
pnpm lint        # ESLint
pnpm format      # Prettier
pnpm typecheck   # TypeScript
```

### Type Synchronization

Frontend types are auto-generated from backend OpenAPI schema:

```bash
cd apps/frontend
pnpm sync-types
```

---

## 🐳 Docker

### Build and Run

**Backend:**
```bash
cd apps/backend/docker
docker-compose up --build
```

**Full Stack (Backend + Frontend):**
```bash
cd apps/backend/docker
# Uncomment frontend section in docker-compose.yml
docker-compose up --build
```

### Docker Images

- **Backend:** `meridinate-backend:latest`
- **Frontend:** `meridinate-frontend:latest` (optional)

---

## 🤝 Contributing

We welcome contributions! Please follow these guidelines:

1. **Fork the repository**
2. **Create a feature branch** (`git checkout -b feature/amazing-feature`)
3. **Make your changes** and add tests
4. **Run code quality checks** (see Development section)
5. **Commit your changes** (`git commit -m 'Add amazing feature'`)
6. **Push to the branch** (`git push origin feature/amazing-feature`)
7. **Open a Pull Request**

### Code Style

- **Python:** Follow PEP 8, use Black formatter (line length: 120)
- **TypeScript:** Follow project ESLint config, use Prettier
- **Commits:** Use conventional commits format

---

## 📄 License

This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.

---

## 🙏 Acknowledgments

- **FastAPI** - Modern Python web framework
- **Next.js** - React framework for production
- **shadcn/ui** - Beautiful component library
- **Helius** - Solana RPC and data APIs
- **DexScreener** - Token market data

---

## 📞 Support

- **Documentation:** `docs/` directory
- **Issues:** [GitHub Issues](https://github.com/your-org/meridinate/issues)
- **Discussions:** [GitHub Discussions](https://github.com/your-org/meridinate/discussions)

---

**Built with ❤️ for the Solana community**
