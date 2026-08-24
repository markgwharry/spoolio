# Security policy

## Supported version

Security fixes target the current `main` branch and the hosted Spoolio deployment.
Older commits, archived firmware, and unmaintained prototypes are not supported.

## Reporting a vulnerability

Use GitHub's private vulnerability reporting for this repository when it is
available. If that option is not visible, open a public issue containing only a
request for private maintainer contact—do not include exploit details, credentials,
device keys, network details, or personal data in the issue.

Include the affected route or component, the impact, and the smallest safe
reproduction you can provide. Please allow the maintainers time to investigate and
coordinate a fix before public disclosure.

## Device credentials

Spoolio returns a device API key only when a device is registered or its key is
rotated. Treat it like a password. If a key may have been exposed, rotate it from the
Hardware page and reprovision the device; deleting it from a file does not revoke it.
