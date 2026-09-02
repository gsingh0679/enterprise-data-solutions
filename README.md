# Enterprise Data Solutions - Phase 1 MVP

A comprehensive data governance and compliance platform designed for multi-tenant enterprise environments. This platform orchestrates KYC data ingestion, data migration, compliance validation, and GDPR deletion workflows with built-in PII masking, data lineage tracking, and immutable audit logging.

## Overview

Enterprise Data Solutions provides a secure, compliant data management platform that handles:

- **KYC Data Ingestion**: Ingest and validate KYC data from multiple sources (S3, Kafka)
- **Data Migration**: Safely migrate data between systems with integrity verification
- **Compliance Checking**: Validate PII masking, data lineage, audit logs, and retention policies
- **GDPR Deletion**: Execute compliant data erasure workflows
- **Audit Trail**: Immutable audit logging for regulatory compliance
- **Multi-Tenancy**: Tenant-aware data isolation and access control

## Features

### Core Components

1. **Connectors** - Pluggable data source and destination connectors
   - Database connectors (PostgreSQL, etc.)
   - Storage connectors (AWS S3, MinIO)
   - Streaming connectors (Kafka)
   - Custom data source connectors

2. **Data Operations** - Data processing and validation
   - Schema registry and validation
   - PII masking engine
   - Data quality validation
   - Compliance checks

3. **Compliance** - Regulatory compliance management
   - Audit logging with immutable records
   - Data lineage tracking
   - GDPR erasure workflows
   - Retention policy enforcement

4. **Platform** - Core platform services
   - Tenant-aware layer for multi-tenancy
   - Configuration management
   - Metrics collection

### Security Features

- **PII Masking**: Automatic detection and masking of sensitive data
- **Data Lineage**: Complete tracking of data transformations
- **Audit Logging**: Immutable audit trail for compliance
- **Encryption**: End-to-end encryption for sensitive data
- **Access Control**: Tenant-aware access isolation
- **Schema Validation**: Prevent invalid data ingestion

## Installation

### Prerequisites

- Python 3.9+
- PostgreSQL 12+ (for audit logs and metadata)
- AWS S3 or MinIO (for data storage)
- Kafka 2.8+ (for streaming ingestion, optional)

### Setup

1. Clone the repository:
```bash
git clone <repository-url>
cd enterprise-data-solutions
```

2. Create a virtual environment:
```bash
python -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate
```

3. Install dependencies:
```bash
pip install -r requirements.txt
```

4. Configure environment variables:
```bash
cp .env.example .env
# Edit .env with your configuration
```

## Configuration

Configuration is managed via YAML files in the `config/` directory. Key configuration sections:

### Database Configuration
```yaml
database:
  engine: postgresql
  host: localhost
  port: 5432
  database: enterprise_data
  connection_pool_size: 10
```

### Storage Configuration
```yaml
storage:
  engine: s3
  bucket: enterprise-data
  region: us-east-1
  kms_key_id: arn:aws:kms:...
```

### Audit Configuration
```yaml
audit:
  enabled: true
  retention_days: 2555  # 7 years
  log_to_file: true
```

## Usage

### Batch Processing

The platform provides a batch job runner for scheduling data operations:

#### KYC Data Ingestion
```bash
python main.py kyc_ingestion --tenant-id tenant-123 \
  --source-path s3://bucket/kyc-data.parquet \
  --target-table kyc_records
```

#### Data Migration
```bash
python main.py data_migration --tenant-id tenant-123 \
  --source-system legacy_db \
  --target-system modern_db \
  --table-name customers
```

#### Compliance Validation
```bash
python main.py compliance_check --tenant-id tenant-123 \
  --check-type full
```

#### GDPR Data Erasure
```bash
python main.py data_erasure --tenant-id tenant-123 \
  --record-ids id1,id2,id3
```

### CLI Options

All batch jobs support:
- `--debug`: Enable debug logging
- `--dry-run`: Preview changes without executing
- `--timeout`: Job timeout in seconds

## Testing

Run the test suite:

```bash
# Run all tests
pytest tests/ -v

# Run with coverage
pytest tests/ -v --cov=src --cov-report=html

# Run specific test file
pytest tests/test_masking_engine.py -v

# Show last 50 lines of output
python -m pytest tests/ -v --tb=line 2>&1 | tail -50
```

## Architecture

### Data Flow

