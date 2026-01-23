# Contributing to Concordance

Thank you for your interest in contributing to Concordance! This document provides guidelines and information for contributors.

## Table of Contents

- [Code of Conduct](#code-of-conduct)
- [Getting Started](#getting-started)
- [How to Contribute](#how-to-contribute)
- [Development Workflow](#development-workflow)
- [Code Style](#code-style)
- [Commit Messages](#commit-messages)
- [Pull Request Process](#pull-request-process)
- [Reporting Issues](#reporting-issues)

## Code of Conduct

By participating in this project, you agree to maintain a respectful and inclusive environment for everyone. Please:

- Be respectful and considerate in all interactions
- Welcome newcomers and help them learn
- Accept constructive criticism gracefully
- Focus on what's best for the community and project
- Show empathy towards other community members

Unacceptable behavior includes harassment, trolling, personal attacks, or publishing others' private information.

## Getting Started

### Prerequisites

- Node.js 18.x or higher
- npm 9.x or higher
- Git
- A code editor (VS Code recommended)

### Setting Up Your Development Environment

1. **Fork the repository** on GitHub

2. **Clone your fork**
   ```bash
   git clone https://github.com/YOUR_USERNAME/concordance.git
   cd concordance/frontend
   ```

3. **Add the upstream remote**
   ```bash
   git remote add upstream https://github.com/concordance-co/concordance.git
   ```

4. **Install dependencies**
   ```bash
   npm install
   ```

5. **Create a branch for your work**
   ```bash
   git checkout -b feature/your-feature-name
   ```

6. **Start the development server**
   ```bash
   npm run dev
   ```

## How to Contribute

### Types of Contributions

We welcome many types of contributions:

- **Bug fixes** - Fix issues reported in GitHub Issues
- **Features** - Implement new functionality
- **Documentation** - Improve README, add code comments, write guides
- **Tests** - Add or improve test coverage
- **Performance** - Optimize code for better performance
- **Accessibility** - Improve accessibility for all users
- **Refactoring** - Improve code quality without changing functionality

### Finding Something to Work On

- Check [GitHub Issues](https://github.com/concordance-co/concordance/issues) for open issues
- Look for issues labeled `good first issue` if you're new
- Look for issues labeled `help wanted` for priority items
- Feel free to ask questions on any issue before starting work

## Development Workflow

### Branch Naming

Use descriptive branch names with a prefix:

- `feature/` - New features (e.g., `feature/add-export-button`)
- `fix/` - Bug fixes (e.g., `fix/websocket-reconnection`)
- `docs/` - Documentation changes (e.g., `docs/update-readme`)
- `refactor/` - Code refactoring (e.g., `refactor/api-client`)
- `test/` - Test additions or fixes (e.g., `test/add-component-tests`)

### Making Changes

1. **Keep changes focused** - One feature or fix per pull request
2. **Write clean code** - Follow the code style guidelines
3. **Test your changes** - Ensure existing functionality isn't broken
4. **Update documentation** - If your change affects usage, update docs

### Running Checks

Before submitting your changes:

```bash
# Type-check the codebase
npm run lint

# Build to ensure no build errors
npm run build
```

## Code Style

### TypeScript

- Use TypeScript for all new code
- Define proper types for props, state, and function parameters
- Avoid using `any` type; use `unknown` if type is truly unknown
- Use interfaces for object shapes, types for unions/intersections

### React

- Use functional components with hooks
- Keep components focused and single-purpose
- Extract reusable logic into custom hooks
- Use proper TypeScript types for props

```typescript
// Good
interface ButtonProps {
  label: string;
  onClick: () => void;
  disabled?: boolean;
}

function Button({ label, onClick, disabled = false }: ButtonProps) {
  return (
    <button onClick={onClick} disabled={disabled}>
      {label}
    </button>
  );
}
```

### Styling

- Use Tailwind CSS for styling
- Follow the existing patterns for component styling
- Use the `cn()` utility for conditional classes
- Keep styles co-located with components

### File Organization

- Place components in `src/components/`
- Place hooks in `src/hooks/`
- Place utilities in `src/lib/`
- Place types in `src/types/`
- Group related components in subdirectories

### Naming Conventions

- **Components**: PascalCase (e.g., `LogDetail.tsx`)
- **Hooks**: camelCase with `use` prefix (e.g., `useLogStream.ts`)
- **Utilities**: camelCase (e.g., `formatDate.ts`)
- **Types**: PascalCase (e.g., `LogResponse`)
- **Constants**: SCREAMING_SNAKE_CASE (e.g., `API_BASE_URL`)

## Commit Messages

Follow the [Conventional Commits](https://www.conventionalcommits.org/) specification:

```
<type>(<scope>): <description>

[optional body]

[optional footer]
```

### Types

- `feat`: New feature
- `fix`: Bug fix
- `docs`: Documentation changes
- `style`: Code style changes (formatting, semicolons, etc.)
- `refactor`: Code changes that neither fix bugs nor add features
- `perf`: Performance improvements
- `test`: Adding or updating tests
- `chore`: Maintenance tasks

### Examples

```
feat(playground): add token injection preview

fix(websocket): handle reconnection on network change

docs(readme): add deployment instructions

refactor(api): simplify error handling logic
```

## Pull Request Process

### Before Submitting

1. **Rebase on latest main**
   ```bash
   git fetch upstream
   git rebase upstream/main
   ```

2. **Run all checks**
   ```bash
   npm run lint
   npm run build
   ```

3. **Review your changes**
   ```bash
   git diff upstream/main
   ```

### Submitting a Pull Request

1. Push your branch to your fork
   ```bash
   git push origin feature/your-feature-name
   ```

2. Open a Pull Request on GitHub

3. Fill out the PR template with:
   - Description of changes
   - Related issue number (if applicable)
   - Screenshots (for UI changes)
   - Testing instructions

### PR Review

- A maintainer will review your PR
- Address any requested changes
- Once approved, a maintainer will merge your PR

### After Your PR is Merged

1. Delete your branch
   ```bash
   git branch -d feature/your-feature-name
   ```

2. Update your local main
   ```bash
   git checkout main
   git pull upstream main
   ```

## Reporting Issues

### Bug Reports

When reporting a bug, include:

- **Description**: Clear description of the bug
- **Steps to Reproduce**: Detailed steps to reproduce the issue
- **Expected Behavior**: What you expected to happen
- **Actual Behavior**: What actually happened
- **Environment**: Browser, OS, Node.js version
- **Screenshots**: If applicable
- **Console Errors**: Any errors from browser console

### Feature Requests

When requesting a feature, include:

- **Description**: Clear description of the feature
- **Use Case**: Why this feature would be useful
- **Proposed Solution**: How you envision it working
- **Alternatives**: Any alternative solutions you've considered

## Questions?

If you have questions about contributing:

- Check existing [GitHub Issues](https://github.com/concordance-co/concordance/issues)
- Open a new issue with your question
- Reach out to maintainers

---

Thank you for contributing to Concordance! 🎉
