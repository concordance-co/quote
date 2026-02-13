# Concordance Frontend

A powerful web interface for monitoring, debugging, and analyzing LLM (Large Language Model) inference in real-time. Concordance provides deep visibility into token generation, trace execution, and model behavior.

![License](https://img.shields.io/badge/license-MIT-blue.svg)
![TypeScript](https://img.shields.io/badge/TypeScript-5.9-blue)
![React](https://img.shields.io/badge/React-19-61dafb)
![Vite](https://img.shields.io/badge/Vite-6-646cff)

## Features

- **Real-time Log Streaming** - Monitor LLM inference requests as they happen via WebSocket
- **Token Sequence Visualization** - Explore token-by-token generation with probability distributions
- **Trace Tree Analysis** - Debug execution traces with detailed step-by-step views
- **Metrics Dashboard** - Visualize latency, throughput, and token statistics
- **Playground** - Interactive environment for running inference experiments
- **Collections** - Organize and group related requests for analysis
- **Sharing** - Share individual requests or collections with public links
- **Discussions** - Add comments and annotations to requests for collaboration
- **Favorites** - Bookmark interesting requests for quick access

## Prerequisites

- **Node.js** 18.x or higher
- **npm** 9.x or higher (or yarn/pnpm)
- **Concordance Backend** - Running instance of the Concordance backend API

## Installation

1. **Clone the repository**
   ```bash
   git clone https://github.com/concordance-co/quote.git
   cd concordance/frontend
   ```

2. **Install dependencies**
   ```bash
   npm install
   ```

3. **Configure environment variables**
   ```bash
   cp env.example .env.local
   ```
   
   Edit `.env.local` with your configuration:
   ```
   VITE_API_URL=http://localhost:8080
   VITE_WS_URL=ws://localhost:6767
   ```

4. **Start the development server**
   ```bash
   npm run dev
   ```

   The application will be available at `http://localhost:3000`

## Configuration

### Environment Variables

| Variable | Description | Default |
|----------|-------------|---------|
| `VITE_API_URL` | Backend API URL | `/api` (proxied) |
| `VITE_WS_URL` | WebSocket URL for real-time streaming | Production URL |

### Development Proxy

During local development, the Vite dev server proxies API requests to avoid CORS issues. Configure the proxy target in `vite.config.ts`:

```typescript
proxy: {
  "/api": {
    target: "http://localhost:8080",
    changeOrigin: true,
    rewrite: (path) => path.replace(/^\/api/, ""),
  },
}
```

## Usage

### Authentication

Concordance uses API key authentication. Enter your API key when prompted to access the dashboard.

### Viewing Logs

The main dashboard displays a real-time feed of LLM inference requests. Click on any request to view detailed information including:

- Request/response metadata
- Token sequence visualization
- Execution trace
- Performance metrics
- Mod (modifier) calls and logs

### Using the Playground

1. Navigate to the Playground via the sparkle icon in the header
2. Configure your injection settings (position, token sequence)
3. Enter a prompt and run inference
4. Analyze the results with the integrated visualizations

### Collections

Organize requests into collections for easier analysis:

1. Click the folder icon on any request
2. Create a new collection or add to an existing one
3. Access collections from the sidebar
4. Share collections publicly with a single click

## Development

### Available Scripts

```bash
# Start development server
npm run dev

# Type-check the codebase
npm run lint

# Build for production
npm run build

# Preview production build
npm run preview
```

### Project Structure

```
frontend/
├── src/
│   ├── components/       # React components
│   │   ├── ui/          # Reusable UI primitives (shadcn/ui)
│   │   ├── LogDetail/   # Log detail view components
│   │   ├── Playground/  # Playground feature components
│   │   ├── TokenSequence/ # Token visualization components
│   │   └── TraceTree/   # Trace tree components
│   ├── hooks/           # Custom React hooks
│   ├── lib/             # Utilities and API client
│   ├── types/           # TypeScript type definitions
│   ├── App.tsx          # Main application component
│   └── main.tsx         # Application entry point
├── public/              # Static assets
└── index.html           # HTML template
```

### Tech Stack

- **Framework**: React 19 with TypeScript
- **Build Tool**: Vite 6
- **Styling**: Tailwind CSS
- **UI Components**: Radix UI primitives
- **State Management**: React hooks
- **Routing**: React Router DOM
- **HTTP Client**: Axios
- **Charts**: Recharts
- **Virtualization**: TanStack Virtual

## Building for Production

```bash
npm run build
```

This creates an optimized production build in the `dist/` directory.

### Deployment

The project includes configuration for Vercel deployment (`vercel.json`). For other platforms:

1. Build the project: `npm run build`
2. Deploy the `dist/` directory as a static site
3. Configure environment variables on your hosting platform
4. Ensure proper routing for SPA (redirect all routes to `index.html`)

Vercel note:
- `vercel.json` includes host-based staging rewrites that route hosts matching `staging` or `git-staging` to the staging Modal backend.
- If your staging custom domain does not include `staging`, update the `host` regex in `vercel.json` accordingly.

## API Integration

The frontend expects a Concordance-compatible backend with the following endpoints:

- `GET /logs` - List inference logs
- `GET /logs/:id` - Get log details
- `WS /logs/stream` - Real-time log streaming
- `GET /collections` - List collections
- `POST /collections` - Create collection
- `GET /api-keys` - List API keys
- `POST /validate-key` - Validate API key

See the backend documentation for complete API reference.

## Contributing

We welcome contributions! Please see [CONTRIBUTING.md](CONTRIBUTING.md) for guidelines.

### Quick Start for Contributors

1. Fork the repository
2. Create a feature branch: `git checkout -b feature/my-feature`
3. Make your changes
4. Run type checking: `npm run lint`
5. Commit your changes: `git commit -m 'Add my feature'`
6. Push to your fork: `git push origin feature/my-feature`
7. Open a Pull Request

## License

This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.

## Acknowledgments

- [Radix UI](https://radix-ui.com/) for accessible UI primitives
- [shadcn/ui](https://ui.shadcn.com/) for component patterns
- [Tailwind CSS](https://tailwindcss.com/) for styling
- [Vite](https://vitejs.dev/) for the blazing fast build tool

---

**Documentation**: [docs.concordance.co](https://docs.concordance.co)

**Issues**: [GitHub Issues](https://github.com/concordance-co/quote/issues)
