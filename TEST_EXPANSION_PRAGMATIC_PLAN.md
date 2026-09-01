# Pragmatic Test Expansion Plan - Local Dev & Production Focus

**Approach:** Add only tests for scenarios that developers encounter locally or systems experience in production  
**Total Tests to Add:** ~150 (not 1,144)  
**Time Estimate:** 3-4 days  
**Focus:** Core correctness, not exotic edge cases

---

## Guiding Principle

**ADD:** Tests that catch real bugs developers see  
**SKIP:** Tests for exotic cloud provider features (Snowflake warehouse suspension, Kafka partition rebalance, PubSub DLQ routing)

---

## Component-by-Component Pragmatic Gaps

### **COMPONENT 2: Storage Connectors (S3, GCS, ADLS)**

**Current:** 59 tests  
**Pragmatic Add:** 25 tests  
**Focus:** Local dev scenarios

#### Tests to Add (25 total)

| Category | Tests | Reason |
|----------|-------|--------|
| **Credential Rotation** | 3 | Devs rotate creds locally, should work |
| **Pool Reuse** | 3 | Core: same tenant reuses connection |
| **Pool Cleanup** | 4 | Bug fix: close() should clear pool |
| **Basic Errors** | 5 | Missing bucket, permission denied, timeout |
| **Tenant Isolation** | 5 | Core: tenant_a cannot see tenant_b files |
| **Large File** | 2 | Devs upload 500MB files locally |
| **Concurrent Same Tenant** | 3 | Multiple threads, same tenant |

