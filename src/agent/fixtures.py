"""Seeded mock user fixtures for the lookup_user tool."""

MOCK_USERS: dict[str, dict] = {
    "alice@example.com": {
        "name": "Alice Johnson",
        "email": "alice@example.com",
        "plan": "Starter",
        "status": "active",
    },
    "bob@example.com": {
        "name": "Bob Martinez",
        "email": "bob@example.com",
        "plan": "Pro",
        "status": "active",
    },
    "carol@example.com": {
        "name": "Carol Chen",
        "email": "carol@example.com",
        "plan": "Enterprise",
        "status": "suspended",
    },
}
