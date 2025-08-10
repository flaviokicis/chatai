## Inboxed Frontend (Next.js + Tailwind + shadcn/ui)

This is the operator UI for Inboxed. It ships with a demo home (logged-in experience) styled with our brand palette.

### Prerequisites

- Node 20+
- pnpm

### Run

```bash
cd /Users/jessica/me/chatai/frontend
pnpm install
pnpm dev
# http://localhost:3000
```

### Tech

- Next.js App Router, React 19
- Tailwind CSS v4 with custom CSS variables in `app/globals.css`
- shadcn/ui primitives (New York style), lucide-react icons

### Theming

We define brand colors ("brand", "ink", "accent") in Tailwind and expose semantic CSS variables (e.g., `--primary`, `--background`) consumed by shadcn tokens.

### Notes

- This is a demo surface meant to showcase the look and feel of the logged-in dashboard. Real data wiring will come from the backend.
