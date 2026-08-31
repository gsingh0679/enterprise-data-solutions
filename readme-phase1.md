# Phase 1: Schema Evolution & Governance

Safe schema versioning and data quality validation for enterprise data platforms.

## What This Phase Does

- **Schema Versioning:** Append-only versioning prevents breaking changes
- **Quality Validation:** Multi-layer validation catches bad data at ingestion
- **Governance:** Approval workflow with full audit trail
- **Real-Time Support:** Same rules work for batch and streaming
- **Brownfield:** Phased migration path for existing schemas

## Quick Start

```bash
# See the MVP (schema versioning + quality)
git checkout mvp
pytest phases/01-schema-evolution-governance/tests/
python -m examples.banking_customer_kyc

# See complete solution
git checkout main
pytest phases/01-schema-evolution-governance/tests/ -v
```

## Branches

| Branch | What | Interview Pitch |
|--------|------|-----------------|
| `mvp` | Schema versioning + quality | "Built schema versioning that prevents breaking changes" |
| `governance` | + Approval workflow + audit | "Added governance with full audit trail" |
| `streaming` | + Kafka integration | "Extended to real-time without changing rules" |
| `tradeoffs` | + Alternatives + brownfield | "Analyzed trade-offs and migration scenarios" |

Each branch is complete and shippable. Checkout any to see that state.

## Examples

- **Banking Customer KYC:** Customer data evolution with compliance requirements
- **Utilities Meter Reading:** Real-time validation with circuit breaker

```bash
python -m examples.banking_customer_kyc
python -m examples.utilities_meter_reading
```

## Architecture

```
Ingestion → Schema Validation → Bronze (validated, versioned)
                                    ↓
                           Quality Validation
                              ↙        ↘
                        Passes      Fails
                          ↓           ↓
                      Silver     Quarantine
                    (ready)    (investigate)
```

## Testing

```bash
# All tests
pytest phases/01-schema-evolution-governance/tests/ -v

# Coverage
pytest phases/01-schema-evolution-governance/tests/ --cov
```

Test count: 80+ (mvp) → 205+ (complete)

## Structure

```
phases/01-schema-evolution-governance/
├── implementation/          (schema registry, quality, circuit breaker)
├── tests/                   (comprehensive test suite)
├── examples/                (banking, utilities scenarios)
└── docs/                    (design, API, case studies)

shared/                       (reusable across all phases)
├── connectors/              (Delta, Kafka, S3, Azure, GCP)
├── ingestion/               (batch + streaming readers)
├── quality/                 (validator base classes)
└── test_fixtures/           (test data, mocks)
```

## Documentation

- **Design details:** See `docs/DESIGN.md`
- **API reference:** See `docs/API.md`
- **Technical architecture:** See `../../../docs/phases/PHASE_1_TECHNICAL_ARCHITECTURE.md`
- **Decision rationale:** See `../../../docs/phases/PHASE_1_DECISION_LOG.md`

## Deploy

See `docs/DEPLOYMENT.md` for cloud setup (AWS, Azure, GCP, on-prem).

## What's Next

Phase 2 (Data Quality Framework) builds on this:
- Anomaly detection
- Statistical profiling
- Auto-remediation

Will reuse: All connectors, validators, and shared components from Phase 1.

---

**Status:** Complete | **Test Coverage:** 92% | **Branches:** 4 | **Examples:** 2
