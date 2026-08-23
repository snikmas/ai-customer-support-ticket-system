# Authentication and staff shell

## Sub-features

- Login and session restoration.
- Role-aware navigation and logout.

## How to get to it (user POV)

Open http://127.0.0.1:5173/login, sign in with synthetic credentials, and
refresh the page.

## Driving it with browser

Use accessible labels for email/password, submit the form, then inspect the
navigation links and profile role label.

## Gotchas

Never record a real password or token. A successful login must be paired with a
visible authenticated route and a safe logout result.