**Tests NOT Adding:**
- ❌ S3 multipart upload edge cases (exotic)
- ❌ GCS versioning/lifecycle rules (cloud-specific)
- ❌ ADLS append blob operations (rare in practice)
- ❌ Cloud storage quota exceeded (doesn't happen locally)

---

### **COMPONENT 3: Data Source Connectors (Kafka, PubSub)**

**Current:** 45 tests  
**Pragmatic Add:** 20 tests  
**Focus:** Local dev & standard operation

#### Tests to Add (20 total)

| Category | Tests | Reason |
|----------|-------|--------|
| **Iterator Cleanup** | 4 | Bug fix: cleanup on exception, not hung process |
| **Basic Message Flow** | 3 | Produce → consume → receive |
| **Tenant Topic Isolation** | 3 | tenant_a_topic ≠ tenant_b_topic |
| **Empty Topic** | 2 | Consume from empty topic doesn't crash |
| **Error Propagation** | 2 | Connection errors bubble up correctly |
| **Concurrent Producers** | 2 | Multiple threads produce safely |
| **Large Messages** | 2 | Devs send 1MB payload |
| **Message Format** | 2 | JSON serialization/deserialization |

**Tests NOT Adding:**
- ❌ Kafka partition rebalancing (exotic)
- ❌ Consumer group lag tracking (monitoring, not core)
- ❌ PubSub dead letter queue (advanced)
- ❌ Offset commit failures (rare)
- ❌ Kafka broker failover (requires cluster)

---

### **COMPONENT 4: Database Connectors (PostgreSQL, MongoDB, Snowflake)**

**Current:** 78 tests (after my expansion)  
**Pragmatic Add:** 40 tests  
**Focus:** ACID, isolation, injection

#### Tests to Add (40 total)

| Category | Tests | Reason |
|----------|-------|--------|
| **SQL Injection Prevention** | 8 | CRITICAL: verify all 3 engines parameterize |
| **Transaction Rollback** | 5 | Already added, but verify all engines |
| **Tenant Data Isolation** | 8 | Core: query doesn't cross tenants |
| **Connection Pool Reuse** | 4 | Same tenant reuses same connection |
| **Basic Errors** | 5 | Connection failed, timeout, constraint |
| **Batch Insert** | 4 | Insert 1000 rows, verify all inserted |
| **Concurrent Transactions** | 3 | Multiple threads, same tenant |
| **Schema Cleanup** | 3 | Close connection clears state |

**Tests NOT Adding:**
- ❌ Snowflake warehouse suspension (AWS feature, doesn't happen locally)
- ❌ MongoDB TTL indexes (advanced feature)
- ❌ PostgreSQL savepoints/nested transactions (not commonly used)
- ❌ Large result set memory tests (scale scenario, not core)
- ❌ Deadlock detection (race condition, hard to test reliably)

---

### **COMPONENT 5: Tenant-Aware Router**

**Current:** 39 tests (26 original + ~13 new)  
**Pragmatic Add:** 30 tests  
**Focus:** Routing, isolation, basic error handling

#### Tests to Add (30 total)

| Category | Tests | Reason |
|----------|-------|--------|
| **Cross-Component Pipeline** | 5 | Read S3 → write DB (end-to-end) |
| **Tenant Data Isolation** | 8 | tenant_a read/write cannot affect tenant_b |
| **Connector Routing** | 4 | Route to correct connector type |
| **Error Propagation** | 5 | Connector error → router error with context |
| **Pool Reuse** | 3 | Multiple ops from same tenant reuse connector |
| **Missing Credentials** | 2 | Empty config fails gracefully |
| **Concurrent Tenants** | 3 | Multiple tenants operate independently |

**Tests NOT Adding:**
- ❌ Circuit breaker pattern (Phase 2 feature)
- ❌ Cascading failures (exotic scenario)
- ❌ Metrics collection (monitoring, not core)
- ❌ Audit trail completeness (logging, not routing)
- ❌ Rate limiting enforcement (policy, not core)

---

## Implementation Order (3-4 Days)

### **Day 1: Database Critical (Component 4) - 8 hours**
- SQL Injection Prevention (8 tests)
  - Each engine: parameterized query tests with attempted injections
  - Verify `%s`, `?`, `:param` placeholders work correctly
  - Verify string interpolation is NOT used

**Why First:** SQL injection is a **security issue**, must be verified

### **Day 2: Storage & Routing (Components 2 & 5) - 8 hours**
- Storage pool cleanup bug (4 tests)
- Router cross-component pipeline (5 tests)
- Tenant isolation in storage (5 tests)
- Tenant isolation in router (8 tests)

**Why Second:** Pool cleanup is a **bug fix**, isolation is **critical for multi-tenant**

### **Day 3: Data Source & Database (Components 3 & 4) - 8 hours**
- Iterator cleanup (4 tests)
- Tenant topic isolation (3 tests)
- Message flow (3 tests)
- Transaction rollback verification (5 tests)
- Tenant data isolation (8 tests)
- Batch insert (4 tests)

**Why Third:** Iterator cleanup is a **resource leak**, batch insert is **common operation**

### **Day 4: Polish & Integration - 4 hours**
- Run full test suite
- Verify no regressions
- Document any findings
- Commit

---

## Specific High-Value Tests

### **Test 1: SQL Injection Prevention (8 tests)**
```python
def test_postgresql_sql_injection_in_where():
    """Parameterized queries prevent injection"""
    postgres = PostgreSQLConnector(config)
    postgres.connect()
    
    # Attempt injection
    malicious = "'; DROP TABLE users; --"
    result = postgres.query(
        "SELECT * FROM users WHERE name = %s",  # Must use %s
        {"name": malicious}
    )
    # Table should still exist
    assert result is not None

def test_mongodb_injection_in_filter():
    """MongoDB query parameterization"""
    mongo = MongoDBConnector(config)
    mongo.connect()
    
    # Attempt injection
    malicious_filter = {"$or": [{"admin": True}]}
    result = mongo.query(malicious_filter, {}, "tenant_1")
    # Should NOT bypass tenant isolation
    assert all(doc.get("tenant") == "tenant_1" for doc in result)

def test_snowflake_injection_in_bind_variable():
    """Snowflake uses ? placeholders safely"""
    snowflake = SnowflakeConnector(config)
    snowflake.connect()
    
    malicious = "1 OR 1=1"
    result = snowflake.query(
        "SELECT * FROM users WHERE id = ?",
        {"id": malicious}
    )
    # Should find 0 or 1 row, not all rows
    assert len(result) <= 1
```

### **Test 2: Connection Pool Cleanup (4 tests)**
```python
def test_storage_close_clears_pool():
    """close() should clear connection pool"""
    s3 = S3Connector(config)
    s3.connect()
    s3.write_object("file.txt", b"data", "tenant_1")
    
    # Pool should have client
    assert "tenant_1" in s3._client_pool
    
    s3.close()
    
    # Pool should be empty
    assert len(s3._client_pool) == 0 or "tenant_1" not in s3._client_pool

def test_reconnect_after_close_works():
    """After close(), can reconnect and get new client"""
    s3 = S3Connector(config)
    s3.connect()
    s3.close()
    
    # Should get new client, not fail with "connection closed"
    s3.connect()
    s3.write_object("file2.txt", b"data2", "tenant_1")  # Should succeed
```

### **Test 3: Cross-Component Pipeline (5 tests)**
```python
def test_read_s3_write_postgres():
    """End-to-end: Read S3 → Write DB"""
    router = TenantAwareRouter()
    
    # Write test data to S3
    s3_config = StorageConfig(..., tenant_id="tenant_1")
    s3 = router.get_connector("s3", "tenant_1", s3_config)
    s3.write_object("data.json", b'{"id": 1, "name": "alice"}', "tenant_1")
    
    # Read from S3, write to PostgreSQL
    data = s3.read_object("data.json", "tenant_1")
    pg_config = DatabaseConfig(..., tenant_id="tenant_1")
    postgres = router.get_connector("postgresql", "tenant_1", pg_config)
    postgres.execute(
        "INSERT INTO users (id, name) VALUES (%s, %s)",
        {"id": 1, "name": "alice"},
        "tenant_1"
    )
    
    # Verify in database
    result = postgres.query("SELECT * FROM users WHERE id = 1", {}, "tenant_1")
    assert result[0]["name"] == "alice"

def test_kafka_produce_postgres_consume():
    """End-to-end: Produce to Kafka → Consume to DB"""
    router = TenantAwareRouter()
    
    kafka_config = DataSourceConfig(..., tenant_id="tenant_1")
    kafka = router.get_connector("kafka", "tenant_1", kafka_config)
    
    # Produce
    kafka.produce("events", {"event": "login", "user": "alice"}, "tenant_1")
    
    # Consume
    postgres = router.get_connector("postgresql", "tenant_1", pg_config)
    messages = list(kafka.consume("events", "tenant_1"))
    
    # Insert to database
    for msg in messages:
        postgres.execute(
            "INSERT INTO events (data) VALUES (%s)",
            {"data": str(msg)},
            "tenant_1"
        )
```

### **Test 4: Tenant Isolation (8 tests per component)**
```python
def test_postgres_tenant_isolation():
    """Tenant A query doesn't return Tenant B data"""
    # Setup two tenants with different databases/schemas
    config_a = DatabaseConfig(..., tenant_id="tenant_a", schema="tenant_a_db")
    config_b = DatabaseConfig(..., tenant_id="tenant_b", schema="tenant_b_db")
    
    postgres_a = PostgreSQLConnector(config_a)
    postgres_b = PostgreSQLConnector(config_b)
    
    postgres_a.connect()
    postgres_b.connect()
    
    # Tenant A inserts
    postgres_a.execute(
        "INSERT INTO users (name) VALUES (%s)",
        {"name": "alice"},
        "tenant_a"
    )
    
    # Tenant B queries (should get nothing)
    result = postgres_b.query("SELECT * FROM users", {}, "tenant_b")
    assert len(result) == 0

def test_s3_tenant_isolation():
    """Tenant A files invisible to Tenant B"""
    config_a = StorageConfig(..., tenant_id="tenant_a")
    config_b = StorageConfig(..., tenant_id="tenant_b")
    
    s3_a = S3Connector(config_a)
    s3_b = S3Connector(config_b)
    
    s3_a.connect()
    s3_b.connect()
    
    # Tenant A writes
    s3_a.write_object("secret.txt", b"secret", "tenant_a")
    
    # Tenant B lists objects (should not see tenant_a's file)
    objects = s3_b.list_objects("", "tenant_b")
    assert not any("secret.txt" in obj for obj in objects)
```

---

## Success Criteria

✅ **SQL Injection:** All 3 database engines verified parameterized  
✅ **Pool Cleanup:** Connection pool cleared on close()  
✅ **Tenant Isolation:** No cross-tenant data leakage (verified for all 5 components)  
✅ **Iterator Cleanup:** Generators close on exception  
✅ **Basic Errors:** Connection/timeout/permission errors propagate correctly  
✅ **Cross-Component:** End-to-end S3→DB, Kafka→DB pipelines work  

**All tests pass locally without requiring external services (use mocks where needed)**

---

## Files to Modify

```
tests/test_connectors/test_database.py        → Add 8 injection tests + expand existing
tests/test_connectors/test_storage.py         → Add 4 pool cleanup + 5 isolation tests
tests/test_connectors/test_data_source.py     → Add 4 iterator + 3 isolation tests
tests/test_tenant_aware_layer.py              → Add 5 pipeline + expand isolation tests
src/connectors/storage.py                     → Fix pool cleanup in close()
src/connectors/data_source.py                 → Fix iterator cleanup on exception
```

---

## Risk Assessment

**Regression Risk:** ✅ LOW
- Only adding tests, not changing core logic (except bug fixes)
- Fixes are small, well-scoped (pool cleanup, iterator finally block)

**Coverage Gain:** ✅ GOOD
- ~150 new tests address the actual bugs developers encounter
- Skip 1,000+ exotic edge cases that never happen locally

**Time to Implement:** ✅ REALISTIC
- 3-4 days for one person
- Tests are straightforward (no complex mocking needed)

---

## NOT Included

| Excluded Tests | Reason |
|---|---|
| Kafka broker failover | Requires Kafka cluster setup |
| Snowflake warehouse suspend | Doesn't happen in local dev |
| GCS lifecycle rules | Cloud-specific, not core |
| MongoDB TTL indexes | Advanced feature, not core |
| Connection pool statistics API | Monitoring, not core |
| Circuit breaker pattern | Phase 2 feature |
| Metrics collection | Observability, not core |
| Rate limiting | Policy enforcement, not core |
| Cascading failure scenarios | Exotic edge case |

---

## Estimated Time Breakdown

| Task | Time |
|------|------|
| SQL Injection tests | 2 hours |
| Pool cleanup tests | 1 hour |
| Tenant isolation tests | 4 hours |
| Iterator cleanup | 1 hour |
| Cross-component pipelines | 2 hours |
| Basic error handling | 2 hours |
| Documentation & polish | 2 hours |
| **TOTAL** | **14 hours** |

**Estimated: 2 days focused work (or 3-4 days at normal pace)**
