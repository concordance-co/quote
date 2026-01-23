---
name: Bug Report
about: Report a bug to help us improve Quote Engine
title: '[BUG] '
labels: bug
assignees: ''
---

## Bug Description

A clear and concise description of what the bug is.

## Steps to Reproduce

1. Start the server with '...'
2. Send request with '...'
3. Register mod '...'
4. See error

## Expected Behavior

A clear and concise description of what you expected to happen.

## Actual Behavior

What actually happened, including any error messages.

## Code Sample

If applicable, provide a minimal code sample that reproduces the issue:

```python
from quote_mod_sdk import mod, ForwardPass

@mod
def my_mod(event, actions, tokenizer):
    # Your code here
    pass
```

## Error Output

```
Paste any error messages or stack traces here
```

## Environment

- **OS**: [e.g., Ubuntu 22.04, macOS 14.0, Windows 11]
- **Python version**: [e.g., 3.13.0]
- **Quote Engine version**: [e.g., 0.4.3]
- **MAX Engine version**: [e.g., 25.6.1]
- **Installation method**: [e.g., uv pip install -e ., pip install]

## Logs

<details>
<summary>Server logs (click to expand)</summary>

```
Paste relevant server logs here
```

</details>

## Additional Context

Add any other context about the problem here, such as:
- Does this happen consistently or intermittently?
- Did this work in a previous version?
- Any recent changes to your environment?

## Checklist

- [ ] I have searched existing issues to ensure this is not a duplicate
- [ ] I have included all relevant information above
- [ ] I have tested with the latest version of Quote Engine