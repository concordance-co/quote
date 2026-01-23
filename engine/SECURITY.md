# Security Policy

## Supported Versions

We release patches for security vulnerabilities in the following versions:

| Version | Supported          |
| ------- | ------------------ |
| 0.4.x   | :white_check_mark: |
| < 0.4   | :x:                |

## Reporting a Vulnerability

We take the security of Quote Engine seriously. If you believe you have found a security vulnerability, please report it to us as described below.

### Please Do

- **Report privately**: Send a description of the vulnerability to [security@concordance.ai](mailto:security@concordance.ai)
- **Include details**: Provide as much information as possible, including:
  - Type of vulnerability (e.g., injection, authentication bypass, information disclosure)
  - Full paths of source files related to the vulnerability
  - Step-by-step instructions to reproduce the issue
  - Proof-of-concept or exploit code (if possible)
  - Impact assessment
- **Allow time**: Give us a reasonable amount of time to address the issue before public disclosure

### Please Don't

- **Don't disclose publicly**: Avoid posting about the vulnerability in public issues, discussions, or social media until we've had a chance to address it
- **Don't exploit**: Don't use the vulnerability to access, modify, or delete data beyond what's necessary to demonstrate the issue
- **Don't attack users**: Don't use the vulnerability to attack other users or deployments

## What to Expect

1. **Acknowledgment**: We will acknowledge receipt of your vulnerability report within 48 hours
2. **Initial Assessment**: Within 7 days, we will provide an initial assessment of the report and an estimated timeline for a fix
3. **Regular Updates**: We will keep you informed about our progress toward addressing the vulnerability
4. **Credit**: We will credit you in the security advisory (unless you prefer to remain anonymous)

## Security Considerations for Users

### Mod Execution

Quote Engine executes Python code from registered mods. Consider the following:

- **Only run mods from trusted sources**: Mods have access to the tokenizer, logits, and can influence generation
- **Isolate in production**: Consider running the inference server in a sandboxed environment
- **Review mod code**: Audit mod source code before registration, especially in multi-tenant environments

### API Keys and Authentication

- **Never commit API keys**: Use environment variables or secure secret management
- **Rotate keys regularly**: If you suspect a key has been compromised, rotate it immediately
- **Use HTTPS**: Always use HTTPS in production to protect API keys and user data in transit

### Multi-Tenant Deployments

If deploying Quote Engine for multiple users:

- **Isolate user mods**: Ensure mods from one user cannot access another user's data
- **Validate inputs**: Sanitize and validate all user-provided inputs
- **Rate limiting**: Implement rate limiting to prevent abuse
- **Audit logging**: Log mod registrations and executions for security review

## Security Best Practices

### For Development

```python
# Good: Use logging, not print
import logging
logger = logging.getLogger(__name__)
logger.debug("Processing request %s", request_id)

# Bad: Print statements may leak sensitive data
print(f"User API key: {api_key}")  # Never do this
```

### For Deployment

1. **Keep dependencies updated**: Regularly update all dependencies to patch known vulnerabilities
2. **Use minimal permissions**: Run the server with the least privileges necessary
3. **Enable logging**: Configure comprehensive logging for security monitoring
4. **Network security**: Use firewalls to restrict access to the inference server
5. **Regular audits**: Periodically review configurations and access patterns

## Vulnerability Disclosure Timeline

We aim to follow this timeline for addressing reported vulnerabilities:

| Severity | Initial Response | Fix Target | Public Disclosure |
|----------|------------------|------------|-------------------|
| Critical | 24 hours         | 7 days     | After fix deployed |
| High     | 48 hours         | 14 days    | After fix deployed |
| Medium   | 72 hours         | 30 days    | After fix deployed |
| Low      | 1 week           | 60 days    | After fix deployed |

## Past Security Advisories

No security advisories have been published yet. When applicable, they will be listed here and on the GitHub Security Advisories page.

## Contact

For security-related inquiries, please contact: [security@concordance.ai](mailto:security@concordance.ai)

For general questions or non-security bugs, please use GitHub Issues.