```
Data Source (S3/Kafka)
    ↓
Schema Validation
    ↓
PII Masking
    ↓
Audit Log Entry
    ↓
Database/Storage
    ↓
Lineage Tracking
```

### Tenancy Model

- **Tenant Isolation**: Each tenant's data is logically and physically isolated
- **Tenant Context**: Operations require explicit tenant context
- **Audit Segregation**: Audit logs include tenant context for filtering

## Development

### Project Structure
```
.
├── src/
│   ├── config.py              # Configuration management
│   ├── errors.py              # Custom exceptions
│   ├── connectors/            # Data connectors
│   ├── data_ops/              # Data operations
│   ├── compliance/            # Compliance features
│   └── platform/              # Core platform
├── tests/                     # Test suite
├── docs/                      # Documentation
├── main.py                    # Batch job entry point
└── requirements.txt           # Python dependencies
```

### Code Quality

The project uses:
- **Black**: Code formatting
- **Flake8**: Linting
- **MyPy**: Type checking
- **Pytest**: Testing

Run code quality checks:
```bash
black src/ tests/
flake8 src/ tests/
mypy src/
pytest tests/ -v
```

## API Documentation

### BatchJobRunner

Main interface for batch job execution:

```python
from main import BatchJobRunner

runner = BatchJobRunner()

# KYC Ingestion
result = runner.run_kyc_ingestion(
    tenant_id="tenant-123",
    source_path="s3://bucket/kyc.parquet",
    target_table="kyc_records"
)

# Data Migration
result = runner.run_data_migration(
    tenant_id="tenant-123",
    source_system="legacy_db",
    target_system="modern_db",
    table_name="customers"
)

# Compliance Check
result = runner.run_compliance_check(
    tenant_id="tenant-123",
    check_type="full"
)

# GDPR Erasure
result = runner.run_data_erasure(
    tenant_id="tenant-123",
    record_ids=["id1", "id2"]
)
```

## Monitoring and Logging

Logs are written to:
- **Console**: For immediate feedback
- **File**: For permanent record (if configured)
- **Audit Log**: For compliance tracking

Enable debug logging:
```bash
python main.py kyc_ingestion --tenant-id tenant-123 \
  --source-path s3://bucket/kyc.parquet \
  --target-table kyc_records \
  --debug
```

## Security Considerations

1. **PII Protection**: All PII fields are automatically masked using configured rules
2. **Encryption**: Data in transit uses TLS; at rest uses KMS
3. **Audit Immutability**: Audit logs are append-only and tamper-evident
4. **Tenant Isolation**: Strict tenant context enforcement at all layers
5. **Access Control**: Role-based access control with audit logging

## Contributing

1. Create a feature branch: `git checkout -b feature/name`
2. Make changes and test: `pytest tests/ -v`
3. Format code: `black src/`
4. Commit with descriptive messages
5. Push and create a pull request

## Troubleshooting

### Connection Issues
- Verify database connection string in `.env`
- Check PostgreSQL is running: `psql -U postgres -h localhost`
- Verify S3/storage credentials

### PII Masking Not Applied
- Check schema registry configuration
- Verify PII patterns in config are correct
- Review audit logs for masking errors

### Compliance Check Failures
- Ensure audit logging is enabled
- Check data lineage is being tracked
- Verify retention policies are configured

## Performance

Typical performance metrics (on standard hardware):
- **KYC Ingestion**: ~1,000 records/second
- **Data Migration**: ~500 records/second (with validation)
- **Compliance Check**: ~10,000 records/second
- **Data Erasure**: ~100 records/second (safe deletion)

## Roadmap

### Phase 1 (Current)
- ✅ Multi-tenant architecture
- ✅ KYC ingestion pipeline
- ✅ PII masking
- ✅ Audit logging
- ✅ Basic compliance checks

### Phase 2
- Data warehouse integration
- Advanced compliance rules
- ML-based anomaly detection
- Enhanced retention policies
- Real-time compliance monitoring

### Phase 3
- Graph-based lineage visualization
- Advanced analytics
- Predictive compliance
- Distributed processing

## License

Proprietary - All rights reserved

## Support

For support and issues:
- Create an issue in the repository
- Contact the development team
- Check documentation in `docs/`

## Authors

- Gurneet Singh (gsingh0679@gmail.com)

## Changelog

### Version 0.1.0 (Initial Release)
- Multi-tenant platform foundation
- KYC ingestion pipeline
- PII masking engine
- Audit logging system
- GDPR erasure workflows
- Compliance validation framework
