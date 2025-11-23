# Universal Software Engineering Patterns

**Purpose:** Project-agnostic architectural principles and patterns for building resilient, production-ready systems. Extract these concepts when starting any new software project.

---

## Core Architectural Principles

### Principle 1: Aggressive Resilience
**Zero-tolerance for silent failures.** Systems must fail loudly and predictably when they cannot self-correct.

**Key Patterns:**
- Fail-fast validation at startup (validate critical dependencies)
- Pre-execution validation (check preconditions before operations)
- Circuit breakers for external dependencies
- Progressive error handling (tiered recovery strategies)

**Example:**
```python
# Startup validation
def validate_critical_dependencies(config):
    missing = []
    for service in config.critical_services:
        if not is_available(service):
            missing.append(service)

    if missing:
        raise StartupError(
            f"Critical services unavailable: {missing}. "
            f"Cannot start application in degraded state."
        )
```

### Principle 2: Explicit State Management
**Structured data over implicit behavior.** Use clear, typed state to direct system behavior deterministically.

**Key Patterns:**
- Separate ephemeral vs. persistent state
- Clear state ownership (who reads, who writes)
- State hygiene (don't pollute root with component-specific fields)
- Immutability where possible

**Example:**
```python
class SystemState:
    # Permanent state (persisted)
    user_data: Dict[str, Any]

    # Transient state (session-scoped)
    cache: Dict[str, Any]

    # Ephemeral state (request-scoped)
    current_operation: Optional[str] = None
```

### Principle 3: Separation of Concerns
**Clear boundaries between decision-making and execution.**

**Key Patterns:**
- **WHAT vs. HOW**: Separate capability selection from implementation
- **Configuration vs. Code**: Runtime behavior driven by config, not hardcoded
- **Interface vs. Implementation**: Abstract contracts, concrete implementations

**Example:**
```python
# WHAT: Strategy interface
class DataStore(Protocol):
    def save(self, data: dict) -> bool:
        ...

# HOW: Concrete implementations
class PostgresStore(DataStore):
    def save(self, data: dict) -> bool:
        # PostgreSQL-specific implementation
        pass

class S3Store(DataStore):
    def save(self, data: dict) -> bool:
        # S3-specific implementation
        pass

# Configuration selects implementation
store = get_store(config.storage_backend)  # postgres or s3
```

### Principle 4: Observable by Default
**All operations must be traceable.** Production systems without observability are undebuggable.

**Key Patterns:**
- Structured logging (JSON, not strings)
- Distributed tracing (correlation IDs)
- Metrics and health checks
- Debug-level verbosity in non-production

---

## Configuration System (3-Tier)

### Tier 1: Secrets
- API keys, connection strings, credentials
- **Never committed to git**
- Environment variables or secret manager

### Tier 2: Architecture
- System blueprint, component definitions
- Feature flags, routing rules
- **Committed to git**
- Defines all possible configurations

### Tier 3: Implementation
- Runtime bindings, environment-specific overrides
- **Git-ignored** (per-environment)
- Local development vs. staging vs. production

**Benefits:**
- Clean separation of concerns
- Easy environment promotion
- No secrets in version control
- Testable architecture definitions

**Example Structure:**
```
.env                    # Tier 1: Secrets (git-ignored)
config.yaml             # Tier 2: Architecture (committed)
config.local.yaml       # Tier 3: Implementation (git-ignored)
```

---

## Progressive Resilience (4-Tier Error Handling)

**Tier 1: Tactical Retry**
- Immediate retry with corrective action
- N=2-3 attempts with specific guidance
- "Your request had invalid JSON. Please fix and retry."

**Tier 2: Heuristic Repair**
- Programmatic fixes for common errors
- Deterministic corrections (normalize data, fix formats)
- "Auto-corrected: normalized phone number format"

**Tier 3: Escalated Recovery**
- Specialized recovery workflow
- Fallback to alternative implementation
- "Primary database unavailable, using read replica"

**Tier 4: Strategic Oversight**
- Longitudinal trend analysis
- Identify systemic issues requiring architecture changes
- "5 consecutive failures indicate infrastructure problem"

**Key Distinction:**
- **Syntactic errors** (Tiers 1-3): Fixable programmatically
- **Semantic errors** (Tier 4): Require human judgment

---

## Provider-Agnostic Architecture

**Never hardcode vendor dependencies.** Design for interchangeable implementations.

**Key Patterns:**
1. **Abstract interfaces** for external dependencies
2. **Adapter pattern** for vendor-specific implementations
3. **Configuration-driven binding** at runtime
4. **Contract tests** to verify adapter compliance

**Example:**
```python
# Abstract interface
class EmailProvider(Protocol):
    def send(self, to: str, subject: str, body: str) -> bool:
        ...

# Adapters for different providers
class SendGridAdapter(EmailProvider):
    def send(self, to: str, subject: str, body: str) -> bool:
        # SendGrid-specific implementation
        pass

class MailgunAdapter(EmailProvider):
    def send(self, to: str, subject: str, body: str) -> bool:
        # Mailgun-specific implementation
        pass

# Configuration selects provider
provider = get_email_provider(config.email_backend)
```

**Benefits:**
- Zero-cost development (use local/free alternatives)
- Seamless provider migration
- No vendor lock-in
- A/B testing between providers

---

## Testing Mandates

### 1. Centralized Test Fixtures
**Problem:** Duplicate setup code leads to drift.

**Solution:** Shared fixtures for common dependencies.
```python
# conftest.py
@pytest.fixture
def db_connection():
    conn = create_test_db()
    yield conn
    conn.close()

# tests/test_users.py
def test_user_creation(db_connection):
    # No local setup needed
    assert create_user(db_connection, "test@example.com")
```

### 2. Contract Tests for Adapters
**Problem:** Provider-specific implementations may not conform to interface.

**Solution:** Shared contract tests for all adapters.
```python
def test_email_adapter_contract(email_adapter):
    """Tests that all EmailProvider adapters must pass."""
    # Test basic send
    assert email_adapter.send("test@example.com", "Test", "Body")

    # Test error handling
    with pytest.raises(InvalidEmailError):
        email_adapter.send("invalid-email", "Test", "Body")
```

### 3. Test-Driven Validation
**All architectural assumptions validated by tests.**

**Example:**
```python
def test_critical_services_required():
    """Validate that app fails fast if critical services unavailable."""
    config = Config(critical_services=["database", "cache"])

    # Mock database as unavailable
    with mock.patch("is_available", return_value=False):
        with pytest.raises(StartupError, match="database"):
            validate_critical_dependencies(config)
```

---

## Observability Requirements

### Structured Logging
```python
import structlog

logger = structlog.get_logger()

# ✅ GOOD: Structured, queryable
logger.info("user_login", user_id=123, ip="1.2.3.4", success=True)

# ❌ BAD: String formatting, hard to query
logger.info(f"User 123 logged in from 1.2.3.4")
```

### Distributed Tracing
```python
import uuid

def handle_request(request):
    # Generate or extract correlation ID
    correlation_id = request.headers.get("X-Correlation-ID") or str(uuid.uuid4())

    # Include in all log entries
    logger = logger.bind(correlation_id=correlation_id)

    # Pass to downstream services
    downstream_request.headers["X-Correlation-ID"] = correlation_id
```

### Health Checks
```python
@app.get("/health")
def health_check():
    checks = {
        "database": check_database_connection(),
        "cache": check_cache_connection(),
        "external_api": check_external_api()
    }

    all_healthy = all(checks.values())

    return {
        "status": "healthy" if all_healthy else "degraded",
        "checks": checks
    }, 200 if all_healthy else 503
```

---

## Fail-Fast Validation

### Startup Validation
**Fail immediately if critical dependencies unavailable.**

```python
def startup():
    # 1. Validate configuration
    config = load_config()
    validate_config_schema(config)

    # 2. Validate critical services
    validate_critical_dependencies(config)

    # 3. Validate data integrity
    validate_database_migrations()

    # Only start if all checks pass
    start_application(config)
```

**Benefits:**
- No partial/broken state
- Clear error messages at startup
- Prevents cascading failures

### Pre-Execution Validation
**Validate preconditions before expensive operations.**

```python
def process_payment(amount: float, account_id: str):
    # Fail fast: validate inputs
    if amount <= 0:
        raise ValueError(f"Invalid amount: {amount}")

    # Fail fast: check preconditions
    account = get_account(account_id)
    if not account.is_active:
        raise AccountInactiveError(f"Account {account_id} is inactive")

    if account.balance < amount:
        raise InsufficientFundsError(f"Balance {account.balance} < {amount}")

    # Only proceed if all checks pass
    return execute_payment(amount, account)
```

---

## State Hygiene Principles

### 1. Clear State Ownership
```python
class Request:
    # Read by: handler
    # Written by: parser
    user_id: str

    # Read by: multiple handlers
    # Written by: auth middleware (ONLY)
    auth_token: Optional[str] = None

    # Read/Written by: request handler (ephemeral)
    _cache: Dict[str, Any] = field(default_factory=dict)
```

### 2. Separate Transient vs. Persistent
```python
class Session:
    # Persistent (database)
    user_id: str
    created_at: datetime

    # Transient (in-memory only)
    _request_count: int = 0
    _last_activity: Optional[datetime] = None
```

### 3. Immutability Where Possible
```python
from dataclasses import dataclass

@dataclass(frozen=True)
class Config:
    """Immutable configuration - cannot be modified after creation."""
    database_url: str
    cache_ttl: int

    # Force new instance for changes
    def with_cache_ttl(self, new_ttl: int) -> "Config":
        return Config(
            database_url=self.database_url,
            cache_ttl=new_ttl
        )
```

---

## Universal Best Practices

### 1. Fail-Fast Philosophy
Silent failures are unacceptable. Every error must be:
- **Loud**: Logged with full context
- **Explicit**: Clear error messages
- **Actionable**: Include remediation steps

### 2. Configuration Over Code
Runtime behavior driven by configuration, not hardcoded logic.

**Example:**
```yaml
# config.yaml
retry_policy:
  max_attempts: 3
  backoff: exponential
  initial_delay_ms: 100

circuit_breaker:
  failure_threshold: 5
  timeout_ms: 30000
  recovery_timeout_ms: 60000
```

### 3. Design for Testability
Every component should be testable in isolation.

**Anti-Pattern:**
```python
# ❌ Hardcoded dependencies, untestable
def send_notification(user_id):
    db = PostgresDB("production-host")  # Hardcoded!
    email = SendGridAPI("prod-key")     # Hardcoded!
    user = db.get_user(user_id)
    email.send(user.email, "Notification")
```

**Better:**
```python
# ✅ Dependency injection, easily testable
def send_notification(user_id, db: Database, email: EmailProvider):
    user = db.get_user(user_id)
    email.send(user.email, "Notification")

# Test with mocks
def test_send_notification():
    mock_db = MockDatabase()
    mock_email = MockEmailProvider()
    send_notification(123, mock_db, mock_email)
    assert mock_email.sent_count == 1
```

### 4. Graceful Degradation
System should degrade gracefully when dependencies fail.

```python
def get_user_recommendations(user_id):
    try:
        # Try ML service
        return ml_service.get_recommendations(user_id)
    except ServiceUnavailableError:
        logger.warning("ML service down, using fallback")
        # Fallback to simple heuristics
        return simple_recommendations(user_id)
```

### 5. Idempotency
Operations should be safe to retry.

```python
def create_user(user_id, email):
    # Idempotent: safe to call multiple times
    existing = db.get_user(user_id)
    if existing:
        logger.info("User already exists", user_id=user_id)
        return existing

    return db.insert_user(user_id, email)
```

---

## Common Anti-Patterns & Solutions

### Anti-Pattern 1: God Objects
**Symptom:** Single class doing too much.

**Solution:** Single Responsibility Principle
```python
# ❌ God object
class UserManager:
    def authenticate(self, credentials): ...
    def send_email(self, user_id, message): ...
    def process_payment(self, user_id, amount): ...
    def generate_report(self, user_id): ...

# ✅ Separate concerns
class Authenticator:
    def authenticate(self, credentials): ...

class EmailService:
    def send(self, user_id, message): ...

class PaymentProcessor:
    def process(self, user_id, amount): ...
```

### Anti-Pattern 2: Primitive Obsession
**Symptom:** Using primitives instead of value objects.

**Solution:** Strongly-typed value objects
```python
# ❌ Primitive obsession
def transfer_money(from_account: str, to_account: str, amount: float):
    # Easy to mix up arguments, no validation
    ...

# ✅ Value objects
@dataclass(frozen=True)
class AccountId:
    value: str

    def __post_init__(self):
        if not is_valid_account_id(self.value):
            raise ValueError(f"Invalid account ID: {self.value}")

@dataclass(frozen=True)
class Money:
    amount: Decimal
    currency: str

    def __post_init__(self):
        if self.amount < 0:
            raise ValueError("Amount cannot be negative")

def transfer_money(from_account: AccountId, to_account: AccountId, amount: Money):
    # Type-safe, validated at construction
    ...
```

### Anti-Pattern 3: Swallowing Exceptions
**Symptom:** Silent failures in exception handlers.

**Solution:** Fail loudly with context
```python
# ❌ Swallows exceptions
try:
    process_payment(user_id, amount)
except Exception:
    pass  # Silent failure!

# ✅ Fail loudly with context
try:
    process_payment(user_id, amount)
except PaymentError as e:
    logger.error("Payment failed", user_id=user_id, amount=amount, error=str(e))
    raise PaymentProcessingError(f"Failed to process payment for user {user_id}") from e
```

### Anti-Pattern 4: Tight Coupling
**Symptom:** Components directly depend on concrete implementations.

**Solution:** Dependency injection + interfaces
```python
# ❌ Tight coupling
class OrderService:
    def __init__(self):
        self.db = PostgresDB()  # Hardcoded dependency
        self.email = SendGridAPI()  # Hardcoded dependency

# ✅ Loose coupling
class OrderService:
    def __init__(self, db: Database, email: EmailProvider):
        self.db = db
        self.email = email
```

---

## Debugging Workflow

### 1. Check Logs
```bash
# Structured logs are queryable
grep '"error"' app.log | jq '.correlation_id' | sort | uniq -c

# Find all errors for specific correlation_id
grep '"correlation_id":"abc-123"' app.log | jq '.message'
```

### 2. Verify Configuration
```bash
# Ensure config loaded correctly
grep "Configuration loaded" app.log

# Check for config errors
grep "config" app.log | grep -i error
```

### 3. Trace Request Flow
```bash
# Follow single request through system
grep '"correlation_id":"abc-123"' app.log | jq -r '[.timestamp, .service, .message] | @tsv'
```

### 4. Check Health Status
```bash
curl http://localhost:8000/health | jq
# {
#   "status": "degraded",
#   "checks": {
#     "database": true,
#     "cache": false,  ← Problem here
#     "external_api": true
#   }
# }
```

---

## Scalability Patterns

### 1. Asynchronous Processing
**Offload expensive operations to background workers.**

```python
# Synchronous (blocks request)
def handle_upload(file):
    process_file(file)  # Slow!
    return {"status": "processed"}

# Asynchronous (returns immediately)
def handle_upload(file):
    job_id = enqueue_processing(file)
    return {"status": "queued", "job_id": job_id}
```

### 2. Caching
**Cache expensive computations.**

```python
from functools import lru_cache

@lru_cache(maxsize=1000)
def get_user_permissions(user_id):
    # Expensive database query
    return db.query_permissions(user_id)
```

### 3. Connection Pooling
**Reuse database connections.**

```python
# ❌ Creates new connection every time
def get_user(user_id):
    conn = create_db_connection()
    result = conn.query(f"SELECT * FROM users WHERE id = {user_id}")
    conn.close()
    return result

# ✅ Uses connection pool
pool = ConnectionPool(max_connections=10)

def get_user(user_id):
    with pool.get_connection() as conn:
        return conn.query(f"SELECT * FROM users WHERE id = {user_id}")
```

---

## Security Best Practices

### 1. Input Validation
**Never trust user input.**

```python
def create_user(email: str, age: int):
    # Validate email format
    if not is_valid_email(email):
        raise ValueError(f"Invalid email: {email}")

    # Validate range
    if not (13 <= age <= 120):
        raise ValueError(f"Invalid age: {age}")

    # Sanitize for SQL injection
    safe_email = sanitize_sql(email)
    db.execute(f"INSERT INTO users (email, age) VALUES (?, ?)", safe_email, age)
```

### 2. Secrets Management
```python
# ❌ Hardcoded secret
api_key = "sk-1234567890abcdef"

# ✅ From environment
api_key = os.getenv("API_KEY")
if not api_key:
    raise ConfigError("API_KEY environment variable not set")
```

### 3. Principle of Least Privilege
```python
# ❌ Admin access for everyone
db_user = "admin"

# ✅ Read-only user for read operations
db_user = "readonly_user"  # Can only SELECT, not INSERT/UPDATE/DELETE
```

---

## License

These patterns are provided as-is for building production systems. Adapt freely to your project's needs.
