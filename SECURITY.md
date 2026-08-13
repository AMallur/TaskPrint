# Security policy

## Supported version

Security fixes are provided for the latest minor release. This repository currently supports
the 0.2 series.

## Reporting

Do not open a public issue containing an unpatched vulnerability, secret, personal data, or
working exploit. Contact the repository owner privately and include the affected version,
impact, reproduction steps, and any proposed mitigation. A public advisory can be coordinated
after a fix is available.

## Security boundary

Taskprint validates artifacts and bounds graph execution. It does not sandbox handler code,
manage secrets, authorize actions, or make an unsafe external operation safe. Treat handlers
as ordinary privileged application code and follow the production guide.
